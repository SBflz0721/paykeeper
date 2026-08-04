# PayKeeper — 演示视频录制指南

> 目标：录一段 1.5~3 分钟视频，展示「用户说一句话 -> Agent 经 KeeperHub 在链上真实付款」。
> 提交要求：GitHub 链接 + 演示视频 + 交易链接。

## 一、准备工作（一次性）

1. 克隆仓库并安装依赖
 ```bash
 git clone https://github.com/SBflz0721/paykeeper.git
 cd paykeeper
 pip install -r requirements.txt
 cp .env.example .env
 ```

2. 填 `.env`（**建议先轮换 key 再用新值**）
 ```bash
 KEEPERHUB_API_KEY=kh_你的key
 LLM_PROVIDER=deepseek # 或 anthropic / openai
 DEEPSEEK_API_KEY=sk-你的key
 TARGET_CHAIN_ID=11155111 # Sepolia 测试网
 DEMO_RECIPIENT=0xc4Ef9855219C03843dd425b23C142d0F059aAfFd # 换成你控制的地址
 DEMO_AMOUNT=0.005
 ```

3. 确认 Sepolia 有测试 ETH（[faucet](https://sepoliafaucet.com/)），组织钱包地址可在 KeeperHub 控制台查到。

## 二、录屏脚本（推荐顺序）

用 OBS / QuickTime / Loom 录屏，建议 1920x1080，终端用深色主题。

### 第 1 幕：项目与架构（~30 秒）
- 打开仓库首页 https://github.com/SBflz0721/paykeeper ，滚动 README
- 口播要点：PayKeeper 让用户用自然语言描述付款意图，由 Agent 经 KeeperHub 执行层真实上链；覆盖 MCP、Turnkey 钱包、Gas Sponsorship、x402 按次付费

### 第 2 幕：自然语言 Agent 真实转账（~60 秒）核心
```bash
python examples/video_demo.py
```
预期输出：
```
KeeperHub MCP : 已连接，加载工具 35 个
> 请经 KeeperHub 向 0xc4Ef.. 转账 0.005 ETH，目标链 11155111（Sepolia）...
[Agent 推理报告：simulate 预飞 -> 广播 -> 链上确认]
>>> 链上交易: https://sepolia.etherscan.io/tx/0x...
```
- 口播：注意 Agent 先 simulate 预飞（wouldRevert: false），再带幂等键广播，最后拿交易哈希复核——可靠性三层防护
- 如果 Agent 输出显示 `sponsored: true`，强调 Gas Sponsorship

### 第 3 幕：链上验证（~30 秒）
- 浏览器打开输出的 etherscan 链接，展示交易已确认
- 也可打开 KeeperHub 控制台的执行记录/审计轨迹页面

### 第 4 幕（可选加分）：订阅工作流
```bash
WORKFLOW_TRIGGER=schedule WORKFLOW_CRON="0 0 1 * *" python examples/workflow_demo.py
```
展示创建「每月 1 号自动付款」的订阅工作流并执行。

## 三、视频规格建议

| 项 | 建议 |
|----|------|
| 时长 | 1.5~3 分钟（评委注意力有限） |
| 分辨率 | 1920x1080 或 1280x720 |
| 格式 | MP4（H.264） |
| 字幕 | 建议加中/英文字幕（配乐可省） |
| 口播 | 讲清「一句话 -> 真实上链」这条主线即可 |

## 四、提交材料清单

- [ ] 演示视频（MP4，上传 YouTube/Bilibili 或 Dorahacks 附件）
- [ ] GitHub 仓库：https://github.com/SBflz0721/paykeeper
- [ ] 交易链接：`examples/output/last_run.json` / `transactions_log.md`
- [ ] Bounty 材料：`docs/TUTORIAL.md` + `docs/ONBOARDING_TEARDOWN.md`（已入库）

> 仓库里附带了 `examples/output/paykeeper_demo.cast`（asciinema 录制的真实执行回放），
> 可在 https://asciinema.org 或本地 `asciinema play` 播放，也可作为视频素材。
