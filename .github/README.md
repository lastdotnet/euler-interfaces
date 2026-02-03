# Contract Verification CI/CD

This directory contains GitHub Actions workflows for automated contract verification.

## Workflows

### `verify-contracts.yml`

Automatically runs on pull requests to `main` when contract address files are modified.

**Triggers:**
- Changes to `addresses/**/*.json`
- Changes to `EulerChains.json`

**What it does:**
1. Detects new or modified contract addresses in the PR using git diff
2. Verifies each contract on Hyperscan.com
3. Compiles contracts from source and compares bytecode
4. Posts results as a PR comment
5. Fails the check if any contract is not verified or doesn't match

**Requirements:**
- All contract addresses must be verified on Hyperscan before merging
- Verified contracts must match their source code exactly (excluding compiler metadata)

## Scripts

### `verify-contracts.py`

Verifies contracts against Hyperscan and their source repositories.

**Usage modes:**

```bash
# Verify all contracts
python3 scripts/verify-contracts.py --all --output report.json

# Verify single contract
python3 scripts/verify-contracts.py \
  --address 0x... \
  --name EthereumVaultConnector \
  --verbose

# Verify from address file
python3 scripts/verify-contracts.py \
  --file addresses/999/CoreAddresses.json \
  --output report.json

# Verify changed contracts (CI mode)
python3 scripts/verify-contracts.py \
  --changed-file changed.json \
  --output report.json \
  --verbose
```

## Local Testing

Test the workflow locally before pushing:

```bash
# 1. Make changes to address files
vim addresses/999/CoreAddresses.json

# 2. Extract changed addresses and verify
git diff origin/main..HEAD -- 'addresses/**/*.json' | \
  grep '^+' | grep '"0x' | \
  python3 -c "
import sys, re, json
addresses = []
for line in sys.stdin:
    line = line[1:].strip().rstrip(',')
    match = re.match(r'\"([^\"]+)\"\s*:\s*\"(0x[a-fA-F0-9]{40})\"', line)
    if match:
        name, address = match.groups()
        if address.lower() != '0x0000000000000000000000000000000000000000':
            addresses.append({'name': name, 'address': address.lower()})
if addresses:
    with open('changed-addresses.json', 'w') as f:
        json.dump(addresses, f, indent=2)
" && \
python3 scripts/verify-contracts.py \
  --changed-file changed-addresses.json \
  --verbose
```

## Verification Process

For each contract, the workflow:

1. **Fetches deployment info** from Hyperscan API
   - Checks if contract is verified on-chain
   - Gets compiler version and settings

2. **Clones source repository** based on mapping in `verify-contracts.py`
   - Checks out specific commit/tag
   - Applies compiler settings from deployment

3. **Compiles from source** using Foundry
   - Matches compiler version
   - Matches optimization settings

4. **Compares bytecode**
   - Strips compiler metadata (CBOR)
   - Compares remaining bytecode exactly

5. **Reports results**
   - Posts to PR as comment
   - Fails CI if verification fails

## Adding New Contracts

When adding new contracts to source mappings:

1. Update `SOURCE_REPOS` in `verify-contracts.py`:

```python
SOURCE_REPOS = {
    "YourContract": {
        "repo": "org/repo-name",
        "commit": "abc123"  # or "tag": "v1.0.0"
    }
}
```

2. Ensure contract is verified on Hyperscan first
3. Create PR with address changes
4. CI will automatically verify

## Troubleshooting

**"Contract is not verified on Hyperscan"**
- Verify the contract manually at https://hyperscan.com

**"No source repository mapping found"**
- Add the contract to `SOURCE_REPOS` in `verify-contracts.py`

**"Bytecode mismatch"**
- Check compiler version matches deployment
- Check optimizer runs match deployment
- Ensure correct commit/tag is specified
- Verify no manual patches were applied during deployment
