#!/usr/bin/env python3
"""
Generate contract-mapping.json

For each deployed address in addresses/999/*.json:
1. Fetch contract metadata from Hyperscan (artifact name, compiler settings, file_path)
2. Resolve the source repo + commit from .gitmodules submodules
3. Write the mapping to contract-mapping.json

Usage:
    python3 scripts/generate-contract-mapping.py
"""

import configparser
import json
import subprocess
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).parent.parent
ADDRESSES_DIR = REPO_ROOT / "addresses" / "999"
HYPERSCAN_API = "https://www.hyperscan.com/api/v2"
OUTPUT_FILE = REPO_ROOT / "contract-mapping.json"


# ---------------------------------------------------------------------------
# Submodule helpers
# ---------------------------------------------------------------------------
def get_repos_from_gitmodules() -> dict[str, Path]:
    """Parse .gitmodules and return {org/repo: local_path}."""
    gitmodules = REPO_ROOT / ".gitmodules"
    config = configparser.ConfigParser()
    config.read(gitmodules)
    repos = {}
    for section in config.sections():
        url = config[section]["url"]
        path = config[section]["path"]
        if url.endswith(".git"):
            url = url[:-4]
        parts = url.rstrip("/").split("/")
        repo_name = f"{parts[-2]}/{parts[-1]}"
        repos[repo_name] = REPO_ROOT / path
    return repos


def get_submodule_commit(path: Path) -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"],
                        cwd=path, capture_output=True, text=True, check=True)
    return r.stdout.strip()


def get_nested_submodule_info(parent: Path, sub_path: str) -> tuple[str, str] | None:
    """Get (org/repo, commit) for a nested submodule inside a parent repo."""
    sub_dir = parent / sub_path
    if not sub_dir.exists():
        return None
    url_r = subprocess.run(
        ["git", "config", "--file", ".gitmodules", "--get",
         f"submodule.{sub_path}.url"],
        cwd=parent, capture_output=True, text=True, timeout=10,
    )
    if url_r.returncode != 0:
        return None
    url = url_r.stdout.strip()
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.rstrip("/").split("/")
    repo_name = f"{parts[-2]}/{parts[-1]}"
    commit_r = subprocess.run(["git", "rev-parse", "HEAD"],
                               cwd=sub_dir, capture_output=True, text=True, timeout=10)
    if commit_r.returncode != 0:
        return None
    return repo_name, commit_r.stdout.strip()


# ---------------------------------------------------------------------------
# Repo resolution
# ---------------------------------------------------------------------------
def resolve_repo(artifact_name: str, file_path: str | None,
                 repos: dict[str, Path]) -> tuple[str, str] | None:
    """Determine (repo, commit) for a contract.

    Strategy:
    1. If Hyperscan provides a file_path starting with lib/X, match X to a
       top-level submodule. If no match, check evk-periphery's nested submodules
       and return evk-periphery (since the contract must build from its context).
    2. Otherwise, search src/ directories in each submodule for the .sol file.
    """
    if file_path and file_path.startswith("lib/"):
        lib_name = file_path.split("/")[1]

        # Check top-level submodules
        for repo_name, repo_path in repos.items():
            if repo_path.name == lib_name and repo_path.exists():
                return repo_name, get_submodule_commit(repo_path)

        # Check evk-periphery nested submodules -- return evk-periphery as the
        # build context since the contract compiles within that repo.
        evk_periphery = repos.get("euler-xyz/evk-periphery")
        if evk_periphery and evk_periphery.exists():
            info = get_nested_submodule_info(evk_periphery, f"lib/{lib_name}")
            if info:
                return "euler-xyz/evk-periphery", get_submodule_commit(evk_periphery)

    # Fallback: search src/ directories
    for repo_name, repo_path in repos.items():
        for src in ("src", "contracts"):
            src_dir = repo_path / src
            if not src_dir.exists():
                continue
            for sol in src_dir.rglob(f"{artifact_name}.sol"):
                if "/test/" in str(sol) or sol.name.endswith(".t.sol"):
                    continue
                return repo_name, get_submodule_commit(repo_path)

    return None


# ---------------------------------------------------------------------------
# Hyperscan
# ---------------------------------------------------------------------------
def fetch_contract_info(address: str) -> dict | None:
    """Fetch verified contract metadata from Hyperscan."""
    try:
        resp = requests.get(f"{HYPERSCAN_API}/smart-contracts/{address}", timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return {
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


# ---------------------------------------------------------------------------
# Hardcoded overrides for contracts that can't be auto-discovered
# (e.g., third-party contracts in deeply nested submodules)
# ---------------------------------------------------------------------------
HARDCODED: dict[str, dict] = {
    "permit2": {
        "address": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "repo": "Uniswap/permit2",
        "artifact_name": "Permit2",
        "file_path": "src/Permit2.sol",
        "compiler_version": "v0.8.17+commit.8df45f5f",
        "optimization_enabled": True,
        "optimization_runs": 1000000,
        "evm_version": "london",
        "via_ir": True,
        "build_context": "lib/euler-vault-kit/lib/permit2",
    },
}


def apply_hardcoded(mapping: dict, repos: dict[str, Path]):
    """Add hardcoded entries for contracts that can't be auto-discovered."""
    for key, entry in HARDCODED.items():
        if key in mapping:
            continue
        # Try to resolve commit from the nested submodule path
        ctx = entry.get("build_context", "")
        ctx_path = REPO_ROOT / ctx
        if ctx_path.exists():
            entry["commit"] = get_submodule_commit(ctx_path)
            mapping[key] = {k: v for k, v in entry.items() if k != "build_context"}
            print(f"  {key}: {entry['artifact_name']} -> {entry['repo']}@{entry['commit'][:12]} (hardcoded)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=== Loading repos from .gitmodules ===\n")
    repos = get_repos_from_gitmodules()
    print(f"Found {len(repos)} repos\n")

    print("=== Processing deployed addresses ===\n")

    mapping: dict[str, dict] = {}
    not_verified: list[str] = []
    no_repo: list[str] = []

    for json_file in sorted(ADDRESSES_DIR.glob("*.json")):
        print(f"\n{json_file.name}:")
        with open(json_file) as f:
            addresses = json.load(f)

        for key, address in addresses.items():
            if not address.startswith("0x") or len(address) != 42:
                continue
            if address == "0x0000000000000000000000000000000000000000":
                continue

            info = fetch_contract_info(address)
            if info is None:
                print(f"  {key}: NOT VERIFIED on Hyperscan")
                not_verified.append(key)
                continue

            # Derive artifact name from Hyperscan's file_path
            file_path = info.get("file_path")
            artifact_name = Path(file_path).stem if file_path else key

            repo_info = resolve_repo(artifact_name, file_path, repos)
            if not repo_info:
                print(f"  {key}: {artifact_name} -> NO REPO FOUND")
                no_repo.append(key)
                continue

            repo_name, commit = repo_info
            print(f"  {key}: {artifact_name} -> {repo_name}@{commit[:12]}")

            mapping[key] = {
                "address": address,
                "repo": repo_name,
                "commit": commit,
                "artifact_name": artifact_name,
                "file_path": file_path,
                "compiler_version": info.get("compiler_version"),
                "optimization_enabled": info.get("optimization_enabled"),
                "optimization_runs": info.get("optimization_runs"),
                "evm_version": info.get("evm_version"),
                "via_ir": info.get("via_ir"),
                "verified_at": info.get("verified_at"),
            }

    apply_hardcoded(mapping, repos)

    print(f"\n=== SUMMARY ===")
    print(f"Mapped:       {len(mapping)}")
    print(f"Not verified: {len(not_verified)}")
    if not_verified:
        print(f"  {not_verified}")
    print(f"No repo:      {len(no_repo)}")
    if no_repo:
        print(f"  {no_repo}")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(mapping, f, indent=2)
    print(f"\nMapping saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
