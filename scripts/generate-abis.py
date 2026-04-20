#!/usr/bin/env python3
import json
import subprocess
import configparser
import sys
from pathlib import Path
import requests

REPO_ROOT = Path(__file__).parent.parent
ADDRESSES_DIR = REPO_ROOT / "addresses" / "999"
ABIS_DIR = REPO_ROOT / "abis"
HYPERSCAN_API = "https://www.hyperscan.com/api/v2"


def log(msg: str):
    print(msg, flush=True)


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


def get_deployed_contracts() -> dict[str, tuple[str, str]]:
    log("=== Fetching artifact names from Hyperscan ===\n")
    
    contracts = {}
    all_addresses = []
    
    for json_file in sorted(ADDRESSES_DIR.glob("*.json")):
        with open(json_file) as f:
            addresses = json.load(f)
        for key, address in addresses.items():
            if address.startswith("0x") and len(address) == 42:
                all_addresses.append((key, address))
    
    total = len(all_addresses)
    for i, (key, address) in enumerate(all_addresses, 1):
        log(f"  [{i}/{total}] {key}...")
        try:
            resp = requests.get(f"{HYPERSCAN_API}/smart-contracts/{address}", timeout=30)
            if resp.status_code == 200:
                name = resp.json().get("name")
                if name:
                    contracts[key] = (name, address)
                    log(f"           -> {name}")
                else:
                    log(f"           -> (no name)")
            else:
                log(f"           -> (not verified)")
        except Exception as e:
            log(f"           -> ERROR: {e}")
    
    unique_artifacts = set(name for name, _ in contracts.values())
    log(f"\nFound {len(unique_artifacts)} unique artifacts to compile\n")
    return contracts


def find_sol_file(artifact_name: str, repos: dict[str, Path]) -> tuple[str, Path] | None:
    for repo_name, repo_path in repos.items():
        for sol_file in repo_path.rglob(f"{artifact_name}.sol"):
            if "/test/" in str(sol_file) or sol_file.name.endswith(".t.sol"):
                continue
            return repo_name, sol_file
    return None


def compile_contract(repo_path: Path, sol_file: Path) -> bool:
    rel_path = sol_file.relative_to(repo_path)
    result = subprocess.run(
        ["forge", "build", "--contracts", str(rel_path)],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def extract_abi(repo_path: Path, artifact_name: str) -> list | None:
    out_file = repo_path / "out" / f"{artifact_name}.sol" / f"{artifact_name}.json"
    if not out_file.exists():
        for f in (repo_path / "out").rglob(f"{artifact_name}.json"):
            out_file = f
            break
    
    if not out_file.exists():
        return None
    
    try:
        with open(out_file) as f:
            data = json.load(f)
        return data.get("abi")
    except:
        return None


def fetch_abi_from_hyperscan(address: str) -> list | None:
    try:
        resp = requests.get(f"{HYPERSCAN_API}/smart-contracts/{address}", timeout=30)
        if resp.status_code == 200:
            return resp.json().get("abi")
    except:
        pass
    return None


def main():
    ABIS_DIR.mkdir(exist_ok=True)
    
    repos = get_repos_from_gitmodules()
    log(f"Found {len(repos)} repos in .gitmodules\n")
    
    contracts = get_deployed_contracts()
    artifact_to_addresses = {}
    for key, (name, address) in contracts.items():
        if name not in artifact_to_addresses:
            artifact_to_addresses[name] = []
        artifact_to_addresses[name].append(address)
    
    unique_artifacts = sorted(artifact_to_addresses.keys())
    
    log(f"=== Processing {len(unique_artifacts)} contracts ===\n")
    
    compiled = 0
    from_hyperscan = 0
    failed = []
    
    for i, artifact_name in enumerate(unique_artifacts, 1):
        log(f"  [{i}/{len(unique_artifacts)}] {artifact_name}...")
        
        abi_file = ABIS_DIR / f"{artifact_name}.json"
        if abi_file.exists():
            log(f"           -> already exists, skipping")
            compiled += 1
            continue
        
        location = find_sol_file(artifact_name, repos)
        abi = None
        
        if location:
            repo_name, sol_file = location
            repo_path = repos[repo_name]
            log(f"           -> found in {repo_name}")
            
            if compile_contract(repo_path, sol_file):
                abi = extract_abi(repo_path, artifact_name)
                if abi:
                    log(f"           -> compiled successfully")
        
        if not abi:
            address = artifact_to_addresses[artifact_name][0]
            log(f"           -> trying Hyperscan fallback...")
            abi = fetch_abi_from_hyperscan(address)
            if abi:
                log(f"           -> fetched from Hyperscan")
                from_hyperscan += 1
        
        if not abi:
            log(f"           -> FAILED")
            failed.append(artifact_name)
            continue
        
        with open(abi_file, "w") as f:
            json.dump(abi, f, indent=2)
        log(f"           -> saved {len(abi)} entries")
        compiled += 1
    
    log(f"\n=== SUMMARY ===")
    log(f"Saved: {compiled} ({from_hyperscan} from Hyperscan)")
    log(f"Failed: {len(failed)}")
    if failed:
        log(f"  {failed}")
    log(f"\nABIs saved to {ABIS_DIR}")
    log(f"Commit the abis/ directory when done.")


if __name__ == "__main__":
    main()
