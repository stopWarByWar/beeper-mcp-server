import asyncio
import os
import logging
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio
from chain.beeper import Beeper


server = Server("beeper_mcp")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        types.Tool(
            name="add-note",
            description="Add a new note",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["name", "content"],
            },
        )
    ]

@server.call_tool()
async def get_balance(
    addr: str,
    token_addr: str,
) -> types.TextContent:
    """
    Handle tool to get the 'token_addr' balance of user address 'addr'.
    Input: 
        addr: str, the address of the user. if user is not provided, the address of the user will be the address of the private key.
        token_addr: str, the address of the token. if token is not provided, the token will be the native token.
    Output:
        balance: int, the balance of the user
    """
    try:
        if len(addr) != 42:
            addr = beeper.get_address_from_private_key()
        balance = beeper.get_balance(addr, token_addr)
        
        return types.TextContent(
                type="text",
                text=f"the balance of {addr} is {balance / (10 ** 18)} ${beeper.get_token_symbol(token_addr)}",
         )
    
    except Exception as e:
        raise ValueError(f"Error processing get balance with error: {str(e)}")
    
@server.call_tool()
async def deploy_token(
    name: str,
    symbol: str,
    desc: str = 'Token created by Beeper',
    image: str = 'https://twitter.com/',
    fee: int = 2500, #1%; 500:0.05%; 2500:0.25%
    buy_fee: int = 2500,     
    token_supply:int = 10000000000 * 10**18,
) -> types.TextContent:
    """
    Deploy a new token.
    Input:
        name: str, the name of the token
        symbol: str, the symbol of the token
        desc: str, the description of the token 
        image: str, the image of the token
    Output:
        token_addr: str, the address of the token
    """
    try:
        tx_hash, token_address, _ = beeper.deploy_token(
            token_name=name, 
            token_symbol=symbol, 
            token_supply=token_supply,
            fee=fee,  # 使用较小的费用 0.25%
            buy_fee=buy_fee,
            image=image,
            desc=desc,
        )
        return types.TextContent(
                type="text",
                text=f"you deploy a new token {name}({token_address}) at tx {tx_hash}",
         )
       
    except Exception as e:
        raise ValueError(f"Error processing deploy token with error: {str(e)}")
    
@server.call_tool()
async def make_trade(
    input_token: str = None,
    output_token: str = None,
    amount: int = 1000000,
) -> types.TextContent:
    """
    Make a trade.
    Input:
        input_token: str, the address of the input token. if input_token is not provided, the input token will be the native token.
        output_token: str, the address of the output token. if output_token is not provided, the output token will be the native token.
        amount: int, the amount of the trade
    Output:
        tx_hash: str, the hash of the trade
    """
    try:
        tx_hash = beeper.make_trade(input_token, output_token, amount)
        return types.TextContent(
            type="text",        
            text=f"you make a trade at tx {tx_hash}",
        )
    except Exception as e:
        raise ValueError(f"Error processing make trade with error: {str(e)}")   
    
@server.call_tool()
async def transfer_asset(
    token_addr: str,
    recipient: str,
    amount: int,
) -> types.TextContent: 
    """
    Transfer an asset.
    Input:
        token_addr: str, the address of the token, if token_addr is not provided, the token will be the native token.
        recipient: str, the address of the recipient.
        amount: int, the amount of the transfer.
    Output: 
        tx_hash: str, the hash of the transfer.
    """
    try:
        tx_hash = beeper.transfer_asset(token_addr, recipient, amount)
        return types.TextContent(
            type="text",
            text=f"you transfer {amount} ${beeper.get_token_symbol(token_addr)} to {recipient} at tx {tx_hash}",
        )
    except Exception as e:
        raise ValueError(f"Error processing transfer asset with error: {str(e)}")   
    
async def main():
    logging.basicConfig(level=logging.INFO)
    logging.info("start beeper_mcp server...")
    
    global beeper
    private_key = os.environ.get('PRIVATE_KEY')
    if private_key is None:
        raise ValueError('Set PRIVATE_KEY Firstly')

    chain_type = os.environ.get('Chain_Type')
    if chain_type is None:
        chain_type = 'bsc-testnet'

    if (chain_type != 'bsc-testnet' and chain_type != 'bsc-mainnet'):
        raise ValueError('Set Chain_Type Firstly')  

    beeper = Beeper(chain_type=chain_type, private_key=private_key)
        
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="beeper_mcp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )