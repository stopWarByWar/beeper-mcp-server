
import pkgutil
from web3 import Web3 
from web3.contract import Contract
from eth_account import Account
import secrets

def _load_contract_erc20(w3: Web3, token_address: str) -> Contract:
    contract_abi = pkgutil.get_data('chain', 'solc/Token.abi').decode()
    return w3.eth.contract(address=token_address, abi=contract_abi)

def get_address_from_private_key(private_key: str) -> str:
    if not private_key.startswith('0x'):
        private_key = '0x' + private_key
        
    try:
        account = Account.from_key(private_key)
        return account.address
    except Exception as e:
        raise ValueError(f"Error processing get address from private key with error: {str(e)}")