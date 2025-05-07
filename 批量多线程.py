import sys
import asyncio

if sys.platform == "win32" and sys.version_info >= (3, 8):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import json
import time
from web3 import AsyncWeb3, AsyncHTTPProvider

AVAX_RPC_URL = "https://填写你的AVAXRPC地址"  # 填写你的AVAX RPC地址
PRIVATE_KEYS_FILE = "private_keys.txt"  # 私钥 "private_keys.txt"
ABI_FILE = "ABI.txt"

SEADROP_CONTRACT_ADDRESS = "0x00005EA00Ac477B1030CE78506496e8C2dE24bf5"
NFT_CONTRACT_ADDRESS = "0xc00Ec66703261EC1393aE136056507709CfeB687"
FEE_RECIPIENT_ADDRESS = "0x0000a26b00c1F0DF003000390027140000fAa719"
MINT_QUANTITY = 1
MINT_VALUE_AVAX = 0

# Gas配置 (可以根据网络情况调整)
GAS_LIMIT = 300000

CONCURRENT_REQUEST_LIMIT = 5 # 并发数为5

def load_abi(filename=ABI_FILE):
    """从文件加载 ABI"""
    try:
        with open(filename, 'r') as f:
            abi = json.load(f)
        return abi
    except FileNotFoundError:
        print(f"错误: ABI 文件 '{filename}' 未找到。请确保它和脚本在同一个目录。")
        exit()
    except json.JSONDecodeError:
        print(f"错误: ABI 文件 '{filename}' 不是有效的 JSON 格式。")
        exit()
    except Exception as e:
        print(f"加载 ABI 时发生未知错误: {e}")
        exit()

async def mint_nft(w3, contract, private_key, nft_contract_addr, fee_recipient_addr, quantity, wallet_index, total_wallets):
    """
    使用给定的私钥铸造 NFT (异步版本)。
    """
    minter_address = "N/A"
    try:
        account = w3.eth.account.from_key(private_key)
        minter_address = account.address
        print(f"\n--- [钱包 {wallet_index+1}/{total_wallets}] 使用地址: {minter_address} 进行铸造... ---")

        nonce = await w3.eth.get_transaction_count(minter_address)
        
        tx_params = {
            'from': minter_address,
            'nonce': nonce,
            'value': w3.to_wei(MINT_VALUE_AVAX, 'ether'),
            'gas': GAS_LIMIT,
        }

        try:
            latest_block = await w3.eth.get_block('latest')
            if 'baseFeePerGas' in latest_block and latest_block['baseFeePerGas'] is not None:
                priority_fee_gwei = 2 
                tx_params['maxPriorityFeePerGas'] = w3.to_wei(priority_fee_gwei, 'gwei')
                estimated_max_fee = int(latest_block['baseFeePerGas'] * 1.2) + tx_params['maxPriorityFeePerGas']
                tx_params['maxFeePerGas'] = estimated_max_fee
            else:
                current_gas_price = await w3.eth.gas_price
                tx_params['gasPrice'] = current_gas_price
        except Exception as e:
            current_gas_price = await w3.eth.gas_price # Fallback
            tx_params['gasPrice'] = current_gas_price

        if 'maxFeePerGas' not in tx_params and 'gasPrice' not in tx_params:
            current_gas_price = await w3.eth.gas_price
            tx_params['gasPrice'] = current_gas_price
        
        
        mint_transaction = await contract.functions.mintPublic(
            nft_contract_addr,
            fee_recipient_addr,
            minter_address,
            quantity
        ).build_transaction(tx_params)

        signed_txn = w3.eth.account.sign_transaction(mint_transaction, private_key=private_key)
        tx_hash = await w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        
        print(f"--- [钱包 {wallet_index+1}/{total_wallets}] 铸造交易已发送: {w3.to_hex(tx_hash)} ---")
        
        receipt = await w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        
        if receipt['status'] == 1:
            print(f"--- [钱包 {wallet_index+1}/{total_wallets}] 成功! NFT 已为地址 {minter_address} 铸造。哈希: {w3.to_hex(receipt['transactionHash'])} ---")
            return True
        else:
            print(f"--- [钱包 {wallet_index+1}/{total_wallets}] 失败! 地址 {minter_address} 铸造交易失败。哈希: {w3.to_hex(receipt['transactionHash'])}, Status: {receipt['status']} ---")
            return False

    except Exception as e:
        print(f"--- [钱包 {wallet_index+1}/{total_wallets}] 为地址 {minter_address} 铸造时发生错误: {e} ---")
        if "reverted" in str(e).lower() or "execution reverted" in str(e).lower():
            print("--- [钱包 {wallet_index+1}/{total_wallets}] 错误提示 'reverted'，通常表示合约执行条件未满足或 Gas 不足。请检查合约逻辑和 Gas 设置。 ---")
        if hasattr(e, 'args') and e.args:
            print(f"--- [钱包 {wallet_index+1}/{total_wallets}] 详细错误参数: {e.args} ---")
        return False

async def mint_nft_with_semaphore_wrapper(semaphore, wallet_index, total_wallets, w3, contract, pk, nft_addr, fee_addr, qty):
    async with semaphore:
        return await mint_nft(w3, contract, pk, nft_addr, fee_addr, qty, wallet_index, total_wallets)

async def main():
    print("--- 冒险岛NFT批量铸造脚本 作者:大大 推特：@designtim ---")

    contract_abi = load_abi()
    if not contract_abi:
        return

    w3 = AsyncWeb3(AsyncHTTPProvider(AVAX_RPC_URL))
    try:
        chain_id = await w3.eth.chain_id
        print(f"已连接到链 ID: {chain_id}")
    except Exception as e:
        print(f"错误: 无法连接到 RPC URL: {AVAX_RPC_URL} 或获取链ID失败: {e}")
        return

    seadrop_contract = w3.eth.contract(address=SEADROP_CONTRACT_ADDRESS, abi=contract_abi)

    try:
        with open(PRIVATE_KEYS_FILE, 'r') as f:
            private_keys = [line.strip() for line in f if line.strip()]
        if not private_keys:
            print(f"错误: 私钥文件 '{PRIVATE_KEYS_FILE}' 为空或格式不正确。")
            return
        print(f"从 '{PRIVATE_KEYS_FILE}' 中加载了 {len(private_keys)} 个私钥。")
    except FileNotFoundError:
        print(f"错误: 私钥文件 '{PRIVATE_KEYS_FILE}' 未找到。")
        return
    except Exception as e:
        print(f"读取私钥文件时发生错误: {e}")
        return

    semaphore = asyncio.Semaphore(CONCURRENT_REQUEST_LIMIT)
    tasks = []
    print(f"准备为 {len(private_keys)} 个钱包进行铸造，并发限制为 {CONCURRENT_REQUEST_LIMIT}...")

    for i, pk in enumerate(private_keys):
        tasks.append(
            mint_nft_with_semaphore_wrapper(
                semaphore, i, len(private_keys), w3, seadrop_contract, pk, 
                NFT_CONTRACT_ADDRESS, FEE_RECIPIENT_ADDRESS, MINT_QUANTITY
            )
        )
    
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successful_mints = 0
    failed_mints = 0
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            failed_mints += 1
        elif result is True:
            successful_mints += 1
        elif result is False:
            failed_mints += 1

    print("\n\n--- 铸造总结 ---")
    print(f"成功铸造: {successful_mints}")
    print(f"失败铸造: {failed_mints}")
    print("脚本执行完毕。")


if __name__ == "__main__":
    rpc_configured = AVAX_RPC_URL != "YOUR_AVAX_RPC_URL"
    keys_file_placeholder = "YOUR_PRIVATE_KEYS_FILE.txt"
    keys_file_potentially_set = PRIVATE_KEYS_FILE != keys_file_placeholder
    
    pre_check_keys_file_exists = True
    if PRIVATE_KEYS_FILE == "private_keys.txt":
        try:
            with open(PRIVATE_KEYS_FILE, 'r') as f:
                pass
        except FileNotFoundError:
            pre_check_keys_file_exists = False
    elif keys_file_placeholder == PRIVATE_KEYS_FILE :
         pre_check_keys_file_exists = False

    if not rpc_configured or not keys_file_potentially_set or not pre_check_keys_file_exists:
        print("--- 预检查失败 ---")
        if not rpc_configured:
            print("错误: 请在脚本中配置 AVAX_RPC_URL。")
        if not keys_file_potentially_set:
            print(f"错误: 请将 PRIVATE_KEYS_FILE 从占位符 '{keys_file_placeholder}' 修改为你实际的私钥文件名。")
        elif not pre_check_keys_file_exists:
            if PRIVATE_KEYS_FILE == "private_keys.txt":
                print(f"错误: 私钥文件 '{PRIVATE_KEYS_FILE}' 未找到。请确保它存在于脚本相同目录，或修改文件名配置。")


    final_pre_check_failed = False
    if AVAX_RPC_URL == "YOUR_AVAX_RPC_URL":
        print("错误: 请在脚本中配置 AVAX_RPC_URL。")
        final_pre_check_failed = True
    
    if PRIVATE_KEYS_FILE == "YOUR_PRIVATE_KEYS_FILE.txt":
        print(f"错误: 请将 PRIVATE_KEYS_FILE 从占位符 '{PRIVATE_KEYS_FILE}' 修改为你实际的私钥文件名。")
        final_pre_check_failed = True
    else:
        try:
            with open(PRIVATE_KEYS_FILE, 'r') as f:
                pass
        except FileNotFoundError:
            print(f"错误: 私钥文件 '{PRIVATE_KEYS_FILE}' 未找到。请确保它存在于脚本相同目录。")
            final_pre_check_failed = True

    if not final_pre_check_failed:
        asyncio.run(main())
    else:
        print("请修复配置后重试。") 