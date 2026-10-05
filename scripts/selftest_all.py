#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selftest_all.py —— 量化交易Agent策略框架 v2.1 · 一键自检（引擎层 + 审计层 + 因子层）

用法：
  PY=python3
  $PY scripts/selftest_all.py
  # 或显式指定解释器（因子层需要 numpy + pandas）：
  QTA_PY=/path/to/python $PY scripts/selftest_all.py

★ 自检不过 ⇒ 后面全部结论作废（这是框架的第一条纪律，不是建议）。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = os.environ.get("QTA_PY") or sys.executable


def run(title: str, script: Path) -> tuple[int, str]:
    """返回 (退出码, 合并输出)。输出同时透传到终端。"""
    print(f"\n{'=' * 74}\n▶ {title}\n  {PY} {script} --selftest\n{'=' * 74}")
    if not script.exists():
        print(f"  ❌ 找不到脚本：{script}")
        return 2, ""
    p = subprocess.run([PY, str(script), "--selftest"], capture_output=True, text=True)
    sys.stdout.write(p.stdout)
    if p.stderr:
        sys.stderr.write(p.stderr)
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    rc_engine, _ = run("引擎层 · qta_loop（三方闭环 + 前向体检 F0–F6 + 部署审计 D0–D4 + 催办）",
                       HERE / "qta_loop.py")
    rc_audit, _ = run("审计层 · preflight_audit（P0/P1/P2 规则 + 代码指纹 + .preflightignore）",
                      HERE / "preflight_audit.py")
    rc_factor, out_factor = run("因子层 · fps_factor（N* / moving-block CI / 选择自由度 / 可分辨性 / FPS）",
                                HERE / "fps_factor.py")

    # ★ 「未测得」必须与「未通过」分开表述（框架自己的第一条纪律）：
    #   缺 numpy/pandas 是环境问题，不是包坏了，绝不能显示成 ❌ 让人以为装错了。
    missing_dep = rc_factor != 0 and ("ModuleNotFoundError" in out_factor
                                      or "No module named" in out_factor)

    def mark(rc: int, missing: bool = False) -> str:
        if rc == 0:
            return "✅ 通过"
        return "⚠️ 未测（环境缺依赖）" if missing else "❌ 未通过"

    print("\n" + "=" * 74)
    print(f"引擎层 qta_loop       ：{mark(rc_engine)}")
    print(f"审计层 preflight_audit：{mark(rc_audit)}")
    print(f"因子层 fps_factor     ：{mark(rc_factor, missing_dep)}")
    if missing_dep:
        print("\n提示：因子层需要 numpy + pandas，当前解释器没装 —— 这不影响引擎层与审计层"
              "（它们零第三方依赖）。\n      装好依赖后重跑，或指定一个装了这两个包的解释器：")
        print("  QTA_PY=/path/to/python-with-numpy-pandas python3 scripts/selftest_all.py")
    print("=" * 74)
    ok = rc_engine == 0 and rc_audit == 0 and (rc_factor == 0 or missing_dep)
    if missing_dep and ok:
        print("结论：核心两层通过；因子层未测（非失败）。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
