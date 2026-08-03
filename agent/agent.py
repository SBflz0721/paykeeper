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
# 默认模型按 2026-08 各 provider 官方最新发布版本更新。
OPENAI_COMPATIBLE_PROVIDERS: dict[str, dict[str, Any]] = {
    "openai": {
        "base_url": None,
        "default_model": "gpt-5",
        "env_key": "OPENAI_API_KEY",
        "label": "OpenAI",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-v4-flash",
        "env_key": "DEEPSEEK_API_KEY",
        "label": "DeepSeek",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "anthropic/claude-sonnet-4.5",
        "env_key": "OPENROUTER_API_KEY",
        "label": "OpenRouter",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY",
        "label": "Groq",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "kimi-k2.5",
        "env_key": "MOONSHOT_API_KEY",
        "label": "Moonshot / Kimi",
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4.6",
        "env_key": "ZHIPU_API_KEY",
        "label": "智谱 GLM",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "qwen3:14b",
        "env_key": "OLLAMA_API_KEY",
        "optional_key": True,
        "label": "Ollama（本地）",
    },
}


def provider_names() -> str:
    return ", ".join(["anthropic", *OPENAI_COMPATIBLE_PROVIDERS.keys(), "custom"])


def build_llm():
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower().strip()
    model = os.getenv("LLM_MODEL", "").strip()

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                f"未设置 ANTHROPIC_API_KEY（或把 LLM_PROVIDER 改为 {provider_names()} 之一）"
            )
        return ChatAnthropic(
            model=model or "claude-sonnet-4-5", api_key=key, temperature=0
        )

    # 任意 OpenAI 兼容端点（自定义）：用 OPENAI_COMPATIBLE_BASE_URL / API_KEY / MODEL
    if provider == "custom":
        from langchain_openai import ChatOpenAI

        base_url = os.getenv("OPENAI_COMPATIBLE_BASE_URL", "").strip()
        key = os.getenv("OPENAI_COMPATIBLE_API_KEY", "").strip()
        if not base_url:
            raise RuntimeError(
                "LLM_PROVIDER=custom 但未设置 OPENAI_COMPATIBLE_BASE_URL（如 https://api.xxx.com/v1）"
            )
        if not key:
            raise RuntimeError("LLM_PROVIDER=custom 但未设置 OPENAI_COMPATIBLE_API_KEY")
        return ChatOpenAI(
            model=model or os.getenv("OPENAI_COMPATIBLE_MODEL", "").strip() or "gpt-4o",
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
    return ChatOpenAI(
        model=model or conf["default_model"],
        # Ollama 本地无需真实 key，SDK 需要非空字符串，这里传占位
        api_key=key or "ollama-local",
        base_url=conf["base_url"],
        temperature=0,
    )


async def build_agent(kh: KeeperHubMCP):
    """用 KeeperHub 工具 + LLM 构建 ReAct Agent。"""
    from langgraph.prebuilt import create_react_agent

    tools = kh.get_tools()
    llm = build_llm()
    return create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)


async def run_instruction(kh: KeeperHubMCP, text: str) -> dict[str, Any]:
    """执行一条自然语言指令，返回 LangGraph 结果（含 messages）。"""
    agent = await build_agent(kh)
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
