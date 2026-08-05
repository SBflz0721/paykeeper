"""
PayKeeper Web Dashboard（FastAPI）。

功能：
  - 自然语言 -> 结构化支付规则（LLM 解析，需配置 LLM key）
  - 风控规则管理（白名单 / 单笔限额 / 每日累计限额）
  - 手动执行：带风控的 KeeperHub 真实链上转账
  - 执行记录 / 钱包信息 / 健康检查

运行：
  uvicorn web.app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from agent.keeperhub_mcp import KeeperHubMCP
from agent.policy import PolicyEngine, PolicyRule
from agent import payments

WEB_DIR = Path(__file__).resolve().parent
ROOT_DIR = WEB_DIR.parent
DATA_DIR = ROOT_DIR / "data"
PROVIDER_CONFIG_FILE = DATA_DIR / "provider.json"
KEEPERHUB_CONFIG_FILE = DATA_DIR / "keeperhub.json"

# ----------------------------------------------------------------------
# 鉴权（Dashboard 必须防住：谁能建规则谁就能转账）
# ----------------------------------------------------------------------
# 所有 /api/*（除 /health）都要求 Authorization: Bearer <token>。
# token 来源：DASHBOARD_TOKEN 环境变量；未设置则自动生成并持久化到
# data/.dashboard_token（启动日志会打印），保证鉴权永远开启、绝不裸奔。
import secrets  # noqa: E402


def dashboard_token() -> str:
    token = os.getenv("DASHBOARD_TOKEN", "").strip()
    if token:
        return token
    token_file = DATA_DIR / ".dashboard_token"
    try:
        if token_file.exists():
            stored = token_file.read_text(encoding="utf-8").strip()
            if stored:
                return stored
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe(24)
        token_file.write_text(token, encoding="utf-8")
    except Exception:
        token = secrets.token_urlsafe(24)  # 持久化失败也保证有 token
    return token


# 自定义 OpenAI 兼容端点 base_url 白名单（防止 /api/provider 把 LLM key 转发到攻击者服务器）
def custom_base_url_allowed(url: str) -> bool:
    from urllib.parse import urlparse

    allow = {
        h.strip().lower()
        for h in os.getenv("OPENAI_COMPATIBLE_BASE_URL_ALLOWLIST", "").split(",")
        if h.strip()
    }
    if not allow:
        return False  # 未显式配置白名单 -> 禁止自定义 base_url（key 外带风险）
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(host == a or host.endswith("." + a) for a in allow)

# ----------------------------------------------------------------------
# 全局单例
# ----------------------------------------------------------------------
_kh: KeeperHubMCP | None = None
_policy: PolicyEngine | None = None


def kh() -> KeeperHubMCP:
    if _kh is None:
        raise HTTPException(503, "KeeperHub 未初始化")
    return _kh


def policy() -> PolicyEngine:
    if _policy is None:
        raise HTTPException(503, "风控引擎未初始化")
    return _policy


def _load_provider_config() -> dict:
    """读取前端保存的 provider 配置（data/provider.json），不存在返回空。"""
    if not PROVIDER_CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(PROVIDER_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


# provider -> API key 环境变量名（模块级，供配置读写复用）
PROVIDER_KEY_MAP = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "zhipu": "ZHIPU_API_KEY",
    "ollama": "OLLAMA_API_KEY",
    "custom": "OPENAI_COMPATIBLE_API_KEY",
}


def _apply_provider_config(cfg: dict) -> None:
    """把 provider 配置写入进程环境变量（运行时生效，不修改 .env）。"""
    provider = str(cfg.get("provider", "")).strip().lower()
    api_key = str(cfg.get("api_key", "")).strip()
    model = str(cfg.get("model", "")).strip()
    base_url = str(cfg.get("base_url", "")).strip()

    if provider:
        os.environ["LLM_PROVIDER"] = provider
    if model:
        os.environ["LLM_MODEL"] = model

    if provider in PROVIDER_KEY_MAP and api_key:
        os.environ[PROVIDER_KEY_MAP[provider]] = api_key
    if provider == "custom" and base_url:
        os.environ["OPENAI_COMPATIBLE_BASE_URL"] = base_url


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _kh, _policy
    _kh = KeeperHubMCP()
    await _kh.__aenter__()
    _policy = PolicyEngine()
    _apply_provider_config(_load_provider_config())
    _apply_keeperhub_config(_load_keeperhub_config())
    # 打印鉴权 token（未显式设置 DASHBOARD_TOKEN 时自动生成）
    if not os.getenv("DASHBOARD_TOKEN", "").strip():
        tok = dashboard_token()
        print("\n" + "=" * 62, flush=True)
        print("  Dashboard 鉴权已启用（未设置 DASHBOARD_TOKEN，自动生成）", flush=True)
        print(f"  打开页面后请输入 token: {tok}", flush=True)
        print(f"  （已持久化到 {DATA_DIR / '.dashboard_token'}，重启不变）", flush=True)
        print("=" * 62 + "\n", flush=True)
    try:
        yield
    finally:
        await _kh.__aexit__(None, None, None)
        _policy.close()


app = FastAPI(title="PayKeeper Dashboard", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    # Dashboard 只服务本机（README 要求绑 127.0.0.1），同源请求不受 CORS 影响；
    # 收紧 origin 防止恶意网页借浏览器跨域调用本机 API（P2-11）。
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # token 永远存在（未配置 DASHBOARD_TOKEN 会自动生成），鉴权始终开启
    token = dashboard_token()
    path = request.url.path
    if path.startswith("/api/") and path != "/health":
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {token}":
            return JSONResponse(
                status_code=401,
                content={"ok": False, "error": "未授权：需要 Bearer token（见启动日志或 DASHBOARD_TOKEN）"},
            )
    return await call_next(request)


# 全局异常处理：避免向客户端裸抛 500（兼容审计要求）
from fastapi.exceptions import RequestValidationError  # noqa: E402


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": f"内部错误: {exc.__class__.__name__}: {exc}"},
    )

# ----------------------------------------------------------------------
# 请求模型
# ----------------------------------------------------------------------
class InterpretIn(BaseModel):
    intent: str


class RuleIn(BaseModel):
    name: str
    whitelist: list[str] = Field(default_factory=list)
    single_limit_eth: float = 0.0      # 单笔限额（ETH）
    daily_limit_eth: float = 0.0       # 每日累计限额（ETH）
    cron: str | None = None


class ExecuteIn(BaseModel):
    rule_id: str
    to_address: str
    amount_eth: float
    chain_id: str = "11155111"


class ProviderIn(BaseModel):
    provider: str
    api_key: str = ""
    model: str = ""
    base_url: str = ""


class KeeperHubConfigIn(BaseModel):
    wallet_integration_id: str = ""


# ----------------------------------------------------------------------
# 页面
# ----------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (WEB_DIR / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "tools": len(kh().get_tools()) if _kh else 0}


# ----------------------------------------------------------------------
# 自然语言 -> 规则（LLM 解析）
# ----------------------------------------------------------------------
INTERPRET_PROMPT = """你是 PayKeeper 的意图解析器。把用户的自然语言支付/订阅意图解析为 JSON。
只输出 JSON，不要 markdown。字段：
{
  "name": "规则名",
  "addresses": ["0x..."],
  "amount_eth": 0.01,
  "schedule": "5 字段 cron 或 null（如每周五=0 0 * * 5，每月1号=0 0 1 * *）",
  "daily_limit_eth": 0.05,
  "warnings": ["潜在问题"]
}
规则：ETH 金额转小数；地址必须是 0x+40hex；没有时间含义则 schedule=null；
daily_limit 默认 = amount x 地址数 x 2；地址缺失时给出 warning。"""


@app.post("/api/agent/interpret")
async def interpret(body: InterpretIn) -> dict:
    try:
        from agent.agent import build_llm

        llm = build_llm()
        raw = llm.invoke(f"{INTERPRET_PROMPT}\n\n用户意图: {body.intent}")
        content = raw.content if hasattr(raw, "content") else str(raw)
        # 去掉可能的 ```json 包裹
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0]
        data = json.loads(content)
        data["warnings"] = data.get("warnings", [])
        return data
    except Exception as e:
        raise HTTPException(422, f"意图解析失败: {e}")


# ----------------------------------------------------------------------
# 规则管理
# ----------------------------------------------------------------------
@app.get("/api/rules")
async def list_rules() -> list[dict]:
    return policy().list_rules()


@app.post("/api/rules")
async def create_rule(body: RuleIn) -> dict:
    from decimal import Decimal, InvalidOperation

    def eth_to_wei(v: float) -> int:
        """float -> wei 用 Decimal 转换，避免 float 精度误差（与 policy 内部一致）。"""
        try:
            return int(Decimal(str(v)) * Decimal(10) ** 18)
        except (InvalidOperation, ValueError, TypeError):
            raise HTTPException(422, f"金额非法: {v!r}")

    rule = PolicyRule(
        name=body.name,
        whitelist=body.whitelist,
        single_limit_wei=eth_to_wei(body.single_limit_eth),
        daily_limit_wei=eth_to_wei(body.daily_limit_eth),
        cron=body.cron,
    )
    try:
        rule_id = policy().add_rule(rule)
    except ValueError as e:
        raise HTTPException(422, str(e))  # 白名单含非法地址：拒绝，绝不静默降级为「不限」
    return policy().get_rule(rule_id) or {}


@app.patch("/api/rules/{rule_id}/enabled")
async def set_rule_enabled(rule_id: str, body: dict) -> dict:
    enabled = bool(body.get("enabled", True))
    if not policy().set_enabled(rule_id, enabled):
        raise HTTPException(404, "规则不存在")
    return {"ok": True, "enabled": enabled}


@app.delete("/api/rules/{rule_id}")
async def delete_rule(rule_id: str) -> dict:
    if not policy().delete_rule(rule_id):
        raise HTTPException(404, "规则不存在")
    return {"ok": True}


# ----------------------------------------------------------------------
# 执行（带风控，真实链上）
# ----------------------------------------------------------------------
@app.post("/api/execute")
async def execute(body: ExecuteIn) -> dict:
    # 链白名单（fail-closed）：请求方不能把交易指到主网等任意网络
    allowed = payments.allowed_chain_ids()
    if body.chain_id not in allowed:
        raise HTTPException(422, f"链不在允许名单: {body.chain_id}（允许 {sorted(allowed)}）")
    result = await payments.execute_transfer(
        kh(),
        chain_id=body.chain_id,
        to_address=body.to_address,
        amount=str(body.amount_eth),
        policy_engine=policy(),
        policy_rule_id=body.rule_id,
    )
    report = result.to_report()
    # 风控拒绝也写入执行记录，便于审计
    if not result.ok and "风控拦截" in result.error:
        from decimal import Decimal, InvalidOperation
        try:
            amount_wei = int(Decimal(str(body.amount_eth)) * Decimal(10) ** 18)
        except (InvalidOperation, ValueError, TypeError):
            amount_wei = 0
        policy().record(body.rule_id, body.to_address,
                        amount_wei, "rejected", error=result.error)
    return report


@app.get("/api/executions")
async def list_executions(limit: int = 50) -> list[dict]:
    return policy().list_executions(limit=limit)


# ----------------------------------------------------------------------
# Provider 配置（前端可视化配置，运行时生效，不写 .env）
# 模型名由用户按各 provider 控制台/文档自填，这里不预填过时的示例
# ----------------------------------------------------------------------
PROVIDER_OPTIONS = [
    {"id": "anthropic", "label": "Anthropic", "model_hint": ""},
    {"id": "openai", "label": "OpenAI", "model_hint": ""},
    {"id": "deepseek", "label": "DeepSeek", "model_hint": ""},
    {"id": "openrouter", "label": "OpenRouter", "model_hint": ""},
    {"id": "groq", "label": "Groq", "model_hint": ""},
    {"id": "moonshot", "label": "Moonshot / Kimi", "model_hint": ""},
    {"id": "zhipu", "label": "Zhipu GLM", "model_hint": ""},
    {"id": "ollama", "label": "Ollama (local)", "model_hint": ""},
    {"id": "custom", "label": "Custom (OpenAI-compatible)", "model_hint": ""},
]


def _mask_key(key: str) -> str:
    if not key:
        return ""
    return key[:4] + "…" + key[-4:] if len(key) > 10 else "***"


@app.get("/api/providers")
async def provider_options() -> list[dict]:
    return PROVIDER_OPTIONS


@app.get("/api/provider")
async def get_provider() -> dict:
    cfg = _load_provider_config()
    # 当前生效配置（脱敏显示 key）
    provider = cfg.get("provider") or os.getenv("LLM_PROVIDER", "anthropic")
    key_env = PROVIDER_KEY_MAP.get(provider, "")
    has_key = bool(os.getenv(key_env)) if key_env else False
    return {
        "provider": provider,
        "model": cfg.get("model") or os.getenv("LLM_MODEL", ""),
        "base_url": cfg.get("base_url") or os.getenv("OPENAI_COMPATIBLE_BASE_URL", ""),
        "has_key": has_key,
        "key_masked": _mask_key(cfg.get("api_key", "") or os.getenv(key_env, "")),
    }


@app.post("/api/provider")
async def set_provider(body: ProviderIn) -> dict:
    provider = body.provider.strip().lower()
    if provider not in {p["id"] for p in PROVIDER_OPTIONS}:
        raise HTTPException(422, f"未知 provider: {provider}")
    if not body.model.strip():
        raise HTTPException(422, "请填写模型名（代码不预设默认模型）")
    if provider == "custom":
        if not body.base_url.strip():
            raise HTTPException(422, "custom 需要 base_url")
        # 自定义 base_url 必须命中白名单，防止 LLM key 被转发到攻击者服务器
        if not custom_base_url_allowed(body.base_url.strip()):
            raise HTTPException(
                422,
                "custom base_url 不在白名单：请设置 OPENAI_COMPATIBLE_BASE_URL_ALLOWLIST"
                " 并只填入可信域名（防止 API Key 外带）",
            )

    # 校验：除 ollama 外必须填 key；为空时保留已配置的 key
    # （前端只改模型/地址时无需重输 API Key）
    api_key = body.api_key.strip()
    if provider != "ollama" and not api_key:
        existing = _load_provider_config()
        if existing.get("provider") == provider:
            api_key = str(existing.get("api_key", "")).strip()
        if not api_key:
            api_key = os.getenv(PROVIDER_KEY_MAP.get(provider, ""), "").strip()
        if not api_key:
            raise HTTPException(422, f"{provider} 需要 API Key（或先填入一次）")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROVIDER_CONFIG_FILE.write_text(
        json.dumps({
            "provider": provider,
            "api_key": api_key,
            "model": body.model.strip(),
            "base_url": body.base_url.strip(),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _apply_provider_config(_load_provider_config())
    return {"ok": True, "provider": provider, "model": body.model.strip()}


# ----------------------------------------------------------------------
# 钱包
# ----------------------------------------------------------------------
@app.get("/api/wallet")
async def wallet() -> dict:
    integration_id = os.getenv("WALLET_INTEGRATION_ID", "")
    if not integration_id:
        return {"wallet": None, "hint": "请在 Dashboard 的 KeeperHub 标签页配置 Wallet Integration ID（或 .env 设置 WALLET_INTEGRATION_ID）"}
    try:
        raw = await kh().call_tool("get_wallet_integration", {"integrationId": integration_id})
        return {"wallet": raw}
    except Exception as e:
        raise HTTPException(502, f"查询钱包失败: {e}")


# ----------------------------------------------------------------------
# KeeperHub 配置（前端可视化配置，运行时注入环境变量，不写 .env）
# ----------------------------------------------------------------------
def _load_keeperhub_config() -> dict:
    """读取前端保存的 KeeperHub 配置（data/keeperhub.json），不存在返回空。"""
    if not KEEPERHUB_CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(KEEPERHUB_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _apply_keeperhub_config(cfg: dict) -> None:
    """把 KeeperHub 配置写入进程环境变量（运行时生效，不修改 .env）。

    注意：KEEPERHUB_API_KEY 不在这里处理——MCP 连接在启动时建立，前端保存的
    key 不会重新连接，属于死代码；API Key 必须在启动前通过 .env 设置。
    这里只处理「请求时读取」的 WALLET_INTEGRATION_ID。
    """
    wallet_id = str(cfg.get("wallet_integration_id", "")).strip()
    if wallet_id:
        os.environ["WALLET_INTEGRATION_ID"] = wallet_id


@app.get("/api/keeperhub-config")
async def get_keeperhub_config() -> dict:
    cfg = _load_keeperhub_config()
    env_key = os.getenv("KEEPERHUB_API_KEY", "")
    env_wallet = os.getenv("WALLET_INTEGRATION_ID", "")
    return {
        # KEEPERHUB_API_KEY 只读展示（启动时生效，前端不保存）
        "api_key_masked": _mask_key(env_key),
        "has_key": bool(env_key),
        "wallet_integration_id": cfg.get("wallet_integration_id", "") or env_wallet,
        "has_wallet_id": bool(env_wallet),
    }


@app.post("/api/keeperhub-config")
async def set_keeperhub_config(body: KeeperHubConfigIn) -> dict:
    # 只管理 Wallet Integration ID（请求时读取，真实生效）；
    # KEEPERHUB_API_KEY 需在 .env 设置（MCP 连接启动时建立，前端保存无效，故不提供）。
    wallet_id = body.wallet_integration_id.strip()
    if not wallet_id:
        raise HTTPException(422, "请填写 Wallet Integration ID")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    KEEPERHUB_CONFIG_FILE.write_text(
        json.dumps({"wallet_integration_id": wallet_id}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _apply_keeperhub_config(_load_keeperhub_config())
    return {
        "ok": True,
        "wallet_integration_id": wallet_id,
        "note": "KEEPERHUB_API_KEY 需在启动前于 .env 配置（MCP 连接在启动时建立）。",
    }
