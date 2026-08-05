"""Agent 资金工具风控包装器测试（对应 AUDIT「包装器 5/5」）。

全部离线运行：使用 fake tool 替换真实 KeeperHub 工具，验证风控拦截时
底层工具绝不被调用（fail-closed，S-05）。
"""
import asyncio

import pytest
from pydantic import BaseModel, Field

from agent.agent import _wrap_policy_tool
from agent.policy import PolicyEngine, make_demo_rule
from tests.conftest import VALID_ADDR


class TransferArgs(BaseModel):
    """模拟真实 KeeperHub execute_transfer 工具的 args_schema。"""

    chain_id: str
    to_address: str
    amount: str
    token_address: str | None = None


class FakeTool:
    """模拟 LangChain StructuredTool：记录是否被底层调用。"""

    def __init__(self, name: str = "execute_transfer"):
        self.name = name
        self.description = "fake keeperhub tool"
        self.args_schema = TransferArgs
        self.calls: list[dict] = []
        self.func = self._func

    async def _func(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True, "tx_hash": "0x" + "ab" * 32, "status": "completed"}


def build():
    eng = PolicyEngine(":memory:")
    rid = eng.add_rule(make_demo_rule(VALID_ADDR, 0.01))  # 单笔 0.01 ETH
    return eng, rid


async def _wrap(tool=None):
    eng, rid = build()
    return await _wrap_policy_tool(tool or FakeTool(), eng, rid, set()), eng, rid


def test_rejects_non_whitelist_address():
    t = FakeTool()
    wrapped, _, _ = asyncio.run(_wrap(t))
    out = asyncio.run(wrapped.ainvoke({
        "chain_id": "11155111",
        "to_address": "0x1111111111111111111111111111111111111111",
        "amount": "0.001",
    }))
    assert not out["ok"] and "风控拦截" in out["error"]
    assert t.calls == [], "风控拒绝时底层工具绝不能被调用"


def test_rejects_mainnet_chain():
    t = FakeTool()
    wrapped, _, _ = asyncio.run(_wrap(t))
    out = asyncio.run(wrapped.ainvoke({
        "chain_id": "1",
        "to_address": VALID_ADDR,
        "amount": "0.001",
    }))
    assert not out["ok"] and "允许名单" in out["error"]
    assert t.calls == []


def test_rejects_over_limit_amount():
    t = FakeTool()
    wrapped, _, _ = asyncio.run(_wrap(t))
    out = asyncio.run(wrapped.ainvoke({
        "chain_id": "11155111",
        "to_address": VALID_ADDR,
        "amount": "5.0",  # 远超 0.01 单笔限额
    }))
    assert not out["ok"] and "限额" in out["error"]
    assert t.calls == []


def test_rejects_bad_amount():
    t = FakeTool()
    wrapped, _, _ = asyncio.run(_wrap(t))
    out = asyncio.run(wrapped.ainvoke({
        "chain_id": "11155111",
        "to_address": VALID_ADDR,
        "amount": "abc",
    }))
    assert not out["ok"] and "金额" in out["error"]
    assert t.calls == []


def test_rejects_missing_chain_id():
    """缺 chain_id 时，schema 层（必填）直接拒绝——同样是 fail-closed。"""
    t = FakeTool()
    wrapped, _, _ = asyncio.run(_wrap(t))
    with pytest.raises(Exception):
        asyncio.run(wrapped.ainvoke({
            "to_address": VALID_ADDR,
            "amount": "0.001",
        }))
    assert t.calls == [], "底层工具绝不能被调用"


def test_valid_args_reach_underlying_tool():
    t = FakeTool()
    wrapped, eng, rid = asyncio.run(_wrap(t))
    out = asyncio.run(wrapped.ainvoke({
        "chain_id": "11155111",
        "to_address": VALID_ADDR,
        "amount": "0.001",
    }))
    assert out["ok"] and len(t.calls) == 1, "合法参数应触达底层"
    # 成功后应记账（每日限额生效）
    rows = eng.list_executions()
    assert len(rows) == 1 and rows[0]["status"] == "success"


def test_build_agent_requires_policy():
    """S-05：不传 policy 直接构建 Agent 必须失败。"""
    import agent.agent as nl_agent

    with pytest.raises(RuntimeError):
        asyncio.run(nl_agent.build_agent(None))
