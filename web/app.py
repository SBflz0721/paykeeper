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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from agent.keeperhub_mcp import KeeperHubMCP
from agent.policy import PolicyEngine, PolicyRule
from agent import payments

WEB_DIR = Path(__file__).resolve().parent
ROOT_DIR = WEB_DIR.parent
DATA_DIR = ROOT_DIR / "data"
PROVIDER_CONFIG_FILE = DATA_DIR / "provider.json"

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

    # provider -> API key 环境变量名
    KEY_MAP = {
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
    if provider in KEY_MAP and api_key:
        os.environ[KEY_MAP[provider]] = api_key
    if provider == "custom" and base_url:
        os.environ["OPENAI_COMPATIBLE_BASE_URL"] = base_url


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _kh, _policy
    _kh = KeeperHubMCP()
    await _kh.__aenter__()
    _policy = PolicyEngine()
    _apply_provider_config(_load_provider_config())
    try:
        yield
    finally:
        await _kh.__aexit__(None, None, None)
        _policy.close()


app = FastAPI(title="PayKeeper Dashboard", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本地演示用；生产请收紧
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理：避免向客户端裸抛 500（兼容审计要求）
from fastapi.responses import JSONResponse  # noqa: E402
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
    rule = PolicyRule(
        name=body.name,
        whitelist=body.whitelist,
        single_limit_wei=int(body.single_limit_eth * 10**18),
        daily_limit_wei=int(body.daily_limit_eth * 10**18),
        cron=body.cron,
    )
    rule_id = policy().add_rule(rule)
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
        policy().record(body.rule_id, body.to_address,
                        int(body.amount_eth * 10**18), "rejected", error=result.error)
    return report


@app.get("/api/executions")
async def list_executions(limit: int = 50) -> list[dict]:
    return policy().list_executions(limit=limit)


# ----------------------------------------------------------------------
# Provider 配置（前端可视化配置，运行时生效，不写 .env）
# ----------------------------------------------------------------------
PROVIDER_OPTIONS = [
    {"id": "anthropic", "label": "Anthropic", "default_model": "claude-sonnet-4-5"},
    {"id": "openai", "label": "OpenAI", "default_model": "gpt-5"},
    {"id": "deepseek", "label": "DeepSeek", "default_model": "deepseek-chat"},
    {"id": "openrouter", "label": "OpenRouter", "default_model": "anthropic/claude-sonnet-4.5"},
    {"id": "groq", "label": "Groq", "default_model": "llama-3.3-70b-versatile"},
    {"id": "moonshot", "label": "Moonshot / Kimi", "default_model": "kimi-k2.5"},
    {"id": "zhipu", "label": "Zhipu GLM", "default_model": "glm-4.6"},
    {"id": "ollama", "label": "Ollama (local)", "default_model": "qwen3:14b"},
    {"id": "custom", "label": "Custom (OpenAI-compatible)", "default_model": ""},
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
    key_map = {
        "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY", "openrouter": "OPENROUTER_API_KEY",
        "groq": "GROQ_API_KEY", "moonshot": "MOONSHOT_API_KEY",
        "zhipu": "ZHIPU_API_KEY", "ollama": "OLLAMA_API_KEY",
        "custom": "OPENAI_COMPATIBLE_API_KEY",
    }
    provider = cfg.get("provider") or os.getenv("LLM_PROVIDER", "anthropic")
    key_env = key_map.get(provider, "")
    has_key = bool(os.getenv(key_env)) if key_env else False
    return {
        "provider": provider,
        "model": cfg.get("model") or os.getenv("LLM_MODEL", ""),
        "base_url": cfg.get("base_url") or os.getenv("OPENAI_COMPATIBLE_BASE_URL", ""),
        "has_key": has_key,
        "key_masked": _mask_key(cfg.get("api_key", "")),
    }


@app.post("/api/provider")
async def set_provider(body: ProviderIn) -> dict:
    provider = body.provider.strip().lower()
    if provider not in {p["id"] for p in PROVIDER_OPTIONS}:
        raise HTTPException(422, f"未知 provider: {provider}")
    # 校验：除 ollama 外必须填 key
    if provider != "ollama" and not body.api_key.strip():
        raise HTTPException(422, f"{provider} 需要 API Key")
    if not body.model.strip():
        raise HTTPException(422, "请填写模型名（代码不预设默认模型）")
    if provider == "custom" and not body.base_url.strip():
        raise HTTPException(422, "custom 需要 base_url")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROVIDER_CONFIG_FILE.write_text(
        json.dumps({
            "provider": provider,
            "api_key": body.api_key.strip(),
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
        return {"wallet": None, "hint": "请在 .env 设置 WALLET_INTEGRATION_ID（KeeperHub 钱包 integrationId）"}
    try:
        raw = await kh().call_tool("get_wallet_integration", {"integrationId": integration_id})
        return {"wallet": raw}
    except Exception as e:
        raise HTTPException(502, f"查询钱包失败: {e}")
