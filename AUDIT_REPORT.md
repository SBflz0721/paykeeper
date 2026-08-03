# PayKeeper 安全审计报告

- **审计对象**：PayKeeper（KeeperHub Agents Onchain Hackathon 参赛项目）
- **审计日期**：2026-08-03
- **审计范围**：`agent/`、`examples/`、`docs/`、`.env*`、`requirements.txt`、`mcp_config.json`
- **审计方式**：静态代码审查 + 真实链上执行验证（6 笔 Sepolia 交易）+ git 敏感信息核查

---

## 0. 结论

| 类别 | 结果 |
|------|------|
| 真实交易验证 | ✅ 6 笔 Sepolia 交易经 KeeperHub 执行成功 |
| 敏感信息泄露 | ⚠️ 1 项（`kh_` Key 暴露于对话；已确保不进 git），**建议轮换** |
| 已修复 bug/漏洞 | 4 项（1 高、2 中、1 低） |
| 待跟进事项 | 3 项（中/低/信息） |

---

## 1. 敏感内容审计

### [S-01] KeeperHub API Key 暴露于对话（高，已缓解，建议轮换）
- **位置**：`.env`（真实 `kh_` Key）
- **发现**：Key 在对话中明文出现，且写入 `.env`。已验证：Key **仅**存在于 `.env`；`.gitignore` 忽略 `.env`（`git add -A` 后 `git ls-files` 无 `.env`）；`mcp_config.json` 仅含 `${KEEPERHUB_API_KEY}` 占位符，代码与文档无硬编码 Key。
- **影响**：该 Key 拥有组织 Turnkey 钱包的执行权（可 `execute_transfer` / `execute_workflow` 动钱）。一旦被提交到公开仓库或被截获，资金可被转走。
- **处置**：已确保不进入 git。
- **建议**：**在 app.keeperhub.com 后台 Rotate 该 Key**（对话已暴露，视为已泄露）；本地改用新 Key 重写 `.env`；部署/CI 用 secret 注入，绝不落盘到仓库。

### [S-02] 其他敏感文件核查（通过）
- 工作区无 `~/.keeperhub/wallet.json`、无 `X402_PRIVATE_KEY`、无 `sk-ant-`/`sk-proj-` 真实值、无 PEM 私钥。
- `examples/output/` 未产生过包含敏感数据的文件。

---

## 2. 已修复的 Bug / 漏洞

### [B-01] execute_transfer 广播后假成功（高）
- **位置**：`agent/payments.py` `execute_transfer`
- **发现**：`if state in ("", "success", ...) or tx_hash: return ok=True` —— 当广播返回 pending/未知状态（`state=""`）且无 tx_hash 时，仍标记成功并返回空哈希。可靠性评审点（"does it understand failure modes?"）会因此失分，且上层可能把未确认交易当作已成功。
- **修复**：仅 `success/confirmed/completed` 或存在 tx_hash 才算成功；pending 状态转为重试；重试耗尽返回 `ok=False` + "交易未确认"。

### [B-02] 模拟预飞未检查 wouldRevert（中）
- **位置**：`agent/payments.py` `execute_transfer` simulate 分支
- **发现**：只查 `error`/`isError` 字段，未检查 `wouldRevert`/`success`。模拟结果 `{"wouldRevert": true}` 时会继续广播一笔必 revert 的交易，浪费 gas。
- **修复**：simulate 返回 `wouldRevert=true` 或 `success=false` 时中止并返回失败原因。

### [B-03] x402 结算可被钓鱼 facilitator 诱导签名（高）
- **位置**：`agent/x402_client.py` `settle`
- **发现**：facilitator 端点取自 challenge（`challenge["facilitator"]`）。若 Agent 调用的是被恶意/被劫持的付费工作流，攻击者可返回指向自己服务器的 facilitator，诱导 Agent 签署 EIP-3009 `TransferWithAuthorization`，进而转走 Base USDC。
- **修复**：新增 `_facilitator_allowed()` —— 强制 https + host 白名单（默认 `keeperhub.com`，可用 `X402_FACILITATOR_ALLOWLIST` 追加）；对前缀欺骗（`evil-keeperhub.com`）做了后缀匹配防护。单测 5/5 通过。

### [B-04] x402 金额换算死代码 + 单位错误风险（低）
- **位置**：`agent/x402_client.py` `settle`
- **发现**：存在先乘 `10**decimals` 又被覆盖的死代码；若 `maxAmountRequired` 本就是最小精度，错误换算会导致多付/少付。
- **修复**：删除死代码，直接采用 `maxAmountRequired`（最小精度），并校验 `amount>0`、`payTo` 非空。

---

## 3. 待跟进（未修改，已在计划中）

### [F-01] 工作流重复创建堆积（中）
- **位置**：`examples/workflow_demo.py`
- **发现**：每次运行 `create_workflow` 都会在组织新增一个工作流（已产生 2 个 "PayKeeper - Subscription Payment"）。长期运行会堆积、干扰 `list_workflows`。
- **建议**：固定工作流 name + 先查重/复用；或增加 `--cleanup` 调用 `delete_workflow`。

### [F-02] 缺 LLM key 时入口报错时机偏晚（低）
- **位置**：`examples/run_demo.py`
- **建议**：入口预检 `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`，缺失时给出明确提示（当前是走到 agent 构建才报 RuntimeError，虽然信息清晰但时机偏晚）。

### [F-03] 信任模型说明（信息）
- `kh_` Key = 组织钱包执行权，是**最大单一风险点**。建议在 README 显著标注：Key 视为高敏资产、最小权限、定期轮换、`X402_PRIVATE_KEY` 同样处理。

---

## 4. 验证记录

| 项 | 结果 |
|----|------|
| `py_compile` 全部模块 | ✅ 通过 |
| `_facilitator_allowed` 单测（5 用例） | ✅ 通过 |
| 修复后 `transfer_demo.py` 实跑 | ✅ `ok=true, tx_hash=0x8bc5…, status=completed` |
| git 暂存核查 | ✅ `.env` 被忽略，16 个文件无敏感内容 |

## 5. 遗留风险

- 测试网已累积 6 笔真实交易；主网执行（Gas Sponsorship）尚未做，需用户在主网钱包准备 USDC 后验证。
- 自然语言 Agent（需 LLM key）与 x402 付费工作流实跑尚未验证（代码已就绪，等待用户提供 LLM key 与付费工作流）。
