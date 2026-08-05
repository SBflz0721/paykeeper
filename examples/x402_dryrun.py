"""
x402 / MPP 按次付费 —— dry-run 检查清单（本地离线，不真实结算）。

黑客松评审指出「x402 仅有代码、无真实结算交易」是最大短板（P0-1）。
本脚本把 x402 链路的每一步拆成可验证的检查项：
  1) challenge 解析（容错提取 402 body）
  2) asset 资产白名单
  3) 金额上限（X402_MAX_AMOUNT_WEI，默认 100 USDC）
  4) facilitator 端点白名单（https + 域后缀防欺骗）
  5) EIP-3009 签名生成（需要 X402_PRIVATE_KEY；未设置则 SKIP）
  6) 真实结算（--real 才会执行，需要完整环境）

用法：
  python examples/x402_dryrun.py            # 全离线检查清单
  python examples/x402_dryrun.py --real     # 真实结算（配好 .env 后）

真实实跑步骤见 README「x402 按次付费」一节（Base Sepolia 几十美分即可）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from agent import x402_client as x
from agent.x402_client import USDC_BASE_SEPOLIA, _asset_allowed, _facilitator_allowed, extract_challenge, settle

SAMPLE_CHALLENGE = {
    "version": 1,
    "scheme": "exact",
    "network": "base-sepolia",
    "maxAmountRequired": "5000",  # 0.005 USDC（6 位小数精度）
    "asset": USDC_BASE_SEPOLIA,
    "payTo": "0x1234567890123456789012345678901234567890",
    "resource": "https://app.keeperhub.com/pay/xxx",
    "facilitator": "https://app.keeperhub.com/settlement",
}

OK, SKIP, FAIL = "OK", "SKIP", "FAIL"


def check(label: str, fn, expect_ok: bool = True) -> None:
    try:
        r = fn()
    except Exception as e:
        print(f"[{FAIL}] {label}: 异常 -> {e}")
        return
    if expect_ok == bool(r):
        print(f"[{OK}] {label}")
    else:
        print(f"[{FAIL}] {label}: 期望 expect_ok={expect_ok}，实际 {r!r}")


def main() -> None:
    real = "--real" in sys.argv
    print("=" * 64)
    print("  x402 / MPP 按次付费 dry-run 检查清单")
    print("  （离线检查白名单/签名链路；--real 才真实结算）")
    print("=" * 64)

    # 1) challenge 解析
    print("\n[1/6] challenge 解析（402 body -> 结构化）")
    parsed = extract_challenge(SAMPLE_CHALLENGE)
    if parsed:
        print(f"      OK: network={parsed.get('network')} asset={parsed.get('asset')} "
              f"amount={parsed.get('maxAmountRequired')} payTo={parsed.get('payTo')[:10]}...")
    else:
        print(f"      [FAIL] 样例 challenge 解析失败")
    # 容错：字符串形式的 402 响应也能解析
    raw_402 = '{"accepts":[{"scheme":"exact","network":"base-sepolia","maxAmountRequired":"5000",' \
              '"asset":"' + USDC_BASE_SEPOLIA + '","payTo":"0x1234567890123456789012345678901234567890"}],' \
              '"x402Version":1,"resource":"https://app.keeperhub.com/pay/xxx"}'
    check("容错解析字符串型 402", lambda: extract_challenge(raw_402) is not None)

    # 2) asset 白名单
    print("\n[2/6] 资产白名单（X402_ASSET_ALLOWLIST）")
    check(f"Base Sepolia USDC 允许: {USDC_BASE_SEPOLIA[:10]}...", lambda: _asset_allowed(USDC_BASE_SEPOLIA))
    check("主网 USDC 允许", lambda: _asset_allowed(x.USDC_BASE))
    check("未知资产拒绝", lambda: not _asset_allowed("0x" + "de" * 20))

    # 3) 金额上限
    print("\n[3/6] 金额上限（X402_MAX_AMOUNT_WEI，默认 100 USDC）")
    cap = x._max_amount_wei()
    print(f"      当前上限: {cap}（最小精度）")
    check("样例金额 5000 <= 上限", lambda: 5000 <= cap)
    check("超上限 challenge 拒绝", lambda: not settle({
        "asset": USDC_BASE_SEPOLIA, "network": "base-sepolia",
        "maxAmountRequired": str(cap + 1), "payTo": "0x1234567890123456789012345678901234567890",
    }).get("ok"))

    # 4) facilitator 白名单
    print("\n[4/6] facilitator 端点白名单（https + 域后缀防欺骗）")
    check("https://app.keeperhub.com/settlement 允许",
          lambda: _facilitator_allowed("https://app.keeperhub.com/settlement"))
    check("http 明文拒绝", lambda: not _facilitator_allowed("http://app.keeperhub.com/settlement"))
    check("evil-keeperhub.com 拒绝", lambda: not _facilitator_allowed("https://evil-keeperhub.com/x"))

    # 5) 签名生成
    print("\n[5/6] EIP-3009 TransferWithAuthorization 签名生成")
    if os.getenv("X402_PRIVATE_KEY"):
        sig = x.sign_eip3009(
            from_addr="0x" + "11" * 20, to_addr="0x1234567890123456789012345678901234567890",
            value=5000, asset=USDC_BASE_SEPOLIA, chain_id=84532,
        )
        assert len(sig["signature"]) == 130, "签名必须是 65 字节 hex"
        print(f"      OK: signature=0x{sig['signature'][:16]}...（{len(sig['signature'])} hex chars）")
        print(f"      nonce={sig['nonce'][:16]}... validBefore={sig['validBefore']}")
    else:
        print(f"      [{SKIP}] 未设置 X402_PRIVATE_KEY（dry-run 跳过签名）")
        print(f"            真实实跑：.env 设置 X402_PRIVATE_KEY 后在 Base 充 USDC")

    # 6) 真实结算
    print("\n[6/6] 真实结算")
    if real:
        r = settle(SAMPLE_CHALLENGE)
        if r.get("ok"):
            print(f"      OK: settlement={r.get('settlement')}")
        else:
            print(f"      [FAIL] {r.get('error')}")
            print("            检查：X402_PRIVATE_KEY / facilitator 端点 / Base 余额")
    else:
        print(f"      [{SKIP}] dry-run 模式不真实结算。配好环境后运行:")
        print(f"            python examples/x402_dryrun.py --real")

    print("\n" + "=" * 64)
    print("  链路状态：白名单/解析全部离线可验；签名与结算需真实环境。")
    print("  对照 docs.keeperhub.com/ai-tools/agentic-wallet 校准字段后即可实跑。")
    print("=" * 64)


if __name__ == "__main__":
    main()
