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
HYPERSCAN_API_BASE = "https://hyperscan.com/api/v2"
REPO_ROOT = Path(__file__).parent.parent

# Known source repository mappings
SOURCE_REPOS = {
    # Euler Vault Kit
    "EVault": {"repo": "euler-xyz/euler-vault-kit", "commit": "5b98b42"},
    "EVaultFactory": {"repo": "euler-xyz/euler-vault-kit", "commit": "5b98b42"},
    "GenericFactory": {"repo": "euler-xyz/euler-vault-kit", "commit": "5b98b42"},
    "BalanceTracker": {"repo": "euler-xyz/euler-vault-kit", "commit": "5b98b42"},
    "ProtocolConfig": {"repo": "euler-xyz/euler-vault-kit", "commit": "5b98b42"},
    "SequenceRegistry": {"repo": "euler-xyz/euler-vault-kit", "commit": "5b98b42"},
    
    # Ethereum Vault Connector
    "EthereumVaultConnector": {"repo": "euler-xyz/ethereum-vault-connector", "tag": "v1.0.1"},
    
    # Permit2 (Uniswap)
    "Permit2": {"repo": "Uniswap/permit2", "tag": "v1.0.0"},
    
    # Euler Earn
    "EulerEarn": {"repo": "euler-xyz/euler-earn", "commit": "b2fd6e6"},
    "EulerEarnFactory": {"repo": "euler-xyz/euler-earn", "commit": "b2fd6e6"},
    "EulerEarnVault": {"repo": "euler-xyz/euler-earn", "commit": "b2fd6e6"},
    
    # Euler Swap
    "EulerSwapV2Factory": {"repo": "euler-xyz/euler-swap", "commit": "dd936d2"},
    "EulerSwapV2": {"repo": "euler-xyz/euler-swap", "commit": "dd936d2"},
    "EulerSwapV2Periphery": {"repo": "euler-xyz/euler-swap", "commit": "dd936d2"},
    "EulerSwapV2ProtocolFeeConfig": {"repo": "euler-xyz/euler-swap", "commit": "dd936d2"},
    
    # EVK Periphery
    "AccountLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163ca"},
    "VaultLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163ca"},
    "OracleLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163ca"},
    "IRMLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163ca"},
    "UtilsLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163ca"},
    "EulerEarnVaultLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163ca"},
    
    # Price Oracle
    "OracleRouterFactory": {"repo": "euler-xyz/euler-price-oracle", "commit": "ffc3cb8"},
    "OracleAdapterRegistry": {"repo": "euler-xyz/euler-price-oracle", "commit": "ffc3cb8"},
    
    # Fee Flow
    "FeeFlowController": {"repo": "euler-xyz/fee-flow", "commit": "3bee858"},
    
    # Reward Streams
    "RewardStreams": {"repo": "euler-xyz/reward-streams", "commit": "a63c358"},
}


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
            
            if not data.get('is_verified'):
                self.result['error'] = "Contract is not verified on Hyperscan"
                return False
            
            hyperscan_name = data.get('name', 'Unknown')
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
        """Fetch verification data from Hyperscan"""
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
            
            return True
            
        except Exception as e:
            self.result['error'] = f"Failed to fetch verification data: {str(e)}"
            return False
    
    def fetch_deployed_bytecode(self) -> Optional[str]:
        """Fetch deployed bytecode from creation transaction"""
        self.log("Fetching deployed bytecode...")
        
        try:
            creation_tx = self.result['details'].get('creation_tx')
            if not creation_tx:
                self.result['error'] = "No creation transaction found"
                return None
            
            url = f"{HYPERSCAN_API_BASE}/transactions/{creation_tx}"
            response = requests.get(url, headers={'Accept': 'application/json'}, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            bytecode = data.get('raw_input')
            if not bytecode:
                self.result['error'] = "No bytecode found in creation transaction"
                return None
            
            self.log(f"Fetched {len(bytecode)} chars of bytecode")
            return bytecode
            
        except Exception as e:
            self.result['error'] = f"Failed to fetch bytecode: {str(e)}"
            return None
    
    def compile_from_source(self) -> Optional[str]:
        """Compile contract from source using repository mapping"""
        self.log("Compiling from source...")
        
        source_info = SOURCE_REPOS.get(self.name)
        if not source_info:
            for contract_name, info in SOURCE_REPOS.items():
                if contract_name.lower() in self.name.lower():
                    source_info = info
                    break
        
        if not source_info:
            self.result['error'] = f"No source repository mapping found for {self.name}"
            return None
        
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                self.log(f"Cloning {source_info['repo']}...")
                
                repo_dir = Path(tmpdir) / "repo"
                
                if 'tag' in source_info:
                    clone_cmd = ["git", "clone", "--depth", "1", "--branch", source_info['tag'], 
                                 f"https://github.com/{source_info['repo']}.git", str(repo_dir)]
                else:
                    clone_cmd = ["git", "clone", "--depth", "1", 
                                 f"https://github.com/{source_info['repo']}.git", str(repo_dir)]
                
                subprocess.run(clone_cmd, check=True, capture_output=True)
                
                if 'commit' in source_info and 'tag' not in source_info:
                    # Fetch all branches to ensure commit is reachable
                    fetch_cmd = ["git", "fetch", "--all"]
                    subprocess.run(fetch_cmd, cwd=repo_dir, check=False, capture_output=True)
                    checkout_cmd = ["git", "checkout", source_info['commit']]
                    subprocess.run(checkout_cmd, cwd=repo_dir, check=True, capture_output=True)
                
                self._patch_foundry_config(repo_dir)
                
                self.log("Building with Foundry...")
                build_cmd = ["forge", "build", "--force"]
                result = subprocess.run(build_cmd, cwd=repo_dir, capture_output=True, text=True)
                
                if result.returncode != 0:
                    self.result['error'] = f"Forge build failed: {result.stderr}"
                    return None
                
                bytecode = self._extract_bytecode_from_artifacts(repo_dir)
                if bytecode:
                    self.log(f"Compiled {len(bytecode)} chars of bytecode")
                else:
                    self.result['error'] = f"Could not find contract bytecode in build artifacts"
                
                return bytecode
                
        except Exception as e:
            self.result['error'] = f"Failed to compile from source: {str(e)}"
            return None
    
    def _patch_foundry_config(self, repo_dir: Path):
        """Patch foundry.toml with deployment compiler settings"""
        foundry_toml = repo_dir / "foundry.toml"
        if not foundry_toml.exists():
            return
        
        content = foundry_toml.read_text()
        
        optimizer_runs = self.result['details'].get('optimization_runs')
        if optimizer_runs:
            content = re.sub(
                r'optimizer_runs\s*=\s*\d+',
                f'optimizer_runs = {optimizer_runs}',
                content
            )
        
        compiler_version = self.result['details'].get('compiler_version', '')
        if compiler_version:
            match = re.search(r'v?(\d+\.\d+\.\d+)', compiler_version)
            if match:
                solc_version = match.group(1)
                content = re.sub(
                    r'solc\s*=\s*"[\d\.]+"',
                    f'solc = "{solc_version}"',
                    content
                )
        
        foundry_toml.write_text(content)
    
    def _extract_bytecode_from_artifacts(self, repo_dir: Path) -> Optional[str]:
        """Extract bytecode from Foundry build artifacts"""
        out_dir = repo_dir / "out"
        if not out_dir.exists():
            return None
        
        for artifact_file in out_dir.rglob("*.json"):
            try:
                with open(artifact_file) as f:
                    data = json.load(f)
                    if data.get('contractName') == self.name or artifact_file.stem == self.name:
                        bytecode = data.get('bytecode', {}).get('object')
                        if bytecode and bytecode != '0x':
                            return bytecode
            except:
                continue
        
        return None
    
    def compare_bytecodes(self, deployed: str, compiled: str) -> bool:
        """Compare deployed and compiled bytecodes (excluding metadata)"""
        self.log("Comparing bytecodes...")
        
        deployed_stripped = self._strip_metadata(deployed)
        compiled_stripped = self._strip_metadata(compiled)
        
        self.result['details']['deployed_size'] = len(deployed) // 2
        self.result['details']['compiled_size'] = len(compiled) // 2
        self.result['details']['stripped_deployed_size'] = len(deployed_stripped) // 2
        self.result['details']['stripped_compiled_size'] = len(compiled_stripped) // 2
        
        if deployed_stripped == compiled_stripped:
            self.log("✅ Bytecodes match!")
            return True
        else:
            self.log("❌ Bytecodes differ")
            for i, (a, b) in enumerate(zip(deployed_stripped, compiled_stripped)):
                if a != b:
                    self.result['details']['first_diff_position'] = i
                    self.result['details']['first_diff_deployed'] = deployed_stripped[max(0, i-20):i+20]
                    self.result['details']['first_diff_compiled'] = compiled_stripped[max(0, i-20):i+20]
                    break
            self.result['error'] = "Bytecode mismatch"
            return False
    
    def _strip_metadata(self, bytecode: str) -> str:
        """Remove CBOR metadata from bytecode"""
        if bytecode.startswith('0x'):
            bytecode = bytecode[2:]
        
        marker = "a264697066735822"
        idx = bytecode.rfind(marker)
        
        if idx != -1:
            return bytecode[:idx]
        
        return bytecode
    
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


def verify_all_contracts(verbose: bool = False) -> Tuple[List[dict], List[dict]]:
    """Verify all contracts in the repository"""
    address_files = [
        "addresses/999/CoreAddresses.json",
        "addresses/999/LensAddresses.json",
        "addresses/999/PeripheryAddresses.json",
        "addresses/999/EulerSwapAddresses.json",
        "addresses/999/TokenAddresses.json",
        "addresses/999/BridgeAddresses.json",
    ]
    
    verified = []
    failed = []
    
    for address_file in address_files:
        filepath = REPO_ROOT / address_file
        if not filepath.exists():
            continue
        
        print(f"\n{'#'*80}")
        print(f"# Processing: {address_file}")
        print(f"{'#'*80}")
        
        addresses = load_address_file(filepath)
        
        for name, address in addresses.items():
            verifier = ContractVerifier(address, name=name, verbose=verbose)
            success = verifier.verify()
            
            if success:
                verified.append(verifier.result)
            else:
                failed.append(verifier.result)
    
    return verified, failed


def print_summary(verified: List[dict], failed: List[dict]):
    """Print verification summary"""
    print(f"\n{'='*80}")
    print("VERIFICATION SUMMARY")
    print(f"{'='*80}")
    print(f"✅ Verified: {len(verified)}")
    print(f"❌ Failed: {len(failed)}")
    print(f"Total: {len(verified) + len(failed)}")
    
    if failed:
        print(f"\nFailed contracts:")
        for result in failed:
            print(f"  - {result['name']}: {result['error']}")


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


def main():
    parser = argparse.ArgumentParser(description='Verify HyperEVM contract deployments')
    parser.add_argument('--all', action='store_true', help='Verify all contracts')
    parser.add_argument('--address', type=str, help='Verify specific contract address')
    parser.add_argument('--file', type=str, help='Verify contracts from JSON file')
    parser.add_argument('--changed-file', type=str, help='Verify contracts from changed addresses JSON (format: [{"name": "contractName", "address": "0x..."}])')
    parser.add_argument('--name', type=str, help='Contract name (used with --address)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--output', '-o', type=str, help='Output JSON report file')
    
    args = parser.parse_args()
    
    if args.all:
        verified, failed = verify_all_contracts(verbose=args.verbose)
        print_summary(verified, failed)
        
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
        verified = []
        failed = []
        
        for name, address in addresses.items():
            verifier = ContractVerifier(address, name=name, verbose=args.verbose)
            success = verifier.verify()
            
            if success:
                verified.append(verifier.result)
            else:
                failed.append(verifier.result)
        
        print_summary(verified, failed)
        
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
        
        verified = []
        failed = []
        
        for contract in changed_contracts:
            address = contract['address']
            name = contract['name']
            change_type = contract.get('change_type', 'unknown')
            
            print(f"\n[{change_type.upper()}] {name}")
            
            verifier = ContractVerifier(address, name=name, verbose=args.verbose)
            success = verifier.verify()
            
            if success:
                verified.append(verifier.result)
            else:
                failed.append(verifier.result)
        
        print_summary(verified, failed)
        
        if args.output:
            save_report(verified, failed, args.output)
        
        sys.exit(0 if len(failed) == 0 else 1)
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
