#!/usr/bin/env python3
"""生成 PayKeeper 终端演示动画 HTML（播放器式，自动逐行打印真实执行输出）。"""
import html
import json

OUT = "/workspace/demo/paykeeper_demo.html"

# 真实执行输出（第 9 笔链上交易，video_demo.py + DeepSeek + KeeperHub）
RAW_LINES = [
    ("$ python examples/video_demo.py", "cmd"),
    ("", "normal"),
    ("==============================================================", "banner"),
    ("  PayKeeper · 自主支付 Agent · 经 KeeperHub 链上执行（链 11155111）", "banner2"),
    ("==============================================================", "banner"),
    ("  LLM provider : deepseek / deepseek-chat", "dim"),
    ("  KeeperHub MCP : 已连接，加载工具 35 个", "dim"),
    ("", "normal"),
    ("==============================================================", "banner"),
    ("  用户自然语言指令", "banner2"),
    ("==============================================================", "banner"),
    ("  > 请经 KeeperHub 向 0xc4Ef9855219C03843dd425b23C142d0F059aAfFd 转账 0.005 ETH，", "instr"),
    ("    目标链 11155111（Sepolia）。先 simulate 预飞，再广播，最后汇报交易哈希和浏览器链接。", "instr"),
    ("", "normal"),
    ("==============================================================", "banner"),
    ("  Agent 推理与执行中（DeepSeek + KeeperHub MCP）...", "thinking"),
    ("==============================================================", "banner"),
    ("✅ 转账已完成并上链确认。", "ok"),
    ("", "normal"),
    ("## 转账执行报告", "h1"),
    ("", "normal"),
    ("  链          : Sepolia (Chain ID 11155111)", "normal"),
    ("  收款方      : 0xc4Ef9855219C03843dd425b23C142d0F059aAfFd", "normal"),
    ("  金额        : 0.005 ETH（5000000000000000 wei）", "normal"),
    ("  执行 ID     : 6lagptosr08ei7e6mtipo", "normal"),
    ("  交易哈希    : 0xf98cd5a476fd61e12af321a72b876f607d7ce8035f5298cd735e2b4d7c666582", "hash"),
    ("  状态        : completed / success: true", "ok"),
    ("  Gas 用量    : 47,693 units", "normal"),
    ("  有效 Gas 价格: 1.254386140 Gwei", "normal"),
    ("  Gas 赞助    : 是（sponsored，无需你支付 gas）", "sponsored"),
    ("", "normal"),
    ("  浏览器链接  : https://sepolia.etherscan.io/tx/0xf98cd5a476fd61e12af321a72b876f607d7ce8035f5298cd735e2b4d7c666582", "link"),
    ("", "normal"),
    ("## 关键审计轨迹", "h1"),
    ("  1. 预飞（simulate）：simulate=true 成功，wouldRevert: false，gas 估算 21,227 units", "normal"),
    ("     —— 确认交易不会回滚。", "dim"),
    ("  2. 广播（broadcast）：携带幂等键 paykeeper-sepolia-eth-0.005-0xc4Ef9855 提交。", "normal"),
    ("  3. 链上确认：get_direct_execution_status 复核，交易哈希与链上回执一致，success: true。", "normal"),
    ("", "normal"),
    ("  交易已真实上链，无伪造哈希。", "ok"),
    ("", "normal"),
    ("$ ", "cmd"),
]

# 每行播放延时（毫秒），关键行放慢
def delay_for(kind: str) -> int:
    return {
        "banner": 220, "banner2": 500, "cmd": 400, "dim": 200,
        "instr": 420, "thinking": 900, "h1": 500, "ok": 350,
        "hash": 1300, "sponsored": 1300, "link": 1500, "normal": 180,
    }.get(kind, 200)

def cls(kind: str) -> str:
    return {
        "cmd": "c-cmd", "banner": "c-banner", "banner2": "c-banner2", "dim": "c-dim",
        "instr": "c-instr", "thinking": "c-thinking", "h1": "c-h1", "ok": "c-ok",
        "hash": "c-hash", "sponsored": "c-sponsored", "link": "c-link", "normal": "",
    }.get(kind, "")

lines_js = []
for i, (text, kind) in enumerate(RAW_LINES):
    lines_js.append({
        "t": html.escape(text),
        "c": cls(kind),
        "d": delay_for(kind),
        "id": i,
    })

HTML_DOC = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PayKeeper · 终端演示动画</title>
<style>
  :root { --bg:#0d1117; --fg:#e6edf3; --dim:#8b949e; --green:#3fb950; --blue:#58a6ff;
          --purple:#bc8cff; --yellow:#d29922; --red:#f85149; --cyan:#39c5cf; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#010409; min-height:100vh; display:flex; flex-direction:column;
         align-items:center; justify-content:center; padding:24px; font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif; }
  .card { width:min(960px, 100%); background:var(--bg); border:1px solid #30363d; border-radius:10px;
          box-shadow:0 16px 48px rgba(0,0,0,.55); overflow:hidden; }
  .titlebar { display:flex; align-items:center; gap:8px; padding:12px 16px; background:#161b22;
              border-bottom:1px solid #30363d; }
  .dot { width:12px; height:12px; border-radius:50%; }
  .d1{background:#ff5f57}.d2{background:#febc2e}.d3{background:#28c840}
  .title { flex:1; text-align:center; color:var(--dim); font-size:13px; }
  .btn { background:var(--blue); color:#010409; border:none; border-radius:6px; padding:5px 14px;
         font-size:13px; font-weight:700; cursor:pointer; }
  .btn:hover { filter:brightness(1.15); }
  .screen { padding:20px 22px; min-height:520px; font-family:'SF Mono','JetBrains Mono','Cascadia Code',Consolas,monospace;
            font-size:14.5px; line-height:1.65; color:var(--fg); white-space:pre-wrap; word-break:break-all; }
  .bar { display:flex; justify-content:space-between; align-items:center; padding:8px 16px;
         background:#161b22; border-top:1px solid #30363d; color:var(--dim); font-size:12px; }
  .c-cmd{color:var(--fg)} .c-banner{color:var(--dim)} .c-banner2{color:var(--blue);font-weight:700}
  .c-dim{color:var(--dim)} .c-instr{color:var(--yellow)} .c-thinking{color:var(--cyan)}
  .c-h1{color:var(--purple);font-weight:700} .c-ok{color:var(--green);font-weight:600}
  .c-hash{color:var(--green);font-weight:700} .c-sponsored{color:var(--yellow);font-weight:700}
  .c-link{color:var(--blue);text-decoration:underline;cursor:pointer}
  .cursor{display:inline-block;width:9px;height:17px;background:var(--fg);vertical-align:text-bottom;
          animation:blink 1s steps(1) infinite}
  @keyframes blink{50%{opacity:0}}
  .status { color:var(--dim); }
  .status .ok-tag { color:var(--green); font-weight:700; }
</style>
</head>
<body>
<div class="card">
  <div class="titlebar">
    <span class="dot d1"></span><span class="dot d2"></span><span class="dot d3"></span>
    <span class="title">PayKeeper — 自主支付 Agent 经 KeeperHub 链上执行 · Sepolia</span>
    <button class="btn" id="playBtn" onclick="restart()">▶ 重新播放</button>
  </div>
  <div class="screen" id="screen"></div>
  <div class="bar">
    <span class="status" id="status">● 准备播放</span>
    <span>LLM: DeepSeek · KeeperHub MCP: 35 tools · 第 9 笔链上交易</span>
  </div>
</div>
<script>
const LINES = __LINES__;
const screen = document.getElementById('screen');
const status = document.getElementById('status');
let timer = null, idx = 0;

function typeNext() {
  if (idx >= LINES.length) {
    status.innerHTML = '● <span class="ok-tag">执行完成</span> · 交易已真实上链';
    const c = document.createElement('span'); c.className='cursor'; screen.appendChild(c);
    return;
  }
  const line = LINES[idx];
  const div = document.createElement('div');
  div.textContent = line.t;
  div.className = line.c || '';
  if (line.c === 'c-link') { div.style.cursor='pointer'; }
  screen.appendChild(div);
  screen.scrollTop = screen.scrollHeight;
  idx++;
  status.innerHTML = '● 播放中 ' + idx + ' / ' + LINES.length;
  timer = setTimeout(typeNext, line.d);
}

function restart() {
  clearTimeout(timer);
  screen.innerHTML = '';
  idx = 0;
  typeNext();
}

typeNext();
</script>
</body>
</html>
"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(HTML_DOC.replace("__LINES__", json.dumps(lines_js, ensure_ascii=False)))

print(f"已生成: {OUT}")
