# Euler HyperEVM Contract Verification Report

| | Count |
|---|---|
| Verified | 45 |
| Known mismatches | 2 |
| Skipped (null address) | 14 |
| Skipped (EOA/multisig) | 5 |
| Skipped (no mapping) | 1 |
| **Total addresses** | **67** |

- **Chain:** HyperEVM (Chain ID 999)
- **RPC:** `https://rpc.hyperliquid.xyz/evm`
- **Explorer:** [Hyperscan](https://www.hyperscan.com) | [Purrsec](https://purrsec.com)
- **Verification date:** 2026-02-05

## Submodule State

| Submodule | Commit |
|---|---|
| [lib/ethereum-vault-connector](https://github.com/euler-xyz/ethereum-vault-connector/tree/34bb788288a0eb0fbba06bc370cb8ca3dd42614e) | `34bb788288a0` |
| [lib/euler-earn](https://github.com/euler-xyz/euler-earn/tree/b2fd6e699ee20bcfe7459f375b3cee5d2fa53345) | `b2fd6e699ee2` |
| [lib/euler-price-oracle](https://github.com/euler-xyz/euler-price-oracle/tree/ffc3cb82615fc7d003a7f431175bd1eaf0bf41c5) | `ffc3cb82615f` |
| [lib/euler-swap](https://github.com/euler-xyz/euler-swap/tree/dd936d2baaacb9064cf919b1fb45ecaa002d2751) | `dd936d2baaac` |
| [lib/euler-vault-kit](https://github.com/euler-xyz/euler-vault-kit/tree/5b98b42048ba11ae82fb62dfec06d1010c8e41e6) | `5b98b42048ba` |
| [lib/evk-periphery](https://github.com/euler-xyz/evk-periphery/tree/89163cad3cbf562101ade9818ff5e28b1975624e) | `89163cad3cbf` |

## Verified Contracts

| Name | Address | Repo | Compiler | Runs |
|---|---|---|---|---|
| eulOFTAdapter | [`0x976666...98C3d1`](https://www.hyperscan.com/address/0x976666e0ae74A8A4059cF1acf706891aDE98C3d1) | evk-periphery | v0.8.24 | 20000 |
| balanceTracker | [`0x05d14f...9b9cD2`](https://www.hyperscan.com/address/0x05d14f4eDFA7Cbfb90711C2EC5505bcbd49b9cD2) | evk-periphery | v0.8.24 | 20000 |
| eVaultFactory | [`0xcF5552...59273A`](https://www.hyperscan.com/address/0xcF5552580fD364cdBBFcB5Ae345f75674c59273A) | euler-vault-kit | v0.8.24 | 20000 |
| eVaultImplementation | [`0x05de07...d5EBDF`](https://www.hyperscan.com/address/0x05de079A28386135E048369cdf0Bc4D326d5EBDF) | euler-vault-kit | v0.8.24 | 20000 |
| eulerEarnFactory | [`0x587DD8...bBc00E`](https://www.hyperscan.com/address/0x587DD8285c01526769aB4803e4F02433ddbBc00E) | euler-earn | v0.8.26 | 200 |
| evc | [`0xceAA7c...613db4`](https://www.hyperscan.com/address/0xceAA7cdCD7dDBee8601127a9Abb17A974d613db4) | ethereum-vault-connector | v0.8.24 | 20000 |
| protocolConfig | [`0x43144f...A51128`](https://www.hyperscan.com/address/0x43144f09896F8759DE2ec6D777391B9F05A51128) | euler-vault-kit | v0.8.24 | 20000 |
| sequenceRegistry | [`0x47618E...719994`](https://www.hyperscan.com/address/0x47618E4CBDcFBf5f21D6594A7e3a4f4683719994) | euler-vault-kit | v0.8.24 | 20000 |
| eulerSwapV2Factory | [`0xFbF2a4...9D29Eb`](https://www.hyperscan.com/address/0xFbF2a49CB0cc50F4ccd4eAc826eF1A76D99D29Eb) | euler-swap | v0.8.27 | 2500 |
| eulerSwapV2Implementation | [`0xC00F0B...42dB84`](https://www.hyperscan.com/address/0xC00F0B7d7B4F7cA3d3f79f3892069f41C142dB84) | euler-swap | v0.8.27 | 2500 |
| eulerSwapV2Periphery | [`0x61aFC3...cE48B1`](https://www.hyperscan.com/address/0x61aFC386b47a11F8721b67Eb1607cFBd9ccE48B1) | euler-swap | v0.8.27 | 2500 |
| eulerSwapV2ProtocolFeeConfig | [`0x434b10...AD4F30`](https://www.hyperscan.com/address/0x434b1072d96ea24967CDe289D3d4d81d2BAD4F30) | euler-swap | v0.8.27 | 2500 |
| eulerSwapV2Registry | [`0x7E1Efb...0c14Fb`](https://www.hyperscan.com/address/0x7E1Efb6A2009A1FDaDee1c5d6615260AD70c14Fb) | euler-swap | v0.8.27 | 2500 |
| accessControlEmergencyGovernor | [`0xd27c32...54ef14`](https://www.hyperscan.com/address/0xd27c32372cA1353c96915a05b558489aa054ef14) | evk-periphery | v0.8.24 | 20000 |
| accessControlEmergencyGovernorAdminTimelockController | [`0x3049E7...5D3c74`](https://www.hyperscan.com/address/0x3049E75f9B41F2147E080c4249d6A0E8765D3c74) | evk-periphery | v0.8.24 | 20000 |
| accessControlEmergencyGovernorWildcardTimelockController | [`0xfa4BD0...D7a592`](https://www.hyperscan.com/address/0xfa4BD0ECb529DD4cC0dE0ec42c10d26603D7a592) | evk-periphery | v0.8.24 | 20000 |
| eVaultFactoryGovernor | [`0x14e280...5B0e45`](https://www.hyperscan.com/address/0x14e280513d1D9a21493e240a29CB9Eb08E5B0e45) | evk-periphery | v0.8.24 | 20000 |
| eVaultFactoryTimelockController | [`0xc05E33...e31901`](https://www.hyperscan.com/address/0xc05E33692a34A3A84DE3094417c65cD3CBe31901) | evk-periphery | v0.8.24 | 20000 |
| accountLens | [`0x66EefD...C42A42`](https://www.hyperscan.com/address/0x66EefD479DD08B7f8B447A703bf76C4b96C42A42) | evk-periphery | v0.8.24 | 20000 |
| eulerEarnVaultLens | [`0x782A21...A71233`](https://www.hyperscan.com/address/0x782A21Ab6eEa4919Fd2F1B6e94c2BE3349A71233) | evk-periphery | v0.8.24 | 20000 |
| irmLens | [`0x2E79A4...ff6D6C`](https://www.hyperscan.com/address/0x2E79A4A15EEAd542cFe663d081D108D9cfff6D6C) | evk-periphery | v0.8.24 | 20000 |
| oracleLens | [`0xb65A75...C1a8C5`](https://www.hyperscan.com/address/0xb65A755dBE9C493dcC3EEC3aaDeb211888C1a8C5) | evk-periphery | v0.8.24 | 20000 |
| utilsLens | [`0xB3EC37...3b67C6`](https://www.hyperscan.com/address/0xB3EC37ebA3Ea95cb4A6A34883485b9e8fC3b67C6) | evk-periphery | v0.8.24 | 20000 |
| adaptiveCurveIRMFactory | [`0xF62bFa...Dc31c9`](https://www.hyperscan.com/address/0xF62bFaA502E4dC83260e34aCF2B4875FdBDc31c9) | evk-periphery | v0.8.24 | 20000 |
| capRiskStewardFactory | [`0x459Fe7...59b089`](https://www.hyperscan.com/address/0x459Fe76a4fc9406feBe3AcFdb42955197059b089) | evk-periphery | v0.8.24 | 20000 |
| edgeFactory | [`0x724904...f2628e`](https://www.hyperscan.com/address/0x724904bc492959Ee175f5664d117B78DCBf2628e) | evk-periphery | v0.8.24 | 20000 |
| edgeFactoryPerspective | [`0xd15E7c...dbc033`](https://www.hyperscan.com/address/0xd15E7cD7875C77E4fA448F72476A93D409dbc033) | evk-periphery | v0.8.24 | 20000 |
| escrowedCollateralPerspective | [`0xaDaDF5...dfF6Fc`](https://www.hyperscan.com/address/0xaDaDF50246512dBA23889A1eC44611B191dfF6Fc) | evk-periphery | v0.8.24 | 20000 |
| eulerEarnFactoryPerspective | [`0x455Dcb...2c79ad`](https://www.hyperscan.com/address/0x455Dcb38c4969f35F698115544eA4108392c79ad) | evk-periphery | v0.8.24 | 20000 |
| eulerEarnGovernedPerspective | [`0x7b27dE...aeA807`](https://www.hyperscan.com/address/0x7b27dED9344D9c66FeAF58D151b52d1359aeA807) | evk-periphery | v0.8.24 | 20000 |
| eulerEarnPublicAllocator | [`0xc00ae6...706939`](https://www.hyperscan.com/address/0xc00ae658ce425Bb668A5Ed96c8ECa9C988706939) | euler-earn | v0.8.26 | 200 |
| eulerUngoverned0xPerspective | [`0xb2b6c3...65bb9E`](https://www.hyperscan.com/address/0xb2b6c3Fc174dC99dF693876740df4939f465bb9E) | evk-periphery | v0.8.24 | 20000 |
| eulerUngovernedNzxPerspective | [`0xdf8E8A...F0E633`](https://www.hyperscan.com/address/0xdf8E8Afc43AF8F2Be5CFDde0f044454DF4F0E633) | evk-periphery | v0.8.24 | 20000 |
| evkFactoryPerspective | [`0x7bd1DA...2480a3`](https://www.hyperscan.com/address/0x7bd1DADB012651606cE70210c9c4d4c94e2480a3) | evk-periphery | v0.8.24 | 20000 |
| externalVaultRegistry | [`0xe09af0...397FEE`](https://www.hyperscan.com/address/0xe09af00Dad8f1d2F056f08Ea1059aa6cA6397FEE) | evk-periphery | v0.8.24 | 20000 |
| governedPerspective | [`0x4936Cd...7a6b57`](https://www.hyperscan.com/address/0x4936Cd82936b6862fDD66CC8c36e1828127a6b57) | evk-periphery | v0.8.24 | 20000 |
| governorAccessControlEmergencyFactory | [`0xaD9cc6...5e74F3`](https://www.hyperscan.com/address/0xaD9cc6ECf49376de4Ea10494Cb519a848e5e74F3) | evk-periphery | v0.8.24 | 20000 |
| irmRegistry | [`0x52930D...84A49d`](https://www.hyperscan.com/address/0x52930DC1b386348E9be3C9260659Dd910384A49d) | evk-periphery | v0.8.24 | 20000 |
| kinkIRMFactory | [`0xc12540...641bf0`](https://www.hyperscan.com/address/0xc1254039763498485a0BC11eb51437A312641bf0) | evk-periphery | v0.8.24 | 20000 |
| oracleAdapterRegistry | [`0x66390e...AD02E7`](https://www.hyperscan.com/address/0x66390e34511DA5DbFeD572Cc5B1337Fe57AD02E7) | evk-periphery | v0.8.24 | 20000 |
| oracleRouterFactory | [`0x1CefA5...A89f7e`](https://www.hyperscan.com/address/0x1CefA54ebBCb6c9Aa7347196B03364aFe9A89f7e) | evk-periphery | v0.8.24 | 20000 |
| swapper | [`0x1dAbE4...96206e`](https://www.hyperscan.com/address/0x1dAbE49020104803084F67C057579a30b396206e) | evk-periphery | v0.8.24 | 20000 |
| termsOfUseSigner | [`0x8C80Fb...d38f02`](https://www.hyperscan.com/address/0x8C80Fb30199d1dF899337183F3d45B333Ed38f02) | evk-periphery | v0.8.24 | 20000 |
| EUL | [`0x3A41f4...aFf711`](https://www.hyperscan.com/address/0x3A41f426E55ECdE4BC734fA79ccE991b94aFf711) | evk-periphery | v0.8.24 | 20000 |
| rEUL | [`0x14DCA6...b6122b`](https://www.hyperscan.com/address/0x14DCA6543Ef03b932cBD801FBfd70e42a9b6122b) | evk-periphery | v0.8.24 | 20000 |

## Known Mismatches

These contracts were deployed from older commits of `evk-periphery`. The source has since been
updated in the submodule. The deployed bytecode does not match the current source.

### vaultLens

- **Address:** [`0x0eaDDE9EfCf1540dcA8f94e813E12db55f8405a8`](https://www.hyperscan.com/address/0x0eaDDE9EfCf1540dcA8f94e813E12db55f8405a8)
- **Repo:** `euler-xyz/evk-periphery`
- **Reason:** Deployed from evk-periphery@a498db29. Submodule at 89163cad includes post-deployment change to src/Lens/Utils.sol (commit e59e1ef6, katana deployment). 36-byte code diff.

### swapVerifier

- **Address:** [`0x02632F49E00a996DB4e2cC114D301542e48C0641`](https://www.hyperscan.com/address/0x02632F49E00a996DB4e2cC114D301542e48C0641)
- **Repo:** `euler-xyz/evk-periphery`
- **Reason:** Deployed at block 1982322 from early version of src/Swaps/SwapVerifier.sol (2520 chars). Current source is 2897 chars. Contract predates current submodule by many commits.

## Skipped

### Null Addresses

| Name | Category |
|---|---|
| eusdOFTAdapter | Bridge |
| seusdOFTAdapter | Bridge |
| eulerSwapV1Factory | EulerSwap |
| eulerSwapV1Implementation | EulerSwap |
| eulerSwapV1Periphery | EulerSwap |
| capRiskSteward | Governor |
| eUSDAdminTimelockController | Governor |
| feeCollector | Periphery |
| feeFlowController | Periphery |
| feeFlowControllerUtil | Periphery |
| fixedCyclicalBinaryIRMFactory | Periphery |
| kinkyIRMFactory | Periphery |
| eUSD | Token |
| seUSD | Token |

### EOA / Multisig

| Name | Address |
|---|---|
| DAO | [`0x48d727...12B9D7`](https://www.hyperscan.com/address/0x48d727Cb58C9D52881C00A47db355457B712B9D7) |
| labs | [`0x6b6457...8Cb117`](https://www.hyperscan.com/address/0x6b6457b7E87958819878982B153AC33fD98Cb117) |
| securityCouncil | [`0xdC40B5...908A09`](https://www.hyperscan.com/address/0xdC40B5C05C14Df79402c16e09fE544Ee77908A09) |
| securityPartnerA | [`0x70a398...a767A4`](https://www.hyperscan.com/address/0x70a398316993a53daB2eD132eaA00270bAa767A4) |
| securityPartnerB | [`0x0fB2e2...8A174c`](https://www.hyperscan.com/address/0x0fB2e23eb9cEb2814b3D4A21e6A91F2B418A174c) |

### No Source Mapping

| Name | Address | Reason |
|---|---|---|
| permit2 | [`0x000000...C78BA3`](https://www.hyperscan.com/address/0x000000000022D473030F116dDEE9F6B43aC78BA3) | Third-party (Uniswap) |

## Methodology

1. Source repos are pinned as git submodules at specific commits.
2. For each contract, compiler settings (solc version, optimizer runs, EVM version, via_ir) are fetched from Hyperscan's verified source data.
3. The submodule's `foundry.toml` is patched with the deployment compiler settings, then restored after building.
4. Creation bytecode is fetched from the deployment transaction via Hyperscan. If unavailable, runtime bytecode is fetched via Hyperscan or `eth_getCode` RPC.
5. CBOR metadata sections are stripped from both deployed and compiled bytecodes before comparison.
6. Constructor arguments (32-byte aligned trailing data) are identified and excluded from the code comparison.
7. A match means the executable code portion is byte-identical between the on-chain deployment and the locally compiled source.

## Reproduce

```bash
git submodule update --init --recursive
python3 scripts/generate-contract-mapping.py
python3 scripts/verify-contracts.py --all --batch --skip-unmapped --verbose
```
