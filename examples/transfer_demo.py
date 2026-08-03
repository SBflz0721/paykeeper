"""
仅执行一次真实链上转账（不需要 LLM Key）。

用于在没有 LLM Key 的情况下，验证"经 KeeperHub 真实执行交易"这一黑客松硬性要求。
读取 .env 的 TARGET_CHAIN_ID / DEMO_RECIPIENT / DEMO_AMOUNT / DEMO_TOKEN_ADDRESS。

运行：
    python examples/transfer_demo.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from agent.keeperhub_mcp import KeeperHubMCP
from agent import payments

EXPLORERS = {
    "1": "https://etherscan.io/tx/{}",
    "11155111": "https://sepolia.etherscan.io/tx/{}",
    "8453": "https://basescan.org/tx/{}",
    "84532": "https://sepolia.basescan.org/tx/{}",
}


async def main() -> None:
    chain = os.getenv("TARGET_CHAIN_ID", "11155111")
    recipient = os.getenv("DEMO_RECIPIENT", "")
    amount = os.getenv("DEMO_AMOUNT", "0.01")
    token = os.getenv("DEMO_TOKEN_ADDRESS") or None

    if not recipient or recipient.startswith("0x0000"):
        print("[跳过] 请在 .env 设置 DEMO_RECIPIENT")
        return

    async with KeeperHubMCP() as kh:
        print(f"链 {chain} -> {recipient} | {amount} {token or '原生币'}")
        res = await payments.run_subscription_once(
            kh, chain_id=chain, to_address=recipient, amount=amount, token_address=token
        )
        print(json.dumps(res.to_report(), indent=2, ensure_ascii=False))
        if res.tx_hash:
            tpl = EXPLORERS.get(str(chain))
            print("交易浏览器:", tpl.format(res.tx_hash) if tpl else res.tx_hash)


if __name__ == "__main__":
    asyncio.run(main())
