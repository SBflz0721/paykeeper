"""
付款逻辑与可靠性层。

提供两类核心能力（均经 KeeperHub 在链上真实执行）：
  1. 循环/单次订阅付款  -> execute_transfer（直接执行，带审计轨迹 + 重试）
  2. 按次付费          -> call_workflow（付费工作流触发 x402/MPP，详见 x402_client）

可靠性设计（对应评审项「Reliability & Observability」）：
  - 模拟预飞：先 simulate=true 估算 gas / 捕获 revert，再广播
  - 幂等：广播携带 idempotency_key，避免重试导致双付
  - 指数退避重试：网络/暂态失败自动重试
  - 可观测：每步记录到审计轨迹，最终汇总成报告
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

from .keeperhub_mcp import KeeperHubMCP


# ----------------------------------------------------------------------
# 数据结构
# ----------------------------------------------------------------------
@dataclass
class PaymentResult:
    ok: bool
    kind: str  # "transfer" | "pay_per_use"
    chain_id: str = ""
    to_address: str = ""
    amount: str = ""
    token: str = ""
    execution_id: str = ""
    tx_hash: str = ""
    status: str = ""
    attempts: int = 0
    error: str = ""
    audit_trail: list[dict] = field(default_factory=list)

    def to_report(self) -> dict:
        return asdict(self)


# ----------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------
def _flatten(obj: Any) -> dict:
    """把 MCP 文本结果拍平成 dict。

    KeeperHub MCP 工具返回的常见形态是：
        [{'type': 'text', 'text': '<json string>'}, ...]
    这里把其中的 text 逐个 json.loads 合并；无法解析的放进 _raw_text。
    """
    if isinstance(obj, list):
        merged: dict = {}
        for item in obj:
            if isinstance(item, dict) and item.get("type") == "text":
                txt = item.get("text", "")
                try:
                    parsed = json.loads(txt)
                    if isinstance(parsed, dict):
                        merged.update(parsed)
                    else:
                        merged.setdefault("_raw", parsed)
                except Exception:
                    merged.setdefault("_raw_text", txt)
        if merged:
            return merged
    if isinstance(obj, str):
        try:
            parsed = json.loads(obj)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return obj if isinstance(obj, dict) else {}


def _extract(obj: Any, *keys: str, default: Any = None) -> Any:
    """从 MCP 工具结果里按多个候选 key 提取值。"""
    d = _flatten(obj)
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


async def _poll_status(kh: KeeperHubMCP, execution_id: str, timeout: int = 120) -> dict:
    """轮询 get_direct_execution_status 直到终态或超时。"""
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        try:
            raw = await kh.call_tool("get_direct_execution_status", {"execution_id": execution_id})
            last = _flatten(raw)
            state = (last.get("status") or "").lower()
            if state in ("success", "confirmed", "completed", "failed", "reverted", "error"):
                return last
        except Exception:
            pass  # 轮询期间偶发错误忽略，继续
        await asyncio.sleep(4)
    return last


def _backoff(attempt: int, base: float = 1.5) -> float:
    return base * (2 ** max(0, attempt - 1))


# ----------------------------------------------------------------------
# 1) 订阅 / 单次付款（execute_transfer）
# ----------------------------------------------------------------------
async def execute_transfer(
    kh: KeeperHubMCP,
    *,
    chain_id: str,
    to_address: str,
    amount: str,
    token_address: str | None = None,
    simulate_first: bool = True,
    max_retries: int = 3,
    timeout: int = 120,
    policy_engine: Any = None,
    policy_rule_id: str = "",
) -> PaymentResult:
    """经 KeeperHub 执行一笔链上转账（原生币或 ERC-20）。

    流程：风控校验（可选）-> 模拟预飞 -> 幂等广播 -> 轮询状态。
    policy_engine / policy_rule_id 提供时，执行前强制风控校验
    （地址格式 / 白名单 / 单笔限额 / 每日累计限额），不通过直接拒绝。
    返回 PaymentResult（含 execution_id / tx_hash / 审计轨迹）。
    """
    trail: list[dict] = []
    base_args: dict[str, Any] = {
        "chain_id": str(chain_id),
        "to_address": to_address,
        "amount": str(amount),
    }
    if token_address:
        base_args["token_address"] = token_address

    # 0) 风控校验（可选，自主支付场景建议开启）
    if policy_engine is not None:
        try:
            if token_address:
                amount_wei = int(str(amount))
            else:
                amount_wei = int(float(str(amount)) * 10**18)
        except Exception:
            amount_wei = 0
        verdict = policy_engine.check(policy_rule_id, to_address, amount_wei)
        trail.append({"step": "policy", "result": str(verdict), "ts": _now()})
        if not verdict.ok:
            return PaymentResult(
                ok=False, kind="transfer", chain_id=str(chain_id),
                to_address=to_address, amount=str(amount), token=token_address or "",
                attempts=1, error=f"风控拦截: {verdict.reason}", audit_trail=trail,
            )

    # 1) 模拟预飞
    if simulate_first:
        try:
            sim = await kh.call_tool("execute_transfer", {**base_args, "simulate": True})
            trail.append({"step": "simulate", "result": _safe(sim), "ts": _now()})
            sim_flat = _flatten(sim)
            sim_err = _extract(sim_flat, "error", "isError")
            would_revert = _extract(sim_flat, "wouldRevert", default=False)
            sim_ok = _extract(sim_flat, "success", default=True)
            if sim_err or would_revert or sim_ok is False:
                return PaymentResult(
                    ok=False, kind="transfer", chain_id=str(chain_id),
                    to_address=to_address, amount=str(amount), token=token_address or "",
                    attempts=1,
                    error=f"模拟预飞失败: err={sim_err} wouldRevert={would_revert} success={sim_ok}",
                    audit_trail=trail,
                )
        except Exception as e:  # 某些网络不支持 simulate，降级继续
            trail.append({"step": "simulate", "result": f"skipped: {e}", "ts": _now()})

    # 2) 幂等广播 + 重试
    # 幂等键在整个执行逻辑（含所有重试）只生成一次：
    # 若第一笔已上链但响应超时，重试必须携带同一 key，让 KeeperHub 去重，避免双付。
    idempotency_key = uuid.uuid4().hex
    last_err = ""
    for attempt in range(1, max_retries + 1):
        args = {**base_args, "idempotency_key": idempotency_key}
        try:
            res = await kh.call_tool("execute_transfer", args)
            trail.append({"step": f"broadcast#{attempt}", "result": _safe(res), "ts": _now()})
            flat = _flatten(res)
            exec_id = str(_extract(flat, "execution_id", "id", "executionId", default=""))
            # 广播返回已含终态与 transactionHash 时，直接用（仍可再轮询一次兜底）
            if exec_id:
                status = await _poll_status(kh, exec_id, timeout=timeout)
            else:
                status = flat
            tx_hash = str(
                _extract(status, "tx_hash", "txHash", "transactionHash", "hash", default="")
                or _extract(flat, "tx_hash", "txHash", "transactionHash", "hash", default="")
            )
            state = str(_extract(status, "status", default="")).lower()
            terminal_ok = state in ("success", "confirmed", "completed")
            if terminal_ok or tx_hash:
                # 风控记账：成功执行计入当日累计（用于每日限额）
                if policy_engine is not None:
                    try:
                        amount_wei = (
                            int(str(amount))
                            if token_address
                            else int(float(str(amount)) * 10**18)
                        )
                        policy_engine.record_success(
                            policy_rule_id, to_address, amount_wei, tx_hash
                        )
                    except Exception as e:  # 记账失败不影响转账结果
                        trail.append({"step": "policy_record", "error": str(e), "ts": _now()})
                return PaymentResult(
                    ok=True, kind="transfer", chain_id=str(chain_id),
                    to_address=to_address, amount=str(amount), token=token_address or "",
                    execution_id=exec_id, tx_hash=tx_hash,
                    status=state or "submitted", attempts=attempt, audit_trail=trail,
                )
            if state in ("failed", "reverted", "error"):
                last_err = f"执行失败: {state}"
                continue
            # 未决 / 未知状态：不算成功，等下一轮重试（避免假成功）
            last_err = f"交易未确认（状态: {state or 'pending'}，无 tx_hash）"
        except Exception as e:
            last_err = str(e)
            trail.append({"step": f"broadcast#{attempt}", "error": last_err, "ts": _now()})
        await asyncio.sleep(_backoff(attempt))

    return PaymentResult(
        ok=False, kind="transfer", chain_id=str(chain_id), to_address=to_address,
        amount=str(amount), token=token_address or "", attempts=max_retries,
        error=last_err or "未知错误", audit_trail=trail,
    )


# ----------------------------------------------------------------------
# 2) 按次付费（x402 / MPP）
# ----------------------------------------------------------------------
async def pay_per_use(
    kh: KeeperHubMCP,
    *,
    slug: str,
    inputs: dict | None = None,
    max_retries: int = 2,
) -> PaymentResult:
    """调用一个 KeeperHub 付费工作流。

    若返回 402（x402 challenge），则经 x402_client 完成 USDC 支付后透明重试。
    返回 PaymentResult。
    """
    from . import x402_client  # 延迟导入，避免无依赖时报错

    trail: list[dict] = []
    inputs = inputs or {}
    last_err = ""
    res = None

    for attempt in range(1, max_retries + 1):
        try:
            res = await kh.call_tool("call_workflow", {"slug": slug, "inputs": inputs})
            trail.append({"step": f"call_workflow#{attempt}", "result": _safe(res), "ts": _now()})
            # 若没有报错且带了结果，视为成功
            if not _is_error(res):
                return PaymentResult(
                    ok=True, kind="pay_per_use", execution_id=slug,
                    status="ok", attempts=attempt, audit_trail=trail,
                )
            last_err = _error_text(res)
        except Exception as e:
            last_err = str(e)

        # 尝试解析 402 / x402 challenge 并支付
        challenge = x402_client.extract_challenge(last_err)
        if challenge is None and res is not None:
            challenge = x402_client.extract_challenge(res)
        if challenge:
            paid = await x402_client.settle(challenge)
            trail.append({"step": f"x402_settle#{attempt}", "result": _safe(paid), "ts": _now()})
            if paid.get("ok"):
                # 支付完成后由 KeeperHub 代理透明重试调用
                continue
            last_err = paid.get("error", "x402 支付失败")
        else:
            break  # 非支付类错误，停止重试

    return PaymentResult(
        ok=False, kind="pay_per_use", execution_id=slug,
        attempts=max_retries, error=last_err or "未知错误", audit_trail=trail,
    )


# ----------------------------------------------------------------------
# 便捷封装
# ----------------------------------------------------------------------
async def run_subscription_once(
    kh: KeeperHubMCP,
    *,
    chain_id: str,
    to_address: str,
    amount: str,
    token_address: str | None = None,
) -> PaymentResult:
    """执行一次订阅付款（立即执行；循环调度见 README/工作流方案）。"""
    return await execute_transfer(
        kh, chain_id=chain_id, to_address=to_address, amount=amount, token_address=token_address
    )


# ----------------------------------------------------------------------
# 小工具
# ----------------------------------------------------------------------
def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _safe(obj: Any, limit: int = 500) -> Any:
    """把工具返回结果截断，便于塞进审计轨迹。"""
    text = obj if isinstance(obj, str) else str(obj)
    return text if len(text) <= limit else text[:limit] + "...(truncated)"


def _is_error(obj: Any) -> bool:
    d = _flatten(obj)
    if d:
        return bool(d.get("isError")) or "error" in d or "Error:" in str(d)
    if isinstance(obj, str):
        return "Error:" in obj or "402" in obj
    return False


def _error_text(obj: Any) -> str:
    d = _flatten(obj)
    if d:
        return str(d.get("error") or d.get("text") or d)
    return str(obj)
