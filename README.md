# PayKeeper

> 用一句自然语言，让 AI Agent 经 KeeperHub 在链上自动完成付款、订阅与按次付费——每一步都可审计。

[![GitHub repo size](https://img.shields.io/github/repo-size/SBflz0721/paykeeper)](https://github.com/SBflz0721/paykeeper)
[![Demo](https://img.shields.io/badge/demo-real_onchain-3fb950)](demo/paykeeper_demo_final.mp4)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](requirements.txt)
[![License](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

参赛作品 · [KeeperHub — Agents Onchain Hackathon](https://dorahacks.io/hackathon/agents-onchain/detail) · [English README ->](README_EN.md)

---

## 为什么做这个（Why This Exists）

链上付款对普通用户仍然太"工程化"：要选工具、拼参数、盯回执、防双付。**PayKeeper 把这件事变成一句话**。

你说「每周五给 `0x…` 转 0.01 ETH，日限额 0.05」，Agent 负责：解析意图 -> 匹配风控规则 -> 经 KeeperHub MCP 预飞 -> 幂等广播 -> 轮询确认 -> 输出可审计报告。钱真的在链上动了，但用户全程只说人话。

**核心解决三个痛点**：
1. **自然语言即支付指令**——不需要懂 MCP 工具、不需要拼 JSON 参数
2. **钱的安全边界**——白名单 / 单笔限额 / 每日累计限额，LLM 理解错了也花不超
3. **可审计、可重试、防双付**——幂等键一次生成全程复用，重试不会重复扣款

---

## 演示视频（真实终端录制）

[`demo/paykeeper_demo_final.mp4`](demo/paykeeper_demo_final.mp4)（38 秒，1600×900）——单进程串联 3 个真实链上能力，**全部经 KeeperHub 真实执行，非模拟**：

1. **确定性转账**：`simulate` 预飞 -> 幂等广播 -> 状态轮询 -> 审计
2. **自然语言 Agent（DeepSeek）**：一句话 -> Agent 选 MCP 工具 -> 真实上链
3. **订阅工作流**：手动触发 `web3/transfer-funds` -> 链上确认

---

## 快速开始（3 步）

```bash
# 1. 克隆 + 装依赖
git clone https://github.com/SBflz0721/paykeeper.git && cd paykeeper
pip install -r requirements.txt

# 2. 配置环境（填入 KeeperHub Key 与任一 LLM Key）
cp .env.example .env && nano .env
# 必填：KEEPERHUB_API_KEY（kh_ 前缀）、LLM_PROVIDER、对应 *_API_KEY、LLM_MODEL

# 3. 一键跑真实演示（确定性转账 + 自然语言 Agent）
python examples/run_demo.py
```

> 推荐演示入口：`python examples/full_demo.py`——单进程串联确定性转账 / NL Agent / 订阅工作流三个真实能力。

---

## 核心亮点

| 维度 | 实现 |
|------|------|
| **真实执行** | **8 笔** Sepolia 链上交易可查（每笔附 Etherscan 链接，含 Gas Sponsorship），不是 mockup |
| **完整风控层** | 白名单 + 单笔限额 + 每日累计限额（SQLite 持久化，执行前强制校验） |
| **Web Dashboard** | FastAPI + 原生前端（6 标签页）：NL 建规则、手动执行、审计记录、钱包、Provider 配置、KeeperHub 配置 |
| **9 个 LLM provider** | OpenAI 兼容协议一行切换（Anthropic / OpenAI / DeepSeek / OpenRouter / Groq / Moonshot / 智谱 / Ollama / 自定义） |
| **可靠性** | simulate 预飞 -> **重试复用同一幂等键**（防双付）-> 指数退避 -> 状态轮询 -> 审计轨迹 |
| **真定时器订阅** | `agent/subscription.py` cron 调度器：到点自动付款；KeeperHub Schedule 工作流作平台侧方案 |
| **x402 按次付费** | EIP-3009 `TransferWithAuthorization` 签名 + facilitator 域名白名单 |
| **安全** | 完成 6 项审计修复（B-01~B-06，含 2 项外部评审发现），报告见 `AUDIT_REPORT.md` |

---

## 架构

```
用户自然语言（如"每月 1 号付 5 USDC"）
        |
        v
┌─────────────────────────────────────────────────────┐
│ LangGraph ReAct Agent · 9 个 LLM provider 可切换     │
│ (Anthropic / OpenAI / DeepSeek / OpenRouter / ...)  │
└────────────────────────┬────────────────────────────┘
                         | MCP (Streamable HTTP, Bearer kh_*)
                         v
┌─────────────────────────────────────────────────────┐
│ KeeperHub 执行层                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │ MCP Server  │  │ x402 / MPP   │  │ Workflow   │  │
│  │ (35 tools)  │  │ Pay-per-use  │  │ Builder    │  │
│  └──────┬──────┘  └──────┬───────┘  └─────┬──────┘  │
│         └────────┬───────┴────────┬────────┘        │
│                  v                v                 │
│  Turnkey Wallet · x402 Agentic Wallet · Audit Trail │
│  Gas Sponsorship (主网)                             │
└────────────────────────┬────────────────────────────┘
                         | EVM
                         v
              Sepolia / Base / Mainnet
```

---

## 配置

### LLM Provider（模型名由你自配，代码不硬编码）

代码**不预设默认模型**（模型迭代快，硬编码示例很快过时）。在 `.env` 设置三件事：

```
LLM_PROVIDER=<provider>      # anthropic | openai | deepseek | openrouter | groq | moonshot | zhipu | ollama | custom
<对应 *_API_KEY>              # 如 DEEPSEEK_API_KEY=sk-xxx
LLM_MODEL=<模型名>            # 必填，请到对应 provider 控制台/文档查当前可用模型
```

`agent/agent.py` 内置 provider 注册表（每个 provider 提供便捷 base_url + key 名），改 `LLM_PROVIDER` 一行切换：

| `LLM_PROVIDER` | 需要的 key | 备注 |
|----------------|-----------|------|
| `anthropic`（默认） | `ANTHROPIC_API_KEY` | 也可用 `ANTHROPIC_MODEL` |
| `openai` | `OPENAI_API_KEY` | |
| `deepseek` | `DEEPSEEK_API_KEY` | 走 OpenAI 兼容 API |
| `openrouter` | `OPENROUTER_API_KEY` | 一个 key 路由多 provider |
| `groq` | `GROQ_API_KEY` | Groq LPU 极速推理 |
| `moonshot` | `MOONSHOT_API_KEY` | Moonshot / Kimi |
| `zhipu` | `ZHIPU_API_KEY` | 智谱 GLM |
| `ollama` | 无需 key | 本地推理（先 `ollama pull <模型名>`） |
| `custom` | `OPENAI_COMPATIBLE_BASE_URL` + `_API_KEY` + `_MODEL` | 任意 OpenAI 兼容端点 |

缺 `LLM_MODEL` 时程序会 fail-fast 并提示去对应平台查可用模型。

### KeeperHub

| 变量 | 必填 | 说明 |
|------|------|------|
| `KEEPERHUB_API_KEY` | 是 | `kh_` 前缀，在 app.keeperhub.com -> Settings -> API Keys 创建 |
| `WALLET_INTEGRATION_ID` | 否 | KeeperHub 托管钱包 integrationId（Dashboard 钱包页用） |
| `KEEPERHUB_MCP_URL` | 否 | 默认 `https://app.keeperhub.com/mcp` |
| `KEEPERHUB_MCP_TRANSPORT` | 否 | 默认 `streamable_http` |

> 以上配置也可以在 **Web Dashboard 前端直接填写**（Provider 标签页 / KeeperHub 标签页），运行时注入环境变量，无需改 `.env`。

---

## 用法

### 命令行示例

```bash
python examples/run_demo.py            # 确定性转账 + 自然语言 Agent
python examples/full_demo.py           # 3 个真实能力串联（推荐演示）
python examples/subscription_demo.py   # 订阅调度器：立即执行一次 + 显示下次触发
python examples/subscription_demo.py --wait  # 额外等待定时触发并自动执行
python examples/transfer_demo.py       # 仅转账
python examples/workflow_demo.py       # 工作流创建 -> 执行 -> 轮询
```

### Web Dashboard

`web/` 提供浏览器界面（FastAPI + 原生 HTML，零构建）：

```bash
# 安全启动：只绑本机回环（鉴权 token 会自动生成并在启动日志打印，无需手动设置）
uvicorn web.app:app --host 127.0.0.1 --port 8000
# 打开 http://127.0.0.1:8000，按启动日志中的 token 登录（浏览器记住）
```

> 安全说明：
> - **务必绑 127.0.0.1 而非 0.0.0.0**：Dashboard 能建规则、触发真实链上转账，暴露到网段等于把钱包交给局域网。
> - **鉴权始终开启**：所有 `/api/*`（除 `/health`）要求 `Authorization: Bearer <token>`。token 来自 `DASHBOARD_TOKEN` 环境变量；未设置会自动生成随机 token（持久化到 `data/.dashboard_token`，启动日志打印）。公网部署请显式设置 `DASHBOARD_TOKEN`。
> - **规则必须有限制**：创建规则时必须设置非空白名单、单笔限额或每日限额之一，拒绝 `0=不限制` 的全开放规则（`/api/rules` 直接 422）。
> - **`chain_id` 白名单**：执行只允许 `PAYKEEPER_ALLOWED_CHAIN_IDS` 内的链（默认仅 Sepolia 11155111 / Base Sepolia 84532），请求方传主网会直接拒绝。
> - **custom provider 需白名单**：`/api/provider` 的自定义 base_url 必须命中 `OPENAI_COMPATIBLE_BASE_URL_ALLOWLIST`，防止 LLM key 被转发到攻击者服务器。
> - **`kh_` API Key 视为高敏资产**：本仓库历史审计中曾有一次 Key 出现在对话记录（AUDIT S-01），**建议在 app.keeperhub.com 立即轮换**，并定期（如每月）轮换；Key 只放 `.env`，禁止提交、禁止通过前端保存。
> - **主网与 Gas Sponsorship**：本项目默认白名单仅含测试网，防止误触主网。要提交"主网 + 赞助 gas"证据链：在 `.env` 将 `PAYKEEPER_ALLOWED_CHAIN_IDS` 追加主网 chain id（Ethereum=1 / Base=8453），给 KeeperHub 托管钱包充少量 ETH/USDC，然后正常执行任意转账——KeeperHub 会在主网自动应用 Gas Sponsorship，审计记录含 `sponsored:true`。

| 标签页 | 功能 |
|--------|------|
| **执行** | 自然语言建规则（一句话 -> LLM 解析 -> 确认创建）；手动执行（选规则 + 地址 + 金额 -> 风控校验 -> 真实上链） |
| **规则** | 创建 / 启用 / 禁用 / 删除风控规则（白名单、单笔限额、每日累计限额、cron） |
| **执行记录** | 全审计：风控拒绝 / 链上成功 / 失败 + txHash Etherscan 链接 |
| **钱包** | 查看 KeeperHub 托管钱包地址 |
| **Provider** | 前端配置 LLM provider（选 provider + API Key + 模型名 + base_url），运行时生效，不写 `.env` |
| **KeeperHub** | 前端配置 KeeperHub API Key + Wallet Integration ID，运行时注入环境变量，不写 `.env` |

---

## 真实链上交易记录（Sepolia, Chain ID `11155111`）

以下 **8 笔真实链上交易**全部可直接在 Sepolia Etherscan 验证（每笔都附链接；开发期另有更多执行记录在本地日志，此处只列可核验的）。

| # | 类型 | 交易哈希 | Gas 赞助 | 执行 ID |
|---|------|---------|---------|---------|
| 1 | `execute_transfer` | [`0x8bc569…1baa`](https://sepolia.etherscan.io/tx/0x8bc5693d4ca307cad4ef5e069124e1ed25eb62b2086dcda29e9c8e8481631baa) | — | — |
| 2 | `execute_transfer` | [`0xe3dff8…1f7e`](https://sepolia.etherscan.io/tx/0xe3dff8ed1870976a54a02cc82d3093ce47f11cde8dfd031d0b448a7671ab1f7e) | — | `tibsnk9bcntdogef6nii4` |
| 3 | `workflow`（订阅） | [`0x5b0fd6…5bf7`](https://sepolia.etherscan.io/tx/0x5b0fd6bf8428c911d1f5882b8ac83604ee228c3c4173bcf17cd2bcacd5e25bf7) | sponsored | `ejwpzvyanilj5hkeqg1wp` |
| 4 | `execute_transfer`（NL Agent） | [`0xf98cd5…6582`](https://sepolia.etherscan.io/tx/0xf98cd5a476fd61e12af321a72b876f607d7ce8035f5298cd735e2b4d7c666582) | sponsored | `6lagptosr08ei7e6mtipo` |
| 5 | `execute_transfer` | [`0x53399d…5eab`](https://sepolia.etherscan.io/tx/0x53399d71ff2b3151753261a5915259975276148ee68fa8771bc06d81a1b45eab) | — | — |
| 6 | `execute_transfer` | [`0x610036…c121`](https://sepolia.etherscan.io/tx/0x6100369c0f9eadd208bc281ea64ef2b9e69489531a29ecfdaf17b239a7bbc121) | sponsored | — |
| 7 | `execute_transfer`（订阅调度器） | [`0x424af7…ca65`](https://sepolia.etherscan.io/tx/0x424af7e9bba7f1b32aa6395d70839c114184a755bf6593fde746672fa803ca65) | — | `iri3e6q76u1dhfqcdyfjm` |
| 8 | `execute_transfer`（Dashboard 手动执行） | [`0x65203c…b7`](https://sepolia.etherscan.io/tx/0x65203cb5a6b650865afe672cd109d2724b5982a63eea1f2a417fcc6ecac236b7) | — | — |
| 9 | `execute_transfer`（风控路径实测，2026-08-05） | [`0xbf5711…1abc`](https://sepolia.etherscan.io/tx/0xbf57113c92ad9ac2747b1dcb5c290b115a9cb6f8112f020a602b57f7e1ee1abc) | — | `yo87vwhomq4cjuo0awhui` |
| 10 | `workflow`（订阅付款，2026-08-05） | [`0x683cae…ca35`](https://sepolia.etherscan.io/tx/0x683cae44fd2506aa8f562ba72a816aaffe528c74b18936bc61729ab9d4e8ca35) | sponsored | `s13ot4cxg7bkimayynwc7` |

> **关于 `sponsored` 列**：标注的是**执行时 KeeperHub 返回的 `sponsored: true` 字段**（#3/#4 记录于 2026-08-03，第 10 笔 2026-08-05 实跑返回同字段，见本地 `examples/output/transactions_log.md`），非本仓库推断。官方文档称 Gas Sponsorship 面向主网 Ethereum，测试网是否实际赞助以执行时返回为准；`—` 表示该笔返回中未出现该字段。
>
> **交易数口径**：以上 10 笔为本仓库可核验的全部链上交易（8 笔历史记录 + 2026-08-05 新增 2 笔），另有更早期会话中的数笔仅存于本地日志、未计入可核验清单。
>
> **主网 / Base Sepolia 实测（2026-08-05）**：已尝试向主网（chain_id=1）与 Base Sepolia（84532）执行小额转账，KeeperHub 返回 `Insufficient ETH/BASE balance. Have: 0.0`——托管钱包仅 Sepolia 有资金，主网与 Base 需先充值（见下文「主网与 Gas Sponsorship」指引）。x402 实跑同理需配置 `X402_PRIVATE_KEY` + Base USDC 资金。

---

## 可靠性与安全性

### 可靠性三层防护

```
请求 -> [1] simulate=true 预飞 -> [2] 幂等键 broadcast -> [3] 状态轮询
        |                        |                        |
        v                        v                        v
  wouldRevert?            transfer-funds            success/failed
  false -> 继续            提交真实交易              指数退避重试
  true -> 拒绝             同一幂等键（防双付）
```

- **幂等键**：`uuid4().hex` 一次生成、**重试全程复用**——若首笔已上链但响应超时，重试仍是同一张"单"，KeeperHub 去重，绝不双付（已通过 mock 单测验证）
- **指数退避**：1.5s 起步，2x 递增，最多 3 次
- **状态轮询**：等待 `success | completed | failed | reverted` 终态
- **审计轨迹**：每次执行回传完整 `audit_trail`（simulate / broadcast / confirm 节点）
- **x402 facilitator 白名单**：强制 HTTPS + 后缀白名单（默认仅 `keeperhub.com`，防钓鱼）

### x402 / MPP 按次付费（代码就绪，实跑指引）

`agent/x402_client.py` 实现了完整的 x402 客户端（EIP-3009 `TransferWithAuthorization` 签名 + challenge 解析 + 资产/金额/facilitator 三重白名单）。提交前请完成一次**真实结算**把交易哈希写入 README：

```bash
# 1) 先跑离线检查清单，确认白名单/解析链路（不需要私钥）
python examples/x402_dryrun.py

# 2) 准备实跑环境（.env）
X402_PRIVATE_KEY=<EOA 私钥>            # 需在 Base Sepolia 充少量 USDC
X402_FACILITATOR_URL=https://app.keeperhub.com/settlement   # 以 docs.keeperhub.com 为准

# 3) 真实结算（几十美分即可）
python examples/x402_dryrun.py --real
```

> 字段契约以 [docs.keeperhub.com/ai-tools/agentic-wallet](https://docs.keeperhub.com) 线上为准；首次实跑如遇 402 body 字段差异，按 `extract_challenge` 的容错结构校准。结算成功后把 `settlement` 里的交易哈希追加到上方交易表并标 `x402` 类型。

### 真定时器订阅

`agent/subscription.py` 实现**真正的 cron 订阅调度器**（`SubscriptionManager` + 最小 cron 解析器，9/9 测试用例通过）：

- 每个订阅配置 cron（如 `0 0 1 * *` = 每月 1 号 00:00 UTC）
- 调度循环到点自动调用 `execute_transfer`（复用可靠性层）
- 支持 `run_once` 立即执行、`--wait` 等待下一次触发、多订阅并发
- 平台侧方案：KeeperHub Schedule 工作流（`triggerType=Schedule` + cron）

### 完整风控层

`agent/policy.py` 在「自然语言 -> 链上执行」之间加一层**强制校验**，防止 LLM 理解错误或恶意指令导致超限 / 打错地址：

```
校验链（任一不过即拒绝，绝不上链）
 [1] 地址格式 -> 必须 0x + 40 位 hex
 [2] 规则存在且启用
 [3] 白名单 -> 收款地址必须在白名单（空 = 不限制）
 [4] 单笔限额 -> amount <= single_limit_wei
 [5] 每日累计限额 -> 当日已成功花费 + amount <= daily_limit_wei
```

- **SQLite 持久化**：规则 + 执行记录（含 tx_hash / 状态 / 错误），零额外依赖
- **记账**：成功执行自动计入当日累计，用于每日限额
- **集成**：`execute_transfer(policy_engine=..., policy_rule_id=...)` 执行前校验、成功后记账，审计轨迹含 `policy` 节点
- 测试覆盖：8/8 单元测试 + 5/5 集成测试

### 运行测试（离线，无需 KeeperHub key）

```bash
pip install pytest
python -m pytest tests/ -q   # 46 用例全通过（风控 / 金额解析 / cron / 订阅幂等 / x402 / Agent 包装器）
```

全部测试不触碰网络与 KeeperHub：风控引擎用 `:memory:` SQLite，Agent 包装器用 fake tool 验证「风控拦截时底层工具绝不被调用」。

### 安全审计

完整报告见 [`AUDIT_REPORT.md`](AUDIT_REPORT.md)（6 项 bug 已修复，3 项 follow-up 保留）：

- B-01：执行状态判定（pending 不再误判为 success）
- B-02：simulate 结果校验（`wouldRevert` 检测）
- B-03：x402 facilitator 域名白名单
- B-04：x402 金额计算冗余清理
- B-05：重试复用同一幂等键（防双付，外部评审发现）
- B-06：真定时器订阅调度器（外部评审发现"订阅只是一次性转账"）

---

## 项目结构

```
paykeeper/
├── agent/                    # 核心模块
│   ├── keeperhub_mcp.py      # KeeperHub MCP 客户端（35 tools）
│   ├── payments.py           # 转账 / 合约调用 / 工作流（可靠性层 + 风控集成）
│   ├── policy.py             # 完整风控引擎（白名单 / 限额 / SQLite）
│   ├── subscription.py       # 真正的 cron 订阅调度器（真定时器）
│   ├── agent.py              # LangGraph ReAct Agent + 9-provider 注册表
│   └── x402_client.py        # EIP-3009 签名 + facilitator 校验
├── web/                      # Web Dashboard
│   ├── app.py                # FastAPI 后端（规则 / 执行 / 钱包 / NL 解析 / Provider / KeeperHub 配置）
│   └── templates/index.html  # 前端单页 Dashboard（6 标签页）
├── examples/                 # 运行入口
│   ├── run_demo.py           # 默认：确定性转账 + NL Agent
│   ├── full_demo.py          # 3 个真实能力串联（推荐演示）
│   ├── subscription_demo.py  # 订阅调度器演示（run_once + --wait 定时触发）
│   ├── transfer_demo.py      # 仅转账
│   ├── video_demo.py         # 单次 NL Agent（紧凑叙事）
│   ├── workflow_demo.py      # 工作流创建 -> 执行 -> 轮询（同名查重复用）
│   └── x402_dryrun.py        # x402 按次付费离线检查清单（--real 真实结算）
├── tests/                    # 离线测试套件（46 用例，pytest 全通过，无需 kh key）
│   ├── test_policy.py        # 风控引擎 10 用例
│   ├── test_payments.py      # 金额 fail-closed + 链白名单 5 用例
│   ├── test_subscription.py  # cron 9 用例 + 订阅幂等/fail-closed 5 用例
│   ├── test_x402_client.py   # facilitator/资产/金额白名单 9 用例
│   └── test_agent_wrapper.py # Agent 资金工具包装器 8 用例（fake tool）
├── docs/                     # 文档（Bounty 材料 + 视频指南）
│   ├── TUTORIAL.md           # 从零到第一次 KeeperHub 交易
│   ├── ONBOARDING_TEARDOWN.md # 上手指引 5 大痛点 + 改进建议
│   └── DEMO_SCRIPT.md        # 演示视频录制指南
├── demo/                     # 演示视频（真实终端录制）
│   └── paykeeper_demo_final.mp4  # 38s 最终视频
├── AUDIT_REPORT.md           # 安全审计报告
├── README.md                 # 中文（本文档）
├── README_EN.md              # English
├── requirements.txt
├── .env.example
└── mcp_config.json
```

---

## Judging Criteria 对照（hackathon 官方标准）

> **Execution is weighted heavily, because that is the point.**

### 1. Does it execute onchain via KeeperHub?（通过）

- **8 笔真实 Sepolia 交易**（上表全部附 Etherscan 链接，每笔含 `transactionHash`、`executionId`、`gasUsed`、`sponsored`）
- 不是 mockup：全部经 KeeperHub 真实广播，浏览器可验证

### 2. Use of KeeperHub surfaces（通过）

- **MCP server**（35 个工具，`agent/keeperhub_mcp.py`）
- **直接执行** `execute_transfer` / `execute_contract_call`
- **x402 / MPP 按次付费**（EIP-3009 签名 + facilitator 白名单）
- **Workflow builder**（创建 / 校验 / 执行 / 轮询，442 actions + 6 触发器）
- **Audit trail**（每次执行回传 + 控制台可视化）

### 3. Reliability and observability（通过）

- **失败模式处理**：`simulate` 预飞拒绝 `wouldRevert=true` 的交易
- **重试机制**：指数退避（1.5s -> 3s -> 6s），重试**复用同一幂等键**（已 mock 单测验证，防"首笔已上链但响应超时 -> 重试双付"）
- **Gas 处理**：`Gas Sponsorship`（`sponsored:true` 多笔验证）+ 非赞助场景的 gas 估算与回执
- **审计使用**：每次执行回传 `audit_trail` 节点列表（simulate / broadcast / confirm）

### 4. Originality and real-world usefulness（通过）

PayKeeper 解决一个真实需求：**让任何能说自然语言的人都能发起可审计的链上付款**。

- **订阅代理（真定时器）**：`agent/subscription.py` cron 调度器到点自动付款
- **余额守卫**："查询余额后若低于 0.5 ETH 就补足到 1 ETH" 类条件支付
- **按次付费**：x402 MPP 场景下 Agent 自动签名 EIP-3009 付款
- **批量结算**：自然语言"把这两个地址各转 0.1 ETH" -> Agent 多次调用 `execute_transfer`

适合场景：DAO 财库自动发薪、DeFi 自动化订阅（VPN/SaaS 代付）、AI Agent 之间 micropayment、电商自动结算。

### 5. Integration quality and developer experience（通过）

- **9 个 LLM provider** 一行切换（`agent/agent.py` 注册表设计，模型名用户自配）
- **端到端文档**：`docs/TUTORIAL.md` 从零到第一次交易、`docs/DEMO_SCRIPT.md` 录屏指南
- **演示脚本开箱即用**：`python examples/full_demo.py` 一行运行
- **依赖锁定**：`mcp<2.0` + `httpx<0.28` 避免 API 兼容问题（requirements.txt）
- **安全审计可见**：`AUDIT_REPORT.md` 列出 6 个已修 bug + 3 个 follow-up
- **零外部数据库依赖**：纯 Python + MCP，不引入 DB / Redis

---

## 提交材料

| 项 | 位置 |
|----|------|
| 源码 | 本仓库 |
| 演示视频（真实终端） | [`demo/paykeeper_demo_final.mp4`](demo/paykeeper_demo_final.mp4)（38s） |
| 视频录制指南 | [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) |
| Bounty 材料：教程 | [`docs/TUTORIAL.md`](docs/TUTORIAL.md) |
| Bounty 材料：上手指引 | [`docs/ONBOARDING_TEARDOWN.md`](docs/ONBOARDING_TEARDOWN.md) |
| 安全审计 | [`AUDIT_REPORT.md`](AUDIT_REPORT.md) |
| 交易证据 | 上表 8 笔 Etherscan 链接 + 本地完整日志 |

---

## Acknowledgments

- [KeeperHub](https://app.keeperhub.com) — MCP / x402 / 审计 / 钱包基础设施
- [DeepSeek](https://platform.deepseek.com) — 默认 LLM，OpenAI 兼容 API
- [LangChain / LangGraph](https://www.langchain.com) — ReAct Agent 框架

---

## License

MIT © 2026 PayKeeper Contributors
