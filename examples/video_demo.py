"""
PayKeeper 录屏演示入口（面向演示视频，输出紧凑、叙事清晰）。

用法：
    LLM_PROVIDER=deepseek python examples/video_demo.py
    python examples/video_demo.py --instruction "给 0x.. 转 0.005 ETH"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from agent.keeperhub_mcp import KeeperHubMCP
from agent import agent as nl_agent
from agent.policy import PolicyEngine, make_demo_rule

EXPLORERS = {
    "1": "https://etherscan.io/tx/{}",
    "11155111": "https://sepolia.etherscan.io/tx/{}",
    "8453": "https://basescan.org/tx/{}",
    "84532": "https://sepolia.basescan.org/tx/{}",
    "42161": "https://arbiscan.io/tx/{}",
    "137": "https://polygonscan.com/tx/{}",
}

DEFAULT_INSTRUCTION = (
    "请经 KeeperHub 向 0xc4Ef9855219C03843dd425b23C142d0F059aAfFd 转账 0.005 ETH，"
    "目标链 11155111（Sepolia）。先 simulate 预飞，再广播，最后汇报交易哈希和浏览器链接。"
)


def banner(title: str) -> None:
    print("\n" + "=" * 62)
    print(f"  {title}")
    print("=" * 62)


def extract_hashes(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"0x[a-fA-F0-9]{64}", text)))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instruction", default=DEFAULT_INSTRUCTION)
    args = parser.parse_args()

    chain_id = os.getenv("TARGET_CHAIN_ID", "11155111")

    banner(f"PayKeeper · 自主支付 Agent · 经 KeeperHub 链上执行（链 {chain_id}）")
    print(f"  LLM provider : {os.getenv('LLM_PROVIDER', 'anthropic')} / {os.getenv('LLM_MODEL', '(未设置 LLM_MODEL)')}")

    async with KeeperHubMCP() as kh:
        tools = kh.get_tools()
        print(f"  KeeperHub MCP : 已连接，加载工具 {len(tools)} 个")

        banner("用户自然语言指令")
        print(f"  > {args.instruction}")

        banner("Agent 推理与执行中（DeepSeek + KeeperHub MCP）...")
        # 强制接入风控：Agent 只能付给白名单地址（默认 demo 收款方）且金额受限
        policy_engine = PolicyEngine()
        demo_rule = make_demo_rule(
            "0xc4Ef9855219C03843dd425b23C142d0F059aAfFd", 0.01, daily_eth=0.02,
            name="video-demo-agent-rule",
        )
        demo_rule_id = policy_engine.add_rule(demo_rule)
        result = await nl_agent.run_instruction(
            kh, args.instruction,
            policy_engine=policy_engine, policy_rule_id=demo_rule_id,
        )
        answer = nl_agent.final_answer(result)
        print(answer)
        policy_engine.close()

        hashes = extract_hashes(answer)
        for h in hashes:
            tpl = EXPLORERS.get(str(chain_id))
            if tpl:
                print(f"\n  >>> 链上交易: {tpl.format(h)}")

        banner("执行完成")
        if hashes:
            print(f"  产生 {len(hashes)} 笔链上交易，均为 KeeperHub 真实广播。")
        else:
            print("  本次为只读/查询类执行，无链上交易（Agent 已如实说明）。")


if __name__ == "__main__":
    asyncio.run(main())
