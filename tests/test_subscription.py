"""订阅调度器测试：cron 解析 9/9 + 周期幂等键 + 跨重启锚点 + fail-closed（S-10/S-12）。

全部离线运行，不触发真实转账（policy 缺失时直接拒绝）。
"""
import datetime

import pytest

from agent.policy import PolicyEngine, make_demo_rule
from agent.subscription import Cron, SubscriptionConfig, SubscriptionManager
from tests.conftest import VALID_ADDR

UTC = datetime.timezone.utc


# ----------------------------------------------------------------------
# Cron 解析（9 用例）
# ----------------------------------------------------------------------
def test_cron_every_minute():
    c = Cron("* * * * *")
    n = c.next(after=datetime.datetime(2026, 8, 5, 12, 0, 0, tzinfo=UTC))
    assert n == datetime.datetime(2026, 8, 5, 12, 1, 0, tzinfo=UTC)


def test_cron_hourly_on_the_hour():
    c = Cron("0 * * * *")
    n = c.next(after=datetime.datetime(2026, 8, 5, 12, 30, 0, tzinfo=UTC))
    assert n.hour == 13 and n.minute == 0


def test_cron_daily_midnight():
    c = Cron("0 0 * * *")
    n = c.next(after=datetime.datetime(2026, 8, 5, 23, 30, 0, tzinfo=UTC))
    assert (n.day, n.hour, n.minute) == (6, 0, 0)


def test_cron_monthly_first():
    c = Cron("0 0 1 * *")
    n = c.next(after=datetime.datetime(2026, 8, 1, 1, 0, 0, tzinfo=UTC))
    assert n.month == 9 and n.day == 1


def test_cron_weekday_monday():
    # 2026-08-10 是周一
    c = Cron("0 0 * * 1")
    n = c.next(after=datetime.datetime(2026, 8, 5, 0, 0, 0, tzinfo=UTC))
    assert n.weekday() == 0 and n.day == 10


def test_cron_sunday_0_and_7_equivalent():
    # 2026-08-09 是周日
    n0 = Cron("0 0 * * 0").next(after=datetime.datetime(2026, 8, 5, 0, 0, tzinfo=UTC))
    n7 = Cron("0 0 * * 7").next(after=datetime.datetime(2026, 8, 5, 0, 0, tzinfo=UTC))
    assert n0 == n7 and n0.weekday() == 6


def test_cron_step_field():
    c = Cron("*/15 * * * *")
    n = c.next(after=datetime.datetime(2026, 8, 5, 12, 10, 0, tzinfo=UTC))
    assert n.minute == 15


def test_cron_leap_year_feb29():
    c = Cron("0 0 29 2 *")
    n = c.next(after=datetime.datetime(2027, 3, 1, 0, 0, 0, tzinfo=UTC))
    assert (n.year, n.month, n.day) == (2028, 2, 29)


def test_cron_invalid_expr_raises():
    with pytest.raises(ValueError):
        Cron("0 0 1 * * *")  # 6 字段


def test_cron_out_of_range_field_never_fires():
    """越界字段（如 99 分）被解析器过滤，构造不抛错但永不触发。"""
    c = Cron("99 * * * *")
    with pytest.raises(RuntimeError):
        c.next(after=datetime.datetime(2026, 8, 5, 12, 0, 0, tzinfo=UTC))


# ----------------------------------------------------------------------
# 周期幂等键 + 跨重启锚点（S-10）
# ----------------------------------------------------------------------
def test_period_key_deterministic_per_period():
    cfg = SubscriptionConfig(to_address=VALID_ADDR, amount="0.001", cron="0 0 1 * *")
    mgr = SubscriptionManager(None, state_file="/tmp/pk_test.json")
    d1 = datetime.datetime(2026, 8, 1, tzinfo=UTC)
    d2 = datetime.datetime(2026, 9, 1, tzinfo=UTC)
    assert mgr._period_key(cfg.id, d1) == mgr._period_key(cfg.id, d1)
    assert mgr._period_key(cfg.id, d1) != mgr._period_key(cfg.id, d2)
    assert "paykeeper-sub" in mgr._period_key(cfg.id, d1)


def test_cron_anchored_after_last_run():
    """重启后以 last_run 为锚点 -> 绝不重复同一周期。"""
    c = Cron("0 0 1 * *")
    last = datetime.datetime(2026, 8, 1, 1, 0, tzinfo=UTC)  # 8 月 1 日已跑
    nxt = c.next(after=last)
    assert nxt.month == 9, f"下次应跳到 9 月，实际 {nxt}"


# ----------------------------------------------------------------------
# fail-closed（S-12）
# ----------------------------------------------------------------------
def test_add_without_policy_rejected(tmp_path):
    mgr = SubscriptionManager(None, state_file=str(tmp_path / "sub.json"))
    with pytest.raises(ValueError):
        mgr.add(SubscriptionConfig(to_address=VALID_ADDR, amount="0.001"))


def test_add_with_policy_accepted(tmp_path):
    eng = PolicyEngine(":memory:")
    rid = eng.add_rule(make_demo_rule(VALID_ADDR, 0.005))
    mgr = SubscriptionManager(None, state_file=str(tmp_path / "sub.json"))
    sub_id = mgr.add(SubscriptionConfig(
        to_address=VALID_ADDR, amount="0.001",
        policy_engine=eng, policy_rule_id=rid,
    ))
    assert sub_id


def test_run_once_without_policy_rejected(tmp_path):
    """即使绕过 add() 直接塞配置，run_once 也必须拒绝。"""
    mgr = SubscriptionManager(None, state_file=str(tmp_path / "sub.json"))
    mgr._subs["bad"] = SubscriptionConfig(to_address=VALID_ADDR, amount="0.001")
    with pytest.raises(RuntimeError):
        import asyncio
        asyncio.run(mgr.run_once("bad"))
