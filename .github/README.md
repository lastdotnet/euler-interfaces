# Contract Verification CI/CD

## Overview

When a PR to `master` modifies files in `addresses/**/*.json`, the CI workflow:

1. Diffs the PR to extract new/changed contract addresses
2. Looks up each contract in `contract-mapping.json` (maps address-file keys to source repos)
3. Groups contracts by (repo, commit, compiler settings) and builds each repo once with Foundry
4. Compares deployed bytecode against compiled artifacts (stripping CBOR metadata)
5. Posts results as a PR comment; fails the check if any contract doesn't match

## Scripts

### `generate-contract-mapping.py`

Builds `contract-mapping.json` by querying Hyperscan for each deployed address and resolving the source repo + commit from `.gitmodules`.

```bash
python3 scripts/generate-contract-mapping.py
```

Run this when submodule commits change or new contracts are deployed.

### `verify-contracts.py`

Verifies contracts against their source code.

```bash
# Verify all contracts
python3 scripts/verify-contracts.py --all --skip-unmapped --verbose

# Verify single contract
python3 scripts/verify-contracts.py --address 0x... --name evc --verbose

# Verify from address file
python3 scripts/verify-contracts.py --file addresses/999/CoreAddresses.json

# CI mode: verify changed contracts
python3 scripts/verify-contracts.py --changed-file changed.json --output report.json
```

## Full Reproduce

```bash
git submodule update --init --recursive
pip install requests
python3 scripts/generate-contract-mapping.py
python3 scripts/verify-contracts.py --all --skip-unmapped --verbose
```
