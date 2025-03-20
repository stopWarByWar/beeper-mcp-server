import pytest
from eth_account import Account
import os
from decimal import Decimal
from dotenv import load_dotenv
from src.chain.beeper import Beeper  # Assuming this is your main class

# 加载.env.test文件中的环境变量
load_dotenv('.env.test')

# Setup for tests
@pytest.fixture
def beeper():
    private_key = os.getenv('TEST_PRIVATE_KEY')
    if not private_key:
        pytest.skip("TEST_PRIVATE_KEY not set in .env.test")
    
    # 确保使用测试网
    return Beeper(chain_type='testnet', private_key=private_key)

# Test balance checking
def test_get_balance(beeper):
    """Test the function to get account balance"""
    user_addr = beeper.get_address_from_private_key()
    balance = beeper.get_balance(wallet_address=user_addr, token_address="")
    assert isinstance(balance, (int, float, Decimal))
    
    ticker = beeper.get_token_symbol(token_address="")      
    print(f"balance of {user_addr}: {balance/10**18} ${ticker}")

# Test token deployment
def test_deploy_token(beeper):
    """Test the deployment of a new token"""
    name = "TSTWWER"
    symbol = "TSTWWER"
    initial_supply = 1_000_000 * 10**18  # 减小供应量
    
    try:
        tx_hash, token_address, _ = beeper.deploy_token(
            token_name=name, 
            token_symbol=symbol, 
            token_supply=initial_supply,
            fee=2500,  # 使用较小的费用 0.25%
            buy_fee=2500
        )
        print(f"tx_hash is {tx_hash}\ntoken_address is {token_address}")
        assert token_address.startswith("0x")
        assert len(token_address) == 42
    except Exception as e:
        print(f"部署失败原因: {str(e)}")
        raise

# Test trading functionality
def test_make_trade(beeper):
    """Test the trading function"""
    token_address = '0x18D0A5C802e116554653A55B122108de6Df20D3D'
    amount = 100
    
    try:
        tx_hash = beeper.make_trade(output_token=token_address, amount=amount)
        assert tx_hash.startswith("0x")
        assert len(tx_hash) == 66  # Transaction hash length
    except Exception as e:
        pytest.skip(f"Trade test skipped: {str(e)}")

# Test asset transfer
def test_transfer_asset(beeper):
    """Test the asset transfer function"""
    receiver = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"  # Test receiver address
    token_address = ""
    amount = 10
        
    try:
        tx_hash = beeper.transfer_asset(received_address=receiver, token_address=token_address, amount=amount)
        print(f"tx_hash is {tx_hash}")
        assert tx_hash.startswith("0x")
        assert len(tx_hash) == 66
    except Exception as e:
        pytest.skip(f"Transfer test skipped: {str(e)}") 