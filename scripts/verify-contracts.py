#!/usr/bin/env python3
"""
HyperEVM Contract Verification Script

Verifies deployed contracts match their source code by:
1. Loading contract-to-repo mapping from contract-mapping.json
2. Grouping contracts by (repo, commit, compiler settings)
3. Building each repo once with Foundry (using local submodules)
4. Comparing deployed bytecode against compiled artifacts (stripping CBOR metadata,
   accounting for constructor args, factory deployments, and immutable variables)

Usage:
    python3 scripts/verify-contracts.py --all
    python3 scripts/verify-contracts.py --address 0x... --name evc
    python3 scripts/verify-contracts.py --file addresses/999/CoreAddresses.json
    python3 scripts/verify-contracts.py --changed-file changed.json
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
HYPERSCAN_API = "https://www.hyperscan.com/api/v2"
HYPERLIQUID_RPC = "https://rpc.hyperliquid.xyz/evm"
REPO_ROOT = Path(__file__).parent.parent
MAPPING_FILE = REPO_ROOT / "contract-mapping.json"
LIB_DIR = REPO_ROOT / "lib"

ADDRESS_FILES = [
    "addresses/999/CoreAddresses.json",
    "addresses/999/LensAddresses.json",
    "addresses/999/PeripheryAddresses.json",
    "addresses/999/EulerSwapAddresses.json",
    "addresses/999/GovernorAddresses.json",
    "addresses/999/TokenAddresses.json",
    "addresses/999/BridgeAddresses.json",
]


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------
def load_mapping() -> dict:
    if not MAPPING_FILE.exists():
        print(f"Error: {MAPPING_FILE} not found. Run generate-contract-mapping.py first.")
        sys.exit(1)
    with open(MAPPING_FILE) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Address loading
# ---------------------------------------------------------------------------
ZERO = "0x0000000000000000000000000000000000000000"


def load_all_contracts() -> list[tuple[str, str]]:
    """Load all non-zero addresses from the standard address files."""
    contracts = []
    for rel_path in ADDRESS_FILES:
        path = REPO_ROOT / rel_path
        if not path.exists():
            continue
        with open(path) as f:
            data = json.load(f)
        for name, addr in data.items():
            if addr != ZERO:
                contracts.append((name, addr))
    return contracts


def load_address_file(filepath: Path) -> list[tuple[str, str]]:
    with open(filepath) as f:
        data = json.load(f)
    return [(name, addr) for name, addr in data.items() if addr != ZERO]


def load_changed_file(filepath: Path) -> list[tuple[str, str]]:
    with open(filepath) as f:
        data = json.load(f)
    return [(c["name"], c["address"]) for c in data]


# ---------------------------------------------------------------------------
# Bytecode fetching (3-tier fallback)
# ---------------------------------------------------------------------------
def fetch_bytecode(address: str, verbose: bool = False) -> tuple[Optional[str], Optional[str]]:
    """Fetch bytecode for address. Returns (bytecode_hex, 'creation'|'runtime')."""
    addr = address.lower()

    # Tier 1: creation tx (only direct deploys, not factory calls)
    try:
        resp = requests.get(f"{HYPERSCAN_API}/addresses/{addr}",
                            headers={"Accept": "application/json"}, timeout=10)
        resp.raise_for_status()
        creation_tx = resp.json().get("creation_transaction_hash")
        if creation_tx:
            tx_resp = requests.get(f"{HYPERSCAN_API}/transactions/{creation_tx}",
                                   headers={"Accept": "application/json"}, timeout=10)
            tx_resp.raise_for_status()
            tx_data = tx_resp.json()
            is_factory = tx_data.get("to") is not None
            raw = tx_data.get("raw_input")
            if raw and not is_factory:
                if verbose:
                    print(f"    Fetched creation bytecode ({len(raw)} chars)")
                return raw, "creation"
            if is_factory and verbose:
                to_hash = tx_data["to"].get("hash", "?")[:14]
                print(f"    Factory deploy via {to_hash}, using runtime")
    except Exception:
        pass

    # Tier 2: runtime bytecode from Hyperscan
    try:
        resp = requests.get(f"{HYPERSCAN_API}/smart-contracts/{addr}",
                            headers={"Accept": "application/json"}, timeout=30)
        resp.raise_for_status()
        runtime = resp.json().get("deployed_bytecode")
        if runtime:
            if verbose:
                print(f"    Fetched runtime bytecode ({len(runtime)} chars, Hyperscan)")
            return runtime, "runtime"
    except Exception:
        pass

    # Tier 3: eth_getCode RPC
    try:
        resp = requests.post(HYPERLIQUID_RPC, json={
            "jsonrpc": "2.0", "method": "eth_getCode",
            "params": [addr, "latest"], "id": 1,
        }, timeout=10)
        resp.raise_for_status()
        code = resp.json().get("result", "0x")
        if code and code != "0x":
            if verbose:
                print(f"    Fetched runtime bytecode ({len(code)} chars, RPC)")
            return code, "runtime"
    except Exception:
        pass

    return None, None


# ---------------------------------------------------------------------------
# Repo build
# ---------------------------------------------------------------------------
def get_local_repo(repo: str) -> Optional[Path]:
    """Return local lib/ path if the repo exists as a submodule."""
    name = repo.split("/")[-1]
    p = LIB_DIR / name
    return p if p.exists() and (p / ".git").exists() else None


def init_submodules(repo_dir: Path):
    """Initialize submodules at their pinned commits."""
    result = subprocess.run(
        ["git", "submodule", "status"],
        cwd=repo_dir, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        commit = parts[0].lstrip("-+")
        sub_path = parts[1]
        subprocess.run(["git", "submodule", "init", sub_path],
                       cwd=repo_dir, capture_output=True, timeout=30)
        sub_dir = repo_dir / sub_path
        sub_dir.mkdir(parents=True, exist_ok=True)
        url_r = subprocess.run(
            ["git", "config", "--get", f"submodule.{sub_path}.url"],
            cwd=repo_dir, capture_output=True, text=True, timeout=10,
        )
        if url_r.returncode != 0:
            continue
        url = url_r.stdout.strip()
        subprocess.run(["git", "init", "-q"], cwd=sub_dir, capture_output=True, timeout=10)
        subprocess.run(["git", "remote", "add", "origin", url],
                       cwd=sub_dir, capture_output=True, timeout=10)
        subprocess.run(["git", "fetch", "--depth", "1", "origin", commit],
                       cwd=sub_dir, capture_output=True, timeout=120)
        subprocess.run(["git", "checkout", "FETCH_HEAD"],
                       cwd=sub_dir, capture_output=True, timeout=30)

    # Nested submodules (one level deep)
    lib = repo_dir / "lib"
    if lib.exists():
        for d in lib.iterdir():
            if d.is_dir() and (d / ".gitmodules").exists():
                init_submodules(d)


def patch_foundry_config(repo_dir: Path, settings: dict):
    """Patch foundry.toml to match deployment compiler settings."""
    toml = repo_dir / "foundry.toml"
    if not toml.exists():
        return
    content = toml.read_text()

    def _set(key: str, val: str, quoted: bool = False):
        nonlocal content
        v = f'"{val}"' if quoted else val
        pattern = rf'{key}\s*=\s*["\']?[^"\'"\n]+["\']?'
        if re.search(pattern, content):
            content = re.sub(pattern, f'{key} = {v}', content)
        elif "[profile.default]" in content:
            content = content.replace("[profile.default]",
                                      f"[profile.default]\n{key} = {v}")

    _set("script", "disabled_script", quoted=True)
    _set("test", "disabled_test", quoted=True)

    if settings.get("optimization_enabled") is not None:
        _set("optimizer", "true" if settings["optimization_enabled"] else "false")
    if settings.get("optimization_runs") is not None:
        _set("optimizer_runs", str(settings["optimization_runs"]))
    if settings.get("evm_version"):
        _set("evm_version", settings["evm_version"], quoted=True)
    if settings.get("via_ir") is not None:
        _set("via_ir", "true" if settings["via_ir"] else "false")
    if settings.get("compiler_version"):
        m = re.search(r"v?(\d+\.\d+\.\d+)", settings["compiler_version"])
        if m:
            _set("solc", m.group(1), quoted=True)

    toml.write_text(content)


def build_repo(repo: str, commit: str, settings: dict, verbose: bool = False
               ) -> tuple[Optional[Path], bool, bool]:
    """Build repo. Returns (repo_dir, success, is_temp)."""
    local = get_local_repo(repo)
    if local:
        cur = subprocess.run(["git", "rev-parse", "HEAD"],
                             cwd=local, capture_output=True, text=True).stdout.strip()
        if cur == commit:
            if verbose:
                print(f"  Using local: {local}")
            toml = local / "foundry.toml"
            backup = toml.read_text() if toml.exists() else None
            try:
                patch_foundry_config(local, settings)
                r = subprocess.run(["forge", "build", "--force"],
                                   cwd=local, capture_output=True, text=True, timeout=600)
                if r.returncode == 0:
                    return local, True, False
                if verbose:
                    print(f"  Local build failed, cloning fresh...")
            finally:
                if backup is not None:
                    toml.write_text(backup)

    if verbose:
        print(f"  Cloning {repo}@{commit[:12]}...")
    tmp = tempfile.mkdtemp()
    repo_dir = Path(tmp) / "repo"
    repo_dir.mkdir()
    url = f"https://github.com/{repo}.git"

    subprocess.run(["git", "init", "-q"], cwd=repo_dir, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", url], cwd=repo_dir, capture_output=True)
    r = subprocess.run(["git", "fetch", "--depth", "1", "origin", commit],
                       cwd=repo_dir, capture_output=True, text=True)
    if r.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        return None, False, False
    subprocess.run(["git", "checkout", "FETCH_HEAD"], cwd=repo_dir, capture_output=True)

    if (repo_dir / ".gitmodules").exists():
        if verbose:
            print(f"  Initializing submodules...")
        init_submodules(repo_dir)

    patch_foundry_config(repo_dir, settings)

    if verbose:
        print(f"  Building...")
    r = subprocess.run(["forge", "build", "--force"],
                       cwd=repo_dir, capture_output=True, text=True, timeout=600)
    return repo_dir, r.returncode == 0, True


# ---------------------------------------------------------------------------
# Artifact extraction
# ---------------------------------------------------------------------------
def find_artifact(repo_dir: Path, artifact_name: str, use_runtime: bool = False
                  ) -> Optional[str]:
    """Find compiled bytecode in Foundry out/ directory."""
    out = repo_dir / "out"
    if not out.exists():
        return None
    key = "deployedBytecode" if use_runtime else "bytecode"
    target = artifact_name.lower()
    for f in out.rglob("*.json"):
        try:
            with open(f) as fh:
                data = json.load(fh)
            name = data.get("contractName", "")
            if name.lower() == target or f.stem.lower() == target:
                bc = data.get(key, {}).get("object")
                if bc and bc != "0x":
                    return bc
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Bytecode comparison
# ---------------------------------------------------------------------------
def strip_metadata(bc: str) -> str:
    """Remove CBOR-encoded compiler metadata from bytecode."""
    if bc.startswith("0x"):
        bc = bc[2:]
    marker = "a264697066735822"
    end = "0033"
    while marker in bc:
        idx = bc.find(marker)
        end_idx = bc.find(end, idx)
        if end_idx != -1:
            bc = bc[:idx] + bc[end_idx + len(end):]
        else:
            bc = bc[:idx]
            break
    return bc


def _match_ignoring_immutables(deployed: str, compiled: str, details: dict) -> bool:
    """Check if two same-length bytecodes differ only at immutable variable slots.

    Immutable variables are zero in compiled output and filled with actual values
    at deploy time. Every diff region in the compiled bytecode must be all zeros.
    """
    immutable_count = 0
    i = 0
    n = len(deployed)
    while i < n:
        if deployed[i] != compiled[i]:
            start = i
            while i < n and deployed[i] != compiled[i]:
                i += 1
            if not all(ch == "0" for ch in compiled[start:i]):
                return False
            immutable_count += 1
        else:
            i += 1
    if immutable_count > 0:
        details["immutable_vars"] = immutable_count
        return True
    return False


def compare_bytecodes(deployed: str, compiled: str) -> tuple[bool, dict]:
    """Compare bytecodes, accounting for constructor args, CREATE2 prefixes,
    and immutable variables. Returns (match, details_dict).
    """
    details: dict = {}
    d = strip_metadata(deployed)
    c = strip_metadata(compiled)
    details["deployed_size"] = len(d) // 2
    details["compiled_size"] = len(c) // 2

    if d == c:
        return True, details

    # Constructor args: deployed = compiled + ABI-encoded args (32-byte aligned)
    if len(d) > len(c) and (len(d) - len(c)) % 64 == 0 and d[: len(c)] == c:
        details["constructor_args_size"] = (len(d) - len(c)) // 2
        return True, details

    # CREATE2: deployed may have a prefix before the compiled code
    if len(d) > len(c):
        prefix_start = c[:40] if len(c) >= 40 else c
        idx = d.find(prefix_start)
        if idx > 0:
            trimmed = d[idx:]
            if trimmed == c:
                details["create2_prefix_size"] = idx // 2
                return True, details
            extra = len(trimmed) - len(c)
            if extra > 0 and extra % 64 == 0 and trimmed[: len(c)] == c:
                details["create2_prefix_size"] = idx // 2
                details["constructor_args_size"] = extra // 2
                return True, details

    # Immutable variables: same length, compiled has zero-filled slots
    if len(d) == len(c):
        if _match_ignoring_immutables(d, c, details):
            return True, details

    # Mismatch -- record first diff for debugging
    for i, (a, b) in enumerate(zip(d, c)):
        if a != b:
            details["first_diff_position"] = i
            details["first_diff_deployed"] = d[max(0, i - 20): i + 20]
            details["first_diff_compiled"] = c[max(0, i - 20): i + 20]
            break

    return False, details


# ---------------------------------------------------------------------------
# Core verification
# ---------------------------------------------------------------------------
def verify_contracts(
    contracts: list[tuple[str, str]],
    mapping: dict,
    verbose: bool = False,
    skip_unmapped: bool = False,
) -> tuple[list[dict], list[dict], list[str]]:
    """Verify contracts. Groups by (repo, commit, settings), builds once per group."""
    verified: list[dict] = []
    failed: list[dict] = []
    skipped: list[str] = []

    # Group by build key
    groups: dict[tuple, list[tuple[str, str, dict]]] = {}
    for name, address in contracts:
        info = mapping.get(name)
        if not info:
            if skip_unmapped:
                skipped.append(name)
            else:
                failed.append({"name": name, "address": address,
                               "verified": False, "error": "No mapping"})
            continue

        key = (
            info.get("repo", ""),
            info.get("commit", ""),
            info.get("compiler_version"),
            info.get("optimization_enabled"),
            info.get("optimization_runs"),
            info.get("evm_version"),
            info.get("via_ir"),
        )
        groups.setdefault(key, []).append((name, address, info))

    if skipped:
        print(f"\n  Skipping {len(skipped)} unmapped: {', '.join(skipped)}\n")

    total_builds = len(groups)
    for build_idx, (build_key, group) in enumerate(groups.items(), 1):
        repo = group[0][2]["repo"]
        commit = group[0][2]["commit"]
        settings = {k: group[0][2].get(k) for k in
                    ("compiler_version", "optimization_enabled",
                     "optimization_runs", "evm_version", "via_ir")}

        print(f"\n{'#' * 70}")
        print(f"# [{build_idx}/{total_builds}] {repo}@{commit[:12]} ({len(group)} contracts)")
        print(f"{'#' * 70}")

        repo_dir, build_ok, is_temp = None, False, False
        try:
            repo_dir, build_ok, is_temp = build_repo(repo, commit, settings, verbose)
        except Exception as e:
            print(f"  Build error: {e}")

        if not build_ok:
            for name, address, _ in group:
                failed.append({"name": name, "address": address,
                               "verified": False, "error": f"Build failed: {repo}"})
            continue

        for ci, (name, address, info) in enumerate(group, 1):
            print(f"  [{ci}/{len(group)}] {name}...", end=" ", flush=True)
            result = _verify_one(name, address, info, repo_dir, verbose)
            if result["verified"]:
                verified.append(result)
                print("VERIFIED")
            else:
                failed.append(result)
                print(f"FAILED: {result['error']}")

        if repo_dir and is_temp:
            shutil.rmtree(repo_dir.parent, ignore_errors=True)

    return verified, failed, skipped


def _verify_one(name: str, address: str, info: dict, repo_dir: Path,
                verbose: bool = False) -> dict:
    """Verify a single contract using pre-built repo artifacts."""
    result: dict = {
        "name": name,
        "address": address.lower(),
        "verified": False,
        "error": None,
        "details": {
            "repo": info.get("repo"),
            "commit": info.get("commit"),
            "compiler_version": info.get("compiler_version"),
            "optimization_runs": info.get("optimization_runs"),
        },
    }
    artifact = info.get("artifact_name", name)

    # Fetch deployed bytecode
    deployed, bc_type = fetch_bytecode(address, verbose)
    if not deployed:
        result["error"] = "Could not fetch deployed bytecode"
        return result
    result["details"]["bytecode_type"] = bc_type
    use_runtime = bc_type == "runtime"

    # Find compiled artifact
    compiled = find_artifact(repo_dir, artifact, use_runtime)
    if not compiled:
        file_path = info.get("file_path")
        if file_path:
            if verbose:
                print(f"\n    Compiling {file_path}...", end=" ", flush=True)
            subprocess.run(["forge", "build", file_path, "--force"],
                           cwd=repo_dir, capture_output=True, text=True, timeout=600)
            compiled = find_artifact(repo_dir, artifact, use_runtime)
    if not compiled:
        result["error"] = f"Artifact not found: {artifact}"
        return result

    # Compare
    match, details = compare_bytecodes(deployed, compiled)
    result["details"].update(details)
    result["verified"] = match
    if not match and not result["error"]:
        result["error"] = "Bytecode mismatch"
    return result


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def print_summary(verified: list, failed: list, skipped: list):
    total = len(verified) + len(failed) + len(skipped)
    print(f"\n{'=' * 60}")
    print(f"VERIFICATION SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Verified: {len(verified)}")
    print(f"  Failed:   {len(failed)}")
    if skipped:
        print(f"  Skipped:  {len(skipped)}")
    print(f"  Total:    {total}")
    if failed:
        print(f"\nFailed contracts:")
        for r in failed:
            print(f"  - {r['name']}: {r['error']}")


def save_report(verified: list, failed: list, path: str):
    report = {
        "verified": verified,
        "failed": failed,
        "summary": {
            "total": len(verified) + len(failed),
            "verified": len(verified),
            "failed": len(failed),
        },
    }
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to: {path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Verify HyperEVM contract deployments")
    parser.add_argument("--all", action="store_true", help="Verify all contracts")
    parser.add_argument("--address", type=str, help="Single contract address")
    parser.add_argument("--name", type=str, help="Contract name (with --address)")
    parser.add_argument("--file", type=str, help="Address JSON file")
    parser.add_argument("--changed-file", type=str,
                        help="Changed-addresses JSON ([{name, address}])")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--output", "-o", type=str, help="Output JSON report path")
    parser.add_argument("--skip-unmapped", action="store_true",
                        help="Skip contracts without a mapping entry")

    args = parser.parse_args()
    mapping = load_mapping()

    if args.all:
        contracts = load_all_contracts()
    elif args.file:
        contracts = load_address_file(Path(args.file))
    elif args.changed_file:
        contracts = load_changed_file(Path(args.changed_file))
    elif args.address:
        if not args.name:
            parser.error("--name is required with --address")
        contracts = [(args.name, args.address)]
    else:
        parser.print_help()
        sys.exit(1)

    if not contracts:
        print("No contracts to verify")
        sys.exit(0)

    verified, failed, skipped = verify_contracts(
        contracts, mapping,
        verbose=args.verbose,
        skip_unmapped=args.skip_unmapped,
    )
    print_summary(verified, failed, skipped)

    if args.output:
        save_report(verified, failed, args.output)

    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
