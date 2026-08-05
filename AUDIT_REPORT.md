# PayKeeper 安全审计报告

- **审计对象**：PayKeeper（KeeperHub Agents Onchain Hackathon 参赛项目）
- **审计日期**：2026-08-03（修订 2026-08-04）
- **审计范围**：`agent/`、`examples/`、`docs/`、`.env*`、`requirements.txt`、`mcp_config.json`
- **审计方式**：静态代码审查 + 真实链上执行验证（8 笔仓库内可核验 Sepolia 交易）+ git 敏感信息核查

---

## 0. 结论

| 类别 | 结果 |
|------|------|
| 真实交易验证 | 通过：8 笔仓库内可验证 Sepolia 交易（全部附 Etherscan 链接，见 README）；开发期另有执行记录仅存本地日志 |
| 敏感信息泄露 | 注意：1 项（`kh_` Key 暴露于对话；已确保不进 git），**建议立即轮换**（README 已加信任模型说明） |
| 已修复 bug/漏洞 | **26 项**（B-01~B-07、F-01/F-04、S-03~S-14、R-02/R-03/R-05~R-08，见第 7、8、9 节） |
| 测试入库 | **46 用例**（`tests/`，`pytest tests/ -q` 全通过，离线可复现） |
| 待跟进事项 | 4 项（需外部条件：x402 真实结算、主网 + 赞助 gas 交易、`kh_` Key 轮换；R-10 为评审误判） |

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

### [B-05] 重试重新生成幂等键 = 双付风险（高，资金安全）——外部评审发现
- **位置**：`agent/payments.py` `execute_transfer`
- **发现**：幂等键在**每次重试**都重新生成（原代码 `for attempt: args = {**base_args, "idempotency_key": uuid.uuid4().hex}`）。若第一笔已上链但响应超时，重试携带**新** key，KeeperHub 视为全新请求 -> 再次转账 = **双付**。评审结论："每次重试都重新生成幂等键，等于换张新单"。
- **修复**：幂等键在整个执行逻辑（含所有重试）只生成一次，重试复用同一 key；KeeperHub 按 key 去重。
- **验证**：mock「第一次广播超时、第二次成功」，断言两次广播 `idempotency_key` 相同（通过）。

### [B-06] 订阅没有真定时器 = 一次性转账（中）——外部评审发现
- **位置**：`agent/payments.py` `run_subscription_once`、`examples/workflow_demo.py`
- **发现**：原 `run_subscription_once` 只是立即执行一次转账（注释自己写明"循环调度见 README/工作流方案"）；`workflow_demo.py` 的 Schedule 触发器只配置了 cron 但**手动执行**，未证明到点自动触发。
- **修复**：新增 `agent/subscription.py` —— 真正的本地 cron 调度器（`SubscriptionManager` + 最小 cron 解析器），到点自动调用 `execute_transfer`（复用可靠性层）。新增 `examples/subscription_demo.py`（run_once 立即执行 + `--wait` 等待定时触发）。
- **验证**：cron 解析 9/9 用例通过（含周字段、闰年、`*/15`、周 0/7）；`subscription_demo.py` 实跑产生真实交易 `0x424af7e9…`（通过）。

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
| `py_compile` 全部模块 | 通过 |
| `_facilitator_allowed` 单测（5 用例） | 通过 |
| cron 解析单测（9 用例） | 通过 |
| 幂等键重试复用单测（mock 首播超时->重试） | 通过：两次广播同 key |
| 修复后 `transfer_demo.py` 实跑 | 通过：`ok=true, tx_hash=0x8bc5…, status=completed` |
| `subscription_demo.py` 实跑 | 通过：真实交易 `0x424af7e9…, status=completed` |
| git 暂存核查 | 通过：`.env` 被忽略，24 个文件无敏感内容 |

## 5. 遗留风险

- 测试网开发期累计执行多次，仓库内可核验 8 笔（README 全部附 Etherscan 链接）；主网执行（Gas Sponsorship）尚未做，需用户在主网钱包准备 USDC 后验证。
- 自然语言 Agent（需 LLM key）与 x402 付费工作流实跑尚未验证（代码已就绪，等待用户提供 LLM key 与付费工作流）。

---

## 6. 第二轮审计（2026-08-04，含安全扫描 + Web 功能）

### 6.1 安全扫描（腾讯云鼎方法论）

| 检查项 | 结果 |
|--------|------|
| 命令执行投毒 | 通过：除 `ffmpeg`/`ffprobe` 等本机标准工具外，代码无动态命令组装；未发现投毒风险 |
| 网络请求目标 | 通过：全部为白名单域名（keeperhub.com / deepseek.com / groq / moonshot / bigmodel / etherscan / github / dorahacks）+ 占位符 |
| 硬编码密钥 | 通过：代码/文档无真实密钥（`grep sk-/kh_/ghp_/AKIA` 全项目 0 命中） |
| Base64 载荷 | 通过：仅 `x402_client.py` 的 USDC 合约地址，无编码载荷 |
| 依赖供应链 | 通过：`mcp<2.0` + `httpx<0.28` 已锁上界；其余设下限，可接受 |
| 前端 Provider 配置 | 说明：`data/provider.json` 明文存 API Key（运行时配置，`data/` 已 gitignore，本地运行可接受；部署建议改 secret 存储） |

### 6.2 发现并修复的 Bug

- **[B-07] emoji 清理破坏 Python 缩进（已修复）**：批量清理脚本用 `re.sub(r" {2,}", " ", txt)` 折叠了 `full_demo.py` / `gen_demo_html.py` 的缩进，导致 `IndentationError`。已 `git checkout` 恢复后用「只删 emoji 不折叠空格」的方式重新清理，`py_compile` 全部通过。
- **[F-04] Dashboard 全局异常处理（已加固）**：新增 `@app.exception_handler(Exception)`，未预期异常返回结构化 JSON 而非裸 500；无效请求返回 422。

### 6.3 500 internal server error 排查结论

用户报告的 `500 internal server error (382ca144e56644608f7eb3a313b37d07)` 出现在会话 JSONL 的 `providerData.error`，是**模型服务端（Deepseek-V4-Flash）临时 500**，非项目代码 bug（uvicorn 日志无 500）。当前已恢复；项目侧已通过全局异常处理保证任何内部错误都以结构化 JSON 返回，杜绝裸 500。

### 6.4 Web Dashboard 功能审计

| 端点 | 结果 |
|------|------|
| `GET /health` | 通过：`{"status":"ok","tools":35}` |
| `GET /` | 通过：首页含 6 个 Tab（执行/规则/记录/钱包/Provider/KeeperHub） |
| `GET/POST /api/provider` | 通过：前端可视化配置 provider，运行时生效，key 脱敏显示 |
| `POST /api/rules` | 通过：创建规则（白名单/单笔/每日限额） |
| `POST /api/execute` | 通过：风控拦截（白名单/限额）返回 `rejected` 并记录；合法请求真实上链（可核验交易 `0x65203c…`，审计 policy->simulate->broadcast） |
| `GET /api/executions` | 通过：全审计记录（含 rejected 原因） |
| `GET /api/wallet` | 通过：返回 KeeperHub 托管钱包（需 `.env` 配 `WALLET_INTEGRATION_ID`） |

---

## 7. 第三轮审计（2026-08-04，安全加固专项）

外部安全评审发现 3 高危 + 5 中危，均已修复并测试：

### 高危

- **[S-03] Dashboard 完全无鉴权（已修复）**：README 原先教绑 `0.0.0.0`，同网段任何人可建规则 / 转账。
  修复：新增 `DASHBOARD_TOKEN` 鉴权——设置后所有 `/api/*`（除 `/health`）要求 `Authorization: Bearer <token>`；README 改为只绑 `127.0.0.1`。
  验证：无 token 访问 `/api/rules` 返回 401，带 token 返回 200。

- **[S-04] chain_id 由请求方任意传（已修复）**：请求方可直接指到主网。
  修复：`PAYKEEPER_ALLOWED_CHAIN_IDS` 白名单（默认仅 Sepolia 11155111 / Base Sepolia 84532），
  `payments.execute_transfer` 与 `web /api/execute` 双重校验，不在名单直接拒绝。
  验证：`chain_id=1`（主网）返回 422。

- **[S-05] Agent 自然语言路径完全绕过风控（已修复）**：35 个工具全绑 LLM，提示词注入可任意转账/调合约。
  修复：`build_agent`/`run_instruction` 强制要求 `policy_engine` + `policy_rule_id`（缺失即抛错），
  并将 `execute_transfer` / `execute_contract_call` / `execute_check_and_execute` 包装为「先风控后执行」：
  链白名单 -> 地址格式 -> 金额解析（fail-closed）-> 风控校验（白名单/单笔/每日限额），不通过直接返回拒绝，绝不触达链上。
  验证：包装器对非白名单地址 / 主网链 / 超限金额 / 非法金额 / 缺 chain_id 全部拒绝（5/5）。

- **[S-06] `/api/provider` 可把 LLM key 转发到攻击者服务器（已修复）**：custom base_url 可指向任意域名。
  修复：自定义 base_url 必须命中 `OPENAI_COMPATIBLE_BASE_URL_ALLOWLIST`，未配置则禁止 custom provider。
  验证：`https://evil.example.com/v1` 返回 422。

### 中危

- **[S-07] 前端保存的 KeeperHub key 是死代码（已修复）**：MCP 连接在启动时建立，前端保存的 key 不会重新连接。
  修复：移除前端 KeeperHub API Key 输入与保存（后端 `_apply_keeperhub_config` 不再写 `KEEPERHUB_API_KEY`）；
  API Key 明确只在 `.env` 配置；前端只保留「请求时读取」的 Wallet Integration ID 配置，并注明原因。

- **[S-08] 风控金额解析失败置 0 放行（已修复）**：`execute_transfer` 解析异常时 `amount_wei=0` 可绕过限额。
  修复：`_amount_to_wei` 解析失败返回错误，调用方 fail-closed 直接拒绝，绝不置 0；
  原生币用 Decimal 换算避免 float 精度误差；负值/NaN/非法输入全部拒绝。
  验证：`"abc"` / `"-1"` 均被拒绝。

- **[S-09] 白名单非法地址被静默删除 -> 受限变不限（已修复）**：`add_rule` 过滤非法地址会让规则悄悄变「不限」。
  修复：`add_rule` 遇任一非法白名单地址直接 `ValueError`，`/api/rules` 转 422，绝不静默降级。
  验证：`"not-an-address"` 返回 422。

- **[S-10] 订阅重启重复付同一期（已修复）**：调度器无持久状态、无周期幂等。
  修复：`SubscriptionManager` 持久化 `last_run` 到 `data/subscriptions.json`，
  重启后以「上次运行」为锚点计算下次触发（不会重付已付周期）；
  每个周期派生确定性幂等键 `paykeeper-sub:{id}:{周期}`，跨实例/并发也由 KeeperHub 去重。
  验证：cron 锚定 last_run 后 next 跳到下一周期；同周期幂等键稳定。

- **[S-11] x402 金额完全信任 challenge（已修复）**：`settle` 直接采用 `maxAmountRequired`，恶意工作流可诱导大额签名。
  修复：新增 `X402_MAX_AMOUNT_WEI`（默认 100 USDC）上限 + `X402_ASSET_ALLOWLIST` 资产白名单，
  超限/非白名单资产一律拒绝。
  验证：`maxAmountRequired=999999999999` 返回「超过单笔上限」。

---

## 8. 第四轮审计（2026-08-04，订阅风控 + 鉴权默认值 + 交易可验证性）

外部评审复检发现 3 项，均已修复并测试：

### 严重

- **[S-12] 订阅自动转账未挂风控 = fail-open（已修复）**：`subscription.py` 的 `SubscriptionConfig.policy_engine` 默认为 None，此时到点自动转账**直接执行、白名单限额全跳过**，配置写错就真金白银飞出去。
  修复（双层 fail-closed）：
  - `SubscriptionManager.add()` 强制校验——订阅必须带 `policy_engine` + `policy_rule_id`，且对应规则存在并启用，否则拒绝注册（`ValueError`）；
  - `run_once()` 兜底——即使绕过 add，也拒绝执行未接风控的订阅。
  验证：无 policy 的 `add()` 抛错；无 policy 的 `run_once()` 抛错。

- **[S-13] Dashboard 鉴权默认关闭 = 公网裸奔（已修复）**：上一轮鉴权仅在显式设置 `DASHBOARD_TOKEN` 时启用，不设置等于没锁；且规则可配 `0=不限制` 全开放。
  修复：
  - 鉴权**永远开启**：未设置 `DASHBOARD_TOKEN` 时自动生成随机 token（持久化到 `data/.dashboard_token`，启动日志打印），中间件对所有 `/api/*` 强制 Bearer 校验；
  - 创建规则必须设置至少一项限制（非空白名单 / 单笔限额 / 每日限额），`0=不限制` 的全开放规则直接 422。
  验证：无 token 访问 `/api/rules` 返回 401（自动 token 同样生效）；全开放规则创建返回 422。

### 中等

- **[S-14] README 交易数不可验证（已修复）**：README 声称 18 笔但仓库内只有 7 笔有 Etherscan 链接，评审要求每条都能甩出链接。
  修复：核验仓库 + `policy.db` 执行记录，共有 **8 笔可验证交易**（7 笔来自文档 + 第 8 笔 `0x65203cb5…` 来自 Dashboard 真实执行记录），README 已全部改为「8 笔，每笔附链接」，并注明其余仅存于本地日志、不列入不可核验的计数。

---

## 9. 第五轮审计（2026-08-05，外部黑客松评估报告应对）

外部评审（《PayKeeper 黑客松评估报告》）通读全部核心源码 + 逐笔核验链上交易后提出 10 项问题，逐项处置如下：

### 高（评审能力面缺失）

- **[R-01] x402 无真实结算交易（部分修复，剩余需实跑）**：`x402_client.py` 完整但从未在真实 facilitator 上跑通。
  修复：新增 `examples/x402_dryrun.py`（离线检查清单：challenge 解析 / 资产白名单 / 金额上限 / facilitator 白名单 / EIP-3009 签名，全链路可验）+ README 实跑指引（Base Sepolia 充少量 USDC → `--real` 结算 → 哈希入表）。真实结算需环境变量 `X402_PRIVATE_KEY`，属用户操作项。

### 中（严谨性 / 可复现性）

- **[R-02] README 与文档自相矛盾：Sepolia 交易标注 Gas Sponsorship（已修复）**：README 交易表 #3/#4/#6 标 `sponsored`，而 `ONBOARDING_TEARDOWN.md` 称"仅主网"。
  修复：核实 `examples/output/transactions_log.md` 原始记录——`sponsored: true` 是 **2026-08-03 执行时 KeeperHub 返回的真实字段**（非推断）。README 加注释注明字段来源与口径（官方文档面向主网，测试网以执行时返回为准）；`ONBOARDING_TEARDOWN.md` 卡点 3 同步加实测注记，消除矛盾。

- **[R-03] 测试代码未入库（已修复）**：AUDIT_REPORT 声称 8/8 单测、5/5 集成、cron 9/9、幂等 mock、facilitator 5/5，但仓库 `tests/` 为空。
  修复：新增 `tests/` 共 **46 用例全部入库并通过**（`python -m pytest tests/ -q`）——policy 10、payments 5、subscription 14（含 cron 9 + 幂等/fail-closed）、x402 9、Agent 包装器 8。全部离线运行（`:memory:` SQLite + fake tool），评审无需 kh key 即可复现。README 加 pytest 说明。

- **[R-04] 主网交易缺失（行动指引）**：8 笔全在 Sepolia，官方 Gas Sponsorship 是主网专属卖点。
  处置：默认链白名单仅含测试网是**有意的安全设计**（防误触主网）。README 安全说明新增"主网 + 赞助 gas 证据链"操作指引（追加 chain id → 充值 → 正常执行）。实跑属用户操作项。

### 低 / 安全提醒 / 信息

- **[R-05] 风控记账不覆盖合约调用（已修复）**：`execute_contract_call` 无金额可记账 → 每日限额可被绕过。
  修复：包装器金额来源扩展为 `amount` / `amount_hint` / `value`；合约调用不传金额被 fail-closed 拦截（提示显式传 `amount_hint`），所有资金工具成功执行统一记账，不存在绕过路径。
- **[R-06] Web 层 float→wei（已修复）**：`create_rule`/`execute` 的 `float * 10**18` 改为 Decimal 转换（与 policy 内部一致），非法金额 422。
- **[R-07] CORS 全开放（已修复）**：`allow_origins` 从 `*` 收紧为 `http://localhost:8000` / `http://127.0.0.1:8000`（Dashboard 本机使用，同源请求不受影响）。
- **[R-08] 工作流重复堆积（已修复，对应 F-01）**：`workflow_demo.py` 每次运行创建新 workflow。修复：固定 name 查重复用 + `WORKFLOW_CLEANUP=1` 清理同名工作流。
- **[R-09] `kh_` Key 曾在对话中暴露（行动项）**：AUDIT S-01 已标注。README 安全说明新增信任模型："Key 视为高敏资产，禁止提交/前端保存，建议立即在 app.keeperhub.com 轮换并定期轮换"。
- **[R-10] git log 仅 1 条提交（误判，无需处理）**：本仓库完整历史 14 条渐进提交（评审侧 shallow clone 所致）。

### 测试统计（入库后）

```
$ python -m pytest tests/ -q
46 passed in ~10s        # policy 10 / payments 5 / subscription 14 / x402 9 / agent wrapper 8
```
