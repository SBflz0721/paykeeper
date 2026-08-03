"""
KeeperHub MCP 客户端封装。

负责连接 KeeperHub 的远程 MCP Server（https://app.keeperhub.com/mcp），
把它的 30+ 工具暴露给上层（付款逻辑 / LangChain Agent）调用。

参考文档：https://docs.keeperhub.com/ai-tools/mcp-server
"""
from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()


class KeeperHubMCP:
    """KeeperHub 远程 MCP 客户端。

    用法（异步上下文管理器）::

        async with KeeperHubMCP() as kh:
            tools = kh.get_tools()
            result = await kh.call_tool("execute_transfer", {...})
    """

    DEFAULT_URL = "https://app.keeperhub.com/mcp"
    DEFAULT_TRANSPORT = "streamable_http"

    def __init__(
        self,
        api_key: str | None = None,
        url: str | None = None,
        transport: str | None = None,
        org: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("KEEPERHUB_API_KEY")
        self.url = url or os.getenv("KEEPERHUB_MCP_URL", self.DEFAULT_URL)
        self.transport = transport or os.getenv(
            "KEEPERHUB_MCP_TRANSPORT", self.DEFAULT_TRANSPORT
        )
        self.org = org or os.getenv("KEEPERHUB_ORG")

        if not self.api_key:
            raise ValueError(
                "缺少 KeeperHub API Key。请在 .env 设置 KEEPERHUB_API_KEY（kh_ 前缀），"
                "或在 app.keeperhub.com -> Settings -> API Keys 创建。"
            )

        self._client: MultiServerMCPClient | None = None
        self._tools: list = []

    def _build_client(self) -> MultiServerMCPClient:
        headers: dict[str, str] = {"Authorization": f"Bearer {self.api_key}"}
        if self.org:
            # API Key 已绑定组织；此头仅作显式声明，KeeperHub 以 Key 的组织为准
            headers["KeeperHub-Org"] = self.org
        return MultiServerMCPClient(
            {
                "keeperhub": {
                    "url": self.url,
                    "transport": self.transport,
                    "headers": headers,
                }
            }
        )

    async def __aenter__(self) -> "KeeperHubMCP":
        self._client = self._build_client()
        self._tools = await self._client.get_tools()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        # MultiServerMCPClient 自行管理底层会话生命周期
        self._client = None
        self._tools = []

    # ------------------------------------------------------------------
    # 工具访问
    # ------------------------------------------------------------------
    def get_tools(self) -> list:
        """返回已加载的 LangChain 工具列表。"""
        return self._tools

    def tool_names(self) -> list[str]:
        return [t.name for t in self._tools]

    async def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        """按名称调用一个 MCP 工具。

        找不到工具时抛 ValueError；工具执行错误由底层抛出。
        """
        for tool in self._tools:
            if tool.name == name:
                return await tool.ainvoke(args)
        raise ValueError(
            f"工具 {name!r} 不存在。已加载工具：{self.tool_names()}"
        )

    async def list_workflows(self) -> Any:
        if "list_workflows" in self.tool_names():
            return await self.call_tool("list_workflows", {})
        return None

    async def tools_documentation(self) -> Any:
        """拉取 KeeperHub 工具文档与最佳实践（调试/上手用）。"""
        if "tools_documentation" in self.tool_names():
            return await self.call_tool("tools_documentation", {})
        return "tools_documentation 不可用"
