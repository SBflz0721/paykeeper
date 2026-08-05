"""x402 客户端测试：facilitator 白名单 5 用例 + 金额上限 + 资产白名单（S-11）。

全部离线运行：不发起真实结算请求。
"""
from agent.x402_client import (
    USDC_BASE,
    USDC_BASE_SEPOLIA,
    _asset_allowed,
    _facilitator_allowed,
    _max_amount_wei,
    settle,
)
from tests.conftest import VALID_ADDR


def test_facilitator_https_required():
    assert not _facilitator_allowed("http://keeperhub.com/x402")
    assert not _facilitator_allowed("http://evil.com")


def test_facilitator_default_allowlist():
    assert _facilitator_allowed("https://keeperhub.com/x402")
    assert _facilitator_allowed("https://app.keeperhub.com/x402")


def test_facilitator_suffix_spoofing_blocked():
    """evil-keeperhub.com 不得通过后缀匹配绕过。"""
    assert not _facilitator_allowed("https://evil-keeperhub.com/x402")
    assert not _facilitator_allowed("https://keeperhub.com.evil.com/x402")


def test_facilitator_env_append(monkeypatch):
    monkeypatch.setenv("X402_FACILITATOR_ALLOWLIST", "trusted.example.com")
    assert _facilitator_allowed("https://trusted.example.com/x402")
    assert not _facilitator_allowed("https://untrusted.example.com/x402")


def test_max_amount_cap():
    assert _max_amount_wei() == 100_000_000  # 默认 100 USDC（1e6 精度）


def test_asset_allowlist():
    assert _asset_allowed(USDC_BASE)
    assert _asset_allowed(USDC_BASE_SEPOLIA)
    assert not _asset_allowed("0x" + "de" * 20)


def test_settle_rejects_oversize_challenge():
    """S-11：金额完全信 challenge 是漏洞，超上限必须拒绝。"""
    r = settle({
        "asset": USDC_BASE,
        "network": "base",
        "maxAmountRequired": "999999999999",  # 远超 100 USDC
        "payTo": VALID_ADDR,
    })
    assert not r["ok"] and "上限" in r["error"]


def test_settle_rejects_non_allowlisted_asset():
    r = settle({
        "asset": "0x" + "de" * 20,
        "network": "base",
        "maxAmountRequired": "1000000",
        "payTo": VALID_ADDR,
    })
    assert not r["ok"] and "asset" in r["error"]


def test_settle_rejects_missing_fields():
    r = settle({"asset": USDC_BASE, "network": "base"})
    assert not r["ok"]
