# PayKeeper

> One sentence of natural language is all it takes for an AI Agent to pay, subscribe, and pay-per-use on-chain via KeeperHub — every step auditable.

[![GitHub repo size](https://img.shields.io/github/repo-size/SBflz0721/paykeeper)](https://github.com/SBflz0721/paykeeper)
[![Demo](https://img.shields.io/badge/demo-real_onchain-3fb950)](demo/paykeeper_demo_final.mp4)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](requirements.txt)
[![License](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

Submission · [KeeperHub — Agents Onchain Hackathon](https://dorahacks.io/hackathon/agents-onchain/detail) · [中文 README ->](README.md)

---

## Why This Exists

On-chain payments are still too "engineering" for regular users: pick a tool, assemble parameters, watch receipts, avoid double-pay. **PayKeeper turns that into one sentence.**

You say *"send 0.01 ETH to `0x…` every Friday, daily limit 0.05"* — the Agent does the rest: parse the intent -> match a risk-control rule -> pre-flight via the KeeperHub MCP -> idempotent broadcast -> poll for confirmation -> output an auditable report. The money really moves on-chain, but the user only ever spoke human language.

**Three problems it solves:**
1. **Natural language as the payment instruction** — no MCP tool knowledge, no hand-written JSON
2. **A hard safety boundary for money** — allowlist / per-tx limit / daily cumulative limit; even a misread LLM intent cannot overspend
3. **Auditable, retryable, double-pay-proof** — one idempotency key reused across all retries

---

## Demo Video (Real Terminal Recording)

[`demo/paykeeper_demo_final.mp4`](demo/paykeeper_demo_final.mp4) (38s, 1600x900) — three real on-chain capabilities executed in a single Python process, **all via KeeperHub, no mocks**:

1. **Deterministic transfer** — `simulate` pre-flight -> idempotent broadcast -> status polling -> audit trail
2. **Natural-language Agent (DeepSeek)** — one sentence -> Agent selects MCP tools -> real on-chain execution
3. **Subscription workflow** — manual trigger of `web3/transfer-funds` -> on-chain confirmation

---

## Quick Start (3 Steps)

```bash
# 1. Clone + install dependencies
git clone https://github.com/SBflz0721/paykeeper.git && cd paykeeper
pip install -r requirements.txt

# 2. Configure environment (KeeperHub Key + any LLM Key)
cp .env.example .env && nano .env
# Required: KEEPERHUB_API_KEY (kh_ prefix), LLM_PROVIDER, matching *_API_KEY, LLM_MODEL

# 3. Run a real on-chain demo (deterministic transfer + NL Agent)
python examples/run_demo.py
```

> Recommended demo entry: `python examples/full_demo.py` — chains deterministic transfer / NL Agent / subscription workflow in a single process.

---

## Highlights

| Dimension | Implementation |
|-----------|----------------|
| **Real execution** | **18** verifiable Sepolia transactions (incl. Gas Sponsorship), not mockups |
| **Full risk-control** | Allowlist + per-tx limit + daily cumulative limit (SQLite-backed, enforced before execution) |
| **Web Dashboard** | FastAPI + vanilla frontend (6 tabs): NL rule creation, manual execution, audit logs, wallet, Provider config, KeeperHub config |
| **9 LLM providers** | OpenAI-compatible protocol, switch with one env var (Anthropic / OpenAI / DeepSeek / OpenRouter / Groq / Moonshot / Zhipu / Ollama / custom) |
| **Reliability** | simulate -> idempotent broadcast (**same key reused across retries**, no double-pay) -> exponential backoff -> status polling -> audit trail |
| **True-timer subscriptions** | `agent/subscription.py` cron scheduler auto-pays on schedule; KeeperHub Schedule workflow as platform-side option |
| **x402 pay-per-use** | EIP-3009 `TransferWithAuthorization` signing + facilitator domain allowlist |
| **Security** | 6 audit fixes shipped (B-01~B-06, incl. 2 from external review), full report in `AUDIT_REPORT.md` |

---

## Architecture

```
User natural language (e.g. "Pay 5 USDC monthly")
        |
        v
+-----------------------------------------------------+
| LangGraph ReAct Agent · 9 LLM providers, switchable  |
| (Anthropic / OpenAI / DeepSeek / OpenRouter / ...)  |
+------------------------+----------------------------+
                         | MCP (Streamable HTTP, Bearer kh_*)
                         v
+-----------------------------------------------------+
| KeeperHub Execution Layer                            |
|  +-------------+  +--------------+  +------------+  |
|  | MCP Server  |  | x402 / MPP   |  | Workflow   |  |
|  | (35 tools)  |  | Pay-per-use  |  | Builder    |  |
|  +------+------+  +------+-------+  +-----+------+  |
|         +---------+------+---------+------+         |
|                  v               v                  |
|  Turnkey Wallet · x402 Agentic Wallet · Audit Trail |
|  Gas Sponsorship (Mainnet)                          |
+------------------------+----------------------------+
                         | EVM
                         v
              Sepolia / Base / Mainnet
```

---

## Configuration

### LLM Provider (model names are yours to configure)

The code ships **no hardcoded default model** (models evolve fast — hardcoding goes stale). Set three things in `.env`:

```
LLM_PROVIDER=<provider>      # anthropic | openai | deepseek | openrouter | groq | moonshot | zhipu | ollama | custom
<matching *_API_KEY>         # e.g. DEEPSEEK_API_KEY=sk-xxx
LLM_MODEL=<model-name>       # required; check the provider console
```

`agent/agent.py` ships a provider registry (each provider gives you a convenient `base_url` + key name). Switch by changing `LLM_PROVIDER`:

| `LLM_PROVIDER` | Required env var | Notes |
|----------------|-----------------|-------|
| `anthropic` (default) | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL` also works |
| `openai` | `OPENAI_API_KEY` | |
| `deepseek` | `DEEPSEEK_API_KEY` | OpenAI-compatible API |
| `openrouter` | `OPENROUTER_API_KEY` | One key, many providers |
| `groq` | `GROQ_API_KEY` | Groq LPU ultra-fast inference |
| `moonshot` | `MOONSHOT_API_KEY` | Moonshot / Kimi |
| `zhipu` | `ZHIPU_API_KEY` | Zhipu GLM |
| `ollama` | none required | Local inference (`ollama pull <model>` first) |
| `custom` | `OPENAI_COMPATIBLE_BASE_URL` + `_API_KEY` + `_MODEL` | Any OpenAI-compatible endpoint |

If `LLM_MODEL` is missing, the app fails fast with a hint to check the provider's available models.

### KeeperHub

| Variable | Required | Description |
|----------|----------|-------------|
| `KEEPERHUB_API_KEY` | yes | `kh_` prefix; create at app.keeperhub.com -> Settings -> API Keys |
| `WALLET_INTEGRATION_ID` | no | KeeperHub managed-wallet integrationId (used by the Dashboard wallet tab) |
| `KEEPERHUB_MCP_URL` | no | Default `https://app.keeperhub.com/mcp` |
| `KEEPERHUB_MCP_TRANSPORT` | no | Default `streamable_http` |

> You can also configure both the LLM provider and the KeeperHub key directly in the **Web Dashboard UI** (Provider / KeeperHub tabs) — runtime env injection, no `.env` editing.

---

## Usage

### CLI examples

```bash
python examples/run_demo.py            # deterministic transfer + NL Agent
python examples/full_demo.py           # 3 real capabilities chained (recommended)
python examples/subscription_demo.py   # subscription scheduler: run once + show next trigger
python examples/subscription_demo.py --wait  # also wait for the scheduled trigger
python examples/transfer_demo.py       # transfer only
python examples/workflow_demo.py       # workflow create -> execute -> poll
```

### Web Dashboard

`web/` provides a browser UI (FastAPI + vanilla HTML, zero build):

```bash
uvicorn web.app:app --host 0.0.0.0 --port 8000
# open http://localhost:8000
```

| Tab | What it does |
|-----|--------------|
| **Execute** | NL rule creation (one sentence -> LLM parse -> confirm); manual execution (rule + address + amount -> risk check -> real on-chain) |
| **Rules** | Create / enable / disable / delete risk-control rules (allowlist, per-tx limit, daily limit, cron) |
| **Logs** | Full audit trail: rejected / success / failed + txHash Etherscan links |
| **Wallet** | View the KeeperHub managed wallet |
| **Provider** | Configure LLM provider in the UI (provider + API Key + model + base_url), runtime effective, no `.env` edit |
| **KeeperHub** | Configure KeeperHub API Key + Wallet Integration ID in the UI, runtime env injection, no `.env` edit |

---

## Real On-Chain Transactions (Sepolia, Chain ID `11155111`)

7 of the **18** total real transactions are linked below for direct verification on Etherscan (full log lives locally in `examples/output/transactions_log.md`, which is git-ignored).

| # | Type | Tx Hash | Gas Sponsored | Execution ID |
|---|------|---------|----------------|---------------|
| 1 | `execute_transfer` | [`0x8bc569…1baa`](https://sepolia.etherscan.io/tx/0x8bc5693d4ca307cad4ef5e069124e1ed25eb62b2086dcda29e9c8e8481631baa) | — | — |
| 2 | `execute_transfer` | [`0xe3dff8…1f7e`](https://sepolia.etherscan.io/tx/0xe3dff8ed1870976a54a02cc82d3093ce47f11cde8dfd031d0b448a7671ab1f7e) | — | `tibsnk9bcntdogef6nii4` |
| 3 | `workflow` (subscription) | [`0x5b0fd6…5bf7`](https://sepolia.etherscan.io/tx/0x5b0fd6bf8428c911d1f5882b8ac83604ee228c3c4173bcf17cd2bcacd5e25bf7) | sponsored | `ejwpzvyanilj5hkeqg1wp` |
| 4 | `execute_transfer` (NL Agent) | [`0xf98cd5…6582`](https://sepolia.etherscan.io/tx/0xf98cd5a476fd61e12af321a72b876f607d7ce8035f5298cd735e2b4d7c666582) | sponsored | `6lagptosr08ei7e6mtipo` |
| 5 | `execute_transfer` | [`0x53399d…5eab`](https://sepolia.etherscan.io/tx/0x53399d71ff2b3151753261a5915259975276148ee68fa8771bc06d81a1b45eab) | — | — |
| 6 | `execute_transfer` | [`0x610036…c121`](https://sepolia.etherscan.io/tx/0x6100369c0f9eadd208bc281ea64ef2b9e69489531a29ecfdaf17b239a7bbc121) | sponsored | — |
| 7 | `execute_transfer` (subscription scheduler) | [`0x424af7…ca65`](https://sepolia.etherscan.io/tx/0x424af7e9bba7f1b32aa6395d70839c114184a755bf6593fde746672fa803ca65) | — | `iri3e6q76u1dhfqcdyfjm` |

---

## Reliability & Security

### Three-layer reliability stack

```
request -> [1] simulate=true pre-flight -> [2] idempotent broadcast -> [3] status poll
          |                              |                              |
          v                              v                              v
    wouldRevert?                  transfer-funds                success/failed
    false -> proceed              submit real tx                exp. backoff retry
    true -> reject                same idempotency key (no double-pay)
```

- **Idempotency key**: `uuid4().hex` generated **once per logical execution and reused across all retries** — if the first attempt is already on-chain but the response times out, the retry carries the same key so KeeperHub de-duplicates (no double-pay). Verified by a mock unit test.
- **Exponential backoff**: 1.5s -> 3s -> 6s (max 3 attempts)
- **Status polling**: waits for terminal states (`success | completed | failed | reverted`)
- **Audit trail**: every execution returns full `audit_trail` (simulate / broadcast / confirm nodes)
- **x402 facilitator allowlist**: HTTPS-only + suffix allowlist (default `keeperhub.com` only — anti-phishing)

### True-timer subscriptions

`agent/subscription.py` implements a **real cron subscription scheduler** (`SubscriptionManager` + minimal cron parser, 9/9 test cases passed):

- Each subscription defines a cron (e.g. `0 0 1 * *` = 1st of every month 00:00 UTC)
- The scheduling loop auto-calls `execute_transfer` when due (reusing the reliability layer)
- Supports `run_once` (immediate), `--wait` (wait for next scheduled trigger), and concurrent multi-subscription
- Platform-side option: KeeperHub Schedule workflow (`triggerType=Schedule` + cron)

### Full risk-control layer

`agent/policy.py` adds a **mandatory validation layer** between "natural language" and "on-chain execution", so a misread or malicious LLM intent cannot overspend or hit the wrong address:

```
Validation chain (any failure = reject, never goes on-chain)
 [1] Address format  -> must be 0x + 40 hex
 [2] Rule exists and is enabled
 [3] Allowlist       -> recipient must be in the allowlist (empty = unrestricted)
 [4] Per-tx limit    -> amount <= single_limit_wei
 [5] Daily limit     -> today's successful spend + amount <= daily_limit_wei
```

- **SQLite persistence**: rules + execution records (tx_hash / status / error), zero extra dependencies
- **Accounting**: successful executions count toward the daily cumulative limit automatically
- **Integration**: `execute_transfer(policy_engine=..., policy_rule_id=...)` validates before execution and books after success; the audit trail includes a `policy` node
- **Test coverage**: 8/8 unit tests + 5/5 integration tests

### Security audit

Full report in [`AUDIT_REPORT.md`](AUDIT_REPORT.md) (6 bugs fixed, 3 follow-ups retained):

- B-01: terminal-state judgment (pending no longer misread as success)
- B-02: simulate result validation (`wouldRevert` detected)
- B-03: x402 facilitator domain allowlist
- B-04: x402 amount calculation cleanup
- B-05: reuse the same idempotency key across retries (no double-pay; from external review)
- B-06: true-timer subscription scheduler (from external review: "subscription was just a one-time transfer")

---

## Project Structure

```
paykeeper/
├── agent/                    # Core modules
│   ├── keeperhub_mcp.py      # KeeperHub MCP client (35 tools)
│   ├── payments.py           # Transfer / contract call / workflow (reliability layer + risk-control integration)
│   ├── policy.py             # Full risk-control engine (allowlist / limits / SQLite)
│   ├── subscription.py       # True cron subscription scheduler (real timer)
│   ├── agent.py              # LangGraph ReAct Agent + 9-provider registry
│   └── x402_client.py        # EIP-3009 signing + facilitator validation
├── web/                      # Web Dashboard
│   ├── app.py                # FastAPI backend (rules / execution / wallet / NL parsing / Provider / KeeperHub config)
│   └── templates/index.html  # Vanilla frontend SPA (6 tabs)
├── examples/                 # Run entry points
│   ├── run_demo.py           # Default: deterministic transfer + NL Agent
│   ├── full_demo.py          # 3 real capabilities chained (recommended)
│   ├── subscription_demo.py  # Subscription scheduler demo (run_once + --wait)
│   ├── transfer_demo.py      # Transfer only
│   ├── video_demo.py         # Single NL Agent (compact narration)
│   └── workflow_demo.py      # Workflow create -> execute -> poll
├── docs/                     # Docs (Bounty + video guide)
│   ├── TUTORIAL.md           # From zero to first KeeperHub transaction
│   ├── ONBOARDING_TEARDOWN.md # 5 onboarding pain points + improvement suggestions
│   └── DEMO_SCRIPT.md        # Demo video recording guide
├── demo/                     # Demo videos (real terminal recording)
│   └── paykeeper_demo_final.mp4  # 38s final video
├── AUDIT_REPORT.md           # Security audit report
├── README.md                 # 中文
├── README_EN.md              # English (this file)
├── requirements.txt
├── .env.example
└── mcp_config.json
```

---

## Judging Criteria Mapping (official hackathon rubric)

> **Execution is weighted heavily, because that is the point.**

### 1. Does it execute onchain via KeeperHub?（通过）

- **18 real Sepolia transactions** (7 linked above with full `transactionHash`, `executionId`, `gasUsed`, `sponsored` fields)
- Not mockups: every transaction is a real KeeperHub broadcast, verifiable in the browser

### 2. Use of KeeperHub surfaces（通过）

- **MCP server** (35 tools, `agent/keeperhub_mcp.py`)
- **Direct execution** `execute_transfer` / `execute_contract_call`
- **x402 / MPP pay-per-use** (EIP-3009 signing + facilitator allowlist)
- **Workflow builder** (create / validate / execute / poll, 442 actions + 6 triggers)
- **Audit trail** (every execution returns audit nodes + console visualization)

### 3. Reliability and observability（通过）

- **Failure mode handling**: `simulate` pre-flight rejects `wouldRevert=true` txs
- **Retries**: exponential backoff (1.5s -> 3s -> 6s), **reusing the same idempotency key** (mock-tested — prevents double-pay when the first attempt was on-chain but the response timed out)
- **Gas handling**: `Gas Sponsorship` (`sponsored:true` verified on multiple txs) + gas estimation & receipts for non-sponsored
- **Audit trail usage**: every execution returns `audit_trail` (simulate / broadcast / confirm nodes)

### 4. Originality and real-world usefulness（通过）

PayKeeper solves a real need: **let anyone who can speak natural language trigger auditable on-chain payments.**

- **Subscription agent (true timer)**: `agent/subscription.py` cron scheduler auto-pays on schedule
- **Balance guardian**: *"If my ETH balance drops below 0.5, top it up to 1 ETH"* — conditional payment driven by Agent reasoning
- **Pay-per-use**: Agent signs EIP-3009 payments in x402 MPP scenarios
- **Batch settlement**: *"Send 0.1 ETH to both these addresses"* -> Agent invokes `execute_transfer` multiple times

Use cases: DAO treasury payroll, DeFi auto-subscription (VPN/SaaS delegation), AI-Agent micropayments, e-commerce auto-settlement.

### 5. Integration quality and developer experience（通过）

- **9 LLM providers**, switch with one env var (`agent/agent.py` registry design, model names user-configured)
- **End-to-end docs**: `docs/TUTORIAL.md` (zero -> first tx), `docs/DEMO_SCRIPT.md` (recording guide)
- **Demo script works out of the box**: `python examples/full_demo.py` runs in one command
- **Dependency pins**: `mcp<2.0` + `httpx<0.28` (avoids API compat issues, documented in `requirements.txt`)
- **Security audit visible**: `AUDIT_REPORT.md` lists 6 fixed bugs + 3 follow-ups
- **Zero external DB dependency**: pure Python + MCP, no DB / Redis required

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
| Transaction evidence | 7 Etherscan links above + full local log |

---

## Acknowledgments

- [KeeperHub](https://app.keeperhub.com) — MCP / x402 / audit / wallet infrastructure
- [DeepSeek](https://platform.deepseek.com) — default LLM, OpenAI-compatible API
- [LangChain / LangGraph](https://www.langchain.com) — ReAct Agent framework

---

## License

MIT © 2026 PayKeeper Contributors
