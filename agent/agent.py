"""
LangChain / LangGraph 自然语言 Agent。

把 KeeperHub 的 MCP 工具绑定给一个 LLM Agent：用户用自然语言描述付款意图，
Agent 自行规划并调用 KeeperHub 工具在链上执行，最后汇总执行报告。

依赖（见 requirements.txt）：langgraph, langchain-anthropic / langchain-openai
支持 provider：anthropic（默认）、openai、deepseek、openrouter、groq、
moonshot、zhipu、ollama，以及任意 OpenAI 兼容端点（custom）。
"""
from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from .keeperhub_mcp import KeeperHubMCP

load_dotenv()

SYSTEM_PROMPT = """你是 PayKeeper —— 一个经 KeeperHub 在链上自动执行付款的 AI Agent。

你的职责：
1. 理解用户的自然语言付款/订阅意图（如"每月给某地址付 5 USDC"、"查余额后若低于阈值就补足"）。
2. 用 KeeperHub MCP 工具在链上真实执行，而不是空谈。
3. 执行转账优先用 execute_transfer；先 simulate=true 预飞，再带 idempotency_key 广播。
4. 不确定某个工具的参数时，先调用 tools_documentation 查看权威说明。
5. 执行后报告：链、收款方、金额、execution_id、交易哈希、状态，以及关键审计轨迹。
6. 若执行失败，说明失败原因并给出重试/修正建议。

硬性约束：所有链上动作都必须通过 KeeperHub 执行层完成。不要伪造交易哈希。
"""

# OpenAI 兼容 provider 注册表（langchain_openai.ChatOpenAI 只需换 base_url / model）
# base_url=None 表示用 openai 官方默认端点。
# 注意：这里【不】预设 default_model —— 模型名由用户在 .env 的 LLM_MODEL 指定，
#      避免代码硬编码模型名（模型迭代快，硬编码会过时）。
#      每个 provider 只提供便捷 base_url 与 API key 环境变量名。
OPENAI_COMPATIBLE_PROVIDERS: dict[str, dict[str, Any]] = {
    "openai": {
        "base_url": None,
        "env_key": "OPENAI_API_KEY",
        "label": "OpenAI",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "env_key": "DEEPSEEK_API_KEY",
        "label": "DeepSeek",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
        "label": "OpenRouter",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "env_key": "GROQ_API_KEY",
        "label": "Groq",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "env_key": "MOONSHOT_API_KEY",
        "label": "Moonshot / Kimi",
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "env_key": "ZHIPU_API_KEY",
        "label": "智谱 GLM",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "env_key": "OLLAMA_API_KEY",
        "optional_key": True,
        "label": "Ollama（本地）",
    },
}


def provider_names() -> str:
    return ", ".join(["anthropic", *OPENAI_COMPATIBLE_PROVIDERS.keys(), "custom"])


def build_llm():
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower().strip()
    # 模型名一律由用户通过 LLM_MODEL（或各 provider 专属 *_MODEL）指定，不做硬编码默认。
    model = os.getenv("LLM_MODEL", "").strip()

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                f"未设置 ANTHROPIC_API_KEY（或把 LLM_PROVIDER 改为 {provider_names()} 之一）"
            )
        model = model or os.getenv("ANTHROPIC_MODEL", "").strip()
        if not model:
            raise RuntimeError(
                "请设置 LLM_MODEL（或 ANTHROPIC_MODEL）指定 Claude 模型名，"
                "例如 claude-sonnet-4-5 / claude-opus-4-1（见 platform.anthropic.com）"
            )
        return ChatAnthropic(model=model, api_key=key, temperature=0)

    # 任意 OpenAI 兼容端点（自定义）：用 OPENAI_COMPATIBLE_BASE_URL / API_KEY / MODEL 完全自配
    if provider == "custom":
        from langchain_openai import ChatOpenAI

        base_url = os.getenv("OPENAI_COMPATIBLE_BASE_URL", "").strip()
        key = os.getenv("OPENAI_COMPATIBLE_API_KEY", "").strip()
        model = model or os.getenv("OPENAI_COMPATIBLE_MODEL", "").strip()
        if not base_url:
            raise RuntimeError(
                "LLM_PROVIDER=custom 但未设置 OPENAI_COMPATIBLE_BASE_URL（如 https://api.xxx.com/v1）"
            )
        if not key:
            raise RuntimeError("LLM_PROVIDER=custom 但未设置 OPENAI_COMPATIBLE_API_KEY")
        if not model:
            raise RuntimeError(
                "LLM_PROVIDER=custom 但未设置模型名：请设置 LLM_MODEL 或 OPENAI_COMPATIBLE_MODEL"
            )
        return ChatOpenAI(
            model=model,
            api_key=key,
            base_url=base_url,
            temperature=0,
        )

    conf = OPENAI_COMPATIBLE_PROVIDERS.get(provider)
    if conf is None:
        raise RuntimeError(
            f"未知 LLM_PROVIDER={provider}，可选：{provider_names()}"
        )

    from langchain_openai import ChatOpenAI

    key = os.getenv(conf["env_key"], "").strip()
    if not key and not conf.get("optional_key"):
        raise RuntimeError(f"LLM_PROVIDER={provider} 但未设置 {conf['env_key']}")
    if not model:
        raise RuntimeError(
            f"LLM_PROVIDER={provider} 未设置模型名：请在 .env 设置 LLM_MODEL="
            f"<模型名>（可在 {conf['label']} 控制台/文档查看可用模型）"
        )
    return ChatOpenAI(
        model=model,
        # Ollama 本地无需真实 key，SDK 需要非空字符串，这里传占位
        api_key=key or "ollama-local",
        base_url=conf["base_url"],
        temperature=0,
    )


# 需要被风控包装的「动钱」工具：Agent 调用它们前必须先过 policy 校验
MONEY_TOOLS = {"execute_transfer", "execute_contract_call", "execute_check_and_execute"}


async def _wrap_policy_tool(
    tool,
    policy_engine,
    policy_rule_id: str,
    chain_allowlist: set[str],
) -> Any:
    """包装一个资金工具：调用前强制 policy 校验 + 链白名单，不通过直接拒绝。"""
    from .payments import _amount_to_wei, allowed_chain_ids
    from .policy import ADDRESS_RE

    name = tool.name
    original = tool.func  # LangChain StructuredTool 的可调用体

    async def guarded(**kwargs: Any) -> Any:
        # 链白名单
        chain = str(kwargs.get("chain_id") or kwargs.get("chainId") or "")
        allow = chain_allowlist or allowed_chain_ids()
        if chain and chain not in allow:
            return {"ok": False, "error": f"风控拦截: 链不在允许名单 chain_id={chain}（允许 {sorted(allow)}）"}
        if not chain:
            return {"ok": False, "error": "风控拦截: 缺少 chain_id"}

        # 金额解析（fail-closed）+ 收款地址
        to_address = kwargs.get("to_address") or kwargs.get("toAddress") or ""
        token_address = kwargs.get("token_address") or kwargs.get("tokenAddress")
        # 金额来源：amount（转账）/ amount_hint（合约调用显式声明金额，计入每日限额）
        amount = str(
            kwargs.get("amount")
            or kwargs.get("amount_hint")
            or kwargs.get("value")
            or ""
        )
        if not ADDRESS_RE.match(to_address):
            return {"ok": False, "error": f"风控拦截: 收款地址格式非法 {to_address!r}"}
        amount_wei, parse_err = _amount_to_wei(amount, token_address)
        if parse_err:
            hint = "（合约调用请显式传 amount_hint 以计入每日限额）" if name != "execute_transfer" else ""
            return {"ok": False, "error": f"风控拦截: {parse_err}{hint}"}

        verdict = policy_engine.check(policy_rule_id, to_address, amount_wei)
        if not verdict.ok:
            return {"ok": False, "error": f"风控拦截: {verdict.reason}"}

        result = await original(**kwargs)
        # 记账：所有带金额的资金工具成功执行后统一计入当日累计（每日限额生效）。
        # execute_contract_call 通过 amount_hint 显式声明金额；不传金额则被上方
        # fail-closed 拦截，不存在"绕过记账"的路径（P1-8）。
        if policy_engine is not None:
            try:
                flat = result if isinstance(result, dict) else {}
                tx_hash = str(flat.get("tx_hash") or flat.get("txHash") or "")
                policy_engine.record_success(policy_rule_id, to_address, amount_wei, tx_hash)
            except Exception:
                pass
        return result

    # 返回一个新的 StructuredTool，保留名称与描述，替换 func
    from langchain_core.tools import StructuredTool

    return StructuredTool.from_function(
        coroutine=guarded,
        name=tool.name,
        description=tool.description or "",
        args_schema=getattr(tool, "args_schema", None),
    )


async def build_agent(
    kh: KeeperHubMCP,
    policy_engine=None,
    policy_rule_id: str = "",
    chain_allowlist: set[str] | None = None,
):
    """用 KeeperHub 工具 + LLM 构建 ReAct Agent。

    安全约束（fail-closed）：
    - 必须传入 policy_engine 与 policy_rule_id，否则不暴露任何资金工具；
    - execute_transfer / execute_contract_call / execute_check_and_execute
      会被包装：调用前强制链白名单 + 风控校验，不通过直接返回拒绝，绝不触达链上。
    """
    from langgraph.prebuilt import create_react_agent

    if policy_engine is None:
        raise RuntimeError(
            "Agent 路径必须接入风控层：请传入 policy_engine 与 policy_rule_id，"
            "否则不向 LLM 暴露资金工具（防止提示词注入/越权转账）。"
        )

    tools = []
    for t in kh.get_tools():
        if t.name in MONEY_TOOLS:
            tools.append(
                await _wrap_policy_tool(t, policy_engine, policy_rule_id, chain_allowlist or set())
            )
        else:
            tools.append(t)
    llm = build_llm()
    return create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)


async def run_instruction(
    kh: KeeperHubMCP,
    text: str,
    policy_engine=None,
    policy_rule_id: str = "",
    chain_allowlist: set[str] | None = None,
) -> dict[str, Any]:
    """执行一条自然语言指令，返回 LangGraph 结果（含 messages）。

    强制接入风控：未提供 policy_engine/policy_rule_id 时直接抛错，避免绕过风控。
    """
    agent = await build_agent(kh, policy_engine=policy_engine,
                              policy_rule_id=policy_rule_id,
                              chain_allowlist=chain_allowlist)
    result = await agent.ainvoke({"messages": [("user", text)]})
    return result


def final_answer(result: dict[str, Any]) -> str:
    """从 LangGraph 结果里取出最后一条 AI 消息文本。"""
    messages = result.get("messages", [])
    for msg in reversed(messages):
        content = getattr(msg, "content", None)
        if content and getattr(msg, "type", "ai") == "ai":
            return content if isinstance(content, str) else str(content)
    return str(messages[-1]) if messages else ""
