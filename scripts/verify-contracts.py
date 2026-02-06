#!/usr/bin/env python3
"""
HyperEVM Contract Verification Script

Verifies that deployed contracts on hyperEVM match their source code by:
1. Fetching deployed bytecode from Hyperscan block explorer
2. Extracting compiler settings from verified contracts
3. Compiling source code locally with same settings
4. Comparing bytecodes (excluding compiler metadata)

Usage:
    python3 scripts/verify-contracts.py --all                    # Verify all contracts
    python3 scripts/verify-contracts.py --address 0x...          # Verify single contract
    python3 scripts/verify-contracts.py --file addresses/999/CoreAddresses.json
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests

# Configuration
HYPERSCAN_API_BASE = "https://www.hyperscan.com/api/v2"
HYPERLIQUID_RPC = "https://rpc.hyperliquid.xyz/evm"
REPO_ROOT = Path(__file__).parent.parent
CONTRACT_MAPPING_FILE = REPO_ROOT / "contract-mapping.json"
LIB_DIR = REPO_ROOT / "lib"

DEFAULT_COMPILER_SETTINGS = {
    "compiler_version": "v0.8.24+commit.e11b9ed9",
    "optimization_enabled": True,
    "optimization_runs": 20000,
    "evm_version": "cancun",
}

CONTRACT_MAPPING: Dict[str, dict] = {}


def load_contract_mapping() -> Dict[str, dict]:
    global CONTRACT_MAPPING
    if CONTRACT_MAPPING:
        return CONTRACT_MAPPING
    
    if not CONTRACT_MAPPING_FILE.exists():
        print(f"Warning: {CONTRACT_MAPPING_FILE} not found. Run generate-contract-mapping.py first.")
        return {}
    
    with open(CONTRACT_MAPPING_FILE) as f:
        data = json.load(f)
    
    CONTRACT_MAPPING = {}
    for name, info in data.items():
        CONTRACT_MAPPING[name] = {**info, "contract_name": name}
        if "address" in info:
            CONTRACT_MAPPING[info["address"].lower()] = {**info, "contract_name": name}
    
    return CONTRACT_MAPPING


def get_local_repo_path(repo: str) -> Optional[Path]:
    repo_name = repo.split("/")[-1]
    local_path = LIB_DIR / repo_name
    if local_path.exists() and (local_path / ".git").exists():
        return local_path
    return None


def get_source_info_for_contract(name: str, address: Optional[str] = None) -> Optional[dict]:
    mapping = load_contract_mapping()
    
    if name in mapping:
        return mapping[name]
    
    if address:
        addr_lower = address.lower()
        if addr_lower in mapping:
            return mapping[addr_lower]
    
    return None


class ContractVerifier:
    """Handles verification of a single contract"""
    
    def __init__(self, address: str, name: Optional[str] = None, verbose: bool = False):
        self.address = address.lower()
        self.name = name
        self.verbose = verbose
        self.result = {
            "address": self.address,
            "name": name,
            "verified": False,
            "error": None,
            "details": {}
        }
    
    def log(self, message: str):
        """Log message if verbose mode enabled"""
        if self.verbose:
            print(f"  {message}")
    
    def fetch_contract_info(self) -> bool:
        """Fetch contract info from Hyperscan"""
        self.log("Fetching contract info from Hyperscan...")
        
        try:
            url = f"{HYPERSCAN_API_BASE}/addresses/{self.address}"
            response = requests.get(url, headers={'Accept': 'application/json'}, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not data.get('is_contract'):
                self.result['error'] = "Address is not a contract"
                return False
            
            self.result['details']['hyperscan_verified'] = data.get('is_verified', False)
            
            hyperscan_name = data.get('name')
            if hyperscan_name:
                if not self.name:
                    self.name = hyperscan_name
                    self.result['name'] = self.name
                else:
                    self.result['name'] = f"{self.name} ({hyperscan_name})"
                    self.name = hyperscan_name
            
            self.result['details']['creation_tx'] = data.get('creation_transaction_hash')
            self.result['details']['deployer'] = data.get('creator_address_hash')
            
            return True
            
        except Exception as e:
            self.result['error'] = f"Failed to fetch contract info: {str(e)}"
            return False
    
    def fetch_verification_data(self) -> bool:
        """Fetch verification data from Hyperscan or use defaults"""
        self.log("Fetching verification data...")
        
        try:
            url = f"{HYPERSCAN_API_BASE}/smart-contracts/{self.address}"
            response = requests.get(url, headers={'Accept': 'application/json'}, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            self.result['details']['compiler_version'] = data.get('compiler_version')
            self.result['details']['optimization_enabled'] = data.get('optimization_enabled')
            self.result['details']['optimization_runs'] = data.get('optimization_runs')
            self.result['details']['evm_version'] = data.get('evm_version')
            self.result['details']['file_path'] = data.get('file_path')
            self.result['details']['source_code'] = data.get('source_code')
            
            compiler_settings = data.get('compiler_settings', {})
            self.result['details']['via_ir'] = compiler_settings.get('viaIR', False)
            
            return True
            
        except Exception as e:
            self.log(f"Hyperscan verification data unavailable, using defaults")
            self.result['details']['compiler_version'] = DEFAULT_COMPILER_SETTINGS['compiler_version']
            self.result['details']['optimization_enabled'] = DEFAULT_COMPILER_SETTINGS['optimization_enabled']
            self.result['details']['optimization_runs'] = DEFAULT_COMPILER_SETTINGS['optimization_runs']
            self.result['details']['evm_version'] = DEFAULT_COMPILER_SETTINGS['evm_version']
            self.result['details']['using_default_settings'] = True
            return True
    
    def fetch_deployed_bytecode(self) -> Optional[str]:
        """Fetch deployed bytecode - tries creation tx, Hyperscan runtime, then RPC fallback"""
        self.log("Fetching deployed bytecode...")
        
        try:
            creation_tx = self.result['details'].get('creation_tx')
            if creation_tx:
                url = f"{HYPERSCAN_API_BASE}/transactions/{creation_tx}"
                response = requests.get(url, headers={'Accept': 'application/json'}, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                bytecode = data.get('raw_input')
                if bytecode:
                    self.log(f"Fetched {len(bytecode)} chars of creation bytecode")
                    self.result['details']['bytecode_type'] = 'creation'
                    return bytecode
            
            self.log("No creation tx, fetching runtime bytecode from Hyperscan...")
            url = f"{HYPERSCAN_API_BASE}/smart-contracts/{self.address}"
            response = requests.get(url, headers={'Accept': 'application/json'}, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            bytecode = data.get('deployed_bytecode')
            if bytecode:
                self.log(f"Fetched {len(bytecode)} chars of runtime bytecode from Hyperscan")
                self.result['details']['bytecode_type'] = 'runtime'
                return bytecode
        except Exception:
            pass
        
        # Final fallback: fetch runtime bytecode directly from RPC
        self.log("Falling back to RPC eth_getCode...")
        bytecode = fetch_runtime_bytecode_from_rpc(self.address)
        if bytecode:
            self.log(f"Fetched {len(bytecode)} chars of runtime bytecode from RPC")
            self.result['details']['bytecode_type'] = 'runtime'
            self.result['details']['bytecode_source'] = 'rpc'
            return bytecode
        
        self.result['error'] = "No bytecode found from any source"
        return None
    
    def compile_from_source(self) -> Optional[str]:
        self.log("Compiling from source...")
        
        source_info = get_source_info_for_contract(self.name, self.address)
        
        if not source_info:
            self.result['error'] = f"No mapping in contract-mapping.json for {self.name}"
            return None
        
        repo = source_info.get('repo')
        commit = source_info.get('commit')
        artifact_name = source_info.get('artifact_name')
        
        if not repo or not commit:
            self.result['error'] = f"Incomplete mapping for {self.name}: missing repo or commit"
            return None
        
        self.result['details']['source_repo'] = repo
        self.result['details']['source_commit'] = commit
        self.result['details']['artifact_name'] = artifact_name
        
        local_repo = get_local_repo_path(repo)
        
        try:
            if local_repo:
                bytecode = self._compile_from_local_repo(local_repo, commit, artifact_name)
                if bytecode:
                    return bytecode
                self.log("Local build failed, trying fresh clone...")
            
            return self._compile_from_cloned_repo(repo, commit, artifact_name)
                
        except Exception as e:
            self.result['error'] = f"Failed to compile from source: {str(e)}"
            return None
    
    def _compile_from_local_repo(self, repo_dir: Path, expected_commit: str, artifact_name: Optional[str]) -> Optional[str]:
        self.log(f"Using local repo: {repo_dir}")
        
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir, capture_output=True, text=True
        )
        current_commit = result.stdout.strip()
        
        if current_commit != expected_commit:
            self.log(f"Warning: local commit {current_commit[:8]} differs from mapping {expected_commit[:8]}")
            self.result['details']['commit_mismatch'] = True
            self.result['details']['local_commit'] = current_commit
        
        # Back up foundry.toml before patching to avoid dirtying the working tree
        foundry_toml = repo_dir / "foundry.toml"
        original_config = foundry_toml.read_text() if foundry_toml.exists() else None
        
        try:
            self._patch_foundry_config(repo_dir)
            
            self.log("Building with Foundry...")
            build_cmd = ["forge", "build", "--force"]
            result = subprocess.run(build_cmd, cwd=repo_dir, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                self.log(f"Local build failed: {result.stderr[:200]}...")
                return None
            
            use_runtime = self.result['details'].get('bytecode_type') == 'runtime'
            bytecode = self._extract_bytecode_from_artifacts(repo_dir, use_runtime=use_runtime, artifact_name=artifact_name)
            if bytecode:
                self.log(f"Compiled {len(bytecode)} chars of {'runtime' if use_runtime else 'creation'} bytecode")
            
            return bytecode
        finally:
            # Restore original foundry.toml
            if original_config is not None:
                foundry_toml.write_text(original_config)
    
    def _compile_from_cloned_repo(self, repo: str, commit: str, artifact_name: Optional[str]) -> Optional[str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            self.log(f"Cloning {repo}...")
            
            repo_dir = Path(tmpdir) / "repo"
            repo_url = f"https://github.com/{repo}.git"
            
            repo_dir.mkdir(exist_ok=True)
            subprocess.run(["git", "init", "-q"], cwd=repo_dir, capture_output=True)
            subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=repo_dir, capture_output=True)
            
            fetch_cmd = ["git", "fetch", "--depth", "1", "origin", commit]
            result = subprocess.run(fetch_cmd, cwd=repo_dir, capture_output=True, text=True)
            if result.returncode != 0:
                self.result['error'] = f"Failed to fetch commit {commit}: {result.stderr}"
                return None
            
            checkout_cmd = ["git", "checkout", "FETCH_HEAD"]
            result = subprocess.run(checkout_cmd, cwd=repo_dir, capture_output=True, text=True)
            if result.returncode != 0:
                self.result['error'] = f"Failed to checkout commit {commit}: {result.stderr}"
                return None
            
            if (repo_dir / ".gitmodules").exists():
                self.log("Initializing submodules...")
                self._init_submodules_exact(repo_dir)
                self._init_nested_submodules(repo_dir)
            
            self._patch_foundry_config(repo_dir)
            
            self.log("Building with Foundry...")
            build_cmd = ["forge", "build", "--force"]
            result = subprocess.run(build_cmd, cwd=repo_dir, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                self.result['error'] = f"Forge build failed: {result.stderr}"
                return None
            
            use_runtime = self.result['details'].get('bytecode_type') == 'runtime'
            bytecode = self._extract_bytecode_from_artifacts(repo_dir, use_runtime=use_runtime, artifact_name=artifact_name)
            if bytecode:
                self.log(f"Compiled {len(bytecode)} chars of {'runtime' if use_runtime else 'creation'} bytecode")
            else:
                self.result['error'] = f"Could not find contract bytecode in build artifacts"
            
            return bytecode
    
    def _init_submodules_exact(self, repo_dir: Path):
        """Delegate to the free function."""
        init_submodules_exact(repo_dir)
    
    def _init_nested_submodules(self, repo_dir: Path):
        """Delegate to the free function."""
        init_nested_submodules(repo_dir)
    
    def _patch_foundry_config(self, repo_dir: Path):
        """Delegate to the free function, converting instance details to a settings dict."""
        compiler_settings = {
            "compiler_version": self.result['details'].get('compiler_version'),
            "optimization_enabled": self.result['details'].get('optimization_enabled'),
            "optimization_runs": self.result['details'].get('optimization_runs'),
            "evm_version": self.result['details'].get('evm_version'),
            "via_ir": self.result['details'].get('via_ir'),
        }
        patch_foundry_config_for_repo(repo_dir, compiler_settings)
    
    def _extract_bytecode_from_artifacts(self, repo_dir: Path, use_runtime: bool = False, artifact_name: Optional[str] = None) -> Optional[str]:
        """Delegate to the free function."""
        name = artifact_name or self.name
        return extract_bytecode_from_artifacts(repo_dir, name, use_runtime=use_runtime)
    
    def compare_bytecodes(self, deployed: str, compiled: str) -> bool:
        """Compare deployed and compiled bytecodes, delegating to the standalone function."""
        self.log("Comparing bytecodes...")
        
        # Store raw sizes for verbose output
        self.result['details']['stripped_deployed_size'] = self.result['details'].get('deployed_size', 0)
        self.result['details']['stripped_compiled_size'] = self.result['details'].get('compiled_size', 0)
        
        match = compare_bytecodes(deployed, compiled, self.result)
        
        if match:
            details = self.result['details']
            if 'create2_prefix_size' in details and 'constructor_args_size' in details:
                self.log(f"✅ Bytecodes match (CREATE2 + {details['constructor_args_size']} bytes constructor args)")
            elif 'create2_prefix_size' in details:
                self.log(f"✅ Bytecodes match (CREATE2 deployment with {details['create2_prefix_size']} byte prefix)")
            elif 'constructor_args_size' in details:
                self.log(f"✅ Bytecodes match (excluding {details['constructor_args_size']} bytes of constructor args)")
            else:
                self.log("✅ Bytecodes match!")
        else:
            self.log("❌ Bytecodes differ")
        
        return match
    
    def verify(self) -> bool:
        """Run full verification process"""
        print(f"\n{'='*80}")
        print(f"Verifying: {self.name or self.address}")
        print(f"{'='*80}")
        
        # Step 1: Fetch contract info
        if not self.fetch_contract_info():
            print(f"❌ Failed: {self.result['error']}")
            return False
        
        # Step 2: Fetch verification data
        if not self.fetch_verification_data():
            print(f"❌ Failed: {self.result['error']}")
            return False
        
        # Step 3: Fetch deployed bytecode
        deployed_bytecode = self.fetch_deployed_bytecode()
        if not deployed_bytecode:
            print(f"❌ Failed: {self.result['error']}")
            return False
        
        # Step 4: Compile from source
        compiled_bytecode = self.compile_from_source()
        if not compiled_bytecode:
            print(f"❌ Failed: {self.result['error']}")
            return False
        
        # Step 5: Compare bytecodes
        match = self.compare_bytecodes(deployed_bytecode, compiled_bytecode)
        self.result['verified'] = match
        
        if match:
            print(f"✅ VERIFIED: {self.name}")
            print(f"   Address: {self.address}")
            print(f"   Compiler: {self.result['details']['compiler_version']}")
            print(f"   Optimizer Runs: {self.result['details']['optimization_runs']}")
            print(f"   Bytecode Size: {self.result['details']['stripped_deployed_size']} bytes")
        else:
            print(f"❌ VERIFICATION FAILED: {self.name}")
            print(f"   Reason: Bytecode mismatch")
        
        return match


def load_address_file(filepath: Path) -> Dict[str, str]:
    """Load addresses from JSON file"""
    with open(filepath) as f:
        data = json.load(f)
    
    return {k: v for k, v in data.items() if v != "0x0000000000000000000000000000000000000000"}


def verify_all_contracts(verbose: bool = False, skip_unmapped: bool = False, batch: bool = False) -> Tuple[List[dict], List[dict], List[str]]:
    address_files = [
        "addresses/999/CoreAddresses.json",
        "addresses/999/LensAddresses.json",
        "addresses/999/PeripheryAddresses.json",
        "addresses/999/EulerSwapAddresses.json",
        "addresses/999/TokenAddresses.json",
        "addresses/999/BridgeAddresses.json",
    ]
    
    all_contracts = []
    for address_file in address_files:
        filepath = REPO_ROOT / address_file
        if not filepath.exists():
            continue
        addresses = load_address_file(filepath)
        for name, address in addresses.items():
            all_contracts.append((name, address))
    
    if batch:
        return verify_contracts_batched(all_contracts, verbose=verbose, skip_unmapped=skip_unmapped)
    return verify_contract_list(all_contracts, verbose=verbose, skip_unmapped=skip_unmapped)


def verify_contracts_batched(
    contracts: List[Tuple[str, str]], 
    verbose: bool = False,
    skip_unmapped: bool = False
) -> Tuple[List[dict], List[dict], List[str]]:
    """Batch verification: compile once per repo, verify all contracts from that repo's artifacts."""
    verified = []
    failed = []
    skipped = []
    
    # Pre-load the mapping cache
    load_contract_mapping()
    
    # Group contracts by (repo, compiler settings) so each unique settings combination gets its own build
    def _settings_key(info: dict) -> tuple:
        return (
            info.get('repo', ''),
            info.get('commit', ''),
            info.get('compiler_version'),
            info.get('optimization_enabled'),
            info.get('optimization_runs'),
            info.get('evm_version'),
            info.get('via_ir'),
        )
    
    by_build: Dict[tuple, List[Tuple[str, str, dict]]] = {}
    for name, address in contracts:
        source_info = get_source_info_for_contract(name, address)
        if not source_info:
            if skip_unmapped:
                skipped.append(name)
            else:
                failed.append({"name": name, "verified": False, "error": "No mapping in contract-mapping.json"})
            continue
        
        key = _settings_key(source_info)
        if key not in by_build:
            by_build[key] = []
        by_build[key].append((name, address, source_info))
    
    if skipped:
        print(f"\n⚠️  Skipping {len(skipped)} unmapped contracts: {', '.join(skipped)}\n")
    
    total_builds = len(by_build)
    for build_idx, (build_key, group_contracts) in enumerate(by_build.items(), 1):
        repo = group_contracts[0][2].get('repo', '')
        print(f"\n{'#'*80}")
        print(f"# [{build_idx}/{total_builds}] Building repo: {repo} ({len(group_contracts)} contracts)")
        print(f"{'#'*80}")
        
        # Use compiler settings from the group (all contracts in this group share the same settings)
        first_info = group_contracts[0][2]
        commit = first_info.get('commit')
        repo_dir = None
        build_success = False
        is_temp = False
        
        compiler_settings = {
            "compiler_version": first_info.get('compiler_version'),
            "optimization_enabled": first_info.get('optimization_enabled'),
            "optimization_runs": first_info.get('optimization_runs'),
            "evm_version": first_info.get('evm_version'),
            "via_ir": first_info.get('via_ir'),
        }
        
        try:
            repo_dir, build_success, is_temp = setup_and_build_repo(repo, commit, compiler_settings, verbose)
        except Exception as e:
            print(f"  ❌ Failed to build repo: {e}")
        
        if not build_success:
            for name, address, source_info in group_contracts:
                failed.append({"name": name, "address": address, "verified": False, "error": f"Repo build failed: {repo}"})
            continue
        
        # Verify each contract from this build
        for contract_idx, (name, address, source_info) in enumerate(group_contracts, 1):
            print(f"\n  [{contract_idx}/{len(group_contracts)}] Verifying: {name}")
            
            result = verify_single_contract_from_build(
                name, address, source_info, repo_dir, verbose
            )
            
            if result.get('verified'):
                verified.append(result)
                print(f"    ✅ VERIFIED")
            else:
                failed.append(result)
                print(f"    ❌ FAILED: {result.get('error', 'Unknown error')}")
        
        # Cleanup temp dir if it was created
        if repo_dir and is_temp:
            import shutil
            shutil.rmtree(repo_dir, ignore_errors=True)
    
    return verified, failed, skipped


def setup_and_build_repo(repo: str, commit: str, compiler_settings: dict, verbose: bool = False) -> Tuple[Optional[Path], bool, bool]:
    """Returns (repo_dir, build_success, is_temp_dir)."""
    local_repo = get_local_repo_path(repo)
    if local_repo:
        current_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=local_repo, capture_output=True, text=True
        ).stdout.strip()
        
        if current_commit == commit:
            print(f"  Using local repo: {local_repo} (commit matches)")
            # Back up foundry.toml before patching to avoid dirtying the working tree
            foundry_toml = local_repo / "foundry.toml"
            original_config = foundry_toml.read_text() if foundry_toml.exists() else None
            try:
                patch_foundry_config_for_repo(local_repo, compiler_settings)
                result = subprocess.run(
                    ["forge", "build", "--force"], 
                    cwd=local_repo, capture_output=True, text=True, timeout=600
                )
                if result.returncode == 0:
                    return local_repo, True, False
                print(f"  Local build failed, cloning fresh...")
            finally:
                # Restore original foundry.toml
                if original_config is not None:
                    foundry_toml.write_text(original_config)
        else:
            print(f"  Local repo at {current_commit[:8]}, need {commit[:8]}, cloning fresh...")
    
    print(f"  Cloning {repo} at {commit[:8]}...")
    tmpdir = tempfile.mkdtemp()
    repo_dir = Path(tmpdir) / "repo"
    repo_dir.mkdir()
    
    repo_url = f"https://github.com/{repo}.git"
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=repo_dir, capture_output=True)
    
    result = subprocess.run(
        ["git", "fetch", "--depth", "1", "origin", commit],
        cwd=repo_dir, capture_output=True, text=True
    )
    if result.returncode != 0:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
        return None, False, False
    
    subprocess.run(["git", "checkout", "FETCH_HEAD"], cwd=repo_dir, capture_output=True)
    
    if (repo_dir / ".gitmodules").exists():
        print(f"  Initializing submodules...")
        init_submodules_exact(repo_dir)
        init_nested_submodules(repo_dir)
    
    patch_foundry_config_for_repo(repo_dir, compiler_settings)
    
    print(f"  Building with Foundry...")
    result = subprocess.run(
        ["forge", "build", "--force"],
        cwd=repo_dir, capture_output=True, text=True, timeout=600
    )
    
    return repo_dir, result.returncode == 0, True


def patch_foundry_config_for_repo(repo_dir: Path, compiler_settings: dict):
    foundry_toml = repo_dir / "foundry.toml"
    if not foundry_toml.exists():
        return
    
    content = foundry_toml.read_text()
    
    if re.search(r'script\s*=\s*["\'][^"\']+["\']', content):
        content = re.sub(r'script\s*=\s*["\'][^"\']+["\']', 'script = "disabled_script"', content)
    else:
        content = content.replace('[profile.default]', '[profile.default]\nscript = "disabled_script"')
    
    if re.search(r'test\s*=\s*["\'][^"\']+["\']', content):
        content = re.sub(r'test\s*=\s*["\'][^"\']+["\']', 'test = "disabled_test"', content)
    else:
        content = content.replace('[profile.default]', '[profile.default]\ntest = "disabled_test"')
    
    if compiler_settings.get('optimization_enabled') is not None:
        opt_val = "true" if compiler_settings['optimization_enabled'] else "false"
        if re.search(r'optimizer\s*=\s*(true|false)', content):
            content = re.sub(r'optimizer\s*=\s*(true|false)', f'optimizer = {opt_val}', content)
        else:
            content = content.replace('[profile.default]', f'[profile.default]\noptimizer = {opt_val}')
    
    if compiler_settings.get('optimization_runs') is not None:
        runs = compiler_settings['optimization_runs']
        if re.search(r'optimizer_runs\s*=\s*[\d_]+', content):
            content = re.sub(r'optimizer_runs\s*=\s*[\d_]+', f'optimizer_runs = {runs}', content)
        else:
            content = content.replace('[profile.default]', f'[profile.default]\noptimizer_runs = {runs}')
    
    if compiler_settings.get('evm_version'):
        evm = compiler_settings['evm_version']
        if re.search(r'evm_version\s*=\s*"[^"]+"', content):
            content = re.sub(r'evm_version\s*=\s*"[^"]+"', f'evm_version = "{evm}"', content)
        else:
            content = content.replace('[profile.default]', f'[profile.default]\nevm_version = "{evm}"')
    
    if compiler_settings.get('via_ir') is not None:
        via_ir_val = "true" if compiler_settings['via_ir'] else "false"
        if re.search(r'via_ir\s*=\s*(true|false)', content):
            content = re.sub(r'via_ir\s*=\s*(true|false)', f'via_ir = {via_ir_val}', content)
        else:
            content = content.replace('[profile.default]', f'[profile.default]\nvia_ir = {via_ir_val}')
    
    if compiler_settings.get('compiler_version'):
        match = re.search(r'v?(\d+\.\d+\.\d+)', compiler_settings['compiler_version'])
        if match:
            solc_ver = match.group(1)
            if re.search(r'solc\s*=\s*"[\d\.]+"', content):
                content = re.sub(r'solc\s*=\s*"[\d\.]+"', f'solc = "{solc_ver}"', content)
            else:
                content = content.replace('[profile.default]', f'[profile.default]\nsolc = "{solc_ver}"')
    
    foundry_toml.write_text(content)


def init_submodules_exact(repo_dir: Path):
    """Initialize submodules at their exact pinned commits."""
    result = subprocess.run(
        ["git", "submodule", "status"],
        cwd=repo_dir, capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        return
    
    for line in result.stdout.strip().split('\n'):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 2:
            commit = parts[0].lstrip('-+')
            submodule_path = parts[1]
            
            subprocess.run(["git", "submodule", "init", submodule_path], cwd=repo_dir, capture_output=True, timeout=30)
            
            submodule_dir = repo_dir / submodule_path
            if not submodule_dir.exists():
                submodule_dir.mkdir(parents=True, exist_ok=True)
            
            url_result = subprocess.run(
                ["git", "config", "--get", f"submodule.{submodule_path}.url"],
                cwd=repo_dir, capture_output=True, text=True, timeout=10
            )
            if url_result.returncode != 0:
                continue
            url = url_result.stdout.strip()
            
            subprocess.run(["git", "init", "-q"], cwd=submodule_dir, capture_output=True, timeout=10)
            subprocess.run(["git", "remote", "add", "origin", url], cwd=submodule_dir, capture_output=True, timeout=10)
            subprocess.run(["git", "fetch", "--depth", "1", "origin", commit], cwd=submodule_dir, capture_output=True, timeout=120)
            subprocess.run(["git", "checkout", "FETCH_HEAD"], cwd=submodule_dir, capture_output=True, timeout=30)


def init_nested_submodules(repo_dir: Path):
    """Initialize nested submodules in lib/* directories."""
    lib_dir = repo_dir / "lib"
    if not lib_dir.exists():
        return
    
    for subdir in lib_dir.iterdir():
        if subdir.is_dir() and (subdir / ".gitmodules").exists():
            init_submodules_exact(subdir)


def fetch_runtime_bytecode_from_rpc(address: str) -> Optional[str]:
    """Fetch runtime bytecode directly from Hyperliquid EVM RPC via eth_getCode."""
    try:
        response = requests.post(
            HYPERLIQUID_RPC,
            json={"jsonrpc": "2.0", "method": "eth_getCode", "params": [address, "latest"], "id": 1},
            timeout=10
        )
        response.raise_for_status()
        result = response.json().get('result', '0x')
        if result and result != '0x':
            return result
        return None
    except Exception:
        return None


def fetch_creation_bytecode_from_hyperscan(address: str) -> Tuple[Optional[str], Optional[str]]:
    """Fetch creation bytecode by looking up the creation tx, falling back to runtime bytecode.
    
    Falls back through: creation tx -> Hyperscan runtime -> RPC eth_getCode.
    Returns (bytecode, type) where type is 'creation' or 'runtime'.
    """
    try:
        # First get the creation tx hash from Hyperscan
        url = f"{HYPERSCAN_API_BASE}/addresses/{address}"
        response = requests.get(url, headers={'Accept': 'application/json'}, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        creation_tx = data.get('creation_transaction_hash')
        if creation_tx:
            # Fetch the raw creation bytecode from the tx
            tx_url = f"{HYPERSCAN_API_BASE}/transactions/{creation_tx}"
            tx_response = requests.get(tx_url, headers={'Accept': 'application/json'}, timeout=10)
            tx_response.raise_for_status()
            tx_data = tx_response.json()
            bytecode = tx_data.get('raw_input')
            if bytecode:
                return bytecode, 'creation'
        
        # Fall back to Hyperscan runtime bytecode
        sc_url = f"{HYPERSCAN_API_BASE}/smart-contracts/{address}"
        sc_response = requests.get(sc_url, headers={'Accept': 'application/json'}, timeout=30)
        sc_response.raise_for_status()
        sc_data = sc_response.json()
        runtime = sc_data.get('deployed_bytecode')
        if runtime:
            return runtime, 'runtime'
    except Exception:
        pass
    
    # Final fallback: fetch runtime bytecode directly from RPC
    runtime = fetch_runtime_bytecode_from_rpc(address)
    if runtime:
        return runtime, 'runtime'
    
    print(f"    Error: could not fetch bytecode for {address} from any source")
    return None, None


def verify_single_contract_from_build(
    name: str, 
    address: str, 
    source_info: dict, 
    repo_dir: Path,
    verbose: bool = False
) -> dict:
    result = {
        "name": name,
        "address": address.lower(),
        "verified": False,
        "error": None,
        "details": {
            "compiler_version": source_info.get('compiler_version'),
            "optimization_runs": source_info.get('optimization_runs'),
        }
    }
    
    artifact_name = source_info.get('artifact_name', name)
    
    deployed_bytecode, bytecode_type = fetch_creation_bytecode_from_hyperscan(address)
    if not deployed_bytecode:
        result['error'] = "Could not fetch deployed bytecode from Hyperscan"
        return result
    
    result['details']['bytecode_type'] = bytecode_type
    use_runtime = bytecode_type == 'runtime'
    
    compiled_bytecode = extract_bytecode_from_artifacts(repo_dir, artifact_name, use_runtime=use_runtime)
    if not compiled_bytecode:
        # Artifact not in main build — try building the specific file (e.g., nested lib contracts)
        file_path = source_info.get('file_path')
        if file_path:
            if verbose:
                print(f"    Artifact not in main build, compiling {file_path}...")
            build_result = subprocess.run(
                ["forge", "build", file_path, "--force"],
                cwd=repo_dir, capture_output=True, text=True, timeout=600
            )
            if build_result.returncode == 0:
                compiled_bytecode = extract_bytecode_from_artifacts(repo_dir, artifact_name, use_runtime=use_runtime)
        if not compiled_bytecode:
            result['error'] = f"Artifact not found: {artifact_name}"
            return result
    
    match = compare_bytecodes(deployed_bytecode, compiled_bytecode, result)
    result['verified'] = match
    
    return result


def extract_bytecode_from_artifacts(repo_dir: Path, artifact_name: str, use_runtime: bool = False) -> Optional[str]:
    out_dir = repo_dir / "out"
    if not out_dir.exists():
        return None
    
    search_name = artifact_name.lower()
    bytecode_key = 'deployedBytecode' if use_runtime else 'bytecode'
    
    for artifact_file in out_dir.rglob("*.json"):
        try:
            with open(artifact_file) as f:
                data = json.load(f)
                contract_name = data.get('contractName', '')
                if contract_name.lower() == search_name or artifact_file.stem.lower() == search_name:
                    bytecode = data.get(bytecode_key, {}).get('object')
                    if bytecode and bytecode != '0x':
                        return bytecode
        except:
            continue
    
    return None


def compare_bytecodes(deployed: str, compiled: str, result: dict) -> bool:
    """Compare deployed and compiled bytecodes."""
    def strip_metadata(bc):
        if bc.startswith('0x'):
            bc = bc[2:]
        marker = "a264697066735822"
        end_marker = "0033"
        while marker in bc:
            idx = bc.find(marker)
            end_idx = bc.find(end_marker, idx)
            if end_idx != -1:
                bc = bc[:idx] + bc[end_idx + len(end_marker):]
            else:
                bc = bc[:idx]
                break
        return bc
    
    deployed_stripped = strip_metadata(deployed)
    compiled_stripped = strip_metadata(compiled)
    
    result['details']['deployed_size'] = len(deployed_stripped) // 2
    result['details']['compiled_size'] = len(compiled_stripped) // 2
    
    if deployed_stripped == compiled_stripped:
        return True
    
    # Check for constructor args
    if len(deployed_stripped) > len(compiled_stripped):
        diff = len(deployed_stripped) - len(compiled_stripped)
        if diff % 64 == 0 and deployed_stripped[:len(compiled_stripped)] == compiled_stripped:
            result['details']['constructor_args_size'] = diff // 2
            return True
    
    # Handle CREATE2 deployments where init code may have a prefix (salt/factory data)
    if len(deployed_stripped) > len(compiled_stripped):
        compiled_start = compiled_stripped[:40]
        prefix_idx = deployed_stripped.find(compiled_start)
        if prefix_idx > 0:
            deployed_trimmed = deployed_stripped[prefix_idx:]
            if deployed_trimmed == compiled_stripped:
                result['details']['create2_prefix_size'] = prefix_idx // 2
                return True
            # Check for constructor args after CREATE2 prefix
            if len(deployed_trimmed) > len(compiled_stripped):
                constructor_args_len = len(deployed_trimmed) - len(compiled_stripped)
                if constructor_args_len % 64 == 0:
                    deployed_without_args = deployed_trimmed[:len(compiled_stripped)]
                    if deployed_without_args == compiled_stripped:
                        result['details']['create2_prefix_size'] = prefix_idx // 2
                        result['details']['constructor_args_size'] = constructor_args_len // 2
                        return True
    
    # Log first diff position for debugging
    for i, (a, b) in enumerate(zip(deployed_stripped, compiled_stripped)):
        if a != b:
            result['details']['first_diff_position'] = i
            result['details']['first_diff_deployed'] = deployed_stripped[max(0, i-20):i+20]
            result['details']['first_diff_compiled'] = compiled_stripped[max(0, i-20):i+20]
            break
    
    result['error'] = "Bytecode mismatch"
    return False


def print_summary(verified: List[dict], failed: List[dict], skipped: List[str] = None):
    print(f"\n{'='*80}")
    print("VERIFICATION SUMMARY")
    print(f"{'='*80}")
    print(f"✅ Verified: {len(verified)}")
    print(f"❌ Failed: {len(failed)}")
    if skipped:
        print(f"⏭️  Skipped: {len(skipped)}")
    print(f"Total: {len(verified) + len(failed) + (len(skipped) if skipped else 0)}")
    
    if failed:
        print(f"\nFailed contracts:")
        for result in failed:
            print(f"  - {result['name']}: {result['error']}")
    
    if skipped:
        print(f"\nSkipped (no mapping):")
        for name in skipped:
            print(f"  - {name}")


def save_report(verified: List[dict], failed: List[dict], output_path: str):
    """Save verification report to JSON file"""
    report = {
        'verified': verified,
        'failed': failed,
        'summary': {
            'total': len(verified) + len(failed),
            'verified': len(verified),
            'failed': len(failed)
        }
    }
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n📄 Report saved to: {output_path}")


def check_source_mappings(contracts: List[Tuple[str, str]]) -> List[str]:
    missing = []
    for contract_info in contracts:
        name = contract_info[0]
        address = contract_info[1] if len(contract_info) > 1 else None
        source_info = get_source_info_for_contract(name, address)
        if not source_info:
            missing.append(name)
    return missing


def verify_contract_list(
    contracts: List[Tuple[str, str]], 
    verbose: bool = False,
    show_change_type: bool = False,
    skip_unmapped: bool = False
) -> Tuple[List[dict], List[dict], List[str]]:
    verified = []
    failed = []
    skipped = []
    
    missing = check_source_mappings(contracts)
    
    if missing and not skip_unmapped:
        print(f"\n{'='*80}")
        print("❌ FATAL: Missing contract-mapping.json entries")
        print(f"{'='*80}")
        print("The following contracts have no mapping (run generate-contract-mapping.py):")
        for name in missing:
            print(f"  - {name}")
        print("\nUse --skip-unmapped to skip these and verify the rest.")
        print(f"{'='*80}\n")
        for name in missing:
            failed.append({
                "name": name,
                "verified": False,
                "error": "No mapping in contract-mapping.json"
            })
        return verified, failed, skipped
    
    if missing:
        print(f"\n⚠️  Skipping {len(missing)} unmapped contracts: {', '.join(missing)}\n")
        skipped = missing
    
    for contract_info in contracts:
        if show_change_type and len(contract_info) >= 3:
            name, address, change_type = contract_info[0], contract_info[1], contract_info[2]
            print(f"\n[{change_type.upper()}] {name}")
        else:
            name, address = contract_info[0], contract_info[1]
        
        if name in skipped:
            continue
        
        verifier = ContractVerifier(address, name=name, verbose=verbose)
        success = verifier.verify()
        
        if success:
            verified.append(verifier.result)
        else:
            failed.append(verifier.result)
    
    return verified, failed, skipped


def main():
    parser = argparse.ArgumentParser(description='Verify HyperEVM contract deployments')
    parser.add_argument('--all', action='store_true', help='Verify all contracts')
    parser.add_argument('--address', type=str, help='Verify specific contract address')
    parser.add_argument('--file', type=str, help='Verify contracts from JSON file')
    parser.add_argument('--changed-file', type=str, help='Verify contracts from changed addresses JSON (format: [{"name": "contractName", "address": "0x..."}])')
    parser.add_argument('--name', type=str, help='Contract name (used with --address)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--output', '-o', type=str, help='Output JSON report file')
    parser.add_argument('--skip-unmapped', action='store_true', help='Skip contracts not in contract-mapping.json')
    parser.add_argument('--batch', action='store_true', help='Batch mode: compile once per repo (faster)')
    
    args = parser.parse_args()
    
    if args.all:
        verified, failed, skipped = verify_all_contracts(
            verbose=args.verbose, skip_unmapped=args.skip_unmapped, batch=args.batch
        )
        print_summary(verified, failed, skipped)
        
        if args.output:
            save_report(verified, failed, args.output)
        
        sys.exit(0 if len(failed) == 0 else 1)
    
    elif args.address:
        verifier = ContractVerifier(args.address, name=args.name, verbose=args.verbose)
        success = verifier.verify()
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(verifier.result, f, indent=2)
        
        sys.exit(0 if success else 1)
    
    elif args.file:
        filepath = Path(args.file)
        if not filepath.exists():
            print(f"Error: File not found: {filepath}")
            sys.exit(1)
        
        addresses = load_address_file(filepath)
        contracts = [(name, address) for name, address in addresses.items()]
        verified, failed, skipped = verify_contract_list(
            contracts, verbose=args.verbose, skip_unmapped=args.skip_unmapped
        )
        
        print_summary(verified, failed, skipped)
        
        if args.output:
            save_report(verified, failed, args.output)
        
        sys.exit(0 if len(failed) == 0 else 1)
    
    elif args.changed_file:
        filepath = Path(args.changed_file)
        if not filepath.exists():
            print(f"Error: File not found: {filepath}")
            sys.exit(1)
        
        with open(filepath) as f:
            changed_contracts = json.load(f)
        
        if not changed_contracts:
            print("No contracts to verify")
            sys.exit(0)
        
        contracts = [
            (c['name'], c['address'], c.get('change_type', 'unknown')) 
            for c in changed_contracts
        ]
        verified, failed, skipped = verify_contract_list(
            contracts, verbose=args.verbose, show_change_type=True, skip_unmapped=args.skip_unmapped
        )
        
        print_summary(verified, failed, skipped)
        
        if args.output:
            save_report(verified, failed, args.output)
        
        sys.exit(0 if len(failed) == 0 else 1)
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
