"""可靠性层测试：金额 fail-closed 解析 + 链白名单（对应 AUDIT「集成 5/5」之一）。

全部离线运行。
"""
from agent.payments import _amount_to_wei, allowed_chain_ids


def test_non_numeric_amount_fails_closed():
    """S-08：解析失败必须拒绝，绝不能默认 0 放行。"""
    for bad in ("abc", "", "-1", "NaN", "Infinity", "0x10"):
        w, err = _amount_to_wei(bad, None)
        assert err, f"{bad!r} 必须解析失败"
        assert w is None


def test_eth_amount_conversion_exact():
    w, err = _amount_to_wei("0.005", None)
    assert not err and w == 5_000_000_000_000_000  # 0.005 ETH in wei


def test_token_amount_passthrough():
    """ERC-20 金额按最小精度原样传入（不是 wei 换算）。"""
    w, err = _amount_to_wei("5000000", "0x" + "ab" * 20)
    assert not err and w == 5_000_000


def test_chain_allowlist_default_no_mainnet():
    """S-04：默认白名单必须不含主网（chain_id=1）。"""
    allow = allowed_chain_ids()
    assert "11155111" in allow
    assert "1" not in allow, "主网必须默认拒绝"


def test_chain_allowlist_env_override(monkeypatch):
    monkeypatch.setenv("PAYKEEPER_ALLOWED_CHAIN_IDS", "1,11155111")
    allow = allowed_chain_ids()
    assert "1" in allow and "11155111" in allow
