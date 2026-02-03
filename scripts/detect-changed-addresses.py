#!/usr/bin/env python3
"""
Detect Changed Contract Addresses

Compares contract addresses between two git refs (typically base and head of a PR)
to identify new or modified contract addresses.

Usage:
    python3 scripts/detect-changed-addresses.py --base origin/main --head HEAD --output changed.json
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple


REPO_ROOT = Path(__file__).parent.parent
ADDRESS_FILES = [
    "addresses/999/CoreAddresses.json",
    "addresses/999/LensAddresses.json",
    "addresses/999/PeripheryAddresses.json",
    "addresses/999/EulerSwapAddresses.json",
    "addresses/999/TokenAddresses.json",
    "addresses/999/BridgeAddresses.json",
    "addresses/999/GovernorAddresses.json",
    "addresses/999/MultisigAddresses.json",
]


def run_git_command(args: List[str]) -> str:
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Git command failed: {e.stderr}", file=sys.stderr)
        raise


def get_file_content_at_ref(filepath: str, ref: str) -> Dict[str, str]:
    try:
        content = run_git_command(["show", f"{ref}:{filepath}"])
        return json.loads(content)
    except subprocess.CalledProcessError:
        return {}
    except json.JSONDecodeError:
        print(f"Warning: Invalid JSON in {filepath} at {ref}", file=sys.stderr)
        return {}


def load_addresses_at_ref(ref: str) -> Dict[str, Dict[str, str]]:
    all_addresses = {}
    
    for filepath in ADDRESS_FILES:
        addresses = get_file_content_at_ref(filepath, ref)
        
        filtered_addresses = {
            k: v for k, v in addresses.items()
            if v and v != "0x0000000000000000000000000000000000000000"
        }
        
        if filtered_addresses:
            all_addresses[filepath] = filtered_addresses
    
    return all_addresses


def flatten_addresses(addresses_by_file: Dict[str, Dict[str, str]]) -> Dict[Tuple[str, str], str]:
    flattened = {}
    for filepath, addresses in addresses_by_file.items():
        for name, address in addresses.items():
            flattened[(filepath, name)] = address.lower()
    return flattened


def detect_changes(base_ref: str, head_ref: str) -> Dict[str, List[Dict[str, str]]]:
    print(f"Comparing {base_ref} -> {head_ref}", file=sys.stderr)
    
    base_addresses_by_file = load_addresses_at_ref(base_ref)
    head_addresses_by_file = load_addresses_at_ref(head_ref)
    
    base_flat = flatten_addresses(base_addresses_by_file)
    head_flat = flatten_addresses(head_addresses_by_file)
    
    base_keys = set(base_flat.keys())
    head_keys = set(head_flat.keys())
    
    new_contracts = []
    modified_contracts = []
    removed_contracts = []
    
    for key in head_keys - base_keys:
        filepath, name = key
        new_contracts.append({
            "file": filepath,
            "name": name,
            "address": head_flat[key],
            "change_type": "added"
        })
    
    for key in base_keys & head_keys:
        if base_flat[key] != head_flat[key]:
            filepath, name = key
            modified_contracts.append({
                "file": filepath,
                "name": name,
                "address": head_flat[key],
                "old_address": base_flat[key],
                "change_type": "modified"
            })
    
    for key in base_keys - head_keys:
        filepath, name = key
        removed_contracts.append({
            "file": filepath,
            "name": name,
            "address": base_flat[key],
            "change_type": "removed"
        })
    
    return {
        "new": new_contracts,
        "modified": modified_contracts,
        "removed": removed_contracts
    }


def print_changes(changes: Dict[str, List[Dict[str, str]]]):
    total = sum(len(v) for v in changes.values())
    
    if total == 0:
        print("No address changes detected", file=sys.stderr)
        return
    
    print(f"\nDetected {total} address change(s):", file=sys.stderr)
    
    if changes["new"]:
        print(f"\n✨ New addresses ({len(changes['new'])}):", file=sys.stderr)
        for item in changes["new"]:
            print(f"  + {item['name']}: {item['address']}", file=sys.stderr)
    
    if changes["modified"]:
        print(f"\n🔄 Modified addresses ({len(changes['modified'])}):", file=sys.stderr)
        for item in changes["modified"]:
            print(f"  ~ {item['name']}:", file=sys.stderr)
            print(f"      {item['old_address']} -> {item['address']}", file=sys.stderr)
    
    if changes["removed"]:
        print(f"\n❌ Removed addresses ({len(changes['removed'])}):", file=sys.stderr)
        for item in changes["removed"]:
            print(f"  - {item['name']}: {item['address']}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description='Detect changed contract addresses between git refs'
    )
    parser.add_argument('--base', required=True, help='Base git ref (e.g., origin/main)')
    parser.add_argument('--head', required=True, help='Head git ref (e.g., HEAD)')
    parser.add_argument('--output', '-o', required=True, help='Output JSON file')
    
    args = parser.parse_args()
    
    try:
        changes = detect_changes(args.base, args.head)
        
        print_changes(changes)
        
        contracts_to_verify = changes["new"] + changes["modified"]
        
        if not contracts_to_verify:
            print(f"\nNo contracts to verify. Not creating output file.", file=sys.stderr)
            sys.exit(0)
        
        with open(args.output, 'w') as f:
            json.dump(contracts_to_verify, f, indent=2)
        
        print(f"\n✅ Wrote {len(contracts_to_verify)} contract(s) to {args.output}", file=sys.stderr)
        sys.exit(0)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
