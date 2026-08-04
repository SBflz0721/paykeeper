"""
真正的订阅调度器（本地定时器）。

订阅场景有两种调度方案：

方案 A（平台侧 · 生产推荐）
    KeeperHub Workflow 配置 triggerType=Schedule + scheduleCron，
    到点由 KeeperHub 平台自动触发 web3/transfer-funds。创建后无需本地进程常驻。

方案 B（本地调度器 · 本文件）
    在 Agent 进程内用 cron 轮询：到点自动调用 payments.execute_transfer（真实上链），
    复用可靠性层（simulate -> 幂等广播 -> 轮询 -> 审计轨迹）。
    适合：演示、无平台调度时的兜底、需要与 Agent 推理联动的场景。

用法：
    from agent.subscription import SubscriptionManager, SubscriptionConfig

    mgr = SubscriptionManager(kh)
    mgr.add(SubscriptionConfig(
        chain_id="11155111",
        to_address="0x...",
        amount="0.001",
        cron="0 0 1 * *",          # 每月 1 号 00:00 UTC
    ))
    await mgr.run_forever()        # 阻塞直到被取消
    await mgr.run_once("sub-id")   # 立即执行一次（演示/手动触发）
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .keeperhub_mcp import KeeperHubMCP
from .payments import PaymentResult, execute_transfer

UTC = timezone.utc


# ----------------------------------------------------------------------
# cron 解析（标准库实现，5 字段：分 时 日 月 周）
# ----------------------------------------------------------------------
def _parse_field(field: str, lo: int, hi: int) -> set[int]:
    """解析单字段：支持 * 、固定值、range(a-b)、step(a/b) 与组合(a,b)。"""
    allowed: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if part == "*":
            allowed.update(range(lo, hi + 1))
        elif "/" in part:
            base, step = part.split("/", 1)
            step = int(step)
            if base == "*":
                rng = range(lo, hi + 1)
            elif "-" in base:
                a, b = base.split("-")
                rng = range(int(a), int(b) + 1)
            else:
                rng = range(int(base), hi + 1)
            allowed.update(rng[::step])
        elif "-" in part:
            a, b = part.split("-", 1)
            allowed.update(range(int(a), int(b) + 1))
        else:
            allowed.add(int(part))
    return {v for v in allowed if lo <= v <= hi}


class Cron:
    """最小 cron 解析器：next(after_dt) 返回下一个触发时刻（UTC）。"""

    def __init__(self, expr: str):
        parts = expr.split()
        if len(parts) != 5:
            raise ValueError(f"cron 需 5 字段（分 时 日 月 周），收到: {expr!r}")
        self.minutes = _parse_field(parts[0], 0, 59)
        self.hours = _parse_field(parts[1], 0, 23)
        self.days = _parse_field(parts[2], 1, 31)
        self.months = _parse_field(parts[3], 1, 12)
        # 周日=0 或 7 都视为周日；cron 周字段 0-6（1=周一）。
        # Python weekday(): 0=周一 ... 6=周日，故转成 (cron_wd + 6) % 7。
        self.weekdays = {(w % 7 + 6) % 7 for w in _parse_field(parts[4], 0, 7)}

    def next(self, after: datetime | None = None) -> datetime:
        after = after or datetime.now(UTC)
        after = after.astimezone(UTC)
        # 暴力枚举未来 5 年，取第一个匹配（足够演示与一般订阅）
        candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(5 * 366 * 24 * 60):
            if (
                candidate.minute in self.minutes
                and candidate.hour in self.hours
                and candidate.month in self.months
                and candidate.day in self.days
                and candidate.weekday() in self.weekdays
            ):
                return candidate
            candidate += timedelta(minutes=1)
        raise RuntimeError(f"5 年内找不到 cron 触发时间: {self}")

    def __repr__(self) -> str:
        return f"Cron({self.minutes} {self.hours} {self.days} {self.months} {self.weekdays})"


# ----------------------------------------------------------------------
# 订阅配置与结果
# ----------------------------------------------------------------------
@dataclass
class SubscriptionConfig:
    to_address: str
    amount: str
    cron: str = "0 0 1 * *"  # 默认每月 1 号 00:00 UTC
    chain_id: str = "11155111"
    token_address: str | None = None
    name: str = ""
    # 风控（可选但强烈建议）：到点自动执行前强制校验
    policy_engine: Any = None
    policy_rule_id: str = ""

    def __post_init__(self) -> None:
        self.id: str = self.name or f"sub-{uuid.uuid4().hex[:10]}"
        self.cron_obj: Cron = Cron(self.cron)


@dataclass
class SubscriptionRun:
    sub_id: str
    due_at: str
    result: PaymentResult
    ts: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# ----------------------------------------------------------------------
# 订阅管理器
# ----------------------------------------------------------------------
class SubscriptionManager:
    """管理多个订阅：每个订阅一个 asyncio 任务，到点自动执行。

    防重复付款设计：
    - 每个周期派生确定性幂等键 `paykeeper-sub:{sub_id}:{周期}`，
      即使两个实例/进程同时触发同一周期，KeeperHub 也会按 key 去重；
    - 上次运行时间持久化到 state 文件，重启后以「上次运行」为锚点计算下次触发，
      不会把已经付过的周期再付一次。
    """

    def __init__(self, kh: KeeperHubMCP, check_interval: float = 15.0,
                 state_file: str | None = None):
        self.kh = kh
        self.check_interval = check_interval
        if state_file is None:
            state_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data", "subscriptions.json",
            )
        self.state_file = state_file
        self._subs: dict[str, SubscriptionConfig] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self.history: list[SubscriptionRun] = []
        self._state: dict[str, dict] = self._load_state()

    # -- 状态持久化（防跨重启重复付同一周期）----------------------------------
    def _load_state(self) -> dict[str, dict]:
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    def _save_state(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # 状态写失败不致命（幂等键仍防双付，只是重启后可能重算锚点）

    def _last_run(self, sub_id: str) -> str:
        return str(self._state.get(sub_id, {}).get("last_run", ""))

    def _period_key(self, sub_id: str, due_at: datetime) -> str:
        # 确定性幂等键：同一订阅同一周期永远同 key，跨实例/跨重启去重
        return f"paykeeper-sub:{sub_id}:{due_at.isoformat()}"

    # -- 管理 ----------------------------------------------------------
    def add(self, cfg: SubscriptionConfig) -> str:
        self._subs[cfg.id] = cfg
        return cfg.id

    def remove(self, sub_id: str) -> None:
        self._subs.pop(sub_id, None)
        task = self._tasks.pop(sub_id, None)
        if task and not task.done():
            task.cancel()

    def list(self) -> list[dict]:
        return [
            {
                "id": cfg.id, "to": cfg.to_address, "amount": cfg.amount,
                "cron": cfg.cron, "chain_id": cfg.chain_id,
                "next": self.next_run(cfg.id), "last_run": self._last_run(cfg.id),
            }
            for cfg in self._subs.values()
        ]

    def next_run(self, sub_id: str) -> str:
        cfg = self._subs.get(sub_id)
        if not cfg:
            return ""
        anchor = self._last_run(sub_id)
        after = None
        if anchor:
            try:
                after = datetime.fromisoformat(anchor)
            except Exception:
                after = None
        return cfg.cron_obj.next(after=after).isoformat()

    # -- 执行 ----------------------------------------------------------
    async def run_once(self, sub_id: str, due_at: datetime | None = None) -> PaymentResult:
        """立即执行一次订阅付款（手动触发 / 演示 / 补跑）。

        due_at 指定本周期归属（调度器传入计划触发时刻；手动触发默认当前时刻）。
        同一 (sub_id, due_at) 会复用同一幂等键，跨重启/并发不重复付款。
        """
        cfg = self._subs.get(sub_id)
        if not cfg:
            raise KeyError(f"未知订阅: {sub_id}")
        due = (due_at or datetime.now(UTC)).astimezone(UTC)
        result = await execute_transfer(
            self.kh,
            chain_id=cfg.chain_id,
            to_address=cfg.to_address,
            amount=cfg.amount,
            token_address=cfg.token_address,
            policy_engine=cfg.policy_engine,
            policy_rule_id=cfg.policy_rule_id,
            idempotency_key=self._period_key(sub_id, due),
        )
        # 记录周期归属，作为下次调度的锚点
        self._state[sub_id] = {"last_run": due.isoformat()}
        self._save_state()
        self.history.append(
            SubscriptionRun(sub_id=sub_id, due_at=due.isoformat(), result=result)
        )
        return result

    async def _loop(self, sub_id: str) -> None:
        cfg = self._subs.get(sub_id)
        if not cfg:
            return
        # 锚点 = 上次运行周期；重启后从该周期之后继续，避免重复付同一期
        anchor = None
        last = self._last_run(sub_id)
        if last:
            try:
                anchor = datetime.fromisoformat(last)
            except Exception:
                anchor = None
        while True:
            try:
                nxt = cfg.cron_obj.next(after=anchor or datetime.now(UTC))
                while True:
                    await asyncio.sleep(min(self.check_interval, 5.0))
                    if datetime.now(UTC) >= nxt:
                        break
                result = await self.run_once(sub_id, due_at=nxt)
                anchor = nxt
                # 记录并输出；失败不打断调度（下一周期会再次尝试）
                print(
                    f"[sub:{sub_id}] {datetime.now(UTC).isoformat()} "
                    f"ok={result.ok} status={result.status} tx={result.tx_hash or result.error}",
                    flush=True,
                )
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001 —— 调度器不因单次异常退出
                print(f"[sub:{sub_id}] error: {e}", flush=True)
                await asyncio.sleep(30)

    async def run_forever(self) -> None:
        """启动所有订阅的调度任务，直到取消。"""
        for sub_id in list(self._subs.keys()):
            if sub_id not in self._tasks or self._tasks[sub_id].done():
                self._tasks[sub_id] = asyncio.create_task(self._loop(sub_id))
        await asyncio.gather(*self._tasks.values())
