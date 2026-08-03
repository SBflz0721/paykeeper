# PayKeeper 💸

> 经 **KeeperHub** 在链上自动执行付款 / 订阅的 AI Agent。
> 参赛作品 · [KeeperHub — Agents Onchain Hackathon](https://dorahacks.io/hackathon/agents-onchain/detail)

PayKeeper 让用户用自然语言描述付款意图（"每月 1 号给某地址付 5 USDC" / "需要实时汇率时调用付费工作流"），由 Agent 经 KeeperHub 在链上**真实执行**，并带回完整的审计轨迹。

- 🛰️ **执行层**：100% 走 KeeperHub（MCP Server + Turnkey 钱包 + 审计轨迹 + Gas Sponsorship）
- 💳 **付款能力**：循环/单次订阅付款（`execute_transfer`）、按次付费（x402 / MPP）
- 🛡️ **可靠性**：模拟预飞 → 幂等广播 → 指数退避重试 → 状态轮询 → 审计汇总
- 🧩 **可观测**：每次动作记录 trigger / 模拟 / 交易哈希 / Gas / 结果 / 时间戳

---

## 架构

```
用户自然语言
    │
    ▼
LangChain/LangGraph Agent  ──(MCP, Bearer kh_*)──►  KeeperHub 执行层
    │                                          ├─ MCP Server（工具发现/调用）
    │                                          ├─ Turnkey Wallet（真实发交易）
    └─ payments 模块（确定性路径）              ├─ Agentic Wallet（x402/MPP）
                                               └─ Gas Sponsorship（主网）
                                                            │
                                                       EVM 链
```

## 快速开始

```bash
cp .env.example .env          # 填入 KEEPERHUB_API_KEY 和任一 LLM key
pip install -r requirements.txt
python examples/run_demo.py   # 跑一次真实链上转账 + 一条 NL 指令
```

### LLM provider 选择

| `LLM_PROVIDER` | 需要的 key | 默认模型 |
|----------------|-----------|---------|
| `anthropic`（默认） | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` |
| `openai` | `OPENAI_API_KEY` | `gpt-4o` |
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat`（OpenAI 兼容 API，平台: platform.deepseek.com） |
| `openrouter` | `OPENROUTER_API_KEY` | `openai/gpt-4o-mini`（一个 key 用多家模型） |
| `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile`（免费额度快） |
| `moonshot` | `MOONSHOT_API_KEY` | `moonshot-v1-8k`（Kimi，平台: platform.moonshot.cn） |
| `zhipu` | `ZHIPU_API_KEY` | `glm-4-flash`（智谱，平台: open.bigmodel.cn） |
| `ollama` | 无需 key | `llama3.1`（本地，先 `ollama pull llama3.1`） |
| `custom` | `OPENAI_COMPATIBLE_*` | 任意 OpenAI 兼容端点 |

想换 provider 只需改 `.env` 里两行，例如：

```bash
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxxx
```

详见 [docs/TUTORIAL.md](docs/TUTORIAL.md)（从零到第一次 KeeperHub 交易）。

## KeeperHub 能力覆盖

| 能力 | 本项目用法 |
|------|-----------|
| MCP Server | `agent/keeperhub_mcp.py` 连接 `app.keeperhub.com/mcp` |
| 直接执行 | `execute_transfer` / `execute_contract_call` |
| x402 / MPP | `agent/x402_client.py` 处理付费工作流 402 |
| 审计轨迹 | 每次执行回传并汇总到报告 |
| Gas Sponsorship | 主网执行时启用（见 `.env`） |

## 提交材料

- 源码：本仓库
- 演示视频：展示 Agent 经 KeeperHub 完成真实链上付款
- 交易链接：`examples/output/last_run.json` 中的 `tx_explorer`

## 目录

```
agent/        Agent + KeeperHub MCP 封装 + 付款可靠性层
examples/     运行入口与输出
docs/         TUTORIAL.md + ONBOARDING_TEARDOWN.md（Bounty）
```
