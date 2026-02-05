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
REPO_ROOT = Path(__file__).parent.parent

DEFAULT_COMPILER_SETTINGS = {
    "compiler_version": "v0.8.24+commit.e11b9ed9",
    "optimization_enabled": True,
    "optimization_runs": 20000,
    "evm_version": "cancun",
}

# Known source repository mappings
SOURCE_REPOS = {
    # Euler Vault Kit (Hyperscan names)
    "EVault": {"repo": "lastdotnet/euler-vault-kit", "commit": "5b98b42048ba11ae82fb62dfec06d1010c8e41e6"},
    "GenericFactory": {"repo": "lastdotnet/euler-vault-kit", "commit": "5b98b42048ba11ae82fb62dfec06d1010c8e41e6"},
    "BalanceTracker": {"repo": "lastdotnet/euler-vault-kit", "commit": "5b98b42048ba11ae82fb62dfec06d1010c8e41e6"},
    "ProtocolConfig": {"repo": "lastdotnet/euler-vault-kit", "commit": "5b98b42048ba11ae82fb62dfec06d1010c8e41e6"},
    "SequenceRegistry": {"repo": "lastdotnet/euler-vault-kit", "commit": "5b98b42048ba11ae82fb62dfec06d1010c8e41e6"},
    # Euler Vault Kit (JSON file aliases)
    "eVaultFactory": {"repo": "lastdotnet/euler-vault-kit", "commit": "5b98b42048ba11ae82fb62dfec06d1010c8e41e6"},
    "eVaultImplementation": {"repo": "lastdotnet/euler-vault-kit", "commit": "5b98b42048ba11ae82fb62dfec06d1010c8e41e6"},
    "balanceTracker": {"repo": "lastdotnet/euler-vault-kit", "commit": "5b98b42048ba11ae82fb62dfec06d1010c8e41e6"},
    "protocolConfig": {"repo": "lastdotnet/euler-vault-kit", "commit": "5b98b42048ba11ae82fb62dfec06d1010c8e41e6"},
    "sequenceRegistry": {"repo": "lastdotnet/euler-vault-kit", "commit": "5b98b42048ba11ae82fb62dfec06d1010c8e41e6"},
    
    # Ethereum Vault Connector (euler-xyz only)
    "EthereumVaultConnector": {"repo": "euler-xyz/ethereum-vault-connector", "tag": "v1.0.1"},
    "evc": {"repo": "euler-xyz/ethereum-vault-connector", "tag": "v1.0.1"},
    
    # Permit2 (Uniswap)
    "Permit2": {"repo": "Uniswap/permit2", "tag": "0x000000000022D473030F116dDEE9F6B43aC78BA3"},
    "permit2": {"repo": "Uniswap/permit2", "tag": "0x000000000022D473030F116dDEE9F6B43aC78BA3"},
    
    # Euler Earn
    "EulerEarn": {
        "repo": "lastdotnet/euler-earn",
        "commit": "b2fd6e699ee20bcfe7459f375b3cee5d2fa53345",
        "submodules": ["lib/forge-std", "lib/openzeppelin-contracts", "lib/ethereum-vault-connector", "lib/euler-vault-kit"],
        "contract_path": "src/EulerEarn.sol"
    },
    "EulerEarnFactory": {
        "repo": "lastdotnet/euler-earn",
        "commit": "b2fd6e699ee20bcfe7459f375b3cee5d2fa53345",
        "submodules": ["lib/forge-std", "lib/openzeppelin-contracts", "lib/ethereum-vault-connector", "lib/euler-vault-kit"],
        "contract_path": "src/EulerEarnFactory.sol"
    },
    "EulerEarnVault": {
        "repo": "lastdotnet/euler-earn",
        "commit": "b2fd6e699ee20bcfe7459f375b3cee5d2fa53345",
        "submodules": ["lib/forge-std", "lib/openzeppelin-contracts", "lib/ethereum-vault-connector", "lib/euler-vault-kit"],
        "contract_path": "src/EulerEarn.sol"
    },
    "eulerEarnFactory": {
        "repo": "lastdotnet/euler-earn",
        "commit": "b2fd6e699ee20bcfe7459f375b3cee5d2fa53345",
        "submodules": ["lib/forge-std", "lib/openzeppelin-contracts", "lib/ethereum-vault-connector", "lib/euler-vault-kit"],
        "contract_path": "src/EulerEarnFactory.sol"
    },
    
    # Euler Swap
    "EulerSwapV2Factory": {"repo": "lastdotnet/euler-swap", "commit": "dd936d2baaacb9064cf919b1fb45ecaa002d2751"},
    "EulerSwapV2": {"repo": "lastdotnet/euler-swap", "commit": "dd936d2baaacb9064cf919b1fb45ecaa002d2751"},
    "EulerSwapV2Periphery": {"repo": "lastdotnet/euler-swap", "commit": "dd936d2baaacb9064cf919b1fb45ecaa002d2751"},
    "EulerSwapV2ProtocolFeeConfig": {"repo": "lastdotnet/euler-swap", "commit": "dd936d2baaacb9064cf919b1fb45ecaa002d2751"},
    "EulerSwapV2Registry": {"repo": "lastdotnet/euler-swap", "commit": "dd936d2baaacb9064cf919b1fb45ecaa002d2751"},
    "eulerSwapV2Factory": {"repo": "lastdotnet/euler-swap", "commit": "dd936d2baaacb9064cf919b1fb45ecaa002d2751"},
    "eulerSwapV2Implementation": {"repo": "lastdotnet/euler-swap", "commit": "dd936d2baaacb9064cf919b1fb45ecaa002d2751"},
    "eulerSwapV2Periphery": {"repo": "lastdotnet/euler-swap", "commit": "dd936d2baaacb9064cf919b1fb45ecaa002d2751"},
    "eulerSwapV2ProtocolFeeConfig": {"repo": "lastdotnet/euler-swap", "commit": "dd936d2baaacb9064cf919b1fb45ecaa002d2751"},
    "eulerSwapV2Registry": {"repo": "lastdotnet/euler-swap", "commit": "dd936d2baaacb9064cf919b1fb45ecaa002d2751"},
    
    # EVK Periphery - uses all-shallow to init all submodules + nested (non-recursive)
    "AccountLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "VaultLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "OracleLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "IRMLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "UtilsLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "EulerEarnVaultLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "accountLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "vaultLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "oracleLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "irmLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "utilsLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "eulerEarnVaultLens": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "Swapper": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "swapper": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "SwapVerifier": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "swapVerifier": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "TermsOfUseSigner": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "termsOfUseSigner": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "GovernedPerspective": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "governedPerspective": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "EscrowedCollateralPerspective": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "escrowedCollateralPerspective": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "EulerUngovernedPerspective": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "eulerUngoverned0xPerspective": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "eulerUngovernedNzxPerspective": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "EVKFactoryPerspective": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "evkFactoryPerspective": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "EulerEarnFactoryPerspective": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "eulerEarnFactoryPerspective": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "EulerEarnGovernedPerspective": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "eulerEarnGovernedPerspective": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "EdgeFactory": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "edgeFactory": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "EdgeFactoryPerspective": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "edgeFactoryPerspective": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "IRMRegistry": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "irmRegistry": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "ExternalVaultRegistry": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "externalVaultRegistry": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "KinkIRMFactory": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "kinkIRMFactory": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "AdaptiveCurveIRMFactory": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "adaptiveCurveIRMFactory": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "EulerIRMAdaptiveCurveFactory": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "CapRiskStewardFactory": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "capRiskStewardFactory": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "GovernorAccessControlEmergencyFactory": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "governorAccessControlEmergencyFactory": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    
    # Price Oracle
    "OracleRouterFactory": {"repo": "euler-xyz/euler-price-oracle", "commit": "ffc3cb82615fc7d003a7f431175bd1eaf0bf41c5", "submodules": "all-shallow"},
    "EulerRouterFactory": {"repo": "euler-xyz/euler-price-oracle", "commit": "ffc3cb82615fc7d003a7f431175bd1eaf0bf41c5", "submodules": "all-shallow"},
    "oracleRouterFactory": {"repo": "euler-xyz/euler-price-oracle", "commit": "ffc3cb82615fc7d003a7f431175bd1eaf0bf41c5", "submodules": "all-shallow"},
    "OracleAdapterRegistry": {"repo": "euler-xyz/euler-price-oracle", "commit": "ffc3cb82615fc7d003a7f431175bd1eaf0bf41c5", "submodules": "all-shallow"},
    "oracleAdapterRegistry": {"repo": "euler-xyz/euler-price-oracle", "commit": "ffc3cb82615fc7d003a7f431175bd1eaf0bf41c5", "submodules": "all-shallow"},
    
    # Fee Flow (euler-xyz only)
    "FeeFlowController": {"repo": "euler-xyz/fee-flow", "commit": "3bee858a1568d1313f37d615953f83391a897866"},
    
    # Reward Streams (deployed from evk-periphery which has reward-streams as submodule)
    "RewardStreams": {
        "repo": "euler-xyz/evk-periphery",
        "commit": "89163cad3cbf562101ade9818ff5e28b1975624e",
        "submodules": "all-shallow",
        "contract_path": "lib/reward-streams/src/BaseRewardStreams.sol"
    },
    "TrackingRewardStreams": {
        "repo": "euler-xyz/evk-periphery",
        "commit": "89163cad3cbf562101ade9818ff5e28b1975624e",
        "submodules": "all-shallow",
        "contract_path": "lib/reward-streams/src/TrackingRewardStreams.sol"
    },
    
    # Euler Earn extras
    "PublicAllocator": {
        "repo": "lastdotnet/euler-earn",
        "commit": "b2fd6e699ee20bcfe7459f375b3cee5d2fa53345",
        "submodules": ["lib/forge-std", "lib/openzeppelin-contracts", "lib/ethereum-vault-connector", "lib/euler-vault-kit"],
        "contract_path": "src/PublicAllocator.sol"
    },
    "eulerEarnPublicAllocator": {
        "repo": "lastdotnet/euler-earn",
        "commit": "b2fd6e699ee20bcfe7459f375b3cee5d2fa53345",
        "submodules": ["lib/forge-std", "lib/openzeppelin-contracts", "lib/ethereum-vault-connector", "lib/euler-vault-kit"],
        "contract_path": "src/PublicAllocator.sol"
    },
    
    # Governor contracts
    "GovernorAccessControlEmergency": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "accessControlEmergencyGovernor": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "FactoryGovernor": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "eVaultFactoryGovernor": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "TimelockController": {"repo": "OpenZeppelin/openzeppelin-contracts", "tag": "v5.0.0"},
    "accessControlEmergencyGovernorAdminTimelockController": {"repo": "OpenZeppelin/openzeppelin-contracts", "tag": "v5.0.0"},
    "accessControlEmergencyGovernorWildcardTimelockController": {"repo": "OpenZeppelin/openzeppelin-contracts", "tag": "v5.0.0"},
    "eVaultFactoryTimelockController": {"repo": "OpenZeppelin/openzeppelin-contracts", "tag": "v5.0.0"},
    
    # OFT Bridge
    "OFTAdapterUpgradeable": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
    "eulOFTAdapter": {"repo": "euler-xyz/evk-periphery", "commit": "89163cad3cbf562101ade9818ff5e28b1975624e", "submodules": "all-shallow"},
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
        """Fetch deployed bytecode - tries creation tx first, falls back to runtime bytecode"""
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
            
            self.log("No creation tx, fetching runtime bytecode...")
            url = f"{HYPERSCAN_API_BASE}/smart-contracts/{self.address}"
            response = requests.get(url, headers={'Accept': 'application/json'}, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            bytecode = data.get('deployed_bytecode')
            if bytecode:
                self.log(f"Fetched {len(bytecode)} chars of runtime bytecode")
                self.result['details']['bytecode_type'] = 'runtime'
                return bytecode
            
            self.result['error'] = "No bytecode found"
            return None
            
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
                    subprocess.run(clone_cmd, check=True, capture_output=True)
                elif 'commit' in source_info:
                    commit = source_info['commit']
                    repo_url = f"https://github.com/{source_info['repo']}.git"
                    
                    subprocess.run(["git", "init", "-q"], cwd=str(repo_dir.parent), capture_output=True)
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
                else:
                    clone_cmd = ["git", "clone", "--depth", "1", 
                                 f"https://github.com/{source_info['repo']}.git", str(repo_dir)]
                    subprocess.run(clone_cmd, check=True, capture_output=True)
                
                if (repo_dir / ".gitmodules").exists():
                    self.log("Initializing submodules...")
                    submodule_config = source_info.get('submodules')
                    if submodule_config == "all-shallow":
                        self._init_submodules_exact(repo_dir)
                        self._init_nested_submodules(repo_dir)
                    elif submodule_config:
                        for submodule in submodule_config:
                            subprocess.run(
                                ["git", "submodule", "update", "--init", "--recursive", "--depth", "1", submodule],
                                cwd=repo_dir, capture_output=True, timeout=120
                            )
                    else:
                        subprocess.run(
                            ["git", "submodule", "update", "--init", "--recursive", "--depth", "1"],
                            cwd=repo_dir, capture_output=True, timeout=300
                        )
                
                self._patch_foundry_config(repo_dir)
                
                self.log("Building with Foundry...")
                contract_path = source_info.get('contract_path')
                if contract_path:
                    build_cmd = ["forge", "build", contract_path, "--force"]
                else:
                    build_cmd = ["forge", "build", "--force"]
                result = subprocess.run(build_cmd, cwd=repo_dir, capture_output=True, text=True)
                
                if result.returncode != 0:
                    self.result['error'] = f"Forge build failed: {result.stderr}"
                    return None
                
                use_runtime = self.result['details'].get('bytecode_type') == 'runtime'
                bytecode = self._extract_bytecode_from_artifacts(repo_dir, use_runtime=use_runtime)
                if bytecode:
                    self.log(f"Compiled {len(bytecode)} chars of {'runtime' if use_runtime else 'creation'} bytecode")
                else:
                    self.result['error'] = f"Could not find contract bytecode in build artifacts"
                
                return bytecode
                
        except Exception as e:
            self.result['error'] = f"Failed to compile from source: {str(e)}"
            return None
    
    def _get_required_submodules(self, source_info: dict) -> Optional[List[str]]:
        return source_info.get('submodules')
    
    def _init_submodules_exact(self, repo_dir: Path):
        """Initialize submodules at their exact pinned commits (not --depth 1 which gets latest)"""
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
    
    def _init_nested_submodules(self, repo_dir: Path):
        """Initialize nested submodules in lib/* directories at their exact pinned commits"""
        lib_dir = repo_dir / "lib"
        if not lib_dir.exists():
            return
        
        for subdir in lib_dir.iterdir():
            if subdir.is_dir() and (subdir / ".gitmodules").exists():
                self._init_submodules_exact(subdir)
    
    def _patch_foundry_config(self, repo_dir: Path):
        """Patch foundry.toml with deployment compiler settings"""
        foundry_toml = repo_dir / "foundry.toml"
        if not foundry_toml.exists():
            return
        
        content = foundry_toml.read_text()
        
        optimization_enabled = self.result['details'].get('optimization_enabled')
        if optimization_enabled is not None:
            optimizer_value = "true" if optimization_enabled else "false"
            if re.search(r'optimizer\s*=\s*(true|false)', content):
                content = re.sub(
                    r'optimizer\s*=\s*(true|false)',
                    f'optimizer = {optimizer_value}',
                    content
                )
            else:
                content = content.replace('[profile.default]', f'[profile.default]\noptimizer = {optimizer_value}')
        
        optimizer_runs = self.result['details'].get('optimization_runs')
        if optimizer_runs is not None:
            if re.search(r'optimizer_runs\s*=\s*[\d_]+', content):
                content = re.sub(
                    r'optimizer_runs\s*=\s*[\d_]+',
                    f'optimizer_runs = {optimizer_runs}',
                    content
                )
            elif optimization_enabled:
                content = content.replace('[profile.default]', f'[profile.default]\noptimizer_runs = {optimizer_runs}')
        
        compiler_version = self.result['details'].get('compiler_version', '')
        if compiler_version:
            match = re.search(r'v?(\d+\.\d+\.\d+)', compiler_version)
            if match:
                solc_version = match.group(1)
                if re.search(r'solc\s*=\s*"[\d\.]+"', content):
                    content = re.sub(
                        r'solc\s*=\s*"[\d\.]+"',
                        f'solc = "{solc_version}"',
                        content
                    )
                else:
                    content = content.replace('[profile.default]', f'[profile.default]\nsolc = "{solc_version}"')
        
        evm_version = self.result['details'].get('evm_version')
        if evm_version:
            if re.search(r'evm_version\s*=\s*"[^"]+"', content):
                content = re.sub(
                    r'evm_version\s*=\s*"[^"]+"',
                    f'evm_version = "{evm_version}"',
                    content
                )
            else:
                content = content.replace('[profile.default]', f'[profile.default]\nevm_version = "{evm_version}"')
        
        via_ir = self.result['details'].get('via_ir')
        if via_ir is not None:
            via_ir_value = "true" if via_ir else "false"
            if re.search(r'via_ir\s*=\s*(true|false)', content):
                content = re.sub(
                    r'via_ir\s*=\s*(true|false)',
                    f'via_ir = {via_ir_value}',
                    content
                )
            else:
                content = content.replace('[profile.default]', f'[profile.default]\nvia_ir = {via_ir_value}')
        
        # Exclude script and test folders to avoid missing dependency errors from uninitialized submodules
        if re.search(r'script\s*=\s*"[^"]+"', content):
            content = re.sub(r'script\s*=\s*"[^"]+"', 'script = "disabled_script"', content)
        else:
            content = content.replace('[profile.default]', '[profile.default]\nscript = "disabled_script"')
        
        if re.search(r'test\s*=\s*"[^"]+"', content):
            content = re.sub(r'test\s*=\s*"[^"]+"', 'test = "disabled_test"', content)
        else:
            content = content.replace('[profile.default]', '[profile.default]\ntest = "disabled_test"')
        
        foundry_toml.write_text(content)
    
    def _extract_bytecode_from_artifacts(self, repo_dir: Path, use_runtime: bool = False) -> Optional[str]:
        """Extract bytecode from Foundry build artifacts"""
        out_dir = repo_dir / "out"
        if not out_dir.exists():
            return None
        
        name_lower = self.name.lower()
        bytecode_key = 'deployedBytecode' if use_runtime else 'bytecode'
        
        for artifact_file in out_dir.rglob("*.json"):
            try:
                with open(artifact_file) as f:
                    data = json.load(f)
                    contract_name = data.get('contractName', '')
                    if contract_name.lower() == name_lower or artifact_file.stem.lower() == name_lower:
                        bytecode = data.get(bytecode_key, {}).get('object')
                        if bytecode and bytecode != '0x':
                            return bytecode
            except:
                continue
        
        return None
    
    def compare_bytecodes(self, deployed: str, compiled: str) -> bool:
        """Compare deployed and compiled bytecodes (excluding metadata and constructor args)"""
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
        
        # Deployed bytecode may have constructor args appended - try matching up to compiled length
        if len(deployed_stripped) > len(compiled_stripped):
            constructor_args_len = len(deployed_stripped) - len(compiled_stripped)
            if constructor_args_len % 64 == 0:  # Constructor args are 32-byte aligned
                deployed_without_args = deployed_stripped[:len(compiled_stripped)]
                if deployed_without_args == compiled_stripped:
                    self.log(f"✅ Bytecodes match (excluding {constructor_args_len // 2} bytes of constructor args)")
                    self.result['details']['constructor_args_size'] = constructor_args_len // 2
                    return True
        
        # Handle CREATE2 deployments where init code may have a prefix (salt/factory data)
        if len(deployed_stripped) > len(compiled_stripped):
            compiled_start = compiled_stripped[:40]
            prefix_idx = deployed_stripped.find(compiled_start)
            if prefix_idx > 0:
                deployed_trimmed = deployed_stripped[prefix_idx:]
                if deployed_trimmed == compiled_stripped:
                    self.log(f"✅ Bytecodes match (CREATE2 deployment with {prefix_idx // 2} byte prefix)")
                    self.result['details']['create2_prefix_size'] = prefix_idx // 2
                    return True
                # Check for constructor args after CREATE2 prefix
                if len(deployed_trimmed) > len(compiled_stripped):
                    constructor_args_len = len(deployed_trimmed) - len(compiled_stripped)
                    if constructor_args_len % 64 == 0:
                        deployed_without_args = deployed_trimmed[:len(compiled_stripped)]
                        if deployed_without_args == compiled_stripped:
                            self.log(f"✅ Bytecodes match (CREATE2 + {constructor_args_len // 2} bytes constructor args)")
                            self.result['details']['create2_prefix_size'] = prefix_idx // 2
                            self.result['details']['constructor_args_size'] = constructor_args_len // 2
                            return True
        
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
        """Remove ALL CBOR metadata sections from bytecode (handles embedded contracts)"""
        if bytecode.startswith('0x'):
            bytecode = bytecode[2:]
        
        marker = "a264697066735822"
        end_marker = "0033"
        
        result = bytecode
        while marker in result:
            idx = result.find(marker)
            end_idx = result.find(end_marker, idx)
            if end_idx != -1:
                result = result[:idx] + result[end_idx + len(end_marker):]
            else:
                result = result[:idx]
                break
        
        return result
    
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


def check_source_mappings(contracts: List[Tuple[str, str]]) -> List[str]:
    """Check that all contracts have SOURCE_REPOS mappings. Returns list of missing contracts."""
    missing = []
    for contract_info in contracts:
        name = contract_info[0]
        source_info = SOURCE_REPOS.get(name)
        if not source_info:
            for contract_name in SOURCE_REPOS:
                if contract_name.lower() in name.lower():
                    source_info = SOURCE_REPOS[contract_name]
                    break
        if not source_info:
            missing.append(name)
    return missing


def verify_contract_list(
    contracts: List[Tuple[str, str]], 
    verbose: bool = False,
    show_change_type: bool = False,
    strict: bool = True
) -> Tuple[List[dict], List[dict]]:
    """contracts: (name, address) or (name, address, change_type) tuples when show_change_type=True"""
    verified = []
    failed = []
    
    if strict:
        missing = check_source_mappings(contracts)
        if missing:
            print(f"\n{'='*80}")
            print("❌ FATAL: Missing SOURCE_REPOS mappings")
            print(f"{'='*80}")
            print("The following contracts have no source repository mapping defined:")
            for name in missing:
                print(f"  - {name}")
            print("\nTo fix: Add entries to SOURCE_REPOS in scripts/verify-contracts.py")
            print("Example:")
            print('  "ContractName": {"repo": "euler-xyz/repo-name", "commit": "abc1234"},')
            print(f"{'='*80}\n")
            for name in missing:
                failed.append({
                    "name": name,
                    "verified": False,
                    "error": "No SOURCE_REPOS mapping - cannot verify without source reference"
                })
            return verified, failed
    
    for contract_info in contracts:
        if show_change_type and len(contract_info) >= 3:
            name, address, change_type = contract_info[0], contract_info[1], contract_info[2]
            print(f"\n[{change_type.upper()}] {name}")
        else:
            name, address = contract_info[0], contract_info[1]
        
        verifier = ContractVerifier(address, name=name, verbose=verbose)
        success = verifier.verify()
        
        if success:
            verified.append(verifier.result)
        else:
            failed.append(verifier.result)
    
    return verified, failed


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
        contracts = [(name, address) for name, address in addresses.items()]
        verified, failed = verify_contract_list(contracts, verbose=args.verbose)
        
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
        
        contracts = [
            (c['name'], c['address'], c.get('change_type', 'unknown')) 
            for c in changed_contracts
        ]
        verified, failed = verify_contract_list(contracts, verbose=args.verbose, show_change_type=True)
        
        print_summary(verified, failed)
        
        if args.output:
            save_report(verified, failed, args.output)
        
        sys.exit(0 if len(failed) == 0 else 1)
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
