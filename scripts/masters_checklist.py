#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""masters_checklist.py —— M 系列规则（大师经验→框架）软检查器
================================================================================
对照 references/masters.md 的 M-1~M-12，检查 round.json / verdict.json 的合规缺口。
输出 PASS/WARN/MISS 清单（不计入硬闸，作裁判人工审阅附件）。

用法：
  python masters_checklist.py --round round.json [--verdict verdict.json]
  python masters_checklist.py --selftest

自检：内置「好/坏」两个样例，验证输出逻辑（全标准库，无第三方依赖）。
"""
from __future__ import annotations
import argparse, json, sys, os

SPEC = "2026-10-10.1"


def load_json(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ✗ 无法读取 {p}: {e}")
        return None


def _get(d, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return cur


def check_m1(round_d):
    """M-1 数据卫生声明。"""
    ctx = _get(round_d, "metrics", "context", default={}) or {}
    if _get(ctx, "data_hygiene") is not None:
        return "PASS", "data_hygiene 已声明"
    return "WARN", "缺 data_hygiene 声明（价格非有限值/停牌缺口/复权跳变/ST 过滤）"


def check_m3(round_d, verdict_d):
    """M-3 回撤阶梯预注册。"""
    if _get(round_d, "proponent", "failure_conditions") is not None:
        fc = " ".join(_get(round_d, "proponent", "failure_conditions", default=[]) or [])
        if "drawdown" in fc.lower() or "回撤" in fc:
            return "PASS", "failure_conditions 含回撤处置"
    if _get(round_d, "metrics", "candidate", "exposure") is not None:
        return "WARN", "满仓形态候选：缺 drawdown_ladder（分级缩仓表）"
    return "MISS", "非满仓形态，M-3 不适用"


def check_m4(round_d):
    """M-4 凯利比例与半凯利建议。"""
    fwd = _get(round_d, "fwd", default={}) or {}
    if _get(fwd, "mean") is None:
        return "MISS", "fwd.mean 缺失，无法计算凯利"
    win = _get(fwd, "win")
    if win is None:
        return "WARN", "缺 fwd.win（信号笔胜率）⇒ 无法算凯利；建议补 win/payoff"
    return "WARN", f"fwd.win={win} ⇒ 请报告凯利比例 F=PW−PL/W 与建议仓位（≤半凯利）"


def check_m6(verdict_d):
    """M-6 adopt ⇒ 必须派 decay_tracker。"""
    if verdict_d is None:
        return "MISS", "无 verdict，跳过"
    v = _get(verdict_d, "verdict")
    if v == "adopt":
        tasks = _get(verdict_d, "next_round", "proponent_tasks", default=[]) or []
        kinds = [t.get("kind") for t in tasks if isinstance(t, dict)]
        if "decay_tracker" in kinds:
            return "PASS", "adopt 已派 decay_tracker"
        return "FAIL", "verdict=adopt 但未派 decay_tracker（M-6 违规）"
    return "PASS", f"verdict={v}，非 adopt，M-6 待触发"


def check_m7(round_d):
    """M-7 元标注/排序键声明。"""
    ck = json.dumps(round_d, ensure_ascii=False)
    if "排序" in ck or "rank" in ck.lower() or "meta" in ck.lower():
        return "PASS", "检测到排序/元标注声明（请确认含精确率 vs 召回率权衡）"
    return "MISS", "无排序键/元标注声明（若主信号有二级过滤，必须补）"


def check_m8(round_d):
    """M-8 模型冻结声明（回测前完全指定）。"""
    ck = json.dumps(round_d, ensure_ascii=False)
    if "model_frozen" in ck:
        return "PASS", "model_frozen 已声明"
    return "WARN", "缺 model_frozen 声明（de Prado：回测时研究=酒驾）"


def check_m9(round_d):
    """M-9 拥挤度自评。"""
    ck = json.dumps(round_d, ensure_ascii=False)
    if "crowding" in ck or "拥挤" in ck:
        return "PASS", "拥挤度已声明"
    return "WARN", "缺拥挤度自评（公开程度/同向行动）"


def check_m10(round_d):
    """M-10 回撤处置预注册于回测通过时。"""
    if _get(round_d, "proponent", "failure_conditions"):
        return "PASS", "failure_conditions 已预注册"
    return "WARN", "缺 failure_conditions（回撤处置未预注册）"


def check_m11(round_d):
    """M-11 研究管线储备。"""
    dims = _get(round_d, "blueocean", "dims", default=[]) or []
    if dims:
        return "PASS", f"储备方向 {len(dims)} 个"
    return "WARN", "blueocean.dims 为空（收敛≠停止研究）"


def check_m12(verdict_d):
    """M-12 联合改进评估（采纳报告模板）。"""
    if verdict_d is None:
        return "MISS", "无 verdict，跳过"
    v = _get(verdict_d, "verdict")
    if v == "adopt":
        ck = json.dumps(verdict_d, ensure_ascii=False)
        if "联合" in ck or "joint" in ck.lower() or "组合" in ck:
            return "PASS", "采纳报告含联合改进评估"
        return "FAIL", "verdict=adopt 但缺与现有组合的联合改进评估（M-12 违规）"
    return "PASS", f"verdict={v}，非 adopt，M-12 待触发"


CHECKS = [
    ("M-1", "数据卫生声明", lambda r, v: check_m1(r)),
    ("M-3", "回撤阶梯预注册", lambda r, v: check_m3(r, v)),
    ("M-4", "凯利比例与半凯利", lambda r, v: check_m4(r)),
    ("M-6", "衰减跟踪（adopt⇒decay_tracker）", lambda r, v: check_m6(v)),
    ("M-7", "元标注/排序键", lambda r, v: check_m7(r)),
    ("M-8", "模型冻结声明", lambda r, v: check_m8(r)),
    ("M-9", "拥挤度自评", lambda r, v: check_m9(r)),
    ("M-10", "回撤处置预注册", lambda r, v: check_m10(r)),
    ("M-11", "研究管线储备", lambda r, v: check_m11(r)),
    ("M-12", "联合改进评估", lambda r, v: check_m12(v)),
]

# M-2/M-5 依赖实时影子盘数据与 G10（已在引擎内），此处只提示人工：
MANUAL = {
    "M-2": "实盘低于回测分布 ⇒ 停机诊断（禁调参）——检查影子盘对比跟踪器",
    "M-5": "新策略与现有组合 60 日相关性 + 高相关仓位折减——G10 已覆盖 max_rho，补仓位折减",
}


def run(round_d, verdict_d):
    out = []
    for mid, name, fn in CHECKS:
        try:
            st, msg = fn(round_d, verdict_d)
        except Exception as e:
            st, msg = "ERROR", f"{type(e).__name__}: {e}"
        out.append((mid, name, st, msg))
    return out


def report(round_d, verdict_d):
    rows = run(round_d, verdict_d)
    print("=" * 78)
    print("M 系列软检查（大师经验 → 框架规则；不计入硬闸，供裁判人工审阅）")
    print("=" * 78)
    tally = {}
    for mid, name, st, msg in rows:
        mark = {"PASS": "✓", "WARN": "⚠", "MISS": "—", "FAIL": "✗"}.get(st, "?")
        print(f"  {mark} {mid:<5} {name:<28} {st:<5} {msg}")
        tally[st] = tally.get(st, 0) + 1
    print("-" * 78)
    for mid, msg in MANUAL.items():
        print(f"  · {mid:<5} （人工）{msg}")
    print("-" * 78)
    print("统计: " + "  ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    print("说明: PASS/WARN/MISS 不计入硬闸；FAIL=M 系列违规，裁判应在 commissar_directives 引用。")
    return 0


# ---------------- selftest ----------------

def _sample_good():
    return {
        "metrics": {"context": {"data_hygiene": "checked"}},
        "proponent": {"failure_conditions": ["drawdown ladder 触发"]},
        "fwd": {"mean": 0.03, "win": 0.62},
        "blueocean": {"dims": ["x", "y"]},
        "proponent_model_frozen": True,
    }


def _sample_bad():
    return {"metrics": {"context": {}}, "proponent": {}, "fwd": {"mean": 0.05},
            "blueocean": {"dims": []}}


def selftest() -> int:
    good = _sample_good()
    good["proponent"]["model_frozen"] = True
    ok = True

    r1 = run(good, {"verdict": "adopt", "next_round": {"proponent_tasks": [
        {"kind": "decay_tracker"}]}, "joint": True})
    d1 = {mid: st for mid, name, st, msg in r1}
    if d1["M-6"] != "PASS" or d1["M-12"] != "PASS":
        print("  ✗ 好样例：adopt 应触发 M-6/M-12 PASS"); ok = False
    if d1["M-1"] != "PASS":
        print("  ✗ 好样例：M-1 应 PASS"); ok = False
    print("  ✓ 好样例（adopt 全字段）逻辑正确")

    r2 = run(_sample_bad(), {"verdict": "pending"})
    d2 = {mid: st for mid, name, st, msg in r2}
    if d2["M-1"] != "WARN" or d2["M-11"] != "WARN":
        print("  ✗ 坏样例：M-1/M-11 应 WARN"); ok = False
    if d2["M-6"] != "PASS":
        print("  ✗ 坏样例：非 adopt 时 M-6 应 PASS（待触发）"); ok = False
    print("  ✓ 坏样例（缺字段）逻辑正确")
    print(f"自检结论: {'✅ 通过' if ok else '❌ 失败'}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="M 系列软检查（大师经验→框架规则）")
    ap.add_argument("--round", help="round.json 路径")
    ap.add_argument("--verdict", help="verdict.json 路径")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.round:
        ap.error("--round 必填（或 --selftest）")
    rd = load_json(a.round) or {}
    vd = load_json(a.verdict) if a.verdict else None
    return report(rd, vd)


if __name__ == "__main__":
    sys.exit(main())
