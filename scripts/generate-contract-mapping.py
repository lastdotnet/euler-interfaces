#!/usr/bin/env python3
import json
import subprocess
import configparser
from pathlib import Path
import requests

REPO_ROOT = Path(__file__).parent.parent
ADDRESSES_DIR = REPO_ROOT / "addresses" / "999"
ABIS_DIR = REPO_ROOT / "abis"
HYPERSCAN_API = "https://www.hyperscan.com/api/v2"
OUTPUT_FILE = REPO_ROOT / "contract-mapping.json"


def get_function_selectors(abi: list) -> set[str]:
    """Compute function selectors using keccak256 (Ethereum standard)."""
    selectors = set()
    for item in abi:
        if item.get("type") == "function":
            name = item["name"]
            inputs = ",".join(normalize_type(i["type"]) for i in item.get("inputs", []))
            sig = f"{name}({inputs})"
            selector = keccak256(sig)[:8]
            selectors.add(selector)
    return selectors


def keccak256(data: str) -> str:
    from Crypto.Hash import keccak
    k = keccak.new(digest_bits=256)
    k.update(data.encode())
    return k.hexdigest()


def get_function_selectors_proper(abi: list) -> set[str]:
    selectors = set()
    for item in abi:
        if item.get("type") == "function":
            name = item["name"]
            inputs = ",".join(normalize_type(i["type"]) for i in item.get("inputs", []))
            sig = f"{name}({inputs})"
            selector = keccak256(sig)[:8]
            selectors.add(selector)
    return selectors


def normalize_type(t: str) -> str:
    return t


def load_local_abis() -> dict[str, set[str]]:
    abis = {}
    for abi_file in ABIS_DIR.glob("*.json"):
        name = abi_file.stem
        with open(abi_file) as f:
            abi = json.load(f)
        selectors = get_function_selectors_proper(abi)
        abis[name] = selectors
    return abis


def get_contract_info(address: str) -> dict | None:
    try:
        resp = requests.get(f"{HYPERSCAN_API}/smart-contracts/{address}", timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        
        return {
            "abi": data.get("abi"),
            "compiler_version": data.get("compiler_version"),
            "optimization_enabled": data.get("optimization_enabled"),
            "optimization_runs": data.get("optimization_runs"),
            "evm_version": data.get("evm_version"),
            "via_ir": data.get("compiler_settings", {}).get("viaIR", False),
            "verified_at": data.get("verified_at"),
            "file_path": data.get("file_path"),
        }
    except Exception as e:
        print(f"    Error fetching {address}: {e}")
        return None


def match_abi(deployed_selectors: set[str], local_abis: dict[str, set[str]]) -> str | None:
    best_match = None
    best_score = 0
    
    for name, local_selectors in local_abis.items():
        if not local_selectors:
            continue
        intersection = deployed_selectors & local_selectors
        union = deployed_selectors | local_selectors
        jaccard = len(intersection) / len(union) if union else 0
        
        if jaccard > best_score and jaccard > 0.8:
            best_score = jaccard
            best_match = name
    
    return best_match


def get_repos_from_gitmodules() -> dict[str, Path]:
    gitmodules = REPO_ROOT / ".gitmodules"
    config = configparser.ConfigParser()
    config.read(gitmodules)
    
    repos = {}
    for section in config.sections():
        url = config[section]["url"]
        path = config[section]["path"]
        if url.endswith('.git'):
            url = url[:-4]
        parts = url.rstrip('/').split('/')
        repo_name = f'{parts[-2]}/{parts[-1]}'
        repos[repo_name] = REPO_ROOT / path
    return repos


def get_submodule_commit(path: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def get_submodule_info(parent_repo_path: Path, submodule_path: str) -> tuple[str, str] | None:
    submodule_dir = parent_repo_path / submodule_path
    if not submodule_dir.exists():
        return None
    
    url_result = subprocess.run(
        ["git", "config", "--file", ".gitmodules", "--get", f"submodule.{submodule_path}.url"],
        cwd=parent_repo_path, capture_output=True, text=True, timeout=10
    )
    if url_result.returncode != 0:
        return None
    
    url = url_result.stdout.strip()
    if url.endswith('.git'):
        url = url[:-4]
    parts = url.rstrip('/').split('/')
    repo_name = f'{parts[-2]}/{parts[-1]}'
    
    commit_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=submodule_dir, capture_output=True, text=True, timeout=10
    )
    if commit_result.returncode != 0:
        return None
    
    return repo_name, commit_result.stdout.strip()


def find_contract_in_repos(artifact_name: str, repos: dict[str, Path], file_path: str | None = None) -> tuple[str, str] | None:
    # If Hyperscan reports a lib/X path, check if X matches a top-level submodule first
    if file_path and file_path.startswith("lib/"):
        parts = file_path.split('/')
        if len(parts) >= 2:
            lib_name = parts[1]
            # Check top-level submodules for a matching repo name
            for repo_name, repo_path in repos.items():
                if repo_path.name == lib_name and repo_path.exists():
                    commit = get_submodule_commit(repo_path)
                    return repo_name, commit
            
            # Fall back to checking evk-periphery's nested submodules.
            # Return evk-periphery as the repo since the contract must be built from its context.
            evk_periphery_path = repos.get("euler-xyz/evk-periphery")
            if evk_periphery_path and evk_periphery_path.exists():
                submodule_path = f"lib/{lib_name}"
                submodule_info = get_submodule_info(evk_periphery_path, submodule_path)
                if submodule_info:
                    evk_commit = get_submodule_commit(evk_periphery_path)
                    return "euler-xyz/evk-periphery", evk_commit
    
    for repo_name, repo_path in repos.items():
        src_dir = repo_path / "src"
        if not src_dir.exists():
            src_dir = repo_path / "contracts"
        if not src_dir.exists():
            continue
        
        for sol_file in src_dir.rglob(f"{artifact_name}.sol"):
            if "/test/" in str(sol_file) or sol_file.name.endswith(".t.sol"):
                continue
            commit = get_submodule_commit(repo_path)
            return repo_name, commit
    
    return None


def main():
    print("=== Loading local ABIs ===\n")
    local_abis = load_local_abis()
    print(f"Loaded {len(local_abis)} ABIs\n")
    
    print("=== Loading repos from .gitmodules ===\n")
    repos = get_repos_from_gitmodules()
    print(f"Found {len(repos)} repos\n")
    
    print("=== Processing deployed addresses ===\n")
    
    mapping = {}
    not_verified = []
    no_abi_match = []
    no_repo_match = []
    
    for json_file in sorted(ADDRESSES_DIR.glob("*.json")):
        print(f"\n{json_file.name}:")
        with open(json_file) as f:
            addresses = json.load(f)
        
        for key, address in addresses.items():
            if not address.startswith("0x") or len(address) != 42:
                print(f"  {key}: SKIP (invalid address)")
                continue
            if address == "0x0000000000000000000000000000000000000000":
                print(f"  {key}: SKIP (null address)")
                continue
            
            contract_info = get_contract_info(address)
            
            if contract_info is None or contract_info.get("abi") is None:
                print(f"  {key}: NOT VERIFIED")
                not_verified.append(key)
                continue
            
            deployed_selectors = get_function_selectors_proper(contract_info["abi"])
            artifact_name = match_abi(deployed_selectors, local_abis)
            
            if artifact_name is None:
                print(f"  {key}: NO ABI MATCH")
                no_abi_match.append(key)
                continue
            
            file_path = contract_info.get("file_path")
            
            # Prefer the contract name from Hyperscan's file_path over ABI matching,
            # since concrete contracts may inherit from a base with identical selectors.
            if file_path:
                file_artifact_name = Path(file_path).stem
                if file_artifact_name != artifact_name:
                    artifact_name = file_artifact_name
            
            repo_info = find_contract_in_repos(artifact_name, repos, file_path)
            
            if repo_info is None:
                print(f"  {key}: {artifact_name} -> NO REPO FOUND")
                no_repo_match.append(key)
                continue
            
            repo_name, commit = repo_info
            print(f"  {key}: {artifact_name} -> {repo_name}@{commit[:12]}")
            
            mapping[key] = {
                "address": address,
                "repo": repo_name,
                "commit": commit,
                "artifact_name": artifact_name,
                "file_path": file_path,
                "compiler_version": contract_info.get("compiler_version"),
                "optimization_enabled": contract_info.get("optimization_enabled"),
                "optimization_runs": contract_info.get("optimization_runs"),
                "evm_version": contract_info.get("evm_version"),
                "via_ir": contract_info.get("via_ir"),
                "verified_at": contract_info.get("verified_at"),
            }
    
    print("\n=== SUMMARY ===")
    print(f"Mapped: {len(mapping)}")
    print(f"Not verified: {len(not_verified)}")
    if not_verified:
        print(f"  {not_verified}")
    print(f"No ABI match: {len(no_abi_match)}")
    if no_abi_match:
        print(f"  {no_abi_match}")
    print(f"No repo found: {len(no_repo_match)}")
    if no_repo_match:
        print(f"  {no_repo_match}")
    
    with open(OUTPUT_FILE, "w") as f:
        json.dump(mapping, f, indent=2)
    print(f"\nMapping saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
