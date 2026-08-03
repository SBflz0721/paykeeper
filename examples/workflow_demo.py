"""
演示 KeeperHub 工作流能力：创建 -> 校验 -> 执行 -> 轮询。

创建一个 Manual 触发器 + web3/transfer-funds 的工作流（"订阅付款"），
经 KeeperHub 执行一次真实链上转账，并返回 get_execution 的执行日志与交易哈希。

读取 .env：TARGET_CHAIN_ID / DEMO_RECIPIENT / DEMO_AMOUNT。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from agent.keeperhub_mcp import KeeperHubMCP


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
                    merged.setdefault("_raw", item.get("text", ""))
        return merged
    if isinstance(obj, dict):
        return obj
    return {}


def get(obj, *keys, default=None):
    d = flatten(obj)
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


async def main() -> None:
    chain = os.getenv("TARGET_CHAIN_ID", "11155111")
    recipient = os.getenv("DEMO_RECIPIENT", "")
    amount = os.getenv("DEMO_AMOUNT", "0.0001")
    trigger_kind = os.getenv("WORKFLOW_TRIGGER", "manual").lower()
    cron = os.getenv("WORKFLOW_CRON", "0 0 1 * *")  # 每月 1 号 0 点（默认）

    if not recipient or recipient.startswith("0x0000"):
        print("[跳过] 请在 .env 设置 DEMO_RECIPIENT")
        return

    if trigger_kind == "schedule":
        trigger_cfg = {"triggerType": "Schedule", "scheduleCron": cron, "scheduleTimezone": "UTC"}
        trigger_label = f"Schedule ({cron})"
    else:
        trigger_cfg = {"triggerType": "Manual"}
        trigger_label = "Manual Trigger"

    nodes = [
        {
            "id": "trigger-1",
            "type": "trigger",
            "data": {
                "label": trigger_label,
                "type": "trigger",
                "config": trigger_cfg,
                "status": "idle",
            },
        },
        {
            "id": "transfer-1",
            "type": "action",
            "data": {
                "label": "Pay Subscription",
                "type": "action",
                "config": {
                    "actionType": "web3/transfer-funds",
                    "network": str(chain),
                    "amount": str(amount),
                    "recipientAddress": recipient,
                },
                "status": "idle",
            },
        },
    ]
    edges = [{"id": "edge-1", "source": "trigger-1", "target": "transfer-1"}]

    async with KeeperHubMCP() as kh:
        # 1) 创建
        print("== 1) create_workflow ==")
        created = await kh.call_tool(
            "create_workflow",
            {
                "name": f"PayKeeper - Subscription Payment ({chain})",
                "description": "PayKeeper demo: manual-triggered subscription payment via web3/transfer-funds.",
                "nodes": nodes,
                "edges": edges,
            },
        )
        print(json.dumps(flatten(created), indent=2, ensure_ascii=False)[:800])
        wf_id = str(get(created, "id", "workflowId", default="") or "")
        if not wf_id:
            print("创建失败，未拿到 workflow id。")
            return

        # 2) 校验
        print("\n== 2) validate_workflow ==")
        try:
            val = await kh.call_tool("validate_workflow", {"workflowId": wf_id})
            print(json.dumps(flatten(val), indent=2, ensure_ascii=False)[:800])
        except Exception as e:
            print("validate 失败:", str(e)[:400])

        # 3) 执行
        print("\n== 3) execute_workflow ==")
        exec_res = await kh.call_tool("execute_workflow", {"workflowId": wf_id})
        print(json.dumps(flatten(exec_res), indent=2, ensure_ascii=False)[:800])
        exec_id = str(get(exec_res, "executionId", "execution_id", "id", default="") or "")

        # 4) 轮询结果
        print("\n== 4) get_execution 轮询 ==")
        if exec_id:
            last = {}
            for _ in range(30):
                await asyncio.sleep(4)
                raw = await kh.call_tool("get_execution", {"executionId": exec_id})
                d = flatten(raw)
                # get_execution 返回嵌套 {status:{status:...}, ...}
                inner = d.get("status")
                if isinstance(inner, dict):
                    status = str(inner.get("status", ""))
                    last = {**d, **inner}
                else:
                    status = str(inner or "")
                    last = d
                print("status:", status)
                if status.lower() in ("success", "completed", "failed", "error", "reverted"):
                    txns = last.get("transactionHashes") or d.get("transactionHashes") or []
                    print(json.dumps(d, indent=2, ensure_ascii=False)[:1500])
                    if txns:
                        print("\n交易哈希汇总:")
                        for t in txns:
                            print(" -", t.get("hash"), "| gas:", t.get("gasUsed"), "| verified:", t.get("verified"))
                    break
            else:
                print("超时未完成，最后状态:", json.dumps(last, indent=2, ensure_ascii=False)[:800])


if __name__ == "__main__":
    asyncio.run(main())
