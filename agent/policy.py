"""
风控引擎（Risk Control / Policy Layer）。

在「自然语言 -> 链上执行」之间加一层强制校验，防止 LLM 理解错误或恶意指令导致
超限 / 打错地址 / 绕过限额：

  校验链（任一不过即拒绝）：
    [1] 地址格式            -> 必须 0x + 40 位 hex
    [2] 规则存在且启用      -> enabled = true
    [3] 白名单              -> to_address 必须在 whitelist（空 = 不限制）
    [4] 单笔限额            -> amount <= single_limit_wei
    [5] 每日累计限额        -> 当日已成功花费 + amount <= daily_limit_wei

持久化：SQLite（标准库 sqlite3，零额外依赖）
  - rules:      风控规则定义
  - executions: 执行记录（含 tx_hash / status），用于当日累计与审计

用法：
    engine = PolicyEngine("data/paykeeper.db")
    rule_id = engine.add_rule(PolicyRule(name="DAO 周薪", whitelist=[...],
                                         single_limit_wei=..., daily_limit_wei=...))
    verdict = engine.check(rule_id, to_address="0x...", amount_wei=123)
    if verdict.ok:
        # ... 执行链上转账 ...
        engine.record_success(rule_id, amount_wei, tx_hash)
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")

# 默认 SQLite 路径（可用 PAYKEEPER_POLICY_DB 覆盖）
DEFAULT_DB = os.environ.get(
    "PAYKEEPER_POLICY_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "policy.db"),
)


@dataclass
class PolicyRule:
    name: str
    whitelist: list[str] = field(default_factory=list)   # 空 = 不限制
    single_limit_wei: int = 0                            # 0 = 不限制
    daily_limit_wei: int = 0                             # 0 = 不限制
    cron: str | None = None                              # 可选定时（配合 subscription）
    enabled: bool = True
    id: str = field(default_factory=lambda: f"rule-{uuid.uuid4().hex[:10]}")
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))


@dataclass
class PolicyVerdict:
    ok: bool
    reason: str = ""
    rule_id: str = ""


class PolicyEngine:
    """风控引擎：规则管理 + 执行前校验 + 执行后记账。"""

    def __init__(self, db_path: str = DEFAULT_DB):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._db = sqlite3.connect(db_path)
        self._db.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS rules (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                whitelist TEXT NOT NULL DEFAULT '[]',
                single_limit_wei INTEGER NOT NULL DEFAULT 0,
                daily_limit_wei INTEGER NOT NULL DEFAULT 0,
                cron TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id TEXT,
                to_address TEXT NOT NULL,
                amount_wei TEXT NOT NULL,
                status TEXT NOT NULL,           -- pending | success | rejected | failed
                tx_hash TEXT,
                error TEXT,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_exec_rule_day
                ON executions(rule_id, status, created_at);
            """
        )
        self._db.commit()

    # ------------------------------------------------------------------
    # 规则管理
    # ------------------------------------------------------------------
    def add_rule(self, rule: PolicyRule) -> str:
        # 白名单严格校验：任一非法地址直接拒绝，绝不静默删除
        # （静默删除会把「受限」规则悄悄变成「不限」，是安全回归）
        for addr in rule.whitelist:
            if not ADDRESS_RE.match(addr):
                raise ValueError(f"白名单地址非法（需 0x+40 位 hex）: {addr!r}")
        self._db.execute(
            "INSERT INTO rules (id, name, whitelist, single_limit_wei, daily_limit_wei,"
            " cron, enabled, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                rule.id, rule.name,
                json.dumps(rule.whitelist),
                rule.single_limit_wei, rule.daily_limit_wei, rule.cron,
                1 if rule.enabled else 0, rule.created_at,
            ),
        )
        self._db.commit()
        return rule.id

    def get_rule(self, rule_id: str) -> dict | None:
        row = self._db.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
        return self._row_to_rule(row) if row else None

    def list_rules(self) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM rules ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_rule(r) for r in rows]

    def set_enabled(self, rule_id: str, enabled: bool) -> bool:
        cur = self._db.execute(
            "UPDATE rules SET enabled = ? WHERE id = ?", (1 if enabled else 0, rule_id)
        )
        self._db.commit()
        return cur.rowcount > 0

    def delete_rule(self, rule_id: str) -> bool:
        cur = self._db.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
        self._db.commit()
        return cur.rowcount > 0

    @staticmethod
    def _row_to_rule(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "whitelist": json.loads(row["whitelist"]),
            "single_limit_wei": row["single_limit_wei"],
            "daily_limit_wei": row["daily_limit_wei"],
            "cron": row["cron"],
            "enabled": bool(row["enabled"]),
            "created_at": row["created_at"],
        }

    # ------------------------------------------------------------------
    # 执行前校验（核心）
    # ------------------------------------------------------------------
    def check(
        self, rule_id: str, to_address: str, amount_wei: int
    ) -> PolicyVerdict:
        if not ADDRESS_RE.match(to_address):
            return PolicyVerdict(False, f"地址格式非法: {to_address}", rule_id)

        rule = self.get_rule(rule_id)
        if rule is None:
            return PolicyVerdict(False, f"规则不存在: {rule_id}", rule_id)
        if not rule["enabled"]:
            return PolicyVerdict(False, f"规则已禁用: {rule['name']}", rule_id)

        # 白名单（空 = 不限制）
        whitelist = rule["whitelist"]
        if whitelist and to_address.lower() not in {a.lower() for a in whitelist}:
            return PolicyVerdict(
                False, f"收款地址不在白名单: {to_address}", rule_id
            )

        # 单笔限额
        single = rule["single_limit_wei"]
        if single > 0 and amount_wei > single:
            return PolicyVerdict(
                False,
                f"金额超过单笔限额: {amount_wei} > {single}",
                rule_id,
            )

        # 每日累计限额
        daily = rule["daily_limit_wei"]
        if daily > 0:
            spent = self.today_spent(rule_id)
            if spent + amount_wei > daily:
                return PolicyVerdict(
                    False,
                    f"超过每日累计限额: 已花 {spent} + {amount_wei} > 限额 {daily}",
                    rule_id,
                )

        return PolicyVerdict(True, "", rule_id)

    def today_spent(self, rule_id: str) -> int:
        """当日（UTC）该规则已成功花费金额（wei）。"""
        day_start = int(time.time()) // 86400 * 86400 * 1000  # 精确到毫秒的当日起点
        row = self._db.execute(
            "SELECT COALESCE(SUM(CAST(amount_wei AS INTEGER)), 0) AS total"
            " FROM executions WHERE rule_id = ? AND status = 'success' AND created_at >= ?",
            (rule_id, day_start),
        ).fetchone()
        return int(row["total"] or 0)

    # ------------------------------------------------------------------
    # 执行记账（供集成层调用）
    # ------------------------------------------------------------------
    def record(
        self,
        rule_id: str,
        to_address: str,
        amount_wei: int,
        status: str,
        tx_hash: str = "",
        error: str = "",
    ) -> int:
        cur = self._db.execute(
            "INSERT INTO executions (rule_id, to_address, amount_wei, status, tx_hash,"
            " error, created_at) VALUES (?,?,?,?,?,?,?)",
            (rule_id, to_address, str(amount_wei), status, tx_hash or None,
             error or None, int(time.time() * 1000)),
        )
        self._db.commit()
        return int(cur.lastrowid)

    def record_success(self, rule_id: str, to_address: str, amount_wei: int, tx_hash: str) -> int:
        return self.record(rule_id, to_address, amount_wei, "success", tx_hash=tx_hash)

    def list_executions(self, limit: int = 50) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM executions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._db.close()


def make_demo_rule(
    recipient: str,
    amount_eth: float | str,
    daily_eth: float | str | None = None,
    name: str = "demo-rule",
) -> PolicyRule:
    """构建一个演示用风控规则：白名单仅允许 demo 收款地址，限额 = 演示金额。

    用于给「自然语言 Agent」演示路径接上风控（否则 Agent 可被提示词注入任意转账）。
    金额用 Decimal 转换，避免 float 精度误差。
    """
    from decimal import Decimal, InvalidOperation

    try:
        single = int(Decimal(str(amount_eth)) * Decimal(10) ** 18)
        daily = int(Decimal(str(daily_eth if daily_eth is not None else float(amount_eth) * 2)) * Decimal(10) ** 18)
    except (InvalidOperation, ValueError, TypeError) as e:
        raise ValueError(f"演示金额非法: {amount_eth!r} / {daily_eth!r}") from e
    whitelist = [recipient] if ADDRESS_RE.match(recipient) else []
    return PolicyRule(
        name=name,
        whitelist=whitelist,
        single_limit_wei=single,
        daily_limit_wei=daily,
    )
