"""风控引擎测试（对应 AUDIT_REPORT 声称的「风控 8/8」）。

全部离线运行：PolicyEngine 使用 :memory: SQLite，不触碰网络 / KeeperHub。
"""
import pytest

from agent.policy import PolicyEngine, PolicyRule, make_demo_rule, ADDRESS_RE
from tests.conftest import VALID_ADDR


def make_rule(**kw) -> PolicyRule:
    base = dict(
        name="t",
        whitelist=[VALID_ADDR],
        single_limit_wei=10**16,   # 0.01 ETH
        daily_limit_wei=10**17,    # 0.1 ETH
    )
    base.update(kw)
    return PolicyRule(**base)


def test_whitelist_rejects_invalid_address():
    """非法白名单地址必须拒绝创建（S-09：绝不静默删除变成'不限'）。"""
    eng = PolicyEngine(":memory:")
    with pytest.raises(ValueError):
        eng.add_rule(make_rule(whitelist=["not-an-address"]))


def test_whitelist_accepts_valid_address():
    eng = PolicyEngine(":memory:")
    rid = eng.add_rule(make_rule())
    assert eng.get_rule(rid)["id"] == rid


def test_unrestricted_rule_rejected():
    """空白名单 + 0 限额 = 全开放，必须拒绝（S-13）。"""
    eng = PolicyEngine(":memory:")
    with pytest.raises(ValueError):
        eng.add_rule(make_rule(whitelist=[], single_limit_wei=0, daily_limit_wei=0))


def test_non_whitelist_address_blocked():
    eng = PolicyEngine(":memory:")
    rid = eng.add_rule(make_rule())
    v = eng.check(rid, "0x1111111111111111111111111111111111111111", 10**15)
    assert not v.ok and "白名单" in v.reason


def test_single_limit_exceeded():
    eng = PolicyEngine(":memory:")
    rid = eng.add_rule(make_rule(single_limit_wei=10**16))  # 0.01 ETH
    v = eng.check(rid, VALID_ADDR, 2 * 10**16)
    assert not v.ok and "单笔" in v.reason


def test_daily_limit_accumulated():
    eng = PolicyEngine(":memory:")
    rid = eng.add_rule(make_rule(single_limit_wei=10**18, daily_limit_wei=10**17))  # 单笔 1 ETH，每日 0.1 ETH
    # 先成功记账 0.09 ETH，再尝试 0.02 ETH -> 超每日累计
    eng.record_success(rid, VALID_ADDR, 9 * 10**16, "0x" + "aa" * 32)
    v = eng.check(rid, VALID_ADDR, 2 * 10**16)
    assert not v.ok and "每日" in v.reason


def test_daily_limit_utc_day_window():
    """每日限额按 UTC 日窗口聚合，昨日成功不计入今日。"""
    eng = PolicyEngine(":memory:")
    rid = eng.add_rule(make_rule(single_limit_wei=10**18, daily_limit_wei=10**17))
    eng.record_success(rid, VALID_ADDR, 9 * 10**16, "0x" + "aa" * 32)
    # 直接把记账时间改成昨天（模拟跨日）
    eng._db.execute(
        "UPDATE executions SET created_at = created_at - 86400000 WHERE rule_id = ?",
        (rid,),
    )
    eng._db.commit()
    v = eng.check(rid, VALID_ADDR, 2 * 10**16)
    assert v.ok, "昨日记账不应消耗今日额度"


def test_disabled_rule_blocked():
    eng = PolicyEngine(":memory:")
    rid = eng.add_rule(make_rule(enabled=False))
    v = eng.check(rid, VALID_ADDR, 10**15)
    assert not v.ok and "禁用" in v.reason


def test_valid_transfer_passes_and_records():
    eng = PolicyEngine(":memory:")
    rid = eng.add_rule(make_rule(single_limit_wei=10**16, daily_limit_wei=10**17))
    v = eng.check(rid, VALID_ADDR, 5 * 10**15)
    assert v.ok
    n = eng.record_success(rid, VALID_ADDR, 5 * 10**15, "0x" + "bb" * 32)
    assert n == 1
    rows = eng.list_executions()
    assert len(rows) == 1 and rows[0]["status"] == "success"


def test_make_demo_rule():
    r = make_demo_rule(VALID_ADDR, 0.005)
    assert r.whitelist == [VALID_ADDR]
    assert r.single_limit_wei == 5 * 10**15
    assert r.daily_limit_wei == 10**16
    with pytest.raises(ValueError):
        make_demo_rule(VALID_ADDR, "not-a-number")
