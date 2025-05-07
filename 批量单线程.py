import json
import time
from web3 import Web3

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

DELAY_BETWEEN_MINTS_SECONDS = 5 # 每个任务等待5秒

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

def mint_nft(w3, contract, private_key, nft_contract_addr, fee_recipient_addr, quantity):
    """
    使用给定的私钥铸造 NFT。
    """
    minter_address = "N/A"
    try:
        account = w3.eth.account.from_key(private_key)
        minter_address = account.address
        print(f"\n[*] 正在使用地址: {minter_address} 进行铸造...")

        nonce = w3.eth.get_transaction_count(minter_address)
        
        tx_params = {
            'from': minter_address,
            'nonce': nonce,
            'value': w3.to_wei(MINT_VALUE_AVAX, 'ether'),
            'gas': GAS_LIMIT,
        }

        try:
            latest_block = w3.eth.get_block('latest')
            if 'baseFeePerGas' in latest_block and latest_block['baseFeePerGas'] is not None:
                priority_fee_gwei = 2 
                tx_params['maxPriorityFeePerGas'] = w3.to_wei(priority_fee_gwei, 'gwei')
                estimated_max_fee = int(latest_block['baseFeePerGas'] * 1.2) + tx_params['maxPriorityFeePerGas']
                tx_params['maxFeePerGas'] = estimated_max_fee
                print(f"使用 EIP-1559 费用: maxFeePerGas={w3.from_wei(tx_params['maxFeePerGas'], 'gwei')} gwei, maxPriorityFeePerGas={priority_fee_gwei} gwei")
            else:
                current_gas_price = w3.eth.gas_price
                tx_params['gasPrice'] = current_gas_price
                print(f"使用 Legacy gas price: {w3.from_wei(current_gas_price, 'gwei')} gwei")
        except Exception as e:
            print(f"获取动态 gas 费用时出错，将回退到默认 gasPrice: {e}")
            current_gas_price = w3.eth.gas_price # Fallback
            tx_params['gasPrice'] = current_gas_price
            print(f"回退使用 Legacy gas price: {w3.from_wei(current_gas_price, 'gwei')} gwei")


        if 'maxFeePerGas' not in tx_params and 'gasPrice' not in tx_params:
            current_gas_price = w3.eth.gas_price
            print(f"警告: Gas 费用参数未明确设置, 默认使用 w3.eth.gas_price: {w3.from_wei(current_gas_price, 'gwei')} gwei")
            tx_params['gasPrice'] = current_gas_price
        
        print(f"交易参数: {tx_params}")
        
        mint_transaction = contract.functions.mintPublic(
            nft_contract_addr,
            fee_recipient_addr,
            minter_address,
            quantity
        ).build_transaction(tx_params)

        signed_txn = w3.eth.account.sign_transaction(mint_transaction, private_key=private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        
        print(f"铸造交易已发送: {w3.to_hex(tx_hash)}")
        print("等待交易确认...")
        
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300) # 等待最多300秒
        
        if receipt['status'] == 1:
            print(f"成功! NFT 已为地址 {minter_address} 铸造。")
            print(f"交易哈希: {w3.to_hex(receipt['transactionHash'])}")
            print(f"区块号: {receipt['blockNumber']}")
            return True
        else:
            print(f"失败! 地址 {minter_address} 的铸造交易失败。")
            print(f"交易哈希: {w3.to_hex(receipt['transactionHash'])}")
            print(f"状态: {receipt['status']}")
            return False

    except Exception as e:
        print(f"为地址 {minter_address} 铸造时发生错误: {e}")
        if "reverted" in str(e).lower() or "execution reverted" in str(e).lower():
            print("错误提示 'reverted'，通常表示合约执行条件未满足或 Gas 不足。请检查合约逻辑和 Gas 设置。")
        if hasattr(e, 'args') and e.args:
            print(f"详细错误参数: {e.args}")
        return False

def main():
    print("--- 冒险岛NFT批量铸造脚本 作者:大大 推特：@designtim ---")

    if AVAX_RPC_URL == "YOUR_AVAX_RPC_URL" or PRIVATE_KEYS_FILE == "YOUR_PRIVATE_KEYS_FILE.txt":
        print("错误: 请在脚本中配置 AVAX_RPC_URL 和 PRIVATE_KEYS_FILE。")
        return

    contract_abi = load_abi()
    if not contract_abi:
        return

    w3 = Web3(Web3.HTTPProvider(AVAX_RPC_URL))
    if not w3.is_connected():
        print(f"错误: 无法连接到 RPC URL: {AVAX_RPC_URL}")
        return
    print(f"已连接到链 ID: {w3.eth.chain_id}")


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

    successful_mints = 0
    failed_mints = 0

    for i, pk in enumerate(private_keys):
        print(f"\n--- 处理第 {i+1}/{len(private_keys)} 个钱包 ---")
        if mint_nft(w3, seadrop_contract, pk, NFT_CONTRACT_ADDRESS, FEE_RECIPIENT_ADDRESS, MINT_QUANTITY):
            successful_mints += 1
        else:
            failed_mints += 1
        
        if i < len(private_keys) - 1:
            print(f"等待 {DELAY_BETWEEN_MINTS_SECONDS} 秒后继续下一个钱包...")
            time.sleep(DELAY_BETWEEN_MINTS_SECONDS)

    print("\n--- 铸造总结 ---")
    print(f"成功铸造: {successful_mints}")
    print(f"失败铸造: {failed_mints}")
    print("脚本执行完毕。")

if __name__ == "__main__":
    main() 