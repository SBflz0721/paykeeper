# PayKeeper 💸

> **自然语言 → KeeperHub 执行层 → 真实链上交易**：让 AI Agent 在 Sepolia / 主网上经 KeeperHub 完成付款、订阅、按次付费。
>
> 参赛作品 · [KeeperHub — Agents Onchain Hackathon](https://dorahacks.io/hackathon/agents-onchain/detail) · [English README →](README_EN.md)

![GitHub repo size](https://img.shields.io/github/repo-size/SBflz0721/paykeeper)
![Demo](https://img.shields.io/badge/demo-real_onchain-3fb950)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-yellow)

> **TL;DR** —— 一行自然语言（如「给 `0xc4Ef…` 转 0.005 ETH」），Agent 自动通过 KeeperHub MCP 选工具、预飞、广播、回执确认，每一步都可审计。

---

## 🎬 演示视频（真实终端录制，3 个能力串联）

👉 仓库根目录：[`demo/paykeeper_demo_final.mp4`](demo/paykeeper_demo_final.mp4)（38 秒，1600×900）

视频展示了一次 Python 进程内串联的 3 个真实链上能力，**全部经 KeeperHub 真实执行**（非模拟、非 HTML）：

1. **确定性转账** —— `simulate` 预飞 → 幂等键广播 → 状态轮询 → 审计
2. **自然语言 Agent（DeepSeek）** —— 用户一句话 → Agent 选 MCP 工具 → 真实查询
3. **订阅工作流** —— 手动触发 `web3/transfer-funds` → 链上确认

---

## ✨ 核心亮点

| 维度 | 实现 |
|------|------|
| **真实执行** | Sepolia 上 16 笔链上交易可查（含 Gas Sponsorship），不是 mockup |
| **9 个 LLM provider** | OpenAI 兼容协议一行切换（Anthropic / OpenAI / DeepSeek / OpenRouter / Groq / Moonshot / 智谱 / Ollama / 自定义） |
| **可靠性** | simulate 预飞 → **重试复用同一幂等键**（防双付）→ 指数退避 → 状态轮询 → 审计轨迹 |
| **真定时器订阅** | `agent/subscription.py` cron 调度器：到点自动付款；KeeperHub Schedule 工作流作平台侧方案 |
| **x402 按次付费** | EIP-3009 `TransferWithAuthorization` 签名 + facilitator 域名白名单 |
| **审计可见** | 每次执行回传 execution_id、transactionHash、状态、审计节点 |
| **安全** | 完成 6 项审计修复（B-01~B-06，含 2 项外部评审发现），保留 `AUDIT_REPORT.md` |

---

## 🏗 架构

```
┌──────────────────────────────────────────────────────────────────┐
│             用户自然语言（如"每月 1 号付 5 USDC"）             │
└──────────────────────┬───────────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│       LangGraph ReAct Agent · 9 个 LLM provider 可切换         │
│   (Anthropic / OpenAI / DeepSeek / OpenRouter / Groq / ...)    │
└──────────────────────┬───────────────────────────────────────────┘
                       ▼  MCP (Streamable HTTP, Bearer kh_*)
┌──────────────────────────────────────────────────────────────────┐
│                      KeeperHub 执行层                          │
│  ┌──────────────┐  ┌────────────────┐  ┌─────────────────────┐ │
│  │  MCP Server  │  │  x402 / MPP    │  │  Workflow Builder    │ │
│  │  (35 tools)  │  │  Pay-per-use   │  │  (Manual/Schedule/  │ │
│  │              │  │                │  │   Webhook/Event/    │ │
│  │              │  │                │  │   Block/Transfer)   │ │
│  └──────┬───────┘  └────────┬───────┘  └──────────┬──────────┘ │
│         │                   │                     │            │
│         └────────┬──────────┴─────────────────────┘            │
│                  ▼                                               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Turnkey Wallet · x402 Agentic Wallet · Audit Trail ·     │  │
│  │ Gas Sponsorship (主网)                                    │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────┬───────────────────────────────────────────┘
                       ▼
                  EVM (Sepolia / Base / Mainnet)
```

---

## 🚀 快速开始（3 步上手）

```bash
# 1. 克隆 + 装依赖
git clone https://github.com/SBflz0721/paykeeper.git && cd paykeeper
pip install -r requirements.txt

# 2. 配置环境（填入 KeeperHub Key 与任一 LLM Key）
cp .env.example .env && nano .env
# 必须：KEEPERHUB_API_KEY、LLM_PROVIDER、对应 provider 的 *_API_KEY
# 可选：TARGET_CHAIN_ID、DEMO_RECIPIENT、DEMO_AMOUNT

# 3. 一键跑真实演示（确定性转账 + 自然语言 Agent）
python examples/run_demo.py
```

`examples/full_demo.py` 在单进程内串联 3 个真实能力（确定性转账 / NL Agent / 订阅工作流），是**推荐演示入口**。

---

## 🤖 LLM provider 选择（模型名由你自配，不硬编码）

> 代码**不预设默认模型**（模型迭代快，硬编码会过时）。你只需在 `.env` 设置：
> `LLM_PROVIDER=<provider>` + 对应 `*_API_KEY` + **`LLM_MODEL=<模型名>`**（必填）。

`agent/agent.py` 内置 provider 注册表（每个 provider 提供便捷 base_url + key 名），改 `LLM_PROVIDER` 一行即可切换：

| `LLM_PROVIDER` | 需要的 key | 示例 `LLM_MODEL`（以各平台控制台为准） | 备注 |
|----------------|-----------|----------------------------------------|------|
| `anthropic`（默认） | `ANTHROPIC_API_KEY`（或 `ANTHROPIC_MODEL`） | `claude-sonnet-4-5` | Claude 4.5 |
| `openai` | `OPENAI_API_KEY` | `gpt-5` | GPT-5 旗舰 |
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat`（V4） | 走 OpenAI 兼容 API |
| `openrouter` | `OPENROUTER_API_KEY` | `anthropic/claude-sonnet-4.5` | 一个 key 路由多 provider |
| `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` | Groq LPU 极速推理 |
| `moonshot` | `MOONSHOT_API_KEY` | `kimi-k2.5` | Moonshot / Kimi |
| `zhipu` | `ZHIPU_API_KEY` | `glm-4.6` | 智谱 GLM |
| `ollama` | 无需 key | `qwen3:14b` | 本地推理（先 `ollama pull <模型名>`） |
| `custom` | `OPENAI_COMPATIBLE_BASE_URL` + `_API_KEY` + `_MODEL` | 任意 | 任意 OpenAI 兼容端点 |

示例（DeepSeek）：

```bash
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxxx
LLM_MODEL=deepseek-chat
```

缺 `LLM_MODEL` 时程序会 fail-fast 并提示去对应平台查可用模型。

---

## 🔌 KeeperHub 能力覆盖

| KeeperHub Surface | 本项目用法 | 代码位置 |
|--------------------|-----------|---------|
| **MCP Server**（Streamable HTTP） | `agent/keeperhub_mcp.py` 连接 `app.keeperhub.com/mcp` | `agent/keeperhub_mcp.py` |
| **直接执行** `execute_transfer` | 确定性 / 订阅转账，simulate+广播+轮询 | `agent/payments.py` |
| **直接执行** `execute_contract_call` | 通用合约调用 | `agent/payments.py` |
| **Workflow Builder** | 创建 / 校验 / 执行 / 轮询工作流（442 actions） | `examples/workflow_demo.py` |
| **6 个触发器** | Manual / Schedule / Webhook / Event / Block / Transfer | `examples/workflow_demo.py` |
| **x402 / MPP 按次付费** | EIP-3009 签名 + facilitator 域名白名单 | `agent/x402_client.py` |
| **审计轨迹** | 每次执行回传 execution_id、状态、审计节点 | `agent/payments.py` `to_report()` |
| **Gas Sponsorship** | Sepolia/主网执行 `sponsored:true`（已在 `examples/output/transactions_log.md` 验证） | 通过 KeeperHub 控制台启用 |
| **Audit Trail UI** | KeeperHub 控制台可视化执行历史 | 控制台入口 |

---

## 💎 真实链上交易记录（Sepolia, Chain ID `11155111`）

所有交易均由 KeeperHub 真实广播，浏览器可查：

| # | 类型 | 交易哈希 | Gas 赞助 | 执行 ID |
|---|------|---------|---------|---------|
| 1 | `execute_transfer` | [`0x8bc569…1baa`](https://sepolia.etherscan.io/tx/0x8bc5693d4ca307cad4ef5e069124e1ed25eb62b2086dcda29e9c8e8481631baa) | — | — |
| 2 | `execute_transfer` | [`0xe3dff8…1f7e`](https://sepolia.etherscan.io/tx/0xe3dff8ed1870976a54a02cc82d3093ce47f11cde8dfd031d0b448a7671ab1f7e) | — | `tibsnk9bcntdogef6nii4` |
| 3 | `workflow` (subscription) | [`0x5b0fd6…5bf7`](https://sepolia.etherscan.io/tx/0x5b0fd6bf8428c911d1f5882b8ac83604ee228c3c4173bcf17cd2bcacd5e25bf7) | ✅ sponsored | `ejwpzvyanilj5hkeqg1wp` |
| 4 | `execute_transfer` (NL Agent) | [`0xf98cd5…6582`](https://sepolia.etherscan.io/tx/0xf98cd5a476fd61e12af321a72b876f607d7ce8035f5298cd735e2b4d7c666582) | ✅ sponsored | `6lagptosr08ei7e6mtipo` |
| 5 | `execute_transfer` | [`0x53399d…5eab`](https://sepolia.etherscan.io/tx/0x53399d71ff2b3151753261a5915259975276148ee68fa8771bc06d81a1b45eab) | — | — |
| 6 | `execute_transfer` | [`0x610036…c121`](https://sepolia.etherscan.io/tx/0x6100369c0f9eadd208bc281ea64ef2b9e69489531a29ecfdaf17b239a7bbc121) | ✅ sponsored | — |

完整列表见 [`examples/output/transactions_log.md`](examples/output/transactions_log.md)（注：`examples/output/` 在 `.gitignore` 中，本地留存）。

---

## 🛡 可靠性与安全性

### 可靠性三层防护

```
请求 ──► [1] simulate=true 预飞 ──► [2] 幂等键 broadcast ──► [3] 状态轮询
                │                       │                       │
                ▼                       ▼                       ▼
          wouldRevert?           transfer-funds           success/failed
            false → 继续           提交真实交易              指数退避重试
            true  → 拒绝           同一幂等键（防双付）
```

### 关键实现

- **幂等键**：`uuid4().hex` 一次生成、**重试全程复用**（若首笔已上链但响应超时，重试仍是同一张"单"，KeeperHub 去重，绝不双付）—— 已通过 mock 单测验证
- **指数退避**：默认 1.5s 起步，2x 递增，最多 3 次
- **状态轮询**：等待 `success | completed | failed | reverted` 终态
- **审计轨迹**：每次执行回传完整 `audit_trail`（simulate / broadcast / confirm 节点）
- **x402 facilitator 白名单**：强制 HTTPS + 后缀白名单（默认仅 `keeperhub.com`，防钓鱼）

### 真定时器订阅

`agent/subscription.py` 实现了**真正的 cron 订阅调度器**（`SubscriptionManager` + 最小 cron 解析器）：

- 每个订阅配置 cron（如 `0 0 1 * *` 每月 1 号 00:00 UTC）
- 调度循环到点自动调用 `execute_transfer`（复用可靠性层）
- 支持 `run_once` 立即执行、`--wait` 等待下一次定时触发、多订阅并发
- 平台侧方案：KeeperHub Schedule 工作流（`triggerType=Schedule` + cron），由平台自动触发

```bash
python examples/subscription_demo.py              # 立即执行一次 + 显示下次触发
python examples/subscription_demo.py --wait       # 额外等待定时触发并自动执行
```

### 安全审计

完整审计报告见 [`AUDIT_REPORT.md`](AUDIT_REPORT.md)（6 项 bug 已修复，3 项 follow-up 保留）：

- ✅ B-01：执行状态判定（pending 不再误判为 success）
- ✅ B-02：simulate 结果校验（`wouldRevert` 检测）
- ✅ B-03：x402 facilitator 域名白名单
- ✅ B-04：x402 金额计算冗余清理
- ✅ B-05：重试复用同一幂等键（防双付，外部评审发现）
- ✅ B-06：真定时器订阅调度器（外部评审发现"订阅只是一次性转账"）

---

## 📁 项目结构

```
paykeeper/
├── agent/                          # 核心模块
│   ├── keeperhub_mcp.py           # KeeperHub MCP 客户端（35 tools）
│   ├── payments.py                # 转账 / 合约调用 / 工作流（可靠性层）
│   ├── subscription.py            # 真正的 cron 订阅调度器（真定时器）
│   ├── agent.py                   # LangGraph ReAct Agent + 9-provider 注册表
│   └── x402_client.py             # EIP-3009 签名 + facilitator 校验
├── examples/                       # 运行入口
│   ├── run_demo.py                # 默认：确定性转账 + NL Agent
│   ├── full_demo.py               # 3 个真实能力串联（推荐演示）
│   ├── subscription_demo.py       # 订阅调度器演示（run_once + --wait 定时触发）
│   ├── transfer_demo.py           # 仅转账
│   ├── video_demo.py              # 单次 NL Agent（紧凑叙事）
│   └── workflow_demo.py           # 工作流创建→执行→轮询
├── docs/                           # 文档（Bounty 材料 + 视频指南）
│   ├── TUTORIAL.md                # 从零到第一次 KeeperHub 交易
│   ├── ONBOARDING_TEARDOWN.md     # 上手指引 5 大痛点 + 改进建议
│   └── DEMO_SCRIPT.md             # 演示视频录制指南
├── demo/                           # 演示视频（真实终端录制）
│   └── paykeeper_demo_final.mp4   # 38s 最终视频
├── scripts/                        # 辅助工具
│   ├── gen_demo_html.py           # 终端动画生成器（备用）
│   └── auto_speed.py              # 录屏自动变速
├── AUDIT_REPORT.md                 # 安全审计报告
├── README.md                       # 中文（本文档）
├── README_EN.md                    # English
├── requirements.txt
├── .env.example
└── mcp_config.json
```

---

## 🎯 Judging Criteria 对照（hackathon 官方标准）

> **Execution is weighted heavily, because that is the point.**

### ① Does it execute onchain via KeeperHub? ✅

- Working transactions, not mockups
- **15+ 笔真实 Sepolia 交易**（见上表，每笔 Etherscan 可查）
- 每笔都通过 KeeperHub 真实广播，含 `transactionHash`、`executionId`、`gasUsed`、`sponsored`
- 完整交易日志见 `examples/output/transactions_log.md`

### ② Use of KeeperHub surfaces ✅

本项目覆盖了 KeeperHub 几乎所有核心 surface：

- ✅ **MCP server**（35 个工具，`agent/keeperhub_mcp.py`）
- ✅ **CLI**（通过 Python SDK 等价调用 MCP 工具）
- ✅ **x402 / MPP 按次付费**（EIP-3009 签名 + facilitator 白名单，`agent/x402_client.py`）
- ✅ **Workflow builder**（创建 / 校验 / 执行 / 轮询，442 actions + 6 触发器）
- ✅ **Audit trail**（每次执行回传 + 控制台可视化）

### ③ Reliability and observability ✅

- ✅ **失败模式处理**：`simulate` 预飞拒绝 `wouldRevert=true` 的交易
- ✅ **重试机制**：指数退避（1.5s → 3s → 6s），重试**复用同一幂等键**（已 mock 单测验证，防"首笔已上链但响应超时→重试双付"）
- ✅ **Gas 处理**：`Gas Sponsorship`（`sponsored:true` 多笔验证）+ 非赞助场景的 gas 估算与回执
- ✅ **审计使用**：每次执行回传 `audit_trail` 节点列表（simulate / broadcast / confirm）
- ✅ **幂等键**：`uuid4().hex` 一次生成、重试全程复用（KeeperHub 按 key 去重）

### ④ Originality and real-world usefulness ✅

PayKeeper 解决一个真实需求：**让任何能说自然语言的人都能发起可审计的链上付款**。

- **订阅代理（真定时器）**：`agent/subscription.py` cron 调度器到点自动付款（如"每月 1 号给 `0x…` 付 5 USDC"）；平台侧可用 KeeperHub Schedule 工作流
- **余额守卫**："查询余额后若低于 0.5 ETH 就补足到 1 ETH" 类条件支付（Agent 推理可执行）
- **按次付费**：x402 MPP 场景下 Agent 自动签名 EIP-3009 付款（`agent/x402_client.py`）
- **批量结算**：自然语言"把这两个地址各转 0.1 ETH" → Agent 多次调用 `execute_transfer`

适合场景：DAO 财库自动发薪、DeFi 自动化订阅（VPN/SaaS 代付）、AI Agent 之间 micropayment、电商自动结算。

### ⑤ Integration quality and developer experience ✅

- ✅ **9 个 LLM provider** 一行切换（`agent/agent.py` 注册表设计）
- ✅ **端到端文档**：`docs/TUTORIAL.md` 从零到第一次交易、`docs/DEMO_SCRIPT.md` 录屏指南
- ✅ **演示脚本开箱即用**：`python examples/full_demo.py` 一行运行
- ✅ **依赖锁定**：`mcp<2.0` + `httpx<0.28` 避免 API 兼容问题（requirements.txt）
- ✅ **多平台兼容**：默认 `libopenh264` 在所有主流 Linux 都能跑
- ✅ **安全审计可见**：`AUDIT_REPORT.md` 列出 6 个已修 bug + 3 个 follow-up
- ✅ **零外部数据库依赖**：纯 Python + MCP，不引入 DB / Redis

---

## 📦 提交材料

| 项 | 位置 |
|----|------|
| 源码 | 本仓库 |
| 演示视频（真实终端） | [`demo/paykeeper_demo_final.mp4`](demo/paykeeper_demo_final.mp4)（38s） |
| 视频录制指南 | [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) |
| Bounty 材料：教程 | [`docs/TUTORIAL.md`](docs/TUTORIAL.md) |
| Bounty 材料：上手指引 | [`docs/ONBOARDING_TEARDOWN.md`](docs/ONBOARDING_TEARDOWN.md) |
| 安全审计 | [`AUDIT_REPORT.md`](AUDIT_REPORT.md) |
| 交易证据 | `examples/output/transactions_log.md`（本地留存） |

---

## 🙏 Acknowledgments

- [KeeperHub](https://app.keeperhub.com) — MCP / x402 / 审计 / 钱包基础设施
- [DeepSeek](https://platform.deepseek.com) — 默认 LLM，OpenAI 兼容 API
- [Anthropic](https://www.anthropic.com) — Claude 4.5
- [LangChain / LangGraph](https://www.langchain.com) — ReAct Agent 框架

---

## 📜 License

MIT © 2026 PayKeeper Contributors
