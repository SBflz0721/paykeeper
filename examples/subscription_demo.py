"""
订阅付款演示 —— 真正的定时器（两种调度方案）。

方案 A：KeeperHub Schedule 工作流（平台侧自动触发）
    - 创建 triggerType=Schedule + cron 的工作流，到点由 KeeperHub 自动执行
    - 适合生产：无需本地进程常驻

方案 B：本地订阅调度器（本演示重点）
    - agent/subscription.py 实现 cron 轮询
    - 到点自动调用 execute_transfer（simulate -> 幂等广播 -> 轮询 -> 审计）
    - 适合：演示 / 与 Agent 推理联动 / 平台无调度时的兜底

用法：
    python examples/subscription_demo.py                    # 立即执行一次 + 显示下次触发
    python examples/subscription_demo.py --wait             # 额外等待下一次定时触发并执行
    python examples/subscription_demo.py --cron "0 0 1 * *" # 自定义 cron
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from agent.keeperhub_mcp import KeeperHubMCP
from agent.subscription import SubscriptionConfig, SubscriptionManager
from agent.policy import PolicyEngine, make_demo_rule


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cron", default="* * * * *", help="订阅 cron（默认每分钟）")
    parser.add_argument("--wait", action="store_true", help="等待下一次定时触发并执行")
    args = parser.parse_args()

    chain = os.getenv("TARGET_CHAIN_ID", "11155111")
    recipient = os.getenv("DEMO_RECIPIENT", "")
    amount = os.getenv("DEMO_AMOUNT", "0.001")
    if not recipient or recipient.startswith("0x0000"):
        print("[跳过] 请在 .env 设置 DEMO_RECIPIENT")
        return

    async with KeeperHubMCP() as kh:
        # 订阅接入风控：只允许付给 demo 收款地址、限额内金额
        engine = PolicyEngine()
        rule_id = engine.add_rule(make_demo_rule(recipient, amount, name="sub-demo-rule"))
        mgr = SubscriptionManager(kh, check_interval=5.0)
        sub_id = mgr.add(SubscriptionConfig(
            name="demo-sub",
            chain_id=chain,
            to_address=recipient,
            amount=amount,
            cron=args.cron,
            policy_engine=engine,
            policy_rule_id=rule_id,
        ))
        print("=" * 62)
        print("  PayKeeper 订阅调度器演示（已接入风控）")
        print(f"  收款方 : {recipient} | 金额 {amount} {os.getenv('DEMO_TOKEN_ADDRESS') or 'ETH'}")
        print(f"  cron   : {args.cron} | 下次触发 {mgr.next_run(sub_id)}")
        print("=" * 62)

        # 1) 立即执行一次（产生真实交易；周期幂等键防止跨重启/并发双付）
        print("\n[1] 立即执行一次（run_once，真实上链）...")
        res = await mgr.run_once(sub_id)
        print(json.dumps(res.to_report(), indent=2, ensure_ascii=False))
        if res.tx_hash:
            print(f"交易浏览器: https://sepolia.etherscan.io/tx/{res.tx_hash}")

        # 2) 等待下一次定时触发（可选）
        if args.wait:
            nxt = mgr.next_run(sub_id)
            print(f"\n[2] 等待下一次定时触发: {nxt} ...")
            await mgr._loop(sub_id)  # noqa: SLF001 —— 演示调度循环
            print("下一次触发已执行（见上方日志）")

        print("\n调度器会持续按 cron 自动付款。取消任务即停止。")
        engine.close()


if __name__ == "__main__":
    asyncio.run(main())
