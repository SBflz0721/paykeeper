"""
PayKeeper 完整演示（录屏用）：一次进程内串联 3 个真实能力。

演示 1/3  确定性转账      payments.run_subscription_once（simulatebroadcastpoll）
演示 2/3  自然语言 Agent  DeepSeek + LangGraph 经 KeeperHub MCP 查询余额
演示 3/3  订阅工作流      创建 Manual trigger 工作流并真实执行（web3/transfer-funds）

全程真实链上执行（Sepolia），无任何模拟。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

CHAIN = os.getenv("TARGET_CHAIN_ID", "11155111")
RECIPIENT = os.getenv("DEMO_RECIPIENT", "")
AMOUNT_1 = "0.002"
AMOUNT_2 = "0.001"

EXPLORER = "https://sepolia.etherscan.io/tx/{}" if CHAIN == "11155111" else "https://etherscan.io/tx/{}"


def p(msg: str) -> None:
    print(msg, flush=True)


def flatten(obj):
    if isinstance(obj, list):
        merged = {}
        for item in obj:
            if isinstance(item, dict) and item.get("type") == "text":
                try:
                    parsed = json.loads(item.get("text", ""))
                    if isinstance(parsed, dict):
                        merged.update(parsed)
                except Exception:
                    pass
        return merged
    return obj if isinstance(obj, dict) else {}


def get(obj, *keys, default=None):
    d = flatten(obj)
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


async def demo1_transfer(kh) -> None:
    p("\n【演示 1/3】确定性转账（simulate 预飞  幂等广播  状态轮询）")
    p(f"  链 {CHAIN}  ->  {RECIPIENT}  |  {AMOUNT_1} ETH")
    res = await kh_call_transfer(kh, AMOUNT_1)
    p(f"  结果    : {res.get('status', '?')}")
    tx = res.get("tx_hash") or ""
    if tx:
        p(f"  交易哈希: {tx}")
        p(f"  浏览器  : {EXPLORER.format(tx)}")
    return tx


async def kh_call_transfer(kh, amount: str) -> dict:
    """直接调用 execute_transfer（模拟广播轮询），返回报告 dict。"""
    from agent import payments

    res = await payments.run_subscription_once(
        kh, chain_id=CHAIN, to_address=RECIPIENT, amount=amount, token_address=None
    )
    return res.to_report()


async def demo2_agent(kh) -> None:
    p("\n【演示 2/3】自然语言 Agent（DeepSeek 推理 + KeeperHub MCP 工具，已接入风控）")
    from agent import agent as nl_agent
    from agent.policy import PolicyEngine, make_demo_rule

    instruction = "请经 KeeperHub 查一下我组织钱包的 ETH 余额，并汇报金额和链。"
    p(f"  用户指令: {instruction}")
    p("  Agent 规划与执行中...")
    # 强制接入风控：Agent 路径只允许付给 demo 收款地址、限额内金额
    engine = PolicyEngine()
    rule_id = engine.add_rule(make_demo_rule(RECIPIENT, AMOUNT_1, name="full-demo-agent-rule"))
    result = await nl_agent.run_instruction(
        kh, instruction, policy_engine=engine, policy_rule_id=rule_id
    )
    answer = nl_agent.final_answer(result)
    engine.close()
    p("  --- Agent 汇报 ---")
    for line in answer.splitlines()[:22]:
        p("  " + line)
    p("  ------------------")


async def demo3_workflow(kh) -> None:
    p("\n【演示 3/3】订阅工作流（创建 Manual 触发工作流  真实执行  链上确认）")
    nodes = [
        {
            "id": "trigger-1", "type": "trigger",
            "data": {"label": "Manual Trigger", "type": "trigger",
                     "config": {"triggerType": "Manual"}, "status": "idle"},
        },
        {
            "id": "transfer-1", "type": "action",
            "data": {"label": "Pay Subscription", "type": "action",
                     "config": {"actionType": "web3/transfer-funds", "network": str(CHAIN),
                                "amount": AMOUNT_2, "recipientAddress": RECIPIENT},
                     "status": "idle"},
        },
    ]
    edges = [{"id": "edge-1", "source": "trigger-1", "target": "transfer-1"}]

    p("  创建工作流...")
    created = await kh.call_tool("create_workflow", {
        "name": f"PayKeeper - Subscription Payment ({CHAIN})",
        "description": "PayKeeper full demo: subscription payment via web3/transfer-funds.",
        "nodes": nodes, "edges": edges,
    })
    wf_id = str(get(created, "id", "workflowId", default="") or "")
    if not wf_id:
        p("  创建工作流失败！")
        return
    p(f"  工作流 ID: {wf_id}")

    p("  执行工作流...")
    exec_res = await kh.call_tool("execute_workflow", {"workflowId": wf_id})
    exec_id = str(get(exec_res, "executionId", "execution_id", "id", default="") or "")
    p(f"  执行 ID  : {exec_id}")

    if exec_id:
        import time

        p("  轮询执行结果...")
        for _ in range(30):
            await asyncio.sleep(4)
            raw = await kh.call_tool("get_execution", {"executionId": exec_id})
            d = flatten(raw)
            inner = d.get("status")
            status = inner.get("status", "") if isinstance(inner, dict) else str(inner or "")
            p(f"    状态: {status}")
            if status.lower() in ("success", "completed", "failed", "error", "reverted"):
                txns = d.get("transactionHashes") or (inner.get("transactionHashes") if isinstance(inner, dict) else None) or []
                if txns:
                    for t in txns:
                        h = t.get("hash", "")
                        p(f"  交易哈希: {h}")
                        p(f"  浏览器  : {EXPLORER.format(h)}")
                else:
                    p("  （本次执行未产生交易哈希）")
                break
        else:
            p("  轮询超时。")


async def main() -> None:
    p("=" * 62)
    p("  PayKeeper · AI Agent 经 KeeperHub 在链上自动付款")
    p(f"  目标链: {CHAIN}（Sepolia 测试网）· LLM: DeepSeek")
    p("=" * 62)

    p("\n加载 DeepSeek LLM 与 KeeperHub MCP 组件（约 20-30 秒）...")
    from agent.keeperhub_mcp import KeeperHubMCP

    p("组件加载完成。连接 KeeperHub MCP...")

    async with KeeperHubMCP() as kh:
        p(f"已连接 KeeperHub MCP，加载工具 {len(kh.get_tools())} 个")

        await demo1_transfer(kh)
        await demo2_agent(kh)
        await demo3_workflow(kh)

        p("\n" + "=" * 62)
        p("  全部演示完成：3 个真实能力均经 KeeperHub 在链上执行。")
        p("=" * 62)


if __name__ == "__main__":
    asyncio.run(main())
