# Onboarding UX Teardown — 新手从零到首次 KeeperHub 交易的卡点与改进建议

> 本文是 PayKeeper 参赛作品为 **Best Onboarding UX Improvement** Bounty 提交的"卡点拆解 + 改进建议"。
> 视角：一个**不熟悉 KeeperHub** 的 Python/LangChain 开发者，想用 KeeperHub 作为 Agent 的链上执行层。
> 配套交付：本仓库即一个可 `git clone` 后 15 分钟跑通首次交易的 **starter 模板**，以及 [TUTORIAL.md](TUTORIAL.md)。

---

## 总览：最影响"上手速度"的 5 个卡点

| # | 卡点 | 严重程度 | 新手的真实代价 |
|---|------|---------|---------------|
| 1 | HTTP MCP 的**传输方式**对 Python 构建者不透明 | 高 | 在 `streamable_http` / `sse` 之间试错，连接直接失败 |
| 2 | **x402 对非 Claude Code Agent 没有 drop-in 方案** | 高 | 想用按次付费却只能逆向工程 402 体与 facilitator |
| 3 | **Gas Sponsorship 仅主网** + 测试网是否算"真实执行"未说明 | 中 | 犹豫要不要花真钱，或担心提交不被认可 |
| 4 | 30+ 工具但**没有"最小首次交易"路径** | 中 | 在工具海里找不到最短路径 |
| 5 | 直接执行前需配置 **org wallet integration**，文档未前置提醒 | 中 | 首次 `execute_transfer` 直接报"无钱包集成" |

---

## 卡点 1：HTTP MCP 传输方式对 Python 构建者不透明

**现状**：MCP 文档的示例都是 Claude Code CLI：
```bash
claude mcp add --transport http keeperhub https://app.keeperhub.com/mcp
```
但一个用 Python（`langchain-mcp-adapters` / `mcp` SDK）的构建者必须显式选 transport。端点是 Streamable HTTP 还是 SSE？文档没明说。`--transport http` 在 Claude Code 里映射到 Streamable HTTP，但 Python 侧参数名是 `streamable_http`，猜错就握手失败。

**影响**：连接阶段最易卡住，且报错不直观（超时 / `Method not found`）。

**建议修复（文档 + 代码示例）**：
- 在 MCP 文档顶部加一句：*"The hosted endpoint `https://app.keeperhub.com/mcp` speaks **Streamable HTTP**. For Python, set `transport='streamable_http'`."*
- 给一个最小 Python 片段：

```python
from langchain_mcp_adapters.client import MultiServerMCPClient
client = MultiServerMCPClient({
 "keeperhub": {
 "url": "https://app.keeperhub.com/mcp",
 "transport": "streamable_http",
 "headers": {"Authorization": f"Bearer {API_KEY}"},
 }
})
tools = await client.get_tools()
```

> 本仓库 `agent/keeperhub_mcp.py` 已把这个坑固化成默认值，新手无需再猜。

---

## 卡点 2：x402 对非 Claude Code Agent 没有 drop-in 方案

**现状**：Agentic Wallet 以 **Claude Code skill + PreToolUse hook** 形式交付（`keeperhub-wallet add` 写 `~/.keeperhub/wallet.json`）。若你的 Agent 不是跑在 Claude Code 里（如本项目的 Python/LangChain），就没有现成钩子自动拦截 402。文档未给出：402 响应的**确切 JSON schema**、**facilitator 端点 URL**、以及**签名方案**（EIP-3009 `TransferWithAuthorization`）的可运行 Python 示例。

**影响**：想展示 x402/MPP（评审明确列为 KeeperHub 能力面之一）的 Python 构建者只能靠猜。

**建议修复**：
- 公开一个 **x402 402 响应的最小 JSON 示例**与字段说明（`accepts[].scheme/network/maxAmountRequired/asset/payTo/resource/facilitator`）。
- 提供 **facilitator 结算端点**（如 `POST {host}/x402/{version}/settlement`）的契约。
- 附一段**非 Claude** 的结算代码（EIP-3009 签名 + POST），类似本仓库 `agent/x402_client.py` 的 `sign_eip3009` / `settle`。

> 本仓库已实现自包含的 `x402_client.py`（EIP-3009 签名 + 容错解析 402），可直接作为参考实现并入官方示例。

---

## 卡点 3：Gas Sponsorship 仅主网 + 测试网资格未说明

**现状**：黑客松强调"working transaction"，但 Gas Sponsorship 只在**主网 Ethereum** 提供；主网执行需要真实 ETH/USDC。文档未说明提交是否接受测试网（Sepolia）交易。

**影响**：新手在"花真钱上主网"和"用免费测试网但不确定认不认可"之间纠结，拖慢决策。

**建议修复**：在黑客松/Quickstart 明确：*"A KeeperHub-executed transaction on **any supported network including Sepolia** qualifies. Gas Sponsorship is mainnet-Ethereum only; on testnets you simply fund the Turnkey wallet from a faucet."*

---

## 卡点 4：30+ 工具但没有"最小首次交易"路径

**现状**：MCP 暴露 30+ 工具，新手不知道最短路径。Quickstart 偏向可视化 Builder，而非"Agent 代码最小可执行片段"。

**建议修复**：加一个 **"Minimal first on-chain transaction"** 片段，只用两个工具：
```python
# 1) 模拟预飞（EVM 必填，捕获 revert / 估 gas）
await call("execute_transfer", {chain_id, to_address, amount, "simulate": True})
# 2) 幂等广播（务必带 idempotency_key，防止重试双付）
await call("execute_transfer", {chain_id, to_address, amount, "idempotency_key": uuid4().hex})
# 3) 轮询
await call("get_direct_execution_status", {"execution_id": exec_id})
```

---

## 卡点 5：直接执行前需配置 org wallet integration，未前置提醒

**现状**：`execute_transfer` / `execute_contract_call` 需要组织已配置 wallet integration，否则失败。文档在 MCP 页末尾才提到用 `get_wallet_integration` 确认。

**建议修复**：在"执行你的第一次转账"步骤前加醒目 callout：
> 注意：首次 `execute_transfer` 前，请确认组织已配置 Wallet Integration（用 `get_wallet_integration` 检查）。未配置会直接报错而非提示。

---

## 附：本仓库已固化的"防坑"默认值（可直接并入官方 starter）

- `transport` 默认 `streamable_http`，无需新手猜测（卡点 1）。
- `execute_transfer` 强制 **先 simulate 再带 `idempotency_key` 广播 + 轮询**（卡点 4/5 的可靠性）。
- 提供 x402 自包含客户端，降低对非 Claude 构建者的门槛（卡点 2）。
- TUTORIAL 明确 Sepolia 即可提交、主网用 Gas Sponsorship（卡点 3）。

---

## 建议的 PR 形态

1. **文档 PR**：在 MCP / Quickstart 文档补上述 5 处说明（传输方式、x402 契约、测试网资格、最小交易片段、wallet integration 前置提醒）。
2. **示例 PR**：将 `agent/keeperhub_mcp.py` + `agent/x402_client.py` 作为官方 Python starter 的参考实现收录。
3. **模板 PR**：本仓库作为"Agent + KeeperHub 最小可运行模板"链接进黑客松资源页。

以上任一项合并即可命中 Best Onboarding UX Improvement Bounty 的"merged PR / starter template / tutorial / teardown"要求。
