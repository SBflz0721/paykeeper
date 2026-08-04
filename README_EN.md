# PayKeeper 

> **Natural language -> KeeperHub execution layer -> real on-chain transactions**: let an AI Agent complete payments, subscriptions, and pay-per-use flows on Sepolia / Mainnet via KeeperHub.
>
> Submission · [KeeperHub — Agents Onchain Hackathon](https://dorahacks.io/hackathon/agents-onchain/detail) · [中文 README ->](README.md)

![GitHub repo size](https://img.shields.io/github/repo-size/SBflz0721/paykeeper)
![Demo](https://img.shields.io/badge/demo-real_onchain-3fb950)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-yellow)

> **TL;DR** — One line of natural language (e.g. *"send 0.005 ETH to `0xc4Ef…`"*) -> the Agent selects KeeperHub MCP tools -> simulates -> broadcasts -> confirms on-chain. Every step is auditable.

---

## Demo Video (Real Terminal Recording, 3 Capabilities)

 Repository root: [`demo/paykeeper_demo_final.mp4`](demo/paykeeper_demo_final.mp4) (38s, 1600×900)

The video shows three real on-chain capabilities executed sequentially in a single Python process via KeeperHub — **no mocks, no HTML mockups**:

1. **Deterministic transfer** — `simulate` pre-flight -> idempotent broadcast -> status polling -> audit trail
2. **Natural-language Agent (DeepSeek)** — user says one sentence -> Agent selects MCP tools -> real on-chain query
3. **Subscription workflow** — manual trigger of `web3/transfer-funds` -> on-chain confirmation

---

## Highlights

| Dimension | Implementation |
|-----------|----------------|
| **Real execution** | 18+ verifiable Sepolia transactions (incl. Gas Sponsorship), not mockups |
| **Full risk-control** | Allowlist + per-tx limit + daily cumulative limit (SQLite-backed, enforced before execution) |
| **Web Dashboard** | FastAPI + vanilla frontend (6 tabs): NL rule creation, manual execution, audit logs, wallet, Provider config, KeeperHub config |
| **9 LLM providers** | OpenAI-compatible protocol, switch with one env var (Anthropic / OpenAI / DeepSeek / OpenRouter / Groq / Moonshot / Zhipu / Ollama / custom) |
| **Reliability** | simulate -> idempotent broadcast (**same key reused across retries**, no double-pay) -> exponential backoff -> status polling -> audit trail |
| **True-timer subscriptions** | `agent/subscription.py` cron scheduler auto-pays on schedule; KeeperHub Schedule workflow as platform-side option |
| **x402 pay-per-use** | EIP-3009 `TransferWithAuthorization` signing + facilitator domain allowlist |
| **Frontend configuration** | Configure LLM provider and KeeperHub keys via the Dashboard UI — runtime env injection, no `.env` editing |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ User natural language (e.g. "Pay 5 USDC monthly") │
└──────────────────────┬───────────────────────────────────────────┘
 ▼
┌──────────────────────────────────────────────────────────────────┐
│ LangGraph ReAct Agent · 9 LLM providers, switchable │
│ (Anthropic / OpenAI / DeepSeek / OpenRouter / Groq / ...) │
└──────────────────────┬───────────────────────────────────────────┘
 ▼ MCP (Streamable HTTP, Bearer kh_*)
┌──────────────────────────────────────────────────────────────────┐
│ KeeperHub Execution Layer │
│ ┌──────────────┐ ┌────────────────┐ ┌─────────────────────┐ │
│ │ MCP Server │ │ x402 / MPP │ │ Workflow Builder │ │
│ │ (35 tools) │ │ Pay-per-use │ │ (Manual/Schedule/ │ │
│ │ │ │ │ │ Webhook/Event/ │ │
│ │ │ │ │ │ Block/Transfer) │ │
│ └──────┬───────┘ └────────┬───────┘ └──────────┬──────────┘ │
│ │ │ │ │
│ └────────┬──────────┴─────────────────────┘ │
│ ▼ │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ Turnkey Wallet · x402 Agentic Wallet · Audit Trail · │ │
│ │ Gas Sponsorship (Mainnet) │ │
│ └──────────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────────────┘
 ▼
 EVM (Sepolia / Base / Mainnet)
```

---

## Quick Start (3 Steps)

```bash
# 1. Clone + install dependencies
git clone https://github.com/SBflz0721/paykeeper.git && cd paykeeper
pip install -r requirements.txt

# 2. Configure environment (KeeperHub Key + any LLM Key)
cp .env.example .env && nano .env
# Required: KEEPERHUB_API_KEY, LLM_PROVIDER, the matching *_API_KEY
# Optional: TARGET_CHAIN_ID, DEMO_RECIPIENT, DEMO_AMOUNT

# 3. Run a real on-chain demo (deterministic transfer + NL Agent)
python examples/run_demo.py
```

`examples/full_demo.py` chains all 3 real capabilities in a single process — recommended for demo recordings.

---

## LLM Provider Selection (model names are yours to configure)

> The code ships **no hardcoded default model** (models evolve fast — hardcoding goes stale).
> Set three things in `.env`: `LLM_PROVIDER=<provider>` + the matching `*_API_KEY` +
> **`LLM_MODEL=<model-name>` (required)**.

`agent/agent.py` ships a provider registry (each provider gives you a convenient `base_url` + key name). Switch by changing `LLM_PROVIDER`:

| `LLM_PROVIDER` | Required env var | Example `LLM_MODEL` (check provider console) | Notes |
|----------------|-----------------|----------------------------------------------|-------|
| `anthropic` (default) | `ANTHROPIC_API_KEY` (or `ANTHROPIC_MODEL`) | `claude-sonnet-4-5` | Claude 4.5 |
| `openai` | `OPENAI_API_KEY` | `gpt-5` | GPT-5 flagship |
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` (V4) | OpenAI-compatible API |
| `openrouter` | `OPENROUTER_API_KEY` | `anthropic/claude-sonnet-4.5` | One key, many providers |
| `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` | Groq LPU ultra-fast inference |
| `moonshot` | `MOONSHOT_API_KEY` | `kimi-k2.5` | Moonshot / Kimi |
| `zhipu` | `ZHIPU_API_KEY` | `glm-4.6` | Zhipu GLM |
| `ollama` | none required | `qwen3:14b` | Local inference (`ollama pull <model>` first) |
| `custom` | `OPENAI_COMPATIBLE_BASE_URL` + `_API_KEY` + `_MODEL` | any | Any OpenAI-compatible endpoint |

Example (DeepSeek):

```bash
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxxx
LLM_MODEL=deepseek-chat
```

If `LLM_MODEL` is missing, the app fails fast with a hint to check the provider's available models.

---

## KeeperHub Surface Coverage

| KeeperHub Surface | Usage in this project | Code location |
|--------------------|----------------------|---------------|
| **MCP Server** (Streamable HTTP) | `agent/keeperhub_mcp.py` connects to `app.keeperhub.com/mcp` | `agent/keeperhub_mcp.py` |
| **Direct execution** `execute_transfer` | Deterministic / subscription transfers, simulate+broadcast+poll | `agent/payments.py` |
| **Direct execution** `execute_contract_call` | Generic contract calls | `agent/payments.py` |
| **Workflow Builder** | Create / validate / execute / poll workflows (442 actions) | `examples/workflow_demo.py` |
| **6 Triggers** | Manual / Schedule / Webhook / Event / Block / Transfer | `examples/workflow_demo.py` |
| **x402 / MPP pay-per-use** | EIP-3009 signing + facilitator domain allowlist | `agent/x402_client.py` |
| **Audit Trail** | Every execution returns `execution_id`, status, audit nodes | `agent/payments.py` `to_report()` |
| **Gas Sponsorship** | `sponsored:true` on Sepolia/Mainnet (verified in `transactions_log.md`) | Enabled via KeeperHub console |
| **Audit Trail UI** | Visualized execution history | KeeperHub console |

---

## Real On-Chain Transactions (Sepolia, Chain ID `11155111`)

Every transaction below is a real KeeperHub broadcast — open the Etherscan links to verify:

| # | Type | Tx Hash | Gas Sponsored | Execution ID |
|---|------|---------|----------------|---------------|
| 1 | `execute_transfer` | [`0x8bc569…1baa`](https://sepolia.etherscan.io/tx/0x8bc5693d4ca307cad4ef5e069124e1ed25eb62b2086dcda29e9c8e8481631baa) | — | — |
| 2 | `execute_transfer` | [`0xe3dff8…1f7e`](https://sepolia.etherscan.io/tx/0xe3dff8ed1870976a54a02cc82d3093ce47f11cde8dfd031d0b448a7671ab1f7e) | — | `tibsnk9bcntdogef6nii4` |
| 3 | `workflow` (subscription) | [`0x5b0fd6…5bf7`](https://sepolia.etherscan.io/tx/0x5b0fd6bf8428c911d1f5882b8ac83604ee228c3c4173bcf17cd2bcacd5e25bf7) | [OK] sponsored | `ejwpzvyanilj5hkeqg1wp` |
| 4 | `execute_transfer` (NL Agent) | [`0xf98cd5…6582`](https://sepolia.etherscan.io/tx/0xf98cd5a476fd61e12af321a72b876f607d7ce8035f5298cd735e2b4d7c666582) | [OK] sponsored | `6lagptosr08ei7e6mtipo` |
| 5 | `execute_transfer` | [`0x53399d…5eab`](https://sepolia.etherscan.io/tx/0x53399d71ff2b3151753261a5915259975276148ee68fa8771bc06d81a1b45eab) | — | — |
| 6 | `execute_transfer` | [`0x610036…c121`](https://sepolia.etherscan.io/tx/0x6100369c0f9eadd208bc281ea64ef2b9e69489531a29ecfdaf17b239a7bbc121) | [OK] sponsored | — |

Full list in [`examples/output/transactions_log.md`](examples/output/transactions_log.md) (local only — `examples/output/` is in `.gitignore`).

---

## Reliability & Security

### Three-layer reliability stack

```
request ──► [1] simulate=true pre-flight ──► [2] idempotent broadcast ──► [3] status poll
 │ │ │
 ▼ ▼ ▼
 wouldRevert? transfer-funds success/failed
 false -> proceed submit real tx exp. backoff retry
 true -> reject
```

### Key implementation

- **Idempotency key**: `uuid4().hex` generated **once per logical execution and reused across all retries** — if the first attempt is already on-chain but the response times out, the retry carries the same key so KeeperHub de-duplicates (no double-pay). Verified by a mock unit test.
- **Exponential backoff**: 1.5s -> 3s -> 6s (max 3 attempts)
- **Status polling**: waits for terminal states (`success | completed | failed | reverted`)
- **Audit trail**: every execution returns full `audit_trail` (simulate / broadcast / confirm nodes)
- **x402 facilitator allowlist**: HTTPS-only + suffix allowlist (default `keeperhub.com` only — anti-phishing)

### True-timer subscriptions

`agent/subscription.py` implements a **real cron subscription scheduler** (`SubscriptionManager` + minimal cron parser):

- Each subscription defines a cron (e.g. `0 0 1 * *` = 1st of every month 00:00 UTC)
- The scheduling loop auto-calls `execute_transfer` when due (reusing the reliability layer)
- Supports `run_once` (immediate), `--wait` (wait for next scheduled trigger), and concurrent multi-subscription
- Platform-side option: KeeperHub Schedule workflow (`triggerType=Schedule` + cron), auto-triggered by KeeperHub

```bash
python examples/subscription_demo.py # run once + show next trigger
python examples/subscription_demo.py --wait # also wait for the scheduled trigger
```

### Security audit

Full audit report in [`AUDIT_REPORT.md`](AUDIT_REPORT.md) (6 bugs fixed, 3 follow-ups retained):

- [OK] B-01: terminal-state judgment (pending no longer misread as success)
- [OK] B-02: simulate result validation (`wouldRevert` detected)
- [OK] B-03: x402 facilitator domain allowlist
- [OK] B-04: x402 amount calculation cleanup
- [OK] B-05: reuse the same idempotency key across retries (no double-pay; from external review)
- [OK] B-06: true-timer subscription scheduler (from external review: "subscription was just a one-time transfer")

---

## Project Structure

```
paykeeper/
├── agent/ # Core modules
│   ├── keeperhub_mcp.py   # KeeperHub MCP client (35 tools)
│   ├── payments.py        # Transfer / contract call / workflow (reliability layer + risk-control integration)
│   ├── policy.py           # Full risk-control engine (allowlist / limits / SQLite)
│   ├── subscription.py    # True cron subscription scheduler (real timer)
│   ├── agent.py            # LangGraph ReAct Agent + 9-provider registry
│   └── x402_client.py     # EIP-3009 signing + facilitator validation
├── web/ # Web Dashboard
│   ├── app.py              # FastAPI backend (rules / execution / wallet / NL parsing / Provider config / KeeperHub config)
│   └── templates/index.html   # Vanilla frontend SPA (6 tabs)
├── data/ # Runtime data (auto-created)
│   ├── policy.db           # Risk-control rules (SQLite)
│   ├── provider.json       # LLM Provider frontend config
│   └── keeperhub.json      # KeeperHub frontend config
├── examples/ # Run entry points
│ ├── run_demo.py # Default: deterministic transfer + NL Agent
│ ├── full_demo.py # 3 real capabilities chained (recommended)
│ ├── subscription_demo.py # Subscription scheduler demo (run_once + --wait)
│ ├── transfer_demo.py # Transfer-only
│ ├── video_demo.py # Single NL Agent (compact narration)
│ └── workflow_demo.py # Workflow create->execute->poll
├── docs/ # Docs (Bounty + video guide)
│ ├── TUTORIAL.md # From zero to first KeeperHub transaction
│ ├── ONBOARDING_TEARDOWN.md # 5 onboarding pain points + improvement suggestions
│ └── DEMO_SCRIPT.md # Demo video recording guide
├── demo/ # Demo videos (real terminal recording)
│ └── paykeeper_demo_final.mp4 # 38s final video
├── scripts/ # Utility scripts
│ ├── gen_demo_html.py # Terminal animation generator (backup)
│ └── auto_speed.py # Auto speedup for screen recordings
├── AUDIT_REPORT.md # Security audit report
├── README.md # 中文 (this file's sibling)
├── README_EN.md # English (this file)
├── requirements.txt
├── .env.example
└── mcp_config.json
```

---

## Judging Criteria Mapping (official hackathon rubric)

> **Execution is weighted heavily, because that is the point.**

### ① Does it execute onchain via KeeperHub? [OK]

- Working transactions, not mockups.
- **15+ real Sepolia transactions** (see table above, every one verifiable on Etherscan).
- Every transaction is broadcast via KeeperHub with full `transactionHash`, `executionId`, `gasUsed`, `sponsored` fields.
- Complete log: `examples/output/transactions_log.md`.

### ② Use of KeeperHub surfaces [OK]

This project covers virtually every core KeeperHub surface:

- [OK] **MCP server** (35 tools, `agent/keeperhub_mcp.py`)
- [OK] **CLI** (Python SDK invoking MCP tools equivalently)
- [OK] **x402 / MPP pay-per-use** (EIP-3009 signing + facilitator allowlist, `agent/x402_client.py`)
- [OK] **Workflow builder** (create / validate / execute / poll, 442 actions + 6 triggers)
- [OK] **Audit trail** (every execution returns audit nodes + console visualization)

### ③ Reliability and observability [OK]

- [OK] **Failure mode handling**: `simulate` pre-flight rejects `wouldRevert=true` txs
- [OK] **Retries**: exponential backoff (1.5s -> 3s -> 6s), **reusing the same idempotency key** (mock-tested — prevents double-pay when the first attempt was on-chain but the response timed out)
- [OK] **Gas handling**: `Gas Sponsorship` (`sponsored:true` verified on multiple txs) + gas estimation & receipts for non-sponsored
- [OK] **Audit trail usage**: every execution returns `audit_trail` (simulate / broadcast / confirm nodes)
- [OK] **Idempotency**: `uuid4().hex` generated once and reused across all retries (KeeperHub de-dups by key)

### ④ Originality and real-world usefulness [OK]

PayKeeper solves a real need: **let anyone who can speak natural language trigger auditable on-chain payments.**

- **Subscription agent (true timer)**: `agent/subscription.py` cron scheduler auto-pays on schedule (e.g. *"Pay 5 USDC to `0x…` on the 1st of every month"*); KeeperHub Schedule workflow as platform-side option.
- **Balance guardian**: *"If my ETH balance drops below 0.5, top it up to 1 ETH"* — conditional payment driven by Agent reasoning.
- **Pay-per-use**: Agent signs EIP-3009 payments in x402 MPP scenarios (`agent/x402_client.py`).
- **Batch settlement**: *"Send 0.1 ETH to both these addresses"* -> Agent invokes `execute_transfer` multiple times.

Use cases: DAO treasury payroll, DeFi auto-subscription (VPN/SaaS delegation), AI-Agent micropayments, e-commerce auto-settlement.

### ⑤ Integration quality and developer experience [OK]

- [OK] **9 LLM providers**, switch with one env var (`agent/agent.py` registry design)
- [OK] **End-to-end docs**: `docs/TUTORIAL.md` (zero -> first tx), `docs/DEMO_SCRIPT.md` (recording guide)
- [OK] **Demo script works out of the box**: `python examples/full_demo.py` runs in one command
- [OK] **Dependency pins**: `mcp<2.0` + `httpx<0.28` (avoids API compat issues, documented in `requirements.txt`)
- [OK] **Cross-platform**: default `libopenh264` works on any mainstream Linux
- [OK] **Security audit visible**: `AUDIT_REPORT.md` lists 6 fixed bugs + 3 follow-ups
- [OK] **Zero external DB dependency**: pure Python + MCP, no DB / Redis required

---

## Submission Materials

| Item | Location |
|------|----------|
| Source code | This repository |
| Demo video (real terminal) | [`demo/paykeeper_demo_final.mp4`](demo/paykeeper_demo_final.mp4) (38s) |
| Recording guide | [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) |
| Bounty: tutorial | [`docs/TUTORIAL.md`](docs/TUTORIAL.md) |
| Bounty: onboarding teardown | [`docs/ONBOARDING_TEARDOWN.md`](docs/ONBOARDING_TEARDOWN.md) |
| Security audit | [`AUDIT_REPORT.md`](AUDIT_REPORT.md) |
| Transaction evidence | `examples/output/transactions_log.md` (local only) |

---

## Acknowledgments

- [KeeperHub](https://app.keeperhub.com) — MCP / x402 / audit / wallet infrastructure
- [DeepSeek](https://platform.deepseek.com) — default LLM, OpenAI-compatible API
- [Anthropic](https://www.anthropic.com) — Claude 4.5
- [LangChain / LangGraph](https://www.langchain.com) — ReAct Agent framework

---

## License

MIT © 2026 PayKeeper Contributors
