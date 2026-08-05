"""
x402 / MPP 按次付费客户端（best-effort，自包含实现）。

背景：KeeperHub 付费工作流返回 HTTP 402(x402 challenge) 时，官方推荐用其
agentic wallet（Claude Code skill）自动拦截支付。本模块提供一个**纯 Python 替代**：
Agent 持有自己的 EOA 私钥（ env: X402_PRIVATE_KEY，需在 Base 充 USDC），
按 EIP-3009 签署 TransferWithAuthorization，向 facilitator 结算，再透明重试调用。

注意：facilitator 端点与 402 body 字段以 KeeperHub 线上为准；本模块做了容错解析，
首次实跑时请对照 docs.keeperhub.com/ai-tools/agentic-wallet 校准。
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

import requests

USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Base 主网 USDC
USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"  # Base Sepolia USDC（示例）
# 允许结算的资产白名单（默认仅上述 USDC 地址；可用 X402_ASSET_ALLOWLIST 追加，逗号分隔）
DEFAULT_ASSET_ALLOWLIST = {USDC_BASE.lower(), USDC_BASE_SEPOLIA.lower()}
# 单笔 x402 支付上限（wei / 最小精度）。默认 100 USDC（1e8 对 6 位小数 = 100 * 1e6）。
# 可用 X402_MAX_AMOUNT_WEI 覆盖；超过上限的 challenge 一律拒绝，绝不「全额信任」。
DEFAULT_MAX_AMOUNT_WEI = 100 * 10**6
# 公共 x402 facilitator 端点（Coinbase 协议开放生态）。历史默认 https://app.keeperhub.com/settlement
# 经核验返回 404（非真实端点），改为 Coinbase 维护的公共 facilitator。可通过 X402_FACILITATOR_URL 覆盖。
DEFAULT_FACILITATOR_URL = "https://facilitator.x402.rs"
EIP3009_TYPE = {
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ]
}


def _max_amount_wei() -> int:
    try:
        return int(os.getenv("X402_MAX_AMOUNT_WEI", str(DEFAULT_MAX_AMOUNT_WEI)))
    except ValueError:
        return DEFAULT_MAX_AMOUNT_WEI


def _asset_allowed(asset: str) -> bool:
    allowlist = {a.strip().lower() for a in os.getenv("X402_ASSET_ALLOWLIST", "").split(",") if a.strip()}
    allowlist |= DEFAULT_ASSET_ALLOWLIST
    return asset.lower() in allowlist


def _private_key() -> str:
    key = os.getenv("X402_PRIVATE_KEY", "")
    if not key:
        raise RuntimeError("未设置 X402_PRIVATE_KEY（用于 x402 签名的 EOA 私钥）。")
    return key


def extract_challenge(payload: Any) -> dict | None:
    """从 402 报错文本 / 字典里尽力解析出 x402 challenge。

    返回结构示例：{
      "version": 1, "scheme": "exact", "network": "base-sepolia",
      "maxAmountRequired": "5000", "asset": "0x...USDC",
      "payTo": "0x...", "resource": "https://...", "facilitator": "https://.../settlement"
    }
    """
    text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    try:
        # 尝试直接定位 JSON 块
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            obj = json.loads(text[start : end + 1])
            # 兼容 x402 标准：accepts 列表
            if isinstance(obj, dict) and "accepts" in obj:
                scheme = (obj["accepts"] or [{}])[0]
                return {**scheme, "version": obj.get("x402Version", 1), "resource": obj.get("resource")}
            if isinstance(obj, dict) and "payTo" in obj:
                return obj
    except Exception:
        pass
    return None


def sign_eip3009(
    *, from_addr: str, to_addr: str, value: int, asset: str, chain_id: int
) -> dict:
    """按 EIP-3009 签署 USDC TransferWithAuthorization。"""
    from eth_account import Account
    from eth_utils import keccak

    acct = Account.from_key(_private_key())
    nonce = keccak(os.urandom(32)).hex()
    valid_after = 0
    valid_before = int(time.time()) + 3600

    domain = {
        "name": "USD Coin",
        "version": "2",
        "chainId": chain_id,
        "verifyingContract": asset,
    }
    message = {
        "from": from_addr,
        "to": to_addr,
        "value": value,
        "validAfter": valid_after,
        "validBefore": valid_before,
        "nonce": nonce,
    }
    signed = acct.sign_typed_data(domain, EIP3009_TYPE, message)
    return {
        "from": from_addr,
        "to": to_addr,
        "value": str(value),
        "validAfter": str(valid_after),
        "validBefore": str(valid_before),
        "nonce": nonce,
        "signature": signed.signature.hex(),
    }


def _facilitator_allowed(url: str) -> bool:
    """校验 facilitator 端点，防止 402 challenge 被恶意/劫持工作流用来钓鱼签名。

    规则：必须 https，且 host 落在允许名单（默认 keeperhub.com 域 + public facilitator
    `facilitator.x402.rs`；可用 X402_FACILITATOR_ALLOWLIST 追加，逗号分隔）。
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    allowlist = [h.strip().lower() for h in os.getenv("X402_FACILITATOR_ALLOWLIST", "").split(",") if h.strip()]
    allowlist.append("keeperhub.com")
    allowlist.append("app.keeperhub.com")
    # 公共 x402 facilitator 开放生态（Coinbase 协议）
    allowlist.append("facilitator.x402.rs")
    allowlist.append("x402.org")
    return any(host == a or host.endswith("." + a) for a in allowlist)


def settle(challenge: dict) -> dict:
    """向 facilitator 结算 x402 付款，返回 {ok, ...}。

    安全要点（fail-closed，绝不「全额信任 challenge」）：
    - facilitator 必须 https 且在允许名单内（见 _facilitator_allowed）。
    - amount 直接采用 challenge 的 maxAmountRequired（最小精度，如 Base USDC 的 1e6 = 1 USDC），
      不做换算，避免单位错误多付/少付。
    - 单笔金额上限 X402_MAX_AMOUNT_WEI（默认 100 USDC）：challenge 金额超上限直接拒绝，
      防止被恶意/被劫持的工作流诱导签署大额转账。
    - asset 必须在允许名单（默认 Base/USDC 主网与 Sepolia），防止被诱导签非预期资产。
    """
    try:
        asset = challenge.get("asset", USDC_BASE)
        if not _asset_allowed(asset):
            return {"ok": False, "error": f"asset 不在允许名单，已拒绝: {asset}"}
        # 链推导（Base 主网=8453 / Base Sepolia=84532）
        network = str(challenge.get("network", "")).lower()
        chain_id = 84532 if "sepolia" in network else 8453

        try:
            amount = int(challenge.get("maxAmountRequired", "0"))
        except Exception:
            amount = 0
        if amount <= 0:
            return {"ok": False, "error": "challenge 缺少有效的 maxAmountRequired"}
        cap = _max_amount_wei()
        if amount > cap:
            return {
                "ok": False,
                "error": f"challenge 金额 {amount} 超过单笔上限 {cap}"
                f"（X402_MAX_AMOUNT_WEI），已拒绝以防范恶意大额",
            }

        to_addr = challenge.get("payTo", "")
        if not to_addr:
            return {"ok": False, "error": "challenge 缺少 payTo"}

        from eth_account import Account

        acct = Account.from_key(_private_key())
        payload = sign_eip3009(
            from_addr=acct.address,
            to_addr=to_addr,
            value=amount,
            asset=asset,
            chain_id=chain_id,
        )
        facilitator = (
            challenge.get("facilitator")
            or os.getenv("X402_FACILITATOR_URL")
            or DEFAULT_FACILITATOR_URL
        )
        if not facilitator:
            return {"ok": False, "error": "缺少 facilitator 端点（challenge 未提供，且未设 X402_FACILITATOR_URL）"}
        if not _facilitator_allowed(facilitator):
            return {"ok": False, "error": f"facilitator 不在允许名单，已拒绝: {facilitator}"}
        resp = requests.post(facilitator, json=payload, timeout=30)
        if resp.ok:
            return {"ok": True, "settlement": resp.json()}
        return {"ok": False, "error": f"facilitator 返回 {resp.status_code}: {resp.text[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
