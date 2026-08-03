# 从零到第一次 KeeperHub 执行的 Agent（15 分钟）

本教程带一个**完全没用过 KeeperHub** 的开发者，从空白环境到跑通一个"经 KeeperHub 在链上真实执行转账"的 AI Agent。无需写智能合约、无需管 nonce/gas/私钥基础设施——这些 KeeperHub 都包了。

> 目标产出：一条真实链上交易哈希 + 浏览器链接。

---

## 第 0 步：前置条件

- Python 3.11+
- 一个 KeeperHub 账号（免费）：https://app.keeperhub.com
- 一个 LLM key（Anthropic 或 OpenAI 任选）
- 约 10 分钟

---

## 第 1 步：建账号 + 拿 API Key

1. 打开 https://app.keeperhub.com 注册，**Turnkey 钱包会自动创建**（私钥在硬件安全区，不出硬件边界——你不用管私钥）。
2. 进入 **Settings → API Keys → Organisation**，创建一个 Key（形如 `kh_xxx`）。
3. 记下这个 Key。

> 提示：开发阶段先在 **Sepolia 测试网** 玩，零成本。需要测试币去 https://sepoliafaucet.com 领。

---

## 第 2 步：拉代码 + 装依赖

```bash
git clone <this-repo> paykeeper && cd paykeeper
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

---

## 第 3 步：配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`：

```ini
KEEPERHUB_API_KEY=kh_你的key
ANTHROPIC_API_KEY=sk-ant-你的key        # 或 OPENAI_API_KEY + LLM_PROVIDER=openai
TARGET_CHAIN_ID=11155111                # Sepolia 测试网
DEMO_RECIPIENT=0x你控制的地址            # 收款方（演示用，换成你自己的地址即可）
DEMO_AMOUNT=0.01                        # 金额（原生币或 token 的小数）
DEMO_TOKEN_ADDRESS=                     # 留空=转原生币；填 ERC-20 地址则转该 token
```

---

## 第 4 步：跑通第一次真实交易 🚀

```bash
python examples/run_demo.py
```

你会看到：

```
已连接 KeeperHub MCP，加载工具 N 个：['execute_transfer', 'execute_workflow', ...]
=== 确定性转账（经 KeeperHub 真实执行）===
链 11155111 -> 0x... | 0.01 原生币
{ ... "tx_hash": "0x...", "status": "confirmed", "audit_trail": [...] }
交易浏览器: https://sepolia.etherscan.io/tx/0x...
```

🎉 **这就是一条经 KeeperHub 真实执行的链上交易。** 把它贴到黑客松提交页即可。

---

## 第 5 步：用自然语言驱动 Agent

```bash
python examples/run_demo.py --instruction "查一下我组织钱包在 Sepolia 的 ETH 余额并汇报"
```

Agent（LangChain + KeeperHub 工具）会自己决定调用 `execute_transfer` / 查询类工具，并给出口语化报告。

---

## 常见卡点速查

| 现象 | 原因 / 解决 |
|------|------|
| `缺少 KeeperHub API Key` | `.env` 没填 `KEEPERHUB_API_KEY`，或没 `source .venv` |
| 工具列表为空 / 401 | Key 无效或组织作用域不对；重新生成 Key |
| 转账报错 `insufficient funds` | 钱包没充测试币；去 Sepolia faucet 领 |
| 想上主网但 gas 贵 | 主网可用 **Gas Sponsorship**，见 `.env` 与 KeeperHub 文档 |

---

## 下一步

- 把"单次转账"改成"循环订阅"：用 KeeperHub 的 **Schedule 触发器** 建一个工作流（或外部 cron 调 `run_subscription_once`）。
- 接 **x402/MPP 按次付费**：见 `agent/x402_client.py` 与 `docs/ONBOARDING_TEARDOWN.md`。

恭喜，你从零跑通了第一个 KeeperHub 执行的 Agent。
