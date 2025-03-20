import time
import json
import pkgutil
import logging
import os
import yaml

from web3 import Web3
from web3.contract.contract import ContractFunction
from web3.constants import ADDRESS_ZERO 
from web3.types import (TxParams, Wei)
from .utils import ( _load_contract_erc20, get_address_from_private_key)

from typing import (
    Optional,
)

logger = logging.getLogger(__name__)

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

class Beeper:
    def __init__(self, 
                 chain_type: str = 'bsc-testnet',
                 private_key: str = None
    ):
        if len(private_key) != 64 and len(private_key) != 66:
            raise ValueError("Private key is required")
        
        config = load_config()
        chain_config = config['chain'][chain_type]
        
        self.private_key = private_key
        self.chain_id = chain_config['chain_id']
        self.web3 = Web3(Web3.HTTPProvider(chain_config['rpc_url']))
        if not self.web3.is_connected():
            raise ValueError("Failed to connect to the chain")
        
        self.max_approval_int = int(f"0x{64 * 'f'}", 16)
        self.max_approval_check_int = int( f"0x{15 * '0'}{49 * 'f'}", 16) 
        
        router_address = Web3.to_checksum_address(chain_config['pancake_v3_swap_router_addr'])
        router_abi = pkgutil.get_data('chain', 'solc/pancake_swaprouter_v3.abi').decode()
        self.router = self.web3.eth.contract(address=router_address, abi=router_abi)
        
        factory_address =  Web3.to_checksum_address(chain_config['pancake_v3_factory_addr'])
        factory_abi = pkgutil.get_data('chain', 'solc/pancake_factory_v3.abi').decode()
        self.factory = self.web3.eth.contract(address=factory_address, abi=factory_abi)
        
        beeper_util_address = Web3.to_checksum_address(chain_config['beeper_util_addr'])
        beeper_util_abi = json.loads(pkgutil.get_data('chain', 'solc/Util.sol/Util.json').decode())
        self.beeper_util = self.web3.eth.contract(address=beeper_util_address, abi=beeper_util_abi ['abi'])
        
        beeper_address = Web3.to_checksum_address(chain_config['beeper_addr'])
        beeper_abi = json.loads(pkgutil.get_data('chain', 'solc/Beeper.sol/Beeper.json').decode())
        self.beeper = self.web3.eth.contract(address=beeper_address, abi=beeper_abi['abi'])
        
       
        
    def get_balance(self, 
                wallet_address: str, 
                token_address :str
                ) -> int:
        wallet_address = Web3.to_checksum_address(wallet_address)
        if token_address == "":
            balance = self.web3.eth.get_balance(wallet_address)
        else:   
            balance = self._get_erc20_balance(wallet_address, token_address)
        return balance        

    def _get_erc20_balance(self, 
                wallet_address: str, 
                token_address :str
                ) -> int:
        wallet_address = Web3.to_checksum_address(wallet_address)
        if token_address == "":
            balance = self.web3.eth.get_balance(wallet_address)
        else:   
            token_address = Web3.to_checksum_address(token_address)
            balance = _load_contract_erc20(self.web3, token_address).functions.balanceOf(wallet_address).call()
        
        return balance
    
    def deploy_token(self, 
                    image: str = 'https://twitter.com/',
                    token_name : str = 'Beeper',
                    token_symbol:  str = 'Power by Beeper',
                    token_supply: int = 10000000000 * 10**18,
                    initial_tick: int = -207400, 
                    fee: int = 2500, #1%; 500:0.05%; 2500:0.25%
                    buy_fee: int = 2500,                     
                    ) -> tuple[str,str,str]:
        
        if self.private_key == "":
            raise Exception(f"No admin private key")
        
        user_addr = self.get_address_from_private_key()
        wbnb = self.router.functions.WETH9().call()
        
        try:
            generated_salt, token_address = self.beeper_util.functions.generateSalt(user_addr, 0, token_name, token_symbol, image, "", token_supply, wbnb).call()
            logger.info(f"Salt: {generated_salt.hex()} {token_address}")
        except Exception as e:
            raise e

        pool_config =[initial_tick,  wbnb,  buy_fee]
        return self._build_and_send_tx(
                self.private_key,
                self.beeper.functions.deployToken(
                    token_name, 
                    token_symbol, 
                    token_supply, 
                    fee, 
                    generated_salt, 
                    user_addr, 
                    0, 
                    image, 
                    "", 
                    pool_config
                ),
                self._get_tx_params(address=user_addr, gas=9_000_000),
            ), token_address, token_supply
        
    def make_trade(self, 
                    input_token :str = None, 
                    output_token :str = None,
                    amount: int = 1000000, 
                    fee: int = 10000 # deploy same setting
                    ):
          
            if input_token is None :
                return self._native_to_token(
                    self.get_address_from_private_key(), self.private_key, output_token, amount, fee
                )
            elif output_token is None:
                return self._token_to_native(
                    self.get_address_from_private_key(), self.private_key, input_token, amount, fee
                )
            else:
                return self._token_to_token(self.get_address_from_private_key(), self.private_key, input_token,output_token, amount, fee)
                         
    def _native_to_token(self, 
                  wallet_address: str, 
                  private_key: str, 
                  token_address :str, 
                  amount: int = 1000000, 
                  fee: int = 10000 # deploy same setting
                  ):
        wallet_address = Web3.to_checksum_address(wallet_address)
        token_address = Web3.to_checksum_address(token_address)

        pool_fees = [10000, 2500, 500, 100]
        for pool_fee in pool_fees:
            pool_addr = self.get_token_pool(token_address, pool_fee)
            if pool_addr != ADDRESS_ZERO:
                logger.debug(f"pool addr at: {pool_addr} {pool_fee}")
                fee = pool_fee
                break
        
        return self._build_and_send_tx(
            private_key,
            self.router.functions.exactInputSingle(
                {
                    "tokenIn": self.router.functions.WETH9().call(),
                    "tokenOut": token_address,
                    "fee": fee,
                    "recipient": wallet_address,
                    "deadline": int(time.time()) + 3600,
                    "amountIn": amount,
                    "amountOutMinimum": 0,
                    "sqrtPriceLimitX96": 0,
                }
            ),
            self._get_tx_params(address=wallet_address,value=amount),
        )

    def _token_to_native(self, 
                  wallet_address: str, 
                  private_key: str, 
                  token_address :str, 
                  amount: int = 1000000, 
                  fee: int = 10000 # deploy same setting
                  ):
        wallet_address = Web3.to_checksum_address(wallet_address)
        token_address = Web3.to_checksum_address(token_address)

        pool_fees = [10000, 2500, 500, 100]
        for pool_fee in pool_fees:
            pool_addr = self.get_token_pool(token_address, pool_fee)
            if pool_addr != ADDRESS_ZERO:
                print(f"pool addr at: {pool_addr} {pool_fee}")
                fee = pool_fee
                break

        self._check_approval(wallet_address, token_address)

        print(f"Seller: {amount} {token_address} to bnb...")

        swap_data = self.router.encode_abi(
            "exactInputSingle",
            args=[
                (
                    token_address,
                    self.router.functions.WETH9().call(),
                    fee,
                    ADDRESS_ZERO,
                    int(time.time()) + 3600,
                    amount,
                    0,
                    0,
                )
            ],
        )
        unwrap_data = self.router.encode_abi(
            "unwrapWETH9", args=[0, wallet_address]
        )

        return self._build_and_send_tx(
            private_key,
            self.router.functions.multicall([swap_data, unwrap_data]),
            self._get_tx_params(address=wallet_address),
        )
    
    def _token_to_token(self, 
                  wallet_address: str, 
                  private_key: str, 
                  input_token :str,
                  output_token :str, 
                  amount: int = 1000000, 
                  fee: int = 10000
                  ):
        wallet_address = Web3.to_checksum_address(wallet_address)
        input_token = Web3.to_checksum_address(input_token)
        output_token = Web3.to_checksum_address(output_token)


        wbnb_address = Web3.to_checksum_address(self.router.functions.WETH9().call())
        if input_token != wbnb_address and output_token != wbnb_address:
            return self._token_to_token_via_hop(wallet_address, private_key, input_token, output_token, amount, fee)

        self._check_approval(wallet_address, input_token)  
        
        return self._build_and_send_tx(
            private_key,
            self.router.functions.exactInputSingle(
                {
                    "tokenIn": input_token,
                    "tokenOut": output_token,
                    "fee": fee,
                    "recipient": wallet_address,
                    "deadline": int(time.time()) + 3600,
                    "amountIn": amount,
                    "amountOutMinimum": 0,
                    "sqrtPriceLimitX96": 0,
                }
            ),
            self._get_tx_params(address=wallet_address),
        )
    
    def _token_to_token_via_hop(self, 
                  wallet_address: str, 
                  input_token :str,
                  output_token :str, 
                  amount: int = 1000000, 
                  fee: int = 10000
                  ):
        wallet_address = Web3.to_checksum_address(wallet_address)
        input_token = Web3.to_checksum_address(input_token)
        output_token = Web3.to_checksum_address(output_token)

        self._check_approval(wallet_address, self.private_key, input_token)

        wbnb_address = self.router.functions.WETH9().call()

        tokens = [input_token, wbnb_address, output_token]
        #fees = [fee, fee]
        fees = []
        # pancake fee: 100, 500, 2500, 10000        
        pool_fees = [10000, 2500, 500, 100]
        for fee in pool_fees:
            pool_addr = self.get_token_pool(input_token, fee)
            if pool_addr != ADDRESS_ZERO:
                logger.debug(f"pool addr at: {pool_addr} {fee}")
                fees.append(fee)
                break
        if len(fees) != 1:
            raise Exception(f"No pair for input token or not paired with wbnb")

        for fee in pool_fees:
            pool_addr = self.get_token_pool(output_token, fee)
            if pool_addr != ADDRESS_ZERO:
                logger.debug(f"pool addr at: {pool_addr} {fee}")
                fees.append(fee)
                break
        if len(fees) != 2:
            raise Exception(f"No pair for output token or not paired with wbnb")            

        path = self._encode_path(tokens, fees)

        return self._build_and_send_tx(
            self.private_key,
            self.router.functions.exactInput(
                {
                    "path": path,
                    "recipient": wallet_address,
                    "deadline": int(time.time()) + 3600,
                    "amountIn": amount,
                    "amountOutMinimum": 0,
                }
            ),
            self._get_tx_params(address=wallet_address),
        )

    def _check_approval(self, wallet_address: str, token_address: str):
        token_address = Web3.to_checksum_address(token_address)
        is_approved = self._is_approved(wallet_address, token_address)
        if not is_approved:
            self.approve(wallet_address, self.private_key, token_address)
        logger.warning(f"Approved {token_address}: {is_approved}")

    def _build_and_send_tx(
        self, private_key: str, function: ContractFunction, tx_params: TxParams
    ) :
        """Build and send a transaction."""
        transaction = function.build_transaction(tx_params)

        try:  
            signed_txn = self.web3.eth.account.sign_transaction(transaction, private_key)
            rawTX = signed_txn.raw_transaction

            tx_hash = self.web3.eth.send_raw_transaction(rawTX)
            tx_receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
            if tx_receipt['status'] == 0:
                logger.error("Transaction failed")
                self._display_cause(tx_hash)
            else:
                logger.debug(f"Transaction succeeded:: {tx_hash.hex()}\nnonce: {tx_params['nonce']}")
                return "0x"+str(tx_hash.hex())
        except Exception as e:
            raise e
    
    def transfer_asset(self, 
                  received_address :str,
                  token_address :str, 
                  amount: int = 1000000
                  ):

        if token_address == "":
            return self._transfer(self.get_address_from_private_key(), self.private_key, received_address, amount)
        else:
            return self._transfer_token(self.get_address_from_private_key(), self.private_key, received_address, token_address, amount)
    
    def _transfer_token(self, 
                  wallet_address: str, 
                  private_key: str,
                  received_address :str,
                  token_address :str, 
                  amount: int = 1000000
                  ):
        wallet_address = Web3.to_checksum_address(wallet_address)
        received_address = Web3.to_checksum_address(received_address)
        token_address = Web3.to_checksum_address(token_address)

        token = _load_contract_erc20(self.web3, token_address)

        return self._build_and_send_tx(
            private_key,
            token.functions.transfer(received_address, amount),
            self._get_tx_params(address=wallet_address),
        )

    def _transfer(self, 
                  wallet_address: str, 
                  private_key: str,
                  received_address :str, 
                  amount: int = 1000000
                  ):
        wallet_address = Web3.to_checksum_address(wallet_address)
        received_address = Web3.to_checksum_address(received_address)

        transaction = {
            'chainId': self.chain_id,
            "to": received_address,
            "nonce": self.web3.eth.get_transaction_count(wallet_address),
            "gas": 100_000,
            "gasPrice": self.web3.eth.gas_price,
            "value": amount, 
        }
        try:
            signed_txn = self.web3.eth.account.sign_transaction(transaction, private_key)
            rawTX = signed_txn.raw_transaction
            tx_hash = self.web3.eth.send_raw_transaction(rawTX)
            tx_receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
            if tx_receipt['status'] == 0:
                logger.error("Transfer transaction failed")
                self._display_cause(tx_hash)
            else:
                logger.debug(f'Transfer transaction succeeded: {tx_hash.hex()}')
                return "0x"+str(tx_hash.hex())
        except Exception as e:
            raise e   

    def _display_cause(self, tx_hash: str):
        print(f"check: {tx_hash.hex()}")
        tx = self.web3.eth.get_transaction(tx_hash)
        replay_tx = {
            'to': tx['to'],
            'from': tx['from'],
            'value': tx['value'],
            'data': tx['input'],
        }

        try:
            self.web3.eth.call(replay_tx, tx.blockNumber - 1)
        except Exception as e: 
            print(e)
            raise e
        
    def _get_tx_params(
        self, address : str, value: Wei = Wei(0), gas: Optional[Wei] = None
        ) -> TxParams:
        """Get generic transaction parameters."""
        params: TxParams = {
            "from": address,
            "value": value,
            "nonce": self.web3.eth.get_transaction_count(address) ,
            "gasPrice": self.web3.eth.gas_price,
            "gas": 300_000,
        }

        if gas:
            params["gas"] = gas

        return params
    
    def get_address_from_private_key(self) -> str:
        return get_address_from_private_key(self.private_key)
    
    def get_token_pool(self, 
                token_address :str,
                fee: int = 10000,
                ) -> str:
        token_address = Web3.to_checksum_address(token_address)
        wbnb_address = self.router.functions.WETH9().call()
        return self.factory.functions.getPool(token_address, wbnb_address, fee).call()

    def get_token_symbol(self, token_address: str) -> str:
        try:
            if len(token_address) != 42:
                return "BNB"   
            
            token_address = Web3.to_checksum_address(token_address)
            token_contract = _load_contract_erc20(self.web3, token_address)
            return token_contract.functions.symbol().call()
        except Exception as e:
            raise ValueError(f"fail to get symbol: {str(e)}")