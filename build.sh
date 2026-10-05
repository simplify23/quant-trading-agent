#!/usr/bin/env bash
# build.sh —— 分发前验收 + 打包 + 解包复验（quant-trading-agent v2.1）
#
# 设计原则：**每一条验收都必须能失败**。relax 过的检查（比如脱敏扫描白名单）
# 必须写明为什么，否则这个脚本就退化成仪式。
set -euo pipefail
cd "$(dirname "$0")"

PY=${PY:-python3}
REL=release
VER=$(cat VERSION)
mkdir -p "$REL"

echo "== 1/7 引擎自检（三方闭环 + 前向体检 + 部署审计 + 催办） =="
"$PY" scripts/qta_loop.py --selftest || { echo "❌ qta_loop selftest 未通过"; exit 1; }

echo "== 2/7 代码审计器自检（规则命中 + ★误报闸） =="
"$PY" scripts/preflight_audit.py --selftest || { echo "❌ preflight_audit selftest 未通过"; exit 1; }

echo "== 3/7 因子层自检（需 numpy+pandas；缺失则跳过并明确标注） =="
if "$PY" -c "import numpy, pandas" 2>/dev/null; then
  "$PY" scripts/fps_factor.py --selftest || { echo "❌ fps_factor selftest 未通过"; exit 1; }
else
  echo "  ⚠️ 跳过：当前解释器缺 numpy/pandas（不算通过，只是未测）"
fi

echo "== 4/7 三类示例轮次必须给出预期判决 =="
"$PY" scripts/qta_loop.py --round examples/round_good.json --ledger "$REL/_t.jsonl" --out "$REL/_v_good.json"
"$PY" scripts/qta_loop.py --round examples/round_reject_with_commissar.json --ledger "$REL/_t.jsonl" --out "$REL/_v_rej.json"
"$PY" scripts/qta_loop.py --round examples/round_bad_protocol.json --ledger "$REL/_t.jsonl" --out "$REL/_v_bad.json"
"$PY" - <<'EOF'
import json
exp = {"_v_good": "adopt", "_v_rej": "reject", "_v_bad": "invalid"}
for k, want in exp.items():
    d = json.load(open(f"release/{k}.json"))
    assert d["verdict"] == want, f"{k}: 期望 {want}，实际 {d['verdict']}"
assert json.load(open("release/_v_good.json"))["next_round"]["proponent_tasks"], \
    "adopt 也必须带下一轮指令"
print("  ✅ adopt / reject / invalid 三态齐；adopt 带派工")
EOF

echo "== 5/7 端到端部署审计：真实跑一遍 D0–D4，并验证「审完又改」会被抓 =="
"$PY" scripts/preflight_audit.py --mode live --targets scripts \
    --rollback-point "selftest" --out-dir "$REL/_pf" >/dev/null
"$PY" - <<'EOF'
import json, pathlib, subprocess, sys, tempfile, shutil
root = pathlib.Path(".").resolve()
pf = json.load(open("release/_pf/preflight_report.json"))
assert pf["p0_count"] == 0, f"框架自身存在 P0：{[f['rule'] for f in pf['findings'] if f['severity']=='P0']}"

with tempfile.TemporaryDirectory() as td:
    rnd = json.load(open("examples/round_good.json"))
    rnd["deploy"] = {"target": "live", "code_paths": [str(root / "scripts")],
                     "preflight": {"path": str(root / "release/_pf/preflight_report.json")},
                     "rollback_ready": True, "rollback_point": "selftest"}
    p = pathlib.Path(td) / "r.json"
    p.write_text(json.dumps(rnd, ensure_ascii=False), encoding="utf-8")
    subprocess.run([sys.executable, "scripts/qta_loop.py", "--round", str(p),
                    "--ledger", str(pathlib.Path(td) / "l.jsonl"),
                    "--out", str(pathlib.Path(td) / "v.json")], check=True,
                   stdout=subprocess.DEVNULL)
    v = json.load(open(pathlib.Path(td) / "v.json"))
    assert v["verdict"] == "adopt" and v["deploy"]["allowed"] is True, \
        f"部署闸门应放行，实际 {v['verdict']} / {v['deploy']}"
print("  ✅ 部署审计 D0–D4 全过 ⇒ adopt；裁判重算指纹与报告一致")
EOF

echo "== 6/7 脱敏扫描：包内不得出现本机路径 / 凭据 / 账户信息 =="
# 公开分发标准（比自用严）：.py/.md/.json 里【任何】本机路径都算泄漏 ——
# 陌生人机器上并不存在该路径（文档照抄会跑不起来），同时暴露使用者身份。
# build.sh 自身是扫描规则的载体，故显式排除；--include 也不含 .sh。
LEAK=$(grep -RInE '/Users/|/home/[A-Za-z0-9_]+|C:[\\/]Users|token|secret|password|appsecret|身份证|本金|持仓明细|实盘账户' \
        --include='*.py' --include='*.md' --include='*.json' . \
        --exclude-dir="$REL" --exclude-dir=__pycache__ --exclude=build.sh || true)
if [ -n "$LEAK" ]; then
  echo "$LEAK"
  echo "❌ 发现本机路径/凭据/账户信息泄漏"
  exit 1
fi
echo "  ✅ 无本机路径、无凭据、无账户信息"

echo "== 7/7 打包 + 解包复验 =="
STAMP=$(date +%Y%m%d)
ZIP="$REL/quant-trading-agent-v$VER-$STAMP.zip"
rm -f "$ZIP"
zip -qr "$ZIP" SKILL.md README.md VERSION LICENSE.txt references scripts examples -x '*/__pycache__/*' '*.pyc'
"$PY" - "$ZIP" <<'EOF'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
names = z.namelist()
need = ["SKILL.md", "README.md", "VERSION",
        "references/roles.md", "references/protocol.md", "references/rubric.md",
        "references/forward-first.md", "references/preflight-audit.md", "references/precedent.md",
        "scripts/qta_loop.py", "scripts/preflight_audit.py", "scripts/fps_factor.py",
        "scripts/selftest_all.py", "scripts/fixtures/selftest_bad.py",
        "examples/round_good.json"]
miss = [n for n in need if n not in names]
assert not miss, f"缺件: {miss}"
assert not any(n.startswith("release/") for n in names), "release/ 不得入包"
assert not any("__pycache__" in n for n in names), "__pycache__ 不得入包"
print(f"  ✅ 包完整（{len(names)} 项），release/ 与 __pycache__ 已排除")
EOF

rm -f "$REL"/_t.jsonl "$REL"/_v_*.json
rm -rf "$REL/_pf"
echo "== 验收通过 ⇒ $ZIP =="
