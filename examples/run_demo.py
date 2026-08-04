"""
PayKeeper 演示入口。

运行方式：
    cp .env.example .env   # 填入 KEEPERHUB_API_KEY 与 LLM key
    python examples/run_demo.py                 # 默认：跑一次真实转账 + 一条 NL 指令
    python examples/run_demo.py --instruction "查 0x.. 的 ETH 余额"   # 仅跑 Agent

产出：
    - 一条经 KeeperHub 真实执行的链上交易（哈希 + 浏览器链接）
    - Agent 的执行报告
    - examples/output/last_run.json（提交时可附）

注意：首次实跑前请确认 .env 里 DEMO_RECIPIENT 换成你控制的地址、目标链已选好。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from agent.keeperhub_mcp import KeeperHubMCP
from agent import payments
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


def explorer_url(chain_id: str, tx_hash: str) -> str:
    tpl = EXPLORERS.get(str(chain_id))
    return tpl.format(tx_hash) if tpl and tx_hash else ""


async def run_demo_instruction(
    kh: KeeperHubMCP, instruction: str, policy_engine, policy_rule_id: str
) -> str:
    print(f"\n=== Agent 执行自然语言指令 ===\n> {instruction}\n")
    result = await nl_agent.run_instruction(
        kh, instruction,
        policy_engine=policy_engine, policy_rule_id=policy_rule_id,
    )
    answer = nl_agent.final_answer(result)
    print(answer)
    return answer


async def main() -> None:
    parser = argparse.ArgumentParser(description="PayKeeper demo")
    parser.add_argument(
        "--instruction",
        default="请经 KeeperHub 查一下我组织钱包的 ETH 余额，并汇报。",
        help="传给 Agent 的自然语言指令",
    )
    parser.add_argument("--skip-transfer", action="store_true", help="跳过确定性转账演示")
    args = parser.parse_args()

    chain_id = os.getenv("TARGET_CHAIN_ID", "11155111")
    recipient = os.getenv("DEMO_RECIPIENT", "")
    amount = os.getenv("DEMO_AMOUNT", "0.01")
    token = os.getenv("DEMO_TOKEN_ADDRESS", "") or None

    report: dict = {"generated_at": datetime.now(timezone.utc).isoformat(), "chain_id": chain_id}

    async with KeeperHubMCP() as kh:
        print(f"已连接 KeeperHub MCP，加载工具 {len(kh.get_tools())} 个：{kh.tool_names()}")

        # ---- 1) 确定性真实交易（保证提交有链上交易）----
        if not args.skip_transfer:
            if not recipient or recipient.startswith("0x0000"):
                print("\n[跳过] DEMO_RECIPIENT 未配置（仍是零地址）。请在 .env 设置一个你控制的地址后再跑转账。")
            else:
                print(f"\n=== 确定性转账（经 KeeperHub 真实执行）===\n链 {chain_id} -> {recipient} | {amount} {token or '原生币'}")
                res = await payments.run_subscription_once(
                    kh, chain_id=chain_id, to_address=recipient, amount=amount, token_address=token
                )
                print(json.dumps(res.to_report(), indent=2, ensure_ascii=False))
                if res.tx_hash:
                    print(f"交易浏览器: {explorer_url(chain_id, res.tx_hash)}")
                report["transfer"] = res.to_report()
                report["tx_hash"] = res.tx_hash
                report["tx_explorer"] = explorer_url(chain_id, res.tx_hash)

        # ---- 2) 自然语言 Agent 演示（强制接入风控：Agent 只能付给白名单地址、限额内金额）----
        policy_engine = PolicyEngine()
        demo_rule = make_demo_rule(recipient, amount, name="demo-agent-rule")
        demo_rule_id = policy_engine.add_rule(demo_rule)
        print(
            f"\n[风控] Agent 路径已接入: 白名单={demo_rule.whitelist or '空(不放行)'} "
            f"单笔限额={demo_rule.single_limit_wei / 1e18} ETH"
        )
        answer = await run_demo_instruction(kh, args.instruction, policy_engine, demo_rule_id)
        report["agent_answer"] = answer
        policy_engine.close()

    # 落盘
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "last_run.json")
    with open(out_path, "w", encoding="utf") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n运行结果已写入: {out_path}")

    if not report.get("tx_hash"):
        print("\n[提示] 本次未产生真实交易哈希。提交前请确保跑通一次真实 execute_transfer（配置 DEMO_RECIPIENT）。")


if __name__ == "__main__":
    asyncio.run(main())
