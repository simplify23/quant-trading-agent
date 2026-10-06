#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qta_loop.py —— 量化交易Agent策略框架 v2.0 · 三方闭环 + 前向体检 + 催办引擎

三方：正方（探索 / 代码优化实现者）· 反方（政委：风险登记 + 优化处方）· 中立裁判（取证 + 裁决 + 派工 + 催办）

v2.0 相对前代的三个执行缺口（本引擎把它们变成机械契约，不靠角色自觉）：
  ★1. 裁判必须【催办】正方的代码优化工作：判决书带 coach（nag_level / must_do / escalation），
      连续未响应 ⇒ 停工清偿（hold_new_candidates）⇒ 再连续 ⇒ 终止迭代。
  ★2. 反方必须是【政委】：非采纳轮硬性要求 commissar_pack.opt_prescriptions 非空
      （每条含 target / action / expected_delta / rollback）——风控以外，必须交付「怎么改」。
  ★3. 任何结论必须先过【前向优先体检】F0–F6：没有体检 ⇒ 判决封顶 pending；
      未到 N* ⇒ 只许「未检出（pending/not_detected）」，不许判「无效（reject）」。

★ 引擎强制的协议（P 系列）：
  P1  裁决 ≠ adopt ⇒ 反方 directions 非空                     否则 invalid
  P3  正方主张挂证据 ID；反方反对挂预注册预期                   否则 invalid
  P5  判据文件 SHA256 指纹随判决落盘                            事件偷改可检出
  P6  ★政委契约：裁决 ≠ adopt ⇒ commissar_pack.opt_prescriptions ≥1 条且四要素齐   否则 invalid
  P7  ★催办契约：正方须回填 responded_tasks；未响应 ⇒ nag+1 ⇒ 升级至停工清偿
  P7b ★代码优化契约：裁判每轮必派 ≥1 条 kind=code_optimization；正方连续空交 ⇒ 计入 nag
  P8  ★前向键契约：rank_key_source ∈ {holdout, full} ⇒ 直接 invalid（作弊键）
  P4  收敛四闸：预算用尽 ｜ 连续 MAX_IDLE 轮无采纳 ｜ 达 max_rounds ｜ 正方连续 NAG_STOP 轮不响应派工

判据（两组，逐条独立成败，不加权）：
  G1–G9 准入组（锚点/主指标/风险/样本/覆盖率/连续优区/跨年/无前视/DSR）
  F0–F6 前向组（口径指纹/N*/选择自由度/前向键/差异笔/留一笔；F4=G6 复用）

零第三方依赖（纯标准库）。用法见底部 CLI；`--selftest` 必跑，不过则后面全部结论作废。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

VERSION = "2.1.0"

# ---- 阈值（改动必须同步 references/rubric.md，且会改变 criteria_sha）----
MAX_IDLE = 3            # 连续无采纳轮数上限（收敛闸）
MIN_N = 8               # G4 影响样本量下限
MIN_COV = 90.0          # G5 覆盖率 %
MIN_REGION = 4          # G6 连续优区格数
DSR_MIN = 0.95          # G9 DSR 判据
NAG_HOLD = 2            # 正方连续未响应 ≥2 轮 ⇒ 停工清偿（不再受理新候选）
NAG_STOP = 3            # 正方连续未响应 ≥3 轮 ⇒ 终止迭代（作业面失效）
MIN_REPEAT_N = 30       # μ≤0 时判「有证据反对」所需最少笔数（防两笔为负就判死）
# ---- v2.2 新增（A3/A6/A1 三项度量升级）----
PBO_MAX = 0.5           # G9b：过拟合概率上限。★ 实测单次 PBO 的 sd≈0.26 ⇒ 只作辅助诊断，作【软闸】
SPA_ALPHA = 0.05        # G9c：Hansen SPA 显著性（族内最优是否真优于基准）
MAX_RHO_NOVELTY = 0.5   # G10：候选与「已采纳结论集」的最大可接受 |ρ|（超过 ⇒ 非新增量）
IC_TMIN = 2.0           # G11：截面 IC 的 t_adj 强阈值（≥2 强 / 1~2 弱 / <1 不可判定）
IC_TWEAK = 1.0

HARD_GATES = ("G1_anchors", "G2_metric", "G3_risk", "G4_n", "G8_nolookahead", "G9a_DSR")
SOFT_GATES = ("G5_coverage", "G6_region", "G7_multiyear",
              "G9b_PBO", "G9c_SPA", "G10_novelty", "G11_panel_ic")
F_LABELS = ("F0_provenance", "F1_nstar", "F2_choice_freedom",
            "F3_forward_key", "F5_diff_trades", "F6_loo")
D_LABELS = ("D0_report_present", "D1_code_fingerprint", "D2_no_blocker",
            "D3_rollback_ready", "D4_report_fresh")

# ★ 复用审计器的指纹实现：裁判重算 code_sha256 时必须与被审工具用【同一份】代码，
#   否则就是本框架自己踩「两份同义实现」的先例（P-13）。
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import preflight_audit as PFA
except Exception:  # pragma: no cover
    PFA = None

MAX_REPORT_AGE_DAYS = int(getattr(PFA, "MAX_REPORT_AGE_DAYS", 7))


# ---------------------------------------------------------------- utilities
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _fingerprint(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _num(x):
    """安全取数：bool/None/非数一律 None（防 nan 被当达标，见纪律：nan 比较恒 False）。"""
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return None if (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else float(x)
    return None


def _fmt(x, nd: int = 4) -> str:
    """展示用：整数不带小数点；浮点保留 nd 位；None 显式打印。"""
    if x is None:
        return "None"
    if isinstance(x, float):
        return str(int(x)) if x == int(x) else f"{x:.{nd}f}"
    return str(x)


def _ci_contains_zero(ci) -> bool:
    if not isinstance(ci, (list, tuple)) or len(ci) != 2:
        return True                      # 缺 CI ⇒ 视为「不可分辨」（保守）
    lo, hi = _num(ci[0]), _num(ci[1])
    if lo is None or hi is None:
        return True
    return lo <= 0.0 <= hi


def load_json(p: str):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_ledger(p: str) -> list:
    if not p or not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


# ---------------------------------------------------------------- DSR（试错折减）
def _norm_ppf(p: float) -> float:
    """标准正态分位数（erf 二分，纯标准库）。"""
    if not 0.0 < p < 1.0:
        raise ValueError(p)
    lo, hi = -8.0, 8.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if _norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def expected_max_sharpe(trials: int, n_obs: int, ppy: int = 252) -> float | None:
    """SR0：零假设下试 trials 次的期望最大 Sharpe（年化）。不可算时返回 None（★不返回 nan）。

    Bailey & López de Prado：
      SR0 = sqrt(Var[SR]) · [ (1−γ)·Φ⁻¹(1−1/N) + γ·Φ⁻¹(1−1/(N·e)) ]
    白噪声零假设下 Var[SR̂] ≈ 1/(n−1)（单观测口径），年化 ×sqrt(ppy)。
    ⚠️ 首版踩坑：误用 Φ(1−1/N)（CDF）而非 Φ⁻¹（分位数），SR0 被灌大 → 真效应全灭。
    ⚠️ 纪律：解析/计算函数**绝不返回 nan**（nan 比较恒为 False，会把闸门静默绕过）。"""
    if trials < 2 or n_obs < 10:
        return None
    g = 0.5772156649  # Euler–Mascheroni
    z1 = _norm_ppf(1.0 - 1.0 / trials)
    z2 = _norm_ppf(1.0 - 1.0 / (trials * math.e))
    term = (1.0 - g) * z1 + g * z2
    return term / math.sqrt(max(1, n_obs - 1)) * math.sqrt(ppy)


def dsr_prob(sharpe_ann: float, sharpe0_ann: float, n_obs: int, ppy: int = 252,
             skew: float = 0.0, kurt: float = 3.0) -> float:
    """Deflated Sharpe Ratio：观测 Sharpe（年化）真 > SR0（年化）的概率。
    内部统一折回单观测口径再算统计量（Bailey–LdP 公式要求 per-observation SR）。"""
    sr = sharpe_ann / math.sqrt(ppy)
    sr0 = sharpe0_ann / math.sqrt(ppy)
    denom = math.sqrt(max(1e-12, 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2))
    return _norm_cdf((sr - sr0) * math.sqrt(max(1, n_obs) - 1.0) / denom)


# preflight-ok: N* 口径与 scripts/fps_factor.py 同名函数一致（⌈(2σ/μ)²⌉），两侧 selftest 各自断言
def n_star(mean: float, sd: float) -> int | None:
    """N* = ⌈(2σ/μ)²⌉ —— 把噪声与真效应分开所需的最小笔数。μ≤0 ⇒ 无定义（返回 None）。"""
    if mean is None or sd is None or mean <= 0 or sd < 0:
        return None
    return int(math.ceil((2.0 * sd / mean) ** 2))


# ---------------------------------------------------------------- G1–G9 准入组
def run_gates(cand: dict, m: dict, cfg: dict) -> dict:
    """m = metrics；cfg = {metric_key, risk_key}。逐条独立成败，不加权。"""
    base = m.get("baseline", {}) or {}
    candm = m.get("candidate", {}) or {}
    ctx = m.get("context", {}) or {}
    mk, rk = cfg.get("metric_key", "ann"), cfg.get("risk_key", "mdd")
    g = {}

    g["G1_anchors"] = {"pass": bool(ctx.get("anchors_ok", False)), "detail": "口径锚点/自校验"}

    cv, bv = _num(candm.get(mk)), _num(base.get(mk))
    g["G2_metric"] = {"pass": (cv is not None and bv is not None and cv > bv),
                      "detail": f"{mk}: cand={candm.get(mk)} vs base={base.get(mk)}"}

    cr, br = _num(candm.get(rk)), _num(base.get(rk))
    g["G3_risk"] = {"pass": (cr is not None and br is not None and cr >= br),
                    "detail": f"{rk}(越大越好): cand={candm.get(rk)} vs base={base.get(rk)}"}

    n = _num(candm.get("n"))
    n_i = int(n) if n is not None else 0
    g["G4_n"] = {"pass": n_i >= MIN_N, "detail": f"n={n_i} ≥ {MIN_N}"}

    cov = ctx.get("coverage", {}) or {}
    uses = cand.get("uses", []) or []
    cov_ok = all(_num(cov.get(v)) is not None and float(cov[v]) >= MIN_COV for v in uses) if uses else False
    g["G5_coverage"] = {"pass": cov_ok, "detail": f"uses={uses} coverage={cov} ≥{MIN_COV}%"}

    region = ctx.get("region", {}) or {}
    rmax = max([_num(v) or 0 for v in region.values()], default=0)
    g["G6_region"] = {"pass": rmax >= MIN_REGION, "detail": f"连续优区={_fmt(rmax)} ≥ {MIN_REGION}格"}

    rby = (ctx.get("removed_by_year", {}) or {}).get(cand.get("kind", ""), {}) or {}
    bby = ctx.get("base_by_year", {}) or {}
    g7 = bool(rby) and all((_num(rby.get(y)) or 0) > 0 for y in bby) if bby else bool(rby)
    g["G7_multiyear"] = {"pass": g7, "detail": "影响集不与单一自然年重合"}

    nla = (ctx.get("no_lookahead", {}) or {}).get(cand.get("kind", ""), {}) or {}
    nlv = _num(nla.get(mk))
    g["G8_nolookahead"] = {"pass": (nlv is not None and bv is not None and nlv > bv),
                           "detail": f"无前视口径 {mk}={nla.get(mk)} 仍优于基线 {base.get(mk)}"}

    # ---- G9a DSR（硬闸：试错次数折减）----
    trials = _num(ctx.get("trials")) or 0
    sr = _num(candm.get("sharpe"))
    if trials >= 2 and sr is not None and n_i > 0:
        ppy = int(_num(ctx.get("ppy")) or 252)
        sr0 = expected_max_sharpe(int(trials), n_i, ppy)
        if sr0 is None:
            g["G9a_DSR"] = {"pass": False,
                            "detail": f"SR0 不可算（trials={int(trials)} 或 n={n_i} 过小）⇒ DSR 不可判，视为未过"}
        else:
            p = dsr_prob(sr, sr0, n_i, ppy,
                         _num(candm.get("skew")) or 0.0, _num(candm.get("kurt")) or 3.0)
            g["G9a_DSR"] = {"pass": p >= DSR_MIN,
                            "detail": f"DSR={p:.4f} ≥{DSR_MIN}（SR0年化={sr0:.2f}，trials={int(trials)}，n={n_i}）"}
    else:
        g["G9a_DSR"] = {"pass": False, "detail": "trials/sharpe/n 缺失 ⇒ DSR 不可判，视为未过"}

    # ---- G9b PBO（软闸：★ 噪声带极宽，只作辅助诊断，绝不单独否决）----
    pbo = _num(ctx.get("pbo"))
    if pbo is None:
        g["G9b_PBO"] = {"pass": None, "skipped": True,
                        "detail": "未提供 PBO（用 scripts/overfit_metrics.py --pbo 计算）"}
    else:
        g["G9b_PBO"] = {"pass": pbo <= PBO_MAX,
                        "detail": f"PBO={pbo:.3f} ≤ {PBO_MAX}"
                                  f"（★实测单次 sd≈0.26 ⇒ 仅作辅助诊断，不作否决依据）"}

    # ---- G9c SPA（软闸：族内最优是否真优于基准）----
    spa = _num(ctx.get("spa_p"))
    if spa is None:
        g["G9c_SPA"] = {"pass": None, "skipped": True,
                        "detail": "未提供 SPA p 值（用 scripts/overfit_metrics.py --spa 计算）"}
    else:
        g["G9c_SPA"] = {"pass": spa <= SPA_ALPHA,
                        "detail": f"SPA p={spa:.4f} ≤ {SPA_ALPHA}（Hansen 2005，族内最优优于基准）"}

    # ---- G10 新增量：与「已采纳结论集」的相关性（A1 · FactorMiner 的去重闸）----
    nov = ctx.get("novelty") or {}
    mr = _num(nov.get("max_rho"))
    if mr is None:
        g["G10_novelty"] = {"pass": None, "skipped": True,
                            "detail": "未提供 novelty.max_rho ⇒ 无法确认是否【新增量】"}
    else:
        g["G10_novelty"] = {"pass": mr <= MAX_RHO_NOVELTY,
                            "detail": f"与已采纳结论集最大 |ρ|={mr:.3f} ≤ {MAX_RHO_NOVELTY}"
                                      f"（against={nov.get('against')}）"}

    # ---- G11 面板级 IC（A6 · 文献通用语言；样本效率比逐笔高一个量级）----
    pic = ctx.get("panel_ic") or {}
    t_adj = _num(pic.get("t_adj"))
    if t_adj is None:
        g["G11_panel_ic"] = {"pass": None, "skipped": True,
                             "detail": "未提供 panel_ic.t_adj（按日聚类后再除 √h 的 t 值）"}
    else:
        weak = IC_TWEAK <= t_adj < IC_TMIN
        g["G11_panel_ic"] = {
            "pass": t_adj >= IC_TMIN,
            "detail": f"截面 IC t_adj={t_adj:.2f}（IC={pic.get('ic')}，IR={pic.get('ir')}，"
                      f"n_days={pic.get('n_days')}）"
                      + ("；≥2 强" if t_adj >= IC_TMIN
                         else ("；1~2 弱（不足以单独支撑采纳）" if weak else "；<1 不可判定"))}
    return g


# ---------------------------------------------------------------- F0–F6 前向体检组
def forward_gates(rnd: dict) -> tuple[dict, dict]:
    """读 round.fwd。返回 (gates, info)。pass=None 表示「不适用/未提供」（不是失败）。"""
    fwd = rnd.get("fwd") or {}
    G: dict = {}
    info: dict = {"coverage": fwd.get("coverage") or ("none" if not fwd else "partial"),
                  "reasons": [], "Nstar": None, "n_obs": None, "mean": None, "sd": None,
                  "inconclusive": None, "selection_dof": None,
                  "single_trade_carried": False, "diff_undecided": [],
                  "rank_key_cheat": False}

    if not fwd or info["coverage"] == "none":
        for k in F_LABELS:
            G[k] = {"pass": None, "skipped": True, "detail": "未提供 fwd 体检段 ⇒ 未做前向优先体检"}
        info["reasons"].append("未做前向优先体检 ⇒ 结论最高只能到 pending（不许 adopt）")
        return G, info

    # F0 口径钉死（数据指纹 + 口径四要素）
    cal = fwd.get("caliber") or {}
    need = ("adjust", "asof", "cost", "universe")
    missing = [k for k in need if not cal.get(k)]
    f0 = bool(fwd.get("panel_md5")) and not missing
    G["F0_provenance"] = {"pass": f0,
                          "detail": f"panel_md5={fwd.get('panel_md5')} caliber缺={missing or '无'}"}

    # F1 样本量算术（N*）
    n_ = _num(fwd.get("n_obs")); mu = _num(fwd.get("mean")); sd = _num(fwd.get("sd"))
    info.update(n_obs=n_, mean=mu, sd=sd)
    if n_ is None or mu is None or sd is None:
        G["F1_nstar"] = {"pass": None, "skipped": True, "detail": "缺 n_obs/mean/sd ⇒ N* 不可算"}
        info["reasons"].append("N* 不可算（缺 n_obs/mean/sd）⇒ 只能判「未检出」")
        info["inconclusive"] = True
    else:
        nstar = n_star(mu, sd)
        info["Nstar"] = nstar
        if nstar is None:
            # μ ≤ 0：N* 无定义。样本足够大且方向为负 ⇒ 允许判「有证据反对」
            inconcl = int(n_) < MIN_REPEAT_N
            G["F1_nstar"] = {"pass": not inconcl, "detail":
                             f"μ={mu:+.4f} ≤ 0 ⇒ N* 无定义（无穷）；n={int(n_)}"
                             + ("，样本已足 ⇒ 允许判「有证据反对」" if not inconcl
                                else f" < {MIN_REPEAT_N} ⇒ 未检出，不许判死")}
        else:
            inconcl = int(n_) < nstar
            G["F1_nstar"] = {"pass": not inconcl, "detail":
                             f"N*={nstar}，n={int(n_)}"
                             + ("（样本未到 ⇒ 未检出，禁止判死也禁止判活）" if inconcl else "（样本已足）")}
        info["inconclusive"] = inconcl
        if inconcl:
            info["reasons"].append(f"样本未到 N*={info['Nstar'] if nstar else '∞'} ⇒ 判决封顶「未检出」")

    # F2 选择自由度诊断（跑随机对照之前必须先做）
    pmax = _num(fwd.get("per_day_max_candidates"))
    if pmax is None:
        G["F2_choice_freedom"] = {"pass": None, "skipped": True, "detail": "未提供单日最大候选数"}
        info["reasons"].append("未做选择自由度诊断 ⇒ 随机对照分位不可信")
    elif int(pmax) <= 1:
        G["F2_choice_freedom"] = {
            "pass": None, "skipped": True, "not_applicable": True,
            "detail": (f"单日最多 {int(pmax)} 个候选 ⇒ 零排序自由度：这是事件过滤器，不是选股策略；"
                       "所有「加因子 / 改排序 / 调 topK」类优化在定义上无效")}
        info["selection_dof"] = "none"
        info["reasons"].append("零排序自由度 ⇒ 排序/加权类优化在定义上无效（不是「没测出」，是「不存在」）")
    else:
        G["F2_choice_freedom"] = {"pass": True,
                                  "detail": f"单日最多 {int(pmax)} 个候选 ⇒ 有排序自由度，随机对照可测"}
        info["selection_dof"] = "present"

    # F3 前向优先排序（选优键禁止触碰留出段）
    src = (fwd.get("rank_key_source") or "").lower()
    if src in ("holdout", "test", "full", "all", "oos"):
        G["F3_forward_key"] = {"pass": False,
                               "detail": f"选优键取自 {src}（含留出段/全期）= 作弊键"}
        info["rank_key_cheat"] = True
    elif src == "train":
        G["F3_forward_key"] = {"pass": True, "detail": "选优键只用训练段 ✅"}
    else:
        G["F3_forward_key"] = {"pass": None, "skipped": True, "detail": "未声明选优键来源"}

    # F5 差异笔集合审计（改动型候选必填）
    if not fwd.get("is_change", False):
        G["F5_diff_trades"] = {"pass": None, "skipped": True, "detail": "非改动型候选 ⇒ 无需差异笔审计"}
    else:
        dt = fwd.get("diff_trades") or {}
        groups = {g: dt.get(g) for g in ("added", "removed") if dt.get(g)}
        if not groups:
            G["F5_diff_trades"] = {
                "pass": False,
                "detail": "改动型候选未提供差异笔审计 ⇒ 改动未被证明（禁止宣称「提高了收益」）"}
            info["diff_undecided"] = ["missing"]
        else:
            und = [g for g, v in groups.items() if _ci_contains_zero(v.get("ci"))]
            det = {g: {"n": v.get("n"), "mean": v.get("mean"), "ci": v.get("ci")} for g, v in groups.items()}
            G["F5_diff_trades"] = {
                "pass": not und,
                "detail": f"差异笔={det}；CI 含 0 的组={und or '无'}"
                          + (f" ⇒ 该组与「不改」统计不可分辨，改动未被证明" if und else " ⇒ 差异可分辨")}
            info["diff_undecided"] = und

    # F6 留一笔 / 留一事件段（单事件独扛检查）
    loo = fwd.get("loo") or {}
    tot, exb = _num(loo.get("total")), _num(loo.get("ex_best"))
    if tot is None or exb is None:
        G["F6_loo"] = {"pass": None, "skipped": True, "detail": "未提供留一笔读数（loo.total / loo.ex_best）"}
    else:
        carried = tot > 0 and exb <= 0
        info["single_trade_carried"] = carried
        G["F6_loo"] = {"pass": not carried,
                       "detail": f"剔最好一笔后 {exb:+.2f}%（原 {tot:+.2f}%）"
                                 + (" ⇒ 结论由单笔独扛，不可当规律" if carried else " ⇒ 非单笔独扛")}
    return G, info


# ---------------------------------------------------------------- D0–D4 部署审计组
def deploy_gates(rnd: dict) -> tuple[dict, dict]:
    """读 round.deploy。未声明 target ⇒ 全部不适用（向后兼容，不影响判决）。

    ★ 独立取证：D1 由裁判**自己重算** code_paths 的 sha256 再与报告比对 ——
      防「审完又改」（拿一份通过的报告去上线另一份代码）。"""
    dep = rnd.get("deploy") or {}
    target = str(dep.get("target") or "").strip().lower()
    G: dict = {}
    info = {"applicable": False, "target": target or None, "allowed": True,
            "blockers": [], "report_path": None, "fingerprint_now": None,
            "fingerprint_report": None, "report_ts": None, "report_age_days": None,
            "notes": []}
    if target not in ("shadow", "live", "prod"):
        for k in D_LABELS:
            G[k] = {"pass": None, "skipped": True, "detail": "未声明部署目标（deploy.target）⇒ 不适用"}
        return G, info
    info["applicable"] = True

    # ---- D0 报告存在且可读 ----
    pf = dep.get("preflight") or {}
    rp = pf.get("path")
    rep = None
    if rp:
        p = Path(str(rp)).expanduser()
        info["report_path"] = str(p)
        if p.exists():
            try:
                rep = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                info["notes"].append(f"报告解析失败：{e}")
    G["D0_report_present"] = {
        "pass": isinstance(rep, dict),
        "detail": f"preflight 报告 = {rp or '（未给出）'}" +
                  ("" if isinstance(rep, dict) else "（缺失/不可读/非 JSON）")}
    rep = rep if isinstance(rep, dict) else {}

    # ---- D1 代码指纹一致性（★ 裁判自己重算）----
    paths = [str(x) for x in (dep.get("code_paths") or []) if str(x).strip()]
    now_sha, files = None, []
    if paths and PFA is not None:
        try:
            now_sha, files = PFA.code_fingerprint(paths)
        except Exception as e:  # noqa: BLE001
            info["notes"].append(f"指纹重算失败：{e}")
    rep_sha = rep.get("code_sha256")
    info.update(fingerprint_now=now_sha, fingerprint_report=rep_sha)
    if now_sha is None:
        G["D1_code_fingerprint"] = {
            "pass": False,
            "detail": ("★ 裁判无法重算指纹：" +
                       ("未提供 deploy.code_paths" if not paths else "审计器不可用")) +
                      " ⇒ 不能确认「审的就是要上的这份代码」"}
    elif not rep_sha:
        G["D1_code_fingerprint"] = {"pass": False, "detail": "报告缺 code_sha256 ⇒ 无法比对"}
    else:
        same = (now_sha == rep_sha)
        G["D1_code_fingerprint"] = {
            "pass": same,
            "detail": f"裁判重算 {now_sha[:16]}… vs 报告 {rep_sha[:16]}…（{len(files)} 个文件）"
                      + ("" if same else " ⇒ ★不一致：审完又改过，必须重审")}

    # ---- D2 无阻断项 ----
    p0 = rep.get("p0_count")
    G["D2_no_blocker"] = {
        "pass": (p0 == 0) and bool(rep.get("passed")),
        "detail": f"报告 p0_count={p0}、passed={rep.get('passed')}"
                  + ("" if p0 == 0 else " ⇒ 存在阻断级 bug，禁止接真实资金/影子账本")}

    # ---- D3 回滚就绪（以 deploy 的当前声明为准；未声明才回落到报告值）----
    rdy = (bool(dep.get("rollback_ready")) if "rollback_ready" in dep
           else bool(rep.get("rollback_ready")))
    rp_txt = dep.get("rollback_point") or rep.get("rollback_point")
    G["D3_rollback_ready"] = {"pass": rdy,
                              "detail": f"回滚点 = {rp_txt or '（未提供）'}"}

    # ---- D4 报告新鲜度 ----
    ts = rep.get("ts")
    age = None
    if ts:
        try:
            age = (time.time() - time.mktime(time.strptime(str(ts), "%Y-%m-%d %H:%M:%S"))) / 86400.0
        except (ValueError, OverflowError):
            age = None
    info.update(report_ts=ts, report_age_days=age)
    G["D4_report_fresh"] = {
        "pass": (age is not None) and (age <= MAX_REPORT_AGE_DAYS),
        "detail": (f"报告时间 {ts}（{age:.1f} 天前）≤ {MAX_REPORT_AGE_DAYS} 天" if age is not None
                   else "报告缺 ts ⇒ 无法判断新鲜度")}

    info["blockers"] = [k for k, v in G.items() if v.get("pass") is False]
    info["allowed"] = not info["blockers"]
    info["target"] = target
    return G, info


# ---------------------------------------------------------------- 协议校验
def protocol_checks(rnd: dict, gates: dict, fg: dict, info: dict, nag: int) -> tuple[list, list]:
    """返回 (violations ⇒ 致 invalid, warnings ⇒ 只标注)。"""
    v, w = [], []
    prop = rnd.get("proponent", {}) or {}
    adv = rnd.get("adversary", {}) or {}

    # P3 举证要求
    claims = prop.get("claims", []) or []
    if not claims:
        v.append("P3: 正方未提交任何主张（claims 为空）")
    for c in claims:
        if not c.get("evidence"):
            v.append("P3: 正方主张缺证据 ID")
    for o in (adv.get("objections", []) or []):
        if not o.get("prereg"):
            v.append("P3: 反方反对缺预注册预期")

    non_adopt = not would_adopt(gates, fg, info)

    # ★ P9：claim ↔ diff 绑定（A2 · 借 AlphaAgent 的「假设-实现一致性」，防「说改 A 实际改 B」）
    ch = (rnd.get("candidate") or {}).get("change") or {}
    if ch.get("is_change"):
        target = str(ch.get("target") or "").strip()
        if not target:
            v.append("P9: 改动型候选必须声明 change.target（改动的文件:函数），"
                     "否则无法核对「主张」与「实际改动」是否一致")
        else:
            actual = [str(x) for x in (ch.get("actual_files") or [])]
            if actual:
                fname = target.split(":")[0].strip()
                if fname and not any(fname in a for a in actual):
                    v.append(f"P9: 声明改动 {target}，但实际改动文件为 {actual} ⇒ 主张与实现不符")

    # P1 反方优化方向
    if non_adopt and not (adv.get("directions") or []):
        v.append("P1: 未采纳 ⇒ 反方必须给出优化方向（directions 非空）")

    # P6 ★政委契约：风控以外必须给「怎么改」
    pack = adv.get("commissar_pack") or {}
    presc = pack.get("opt_prescriptions") or []
    if non_adopt:
        if not presc:
            v.append("P6: 未采纳 ⇒ 政委包必须给出优化处方（commissar_pack.opt_prescriptions 非空）")
        for i, p in enumerate(presc):
            miss = [k for k in ("target", "action", "expected_delta", "rollback") if not p.get(k)]
            if miss:
                v.append(f"P6: 处方#{i + 1} 缺要素 {miss}（target/action/expected_delta/rollback 必填）")
        if not (pack.get("risk_register") or []):
            w.append("P6w: 政委包缺风险登记（risk_register）——只给进攻不给防守")
    else:
        for i, p in enumerate(presc):
            miss = [k for k in ("target", "action", "expected_delta", "rollback") if not p.get(k)]
            if miss:
                w.append(f"P6w: 处方#{i + 1} 缺要素 {miss}")

    # P8 ★前向键作弊
    if info.get("rank_key_cheat"):
        v.append("P8: 选优键触碰留出段/全期（作弊键）⇒ 本轮作废")

    # P7b ★代码优化契约
    cops = prop.get("code_opt_points") or []
    if not cops:
        w.append("P7b: 本轮未交付代码级优化点（BS-x）——调参前先扫「写死、从未进过搜索自由度」的硬编码")

    # P7 ★催办：非首轮且未响应
    if nag > 0:
        w.append(f"P7: 正方连续 {nag} 轮未响应裁判派工 ⇒ 见 coach.nag_message")
    return v, w


# ---------------------------------------------------------------- 下一轮派工 + 催办
def _mk_tasks(prefix: str, items: list) -> list:
    """补全任务字段并分配不冲突的 ID（欠账任务已带 ID，新任务从空号开始编）。"""
    out, used, k = [], {it.get("id") for it in items if it.get("id")}, 0
    for it in items:
        t = dict(it)
        if not t.get("id"):
            while True:
                k += 1
                cand = f"{prefix}-{k}"
                if cand not in used:
                    t["id"] = cand
                    used.add(cand)
                    break
        t.setdefault("kind", "exploration")
        t.setdefault("due_round", None)
        t.setdefault("blocking", t.get("kind") == "code_optimization")
        out.append(t)
    return out


def next_round_directives(rnd: dict, verdict: str, gates: dict, fg: dict, info: dict,
                          ledger: list, budget_left: int, round_id: int,
                          nag: int, unresolved: list, no_nag: bool = False,
                          dinfo: dict | None = None, dg: dict | None = None) -> dict:
    failed = [k for k, g in gates.items() if not g["pass"]]
    f_fail = [k for k, v in fg.items() if v.get("pass") is False]
    prop_tasks, adv_focus = [], []
    nid = round_id + 1

    if verdict == "adopt":
        prop_tasks.append({"task": "巩固已采纳候选：参数邻域扫描 + 成本/执行可行性复核（换手、容量、整手约束）",
                           "kind": "consolidation", "why": "采纳 ≠ 稳健；采纳后第一轮只做巩固，不做新扩张",
                           "priority": 1})
        adv_focus.append("攻击新采纳候选最脆弱的假设（通常是 G6 连续优区 / G8 无前视口径的选择）")
    elif verdict == "reject":
        for d in sorted(rnd.get("adversary", {}).get("directions", []) or [],
                        key=lambda x: x.get("priority", 99))[:3]:
            prop_tasks.append({"task": d.get("direction", ""), "kind": "exploration",
                               "why": d.get("mechanism", ""), "prereg": d.get("prereg", ""),
                               "priority": d.get("priority", 9)})
        for c in (rnd.get("proponent", {}).get("claims", []) or []):
            adv_focus.append(f"下一轮优先击穿未被本轮反驳的主张：{str(c.get('claim', ''))[:60]}")
    elif verdict == "pending":
        if info.get("inconclusive"):
            prop_tasks.append({
                "task": f"补样本/补效应：当前 n={info.get('n_obs')} 未到 N*={info.get('Nstar')}；"
                        f"要么延长前向窗口，要么改用面板级检验（截面 IC / 增量 IC / top1 前瞻）",
                "kind": "evidence", "why": "未到 N* ⇒ 一切「有效/无效」结论都是无信息的",
                "priority": 1})
        for k in (failed + f_fail)[:3]:
            prop_tasks.append({"task": f"补证据以复核 {k}（缺什么补什么，不许换判据）",
                               "kind": "evidence",
                               "why": (gates.get(k) or fg.get(k) or {}).get("detail", ""), "priority": 1})
    else:  # invalid
        prop_tasks.append({"task": "修协议后重交（见 protocol_violations）；本轮不进台账统计",
                           "kind": "protocol_fix", "why": "协议违规轮不得计入试错次数",
                           "priority": 1, "blocking": True})

    # ★ 欠账置顶（P7：未响应的一律 blocking）
    for t in unresolved:
        t2 = dict(t)
        t2.update({"blocking": True, "why": (t.get("why") or "") + "【欠账·上轮未响应】",
                   "priority": 0})
        prop_tasks.insert(0, t2)

    # ★ 部署审计未过 ⇒ 先修阻断项，再谈上线（优先级高于一切新探索）
    if dinfo and dinfo.get("applicable") and not dinfo.get("allowed"):
        prop_tasks.append({
            "task": f"修掉上线前代码审计的阻断项（{', '.join(dinfo['blockers'])}）后**重跑 preflight_audit**，"
                    f"用新报告重开一轮；未过之前禁止接真实资金或影子账本",
            "kind": "preflight_fix",
            "why": "P0 / 指纹不一致 / 缺回滚点 = 代码层风险未清；研究结论再好也不能上线",
            "priority": 0, "blocking": True, "due_round": nid})

    # ★ P7b：裁判每轮必须派 ≥1 条代码优化任务（持续推进正方的代码优化工作）
    cop = (rnd.get("proponent", {}).get("code_opt_points") or [])
    open_bs = [p.get("id") for p in cop if p.get("id")]
    prop_tasks.append({
        "task": ("继续挖代码级硬编码盲区并提交 BS-x 清单：扫「写死在代码里、从未进过搜索自由度」的"
                 "档位/开关/候选集/权重（增量只能来自新自由度，换引擎无关）"
                 + (f"；本轮已交付 {open_bs} ⇒ 下一轮至少推进其中 1 条到实验结果" if open_bs else "")),
        "kind": "code_optimization",
        "why": "P12：纯搜索边际增量为零；调参是在旧自由度里再抽样，放开新自由度才是扩搜索空间",
        "priority": 1, "blocking": True, "due_round": nid})

    # 跨轮学习：同族 ≥2 次被驳 ⇒ 先证伪机制，禁止调参
    family = (rnd.get("candidate", {}) or {}).get("family", "")
    same_fail = [r for r in ledger
                 if ((r.get("candidate") or {}).get("family") == family and r.get("verdict") == "reject")]
    if family and (len(same_fail) >= 1 or verdict == "reject"):
        prop_tasks.append({
            "task": f"候选族「{family}」已累计被驳 {len(same_fail) + (verdict == 'reject')} 次 ⇒ "
                    f"下一轮只许做机制证伪实验，不许调参重测",
            "kind": "mechanism_falsification", "why": "防「换参数再试一次」的多重检验累积",
            "priority": 0})

    bo = (rnd.get("blueocean", {}) or {}).get("dims", []) or []
    if bo:
        prop_tasks.append({"task": f"评估蓝海维度（只判覆盖，不承诺有效）：{'; '.join(bo[:3])}",
                           "kind": "new_information", "why": "增量只能来自新信息源/新推断层",
                           "priority": 2})

    prop_tasks = _mk_tasks(f"T-{nid}", prop_tasks)

    # 裁判给反方的政委要求
    commissar_directives = [{
        "to": "adversary",
        "demand": "政委包四件套：target（文件:函数）+ action（可执行动作）+ expected_delta（预期读数）+ "
                  "rollback（回退口径）；风控侧须给出 risk_register（触发条件 + 处置动作 + 严重度）",
        "priority": 1}]
    if f_fail:
        commissar_directives.append({
            "to": "adversary",
            "demand": f"本轮前向体检未过 {f_fail} ⇒ 下一轮处方必须直接修这些缺口"
                      "（口径 / 样本 / 差异笔 / 单笔独扛）", "priority": 1})
    if verdict == "adopt":
        commissar_directives.append({
            "to": "adversary",
            "demand": "对已采纳候选给出 ≥2 条优化处方（不许只说「有风险」）", "priority": 2})

    # ★ 催办（coach）
    coach = {
        "nag_level": 0 if no_nag else nag,
        "nag_message": "",
        "must_do": [],
        "code_backlog_open": len(open_bs),
        "escalation": None,
    }
    if not no_nag:
        if nag == 0:
            coach["nag_message"] = "上一轮派工已响应 ✅ 本轮继续交付 ≥1 个代码级优化点（BS-x）。"
        elif nag == 1:
            coach["nag_message"] = (
                f"⚠️ 催办 L1：正方未响应上一轮派工（{len(unresolved)} 条）。本轮必须清偿欠账，"
                f"且必须把至少 1 条 BS-x 推到实验结果——只在参数上打转不算响应。")
        else:
            coach["nag_message"] = (
                f"🔴 催办 L{nag}：正方连续 {nag} 轮未响应裁判派工 ⇒ 停工清偿（不再受理新候选）。"
                f"先还清 {len(unresolved)} 条欠账 + 交付代码级优化点，再谈新方向。")
    coach["must_do"] = [{"task_id": t.get("id"), "task": t.get("task"), "kind": t.get("kind"),
                         "blocking": t.get("blocking")} for t in prop_tasks
                        if t.get("kind") in ("code_optimization", "mechanism_falsification")
                        or t.get("blocking")]
    hold = (not no_nag) and nag >= NAG_HOLD
    coach["escalation"] = "hold_new_candidates" if hold else None

    # 收敛四闸（P4）
    idle = sum(1 for r in reversed(ledger) if r.get("verdict") != "adopt") + (verdict != "adopt")
    cont, stop = True, None
    if (not no_nag) and nag >= NAG_STOP:
        cont, stop = False, (f"正方连续 {nag} 轮未响应裁判派工 ⇒ 作业面失效，停止迭代"
                             "（先修作业面，再谈策略）")
    if idle >= MAX_IDLE:
        cont, stop = False, f"连续 {idle} 轮无采纳 ⇒ 收敛，停止迭代（防多重检验空转）"
    if budget_left <= 0:
        cont, stop = False, "留出段预算用尽 ⇒ 停止（继续只能自娱自乐）"
    if ledger and round_id >= int((rnd.get("config", {}) or {}).get("max_rounds", 10 ** 9)):
        cont, stop = False, "达到 max_rounds"

    return {"continue": cont, "stop_reason": stop,
            "rounds_since_adopt": idle, "budget_left": budget_left,
            "hold_new_candidates": hold,
            "proponent_tasks": prop_tasks,
            "adversary_focus": adv_focus[:4],
            "commissar_directives": commissar_directives,
            "blueocean_dims": bo,
            "coach": coach}


# ---------------------------------------------------------------- 催办状态（读台账）
def nag_state(ledger: list, rnd: dict, no_nag: bool = False) -> tuple[int, list]:
    """算连续未响应轮数与欠账任务清单。规则：只要上一轮派了工而未回填 responded_tasks ⇒ 未响应。"""
    if no_nag:
        return 0, []
    prev = None
    for r in reversed(ledger):
        if (r.get("next_round") or {}).get("proponent_tasks"):
            prev = r
            break
    if not prev:
        return 0, []
    prev_tasks = [t for t in (prev["next_round"]["proponent_tasks"] or []) if t.get("blocking")]
    resp = set((rnd.get("proponent", {}) or {}).get("responded_tasks") or [])
    unresolved = [t for t in prev_tasks if t.get("id") and t["id"] not in resp]
    prev_nag = int(prev.get("nag_level", 0) or 0)
    nag = prev_nag + 1 if unresolved else 0
    return nag, unresolved


# ---------------------------------------------------------------- 主裁决
def would_adopt(gates: dict, fg: dict, info: dict) -> bool:
    """adopt 的必要条件（不含 deploy 维度与协议违规）。

    ★ 与 decide() **共用同一判定**，防止两处漂移（先例 P-13：两份同义实现 = 最危险的 bug）。
    ★ 关键语义：`pass is None`（不适用/未提供）**既不算过也不算不过** ——
      只有明确的 `False` 才阻断 adopt；而未经前向体检（fg 全 skip）则封顶 pending。
    """
    if not all(gates.get(k, {}).get("pass") is True for k in HARD_GATES):
        return False
    if any(v.get("pass") is False for k, v in gates.items() if k not in HARD_GATES):
        return False
    if any(v.get("pass") is False for v in fg.values()):
        return False
    if info.get("inconclusive"):
        return False
    if all(v.get("pass") is None for v in fg.values()):
        return False
    return True


def decide(gates: dict, fg: dict, viol: list, info: dict) -> tuple[str, str]:
    """返回 (verdict, reason_bucket)。"""
    if viol:
        return "invalid", "protocol_invalid"
    hard_pass = all(gates.get(k, {}).get("pass") is True for k in HARD_GATES)
    soft_fail = [k for k in gates if k not in HARD_GATES and gates[k].get("pass") is False]
    f_fail = [k for k, v in fg.items() if v.get("pass") is False]
    inconcl = bool(info.get("inconclusive"))

    if not hard_pass:
        # ★ 硬闸未过：但样本未到 N* ⇒ 只许「未检出」，绝不许判死
        if inconcl or info.get("coverage") == "none":
            return "pending", "not_detected"
        return "reject", "evidence_against"
    if f_fail or soft_fail:
        return "pending", "evidence_pending"
    if inconcl:
        return "pending", "not_detected"
    if all(v.get("pass") is None for v in fg.values()):
        return "pending", "evidence_pending"
    return "adopt", "effective"


def adjudicate(rnd: dict, ledger: list, no_nag: bool = False,
               criteria_snapshot: dict | None = None) -> dict:
    cand = rnd.get("candidate", {}) or {}
    m = rnd.get("metrics", {}) or {}
    cfg = {"metric_key": (rnd.get("config", {}) or {}).get("metric_key", "ann"),
           "risk_key": (rnd.get("config", {}) or {}).get("risk_key", "mdd")}

    gates = run_gates(cand, m, cfg)
    fg, info = forward_gates(rnd)
    dg, dinfo = deploy_gates(rnd)
    nag, unresolved = nag_state(ledger, rnd, no_nag)
    viol, warns = protocol_checks(rnd, gates, fg, info, nag)
    verdict, bucket = decide(gates, fg, viol, info)

    # ★ 部署维度：研究结论可以采纳 ≠ 这份代码可以接钱。审计未过 ⇒ adopt 降为 pending。
    if verdict == "adopt" and dinfo["applicable"] and not dinfo["allowed"]:
        verdict, bucket = "pending", "deploy_blocked"
        for k in dinfo["blockers"]:
            warns.append(f"D: 部署审计未过 {k}（{dg[k]['detail']}）")
    elif dinfo["applicable"] and not dinfo["allowed"]:
        for k in dinfo["blockers"]:
            warns.append(f"D: 部署审计未过 {k}（{dg[k]['detail']}）")

    # 同族被驳 ≥2 ⇒ 引擎强制降级（禁止在本轮重复调参）
    family = cand.get("family", "")
    same_fail = [r for r in ledger
                 if ((r.get("candidate") or {}).get("family") == family and r.get("verdict") == "reject")]
    if verdict in ("adopt", "pending") and family and same_fail:
        warns.append(f"P12w: 候选族「{family}」已有 {len(same_fail)} 轮被驳；同族重复提交需附「机制证伪实验」结果")

    budget = int((rnd.get("config", {}) or {}).get("budget_left", 0) or 0)
    out = {
        "schema": "qta-verdict/2.0", "version": VERSION,
        "round_id": rnd.get("round_id"), "candidate_id": cand.get("id"),
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "verdict": verdict,
        "reason_bucket": bucket,
        "gates": gates,
        "fwd_gates": fg,
        "deploy_gates": dg,
        "deploy": dinfo,
        "fwd_summary": {
            "coverage": info.get("coverage"),
            "Nstar": info.get("Nstar"), "n_obs": info.get("n_obs"),
            "mean": info.get("mean"), "sd": info.get("sd"),
            "inconclusive": info.get("inconclusive"),
            "selection_dof": info.get("selection_dof"),
            "single_trade_carried": info.get("single_trade_carried"),
            "diff_undecided": info.get("diff_undecided"),
            "notes": info.get("reasons", []),
        },
        "protocol_violations": viol,
        "protocol_warnings": warns,
        "criteria_sha": _fingerprint({"gates": list(gates.keys()) + list(fg.keys()) + list(dg.keys()),
                                      "MIN_N": MIN_N, "MIN_COV": MIN_COV,
                                      "MIN_REGION": MIN_REGION, "DSR_MIN": DSR_MIN,
                                      "MAX_IDLE": MAX_IDLE, "NAG_HOLD": NAG_HOLD,
                                      "NAG_STOP": NAG_STOP, "MIN_REPEAT_N": MIN_REPEAT_N,
                                      "MAX_REPORT_AGE_DAYS": MAX_REPORT_AGE_DAYS,
                                      "PBO_MAX": PBO_MAX, "SPA_ALPHA": SPA_ALPHA,
                                      "MAX_RHO_NOVELTY": MAX_RHO_NOVELTY,
                                      "IC_TMIN": IC_TMIN, "IC_TWEAK": IC_TWEAK,
                                      **(criteria_snapshot or {})}),
    }
    out["next_round"] = next_round_directives(rnd, verdict, gates, fg, info, ledger, budget,
                                              int(rnd.get("round_id", 0) or 0),
                                              nag, unresolved, no_nag, dinfo, dg)
    return out


# ---------------------------------------------------------------- 汇报（人类可读）
def explain(v: dict) -> str:
    w = {"adopt": "✅ 采纳", "pending": "⏸ 挂起", "reject": "❌ 驳回", "invalid": "🚫 违规作废"}
    L = [f"[round {v['round_id']}] {w.get(v['verdict'], v['verdict'])}  "
         f"({v['reason_bucket']})  candidate={v['candidate_id']}"]
    bad = [f"{k}({g['detail']})" for k, g in v["gates"].items() if not g["pass"]]
    fb = [f"{k}({g['detail']})" for k, g in v["fwd_gates"].items()
          if g.get("pass") is False]
    na = [k for k, g in v["fwd_gates"].items() if g.get("skipped") and g.get("not_applicable")]
    if bad:
        L.append("  准入未过：" + "；".join(bad))
    if fb:
        L.append("  前向未过：" + "；".join(fb))
    if na:
        L.append("  不适用：" + "；".join(na))
    fs = v["fwd_summary"]
    L.append(f"  前向体检：coverage={fs['coverage']} N*={_fmt(fs['Nstar'])} n={_fmt(fs['n_obs'])} "
             f"未检出={fs['inconclusive']} 自由度={fs['selection_dof']} "
             f"单笔独扛={fs['single_trade_carried']}")
    for n in fs["notes"]:
        L.append(f"    · {n}")
    dep = v.get("deploy") or {}
    if dep.get("applicable"):
        dgv = v.get("deploy_gates") or {}
        state = "✅ 允许上线" if dep.get("allowed") else f"⛔ 禁止上线（{','.join(dep['blockers'])}）"
        L.append(f"  部署审计（target={dep.get('target')}）：{state}　"
                 f"裁判重算指纹={(dep.get('fingerprint_now') or 'NA')[:16]}… / "
                 f"报告={(dep.get('fingerprint_report') or 'NA')[:16]}…")
        for k in dep.get("blockers", []):
            L.append(f"    ⛔ {k}: {dgv.get(k, {}).get('detail', '')}")
    for s in v["protocol_violations"]:
        L.append(f"  ⛔ {s}")
    for s in v["protocol_warnings"]:
        L.append(f"  ⚠️ {s}")
    nr = v["next_round"]
    c = nr["coach"]
    L.append(f"  下一轮：continue={nr['continue']} 停工清偿={nr['hold_new_candidates']} "
             f"nag_level={c['nag_level']} rounds_since_adopt={nr['rounds_since_adopt']}")
    if c["nag_message"]:
        L.append(f"  催办：{c['nag_message']}")
    for t in nr["proponent_tasks"]:
        L.append(f"    → [{t['id']}/{t['kind']}]{'★' if t.get('blocking') else ' '} {t['task']}")
    for d in nr["commissar_directives"]:
        L.append(f"    政委指令 → {d['to']}：{d['demand']}")
    if nr["stop_reason"]:
        L.append(f"  🛑 收敛：{nr['stop_reason']}")
    return "\n".join(L)


# ---------------------------------------------------------------- selftest
def _good_round() -> dict:
    return {
        "round_id": 1,
        "candidate": {"id": "BS-1", "name": "因子连续权重", "kind": "k", "family": "fam",
                      "uses": ["ret20"], "change": {"is_change": True,
                                                     "target": "engine.py:weight()"}},
        "metrics": {
            "baseline": {"ann": 0.10, "mdd": -0.30},
            "candidate": {"ann": 0.30, "mdd": -0.20, "n": 500, "sharpe": 2.0, "skew": 0.0, "kurt": 3.0},
            "context": {"anchors_ok": True, "coverage": {"ret20": 95.0}, "region": {"expanding": 6},
                        "removed_by_year": {"k": {"2023": 10, "2024": 10}},
                        "base_by_year": {"2023": 10, "2024": 10},
                        "no_lookahead": {"k": {"ann": 0.25}}, "trials": 3, "ppy": 252,
                        "pbo": 0.31, "spa_p": 0.012,
                        "novelty": {"max_rho": 0.22, "against": ["BS-3"]},
                        "panel_ic": {"ic": 0.031, "t_adj": 3.1, "ir": 0.62, "n_days": 322}},
        },
        "fwd": {"coverage": "full", "panel_md5": "deadbeef",
                "caliber": {"adjust": "后复权", "asof": "D−1收盘", "cost": "单边3bp", "universe": "29只ETF"},
                "n_obs": 63, "mean": 0.0318, "sd": 0.06,
                "per_day_max_candidates": 5, "rank_key_source": "train", "is_change": True,
                "diff_trades": {"added": {"n": 22, "mean": 0.0318, "ci": [0.005, 0.050], "p": 0.02},
                                "removed": {"n": 3, "mean": -0.02, "ci": [-0.05, -0.005], "p": 0.03}},
                "loo": {"total": 527.6, "best_trade": 45.2, "ex_best": 120.0}},
        "proponent": {"claims": [{"claim": "机制成立", "evidence": "E1"}],
                      "failure_conditions": ["若 G6 <4 格 ⇒ 承认切点挑选"],
                      "code_opt_points": [{"id": "BS-7", "locus": "engine.py:weight()",
                                           "why_hardcoded": "权重只有两档"}]},
        "adversary": {"objections": [{"objection": "n 不足", "prereg": "若 n<100 则不成立"}],
                      "directions": [{"direction": "扩样本", "mechanism": "m", "prereg": "p<0.05",
                                      "cost": "low", "priority": 1}],
                      "commissar_pack": {
                          "risk_register": [{"risk": "样本集中", "trigger": "单年占比>50%",
                                             "action": "分年拆解", "severity": "high"}],
                          "opt_prescriptions": [{"target": "engine.py:weight()",
                                                 "action": "两档权重→连续风险预算",
                                                 "mechanism": "风险预算优于打分加权",
                                                 "expected_delta": "Calmar +0.15",
                                                 "cost": "low", "priority": 1,
                                                 "rollback": "改回 w∈{0.5,1.0}"}]}},
        "blueocean": {"dims": ["ETF折溢价/份额流"]},
        "config": {"metric_key": "ann", "risk_key": "mdd", "budget_left": 5, "max_rounds": 12},
    }


def selftest() -> int:
    rng = random.Random(20261005)
    fails: list[str] = []

    def chk(name, cond):
        print(f"  {'✅' if cond else '❌'} {name}")
        if not cond:
            fails.append(name)

    print(f"qta_loop selftest  v{VERSION}（三方闭环 + 前向体检 + 催办）")

    # 1) 白噪声上不乱判
    trials, n_obs, ppy = 40, 500, 252
    best = 0.0
    for _ in range(trials):
        r = [rng.gauss(0.0, 0.01) for _ in range(n_obs)]
        mu = sum(r) / n_obs
        sd = (sum((x - mu) ** 2 for x in r) / (n_obs - 1)) ** 0.5
        best = max(best, mu / sd * math.sqrt(ppy))
    sr0 = expected_max_sharpe(trials, n_obs, ppy)
    assert sr0 is not None, "trials=40/n=500 应可算 SR0"
    chk(f"噪声最优年化Sharpe={best:.2f} vs SR0={sr0:.2f} ⇒ DSR={dsr_prob(best, sr0, n_obs, ppy):.3f} < 0.95",
        dsr_prob(best, sr0, n_obs, ppy) < DSR_MIN)

    # 2) 真效应 + 完整前向体检 ⇒ adopt
    gr = _good_round()
    v = adjudicate(gr, [])
    chk(f"真效应 + 前向体检齐 ⇒ adopt（got={v['verdict']}）", v["verdict"] == "adopt")
    chk("adopt 也必须带下一轮指令（含代码优化任务）",
        len(v["next_round"]["proponent_tasks"]) >= 1 and
        any(t["kind"] == "code_optimization" for t in v["next_round"]["proponent_tasks"]))
    chk("N* 计算正确（μ=3.18% σ=6% ⇒ N*=15）", v["fwd_summary"]["Nstar"] == 15)

    # 3) P1：驳回但反方无方向 ⇒ invalid
    bad = json.loads(json.dumps(gr))
    bad["metrics"]["candidate"]["ann"] = 0.05
    bad["adversary"]["directions"] = []
    bad["adversary"]["commissar_pack"]["opt_prescriptions"] = []
    chk(f"P1 驳回且反方无方向 ⇒ invalid（got={adjudicate(bad, [])['verdict']}）",
        adjudicate(bad, [])["verdict"] == "invalid")

    # 4) P6 ★政委契约：有方向但无优化处方 ⇒ invalid
    bad2 = json.loads(json.dumps(bad))
    bad2["adversary"]["directions"] = [{"direction": "扩样本", "mechanism": "m", "prereg": "p<0.05",
                                        "cost": "low", "priority": 1}]
    chk(f"P6 有方向但政委无优化处方 ⇒ invalid（got={adjudicate(bad2, [])['verdict']}）",
        adjudicate(bad2, [])["verdict"] == "invalid")

    # 5) P6：处方缺要素 ⇒ invalid
    bad3 = json.loads(json.dumps(bad2))
    bad3["adversary"]["commissar_pack"]["opt_prescriptions"] = [
        {"target": "engine.py:weight()", "action": "改连续权重"}]  # 缺 expected_delta / rollback
    vp6 = adjudicate(bad3, [])
    chk(f"P6 处方缺 expected_delta/rollback ⇒ invalid（got={vp6['verdict']}）",
        vp6["verdict"] == "invalid" and any("P6" in s for s in vp6["protocol_violations"]))

    # 6) 驳回 + 政委齐 ⇒ reject，且下一轮派工来自处方方向
    ok = json.loads(json.dumps(bad2))
    ok["adversary"]["commissar_pack"] = {
        "risk_register": [{"risk": "样本集中", "trigger": "单年占比>50%",
                           "action": "分年拆解", "severity": "high"}],
        "opt_prescriptions": [{"target": "engine.py:weight()", "action": "两档权重→连续风险预算",
                               "mechanism": "风险预算优于打分加权", "expected_delta": "Calmar +0.15",
                               "cost": "low", "priority": 1, "rollback": "改回 w∈{0.5,1.0}"}],
    }
    v3 = adjudicate(ok, [])
    chk(f"驳回 + 政委齐 ⇒ reject（got={v3['verdict']}）", v3["verdict"] == "reject")
    chk("驳回 ⇒ 下一轮必带政委指令", len(v3["next_round"]["commissar_directives"]) >= 1)

    # 7) ★ 核心纪律：n 未到 N* 且硬闸不过 ⇒ pending（未检出），不许判 reject
    small = json.loads(json.dumps(ok))
    small["metrics"]["candidate"].update({"ann": 0.05, "n": 12})
    small["fwd"].update({"n_obs": 12, "mean": 0.005, "sd": 0.08})   # N* = 1024 ≫ 12
    v7 = adjudicate(small, [])
    chk(f"★ 样本未到 N* ⇒ pending/not_detected 而非 reject（got={v7['verdict']}/{v7['reason_bucket']}）",
        v7["verdict"] == "pending" and v7["reason_bucket"] == "not_detected")

    # 8) 样本已到 N* 且硬闸不过 ⇒ 允许判死
    big = json.loads(json.dumps(ok))
    big["metrics"]["candidate"].update({"ann": 0.05, "n": 900})
    big["fwd"].update({"n_obs": 900, "mean": 0.02, "sd": 0.08})     # N* = 64 ≤ 900 ⇒ 样本已足
    v8 = adjudicate(big, [])
    chk(f"样本已到 N* 且硬闸不过 ⇒ reject（got={v8['verdict']}/{v8['reason_bucket']}）",
        v8["verdict"] == "reject" and v8["reason_bucket"] == "evidence_against")

    # 9) F5 差异笔 CI 含 0 ⇒ 不得 adopt
    f5 = json.loads(json.dumps(gr))
    f5["fwd"]["diff_trades"]["added"]["ci"] = [-0.006, 0.05]
    v9 = adjudicate(f5, [])
    chk(f"F5 差异笔 CI 含 0 ⇒ 降 pending（got={v9['verdict']}）", v9["verdict"] == "pending")
    chk("F5 命中被写进 fwd_summary", v9["fwd_summary"]["diff_undecided"] == ["added"])

    # 10) F6 剔最好一笔后翻负 ⇒ 不得 adopt
    f6 = json.loads(json.dumps(gr))
    f6["fwd"]["loo"]["ex_best"] = -8.5
    v10 = adjudicate(f6, [])
    chk(f"F6 单笔独扛 ⇒ 降 pending（got={v10['verdict']}）", v10["verdict"] == "pending")
    chk("单笔独扛被标记", v10["fwd_summary"]["single_trade_carried"] is True)

    # 11) P8 前向键作弊（留出段/全期）⇒ invalid
    f3 = json.loads(json.dumps(gr))
    f3["fwd"]["rank_key_source"] = "holdout"
    v11 = adjudicate(f3, [])
    chk(f"P8 选优键用留出段 ⇒ invalid（got={v11['verdict']}）", v11["verdict"] == "invalid")

    # 12) F2 选择自由度 = 1 ⇒ 标记 not_applicable + 写明排序类优化无效
    f2 = json.loads(json.dumps(gr))
    f2["fwd"]["per_day_max_candidates"] = 1
    v12 = adjudicate(f2, [])
    chk("F2 零自由度 ⇒ 标 not_applicable 且给出「排序类优化定义上无效」",
        v12["fwd_gates"]["F2_choice_freedom"].get("not_applicable") is True and
        v12["fwd_summary"]["selection_dof"] == "none" and
        any("定义上无效" in s for s in v12["fwd_summary"]["notes"]))

    # 13) 未做前向体检 ⇒ 封顶 pending
    nf = json.loads(json.dumps(gr))
    nf.pop("fwd")
    v13 = adjudicate(nf, [])
    chk(f"未做前向体检 ⇒ 封顶 pending（got={v13['verdict']}）", v13["verdict"] == "pending")

    # 14) ★催办：上一轮派工未响应 ⇒ nag=1；再一轮 ⇒ nag=2 且停工清偿
    led1 = [{"candidate": {"family": "f"}, "verdict": "pending", "nag_level": 0,
             "next_round": {"proponent_tasks": [{"id": "T-2-1", "kind": "code_optimization",
                                                 "blocking": True, "task": "扫硬编码"}]}}]
    r_no = json.loads(json.dumps(gr)); r_no["proponent"].pop("responded_tasks", None)
    v14a = adjudicate(r_no, led1)
    chk(f"催办 L1：未响应 ⇒ nag_level=1（got={v14a['next_round']['coach']['nag_level']}）",
        v14a["next_round"]["coach"]["nag_level"] == 1)
    chk("催办 L1：欠账任务被置顶为 blocking",
        v14a["next_round"]["proponent_tasks"][0]["id"] == "T-2-1" and
        v14a["next_round"]["proponent_tasks"][0]["blocking"] is True)
    led2 = [{"candidate": {"family": "f"}, "verdict": "pending", "nag_level": 1,
             "next_round": {"proponent_tasks": [{"id": "T-2-1", "kind": "code_optimization",
                                                 "blocking": True, "task": "扫硬编码"}]}}]
    v14b = adjudicate(r_no, led2)
    chk(f"催办 L2：停工清偿（hold_new_candidates=True，nag={v14b['next_round']['coach']['nag_level']}）",
        v14b["next_round"]["hold_new_candidates"] is True and
        v14b["next_round"]["coach"]["escalation"] == "hold_new_candidates")
    # 响应即复位
    r_yes = json.loads(json.dumps(gr)); r_yes["proponent"]["responded_tasks"] = ["T-2-1"]
    v14c = adjudicate(r_yes, led2)
    chk(f"催办复位：已响应 ⇒ nag_level 归零（got={v14c['next_round']['coach']['nag_level']}）",
        v14c["next_round"]["coach"]["nag_level"] == 0)

    # 15) 催办 L3 ⇒ 收敛停止
    led3 = [{"candidate": {"family": "f"}, "verdict": "pending", "nag_level": 2,
             "next_round": {"proponent_tasks": [{"id": "T-2-1", "kind": "code_optimization",
                                                 "blocking": True, "task": "扫硬编码"}]}}]
    v15 = adjudicate(r_no, led3)
    chk(f"催办 L3 ⇒ 收敛停止（reason={v15['next_round']['stop_reason']}）",
        v15["next_round"]["continue"] is False and v15["next_round"]["stop_reason"] is not None)

    # 16) 收敛闸：连续 MAX_IDLE 轮无采纳
    led4 = [{"verdict": "reject"}] * (MAX_IDLE - 1)
    v16 = adjudicate(ok, led4)
    chk(f"台账{MAX_IDLE - 1}轮无采纳 + 本轮 reject ⇒ 停止", v16["next_round"]["continue"] is False)

    # 17) 判据指纹可复现
    chk("判据指纹可复现", v3["criteria_sha"] == adjudicate(ok, [])["criteria_sha"])

    # 18) nan 不得被当达标（G2 用 nan 必须判不过）
    nn = json.loads(json.dumps(gr))
    nn["metrics"]["candidate"]["ann"] = float("nan")
    v18 = adjudicate(nn, [])
    chk("nan 主指标不得被当成达标（G2 必不过）", v18["gates"]["G2_metric"]["pass"] is False)

    # 19–23) ★ 部署审计（D0–D4）：上线/实盘/影子盘前的代码 bug 闸门
    chk("未声明 deploy.target ⇒ 不影响判决（仍 adopt）", adjudicate(gr, [])["verdict"] == "adopt")
    if PFA is None:
        print("  ⚠️ 审计器 preflight_audit 不可用 ⇒ 跳过 D 组用例")
        fails.append("D 组用例被跳过（审计器不可用）")
    else:
        with tempfile.TemporaryDirectory() as td:
            code = Path(td) / "live_legacy.py"
            code.write_text("def run():\n    return 1\n", encoding="utf-8")
            rep_path = Path(td) / "preflight_report.json"
            # 用审计器本体生成报告 ⇒ 同时验证「裁判与审计器的指纹口径一致」
            rep_ok = PFA.audit([str(code)], mode="live", rollback_point="backup dir A")
            rep_path.write_text(json.dumps(rep_ok, ensure_ascii=False), encoding="utf-8")

            dr = json.loads(json.dumps(gr))
            dr["deploy"] = {"target": "live", "code_paths": [str(code)],
                            "preflight": {"path": str(rep_path)},
                            "rollback_ready": True, "rollback_point": "backup dir A"}
            v19 = adjudicate(dr, [])
            chk(f"D 组全过 ⇒ 仍 adopt 且 deploy.allowed（got={v19['verdict']}）",
                v19["verdict"] == "adopt" and v19["deploy"]["allowed"] is True)

            dr2 = json.loads(json.dumps(dr))
            dr2["deploy"]["preflight"] = {"path": str(Path(td) / "nope.json")}
            v20 = adjudicate(dr2, [])
            chk(f"缺审计报告 ⇒ pending/deploy_blocked（got={v20['verdict']}/{v20['reason_bucket']}）",
                v20["verdict"] == "pending" and v20["reason_bucket"] == "deploy_blocked")
            chk("缺报告时派了 preflight_fix 任务",
                any(t["kind"] == "preflight_fix" for t in v20["next_round"]["proponent_tasks"]))

            code.write_text("def run():\n    return 2   # 审完又改\n", encoding="utf-8")
            v21 = adjudicate(dr, [])
            chk(f"★ 审完又改（指纹不一致）⇒ 阻断（got={v21['verdict']}）",
                v21["verdict"] == "pending" and
                "D1_code_fingerprint" in v21["deploy"]["blockers"])

            bad_code = Path(td) / "bad_live.py"
            # 用 fixtures 里的坏样本（copy 而非内嵌字符串：避免审计器扫到自己的测试样本）
            shutil.copy2(Path(__file__).resolve().parent / "fixtures" / "selftest_bad.py", bad_code)
            rep_bad = PFA.audit([str(bad_code)], mode="live", rollback_point="tag v1")
            rep_bad_path = Path(td) / "bad_report.json"
            rep_bad_path.write_text(json.dumps(rep_bad, ensure_ascii=False), encoding="utf-8")
            dr3 = json.loads(json.dumps(gr))
            dr3["deploy"] = {"target": "live", "code_paths": [str(bad_code)],
                             "preflight": {"path": str(rep_bad_path)},
                             "rollback_ready": True, "rollback_point": "tag v1"}
            v22 = adjudicate(dr3, [])
            chk(f"P0 存在 ⇒ 阻断（got={v22['verdict']}，报告 p0={rep_bad['p0_count']}）",
                v22["verdict"] == "pending" and "D2_no_blocker" in v22["deploy"]["blockers"])

            code.write_text("def run():\n    return 1\n", encoding="utf-8")   # 复原，避免上一条污染
            dr4 = json.loads(json.dumps(dr))
            dr4["deploy"]["rollback_ready"] = False
            dr4["deploy"]["rollback_point"] = None
            v23 = adjudicate(dr4, [])
            chk(f"缺回滚点 ⇒ 仅 D3 阻断（blockers={v23['deploy']['blockers']}）",
                v23["deploy"]["blockers"] == ["D3_rollback_ready"])

    # 24–29) ★ v2.2 四项度量升级（A1 新增量 / A3 PBO·SPA / A6 面板 IC / A2 claim↔diff）
    chk("新增量 · PBO · SPA · 面板 IC 全过 ⇒ 仍 adopt（未误伤）",
        adjudicate(gr, [])["verdict"] == "adopt")

    g10 = json.loads(json.dumps(gr))
    g10["metrics"]["context"]["novelty"] = {"max_rho": 0.78, "against": ["BS-3"]}
    v10 = adjudicate(g10, [])
    chk(f"G10 与已采纳结论 ρ=0.78>0.5 ⇒ pending（非新增量）（got={v10['verdict']}）",
        v10["verdict"] == "pending" and v10["gates"]["G10_novelty"]["pass"] is False)

    g11 = json.loads(json.dumps(gr))
    g11["metrics"]["context"]["panel_ic"] = {"ic": 0.004, "t_adj": 0.6, "n_days": 322}
    v11b = adjudicate(g11, [])
    chk(f"G11 截面 IC t_adj=0.6<1 ⇒ pending（不可判定）（got={v11b['verdict']}）",
        v11b["verdict"] == "pending" and v11b["gates"]["G11_panel_ic"]["pass"] is False)

    g9b = json.loads(json.dumps(gr))
    g9b["metrics"]["context"]["pbo"] = 0.72
    v9b = adjudicate(g9b, [])
    chk(f"G9b PBO=0.72>0.5 ⇒ pending/evidence_pending（软闸，不判死）（got={v9b['verdict']}/{v9b['reason_bucket']}）",
        v9b["verdict"] == "pending" and v9b["reason_bucket"] == "evidence_pending")

    g9c = json.loads(json.dumps(gr))
    g9c["metrics"]["context"]["spa_p"] = 0.31
    chk(f"G9c SPA p=0.31>0.05 ⇒ pending（got={adjudicate(g9c, [])['verdict']}）",
        adjudicate(g9c, [])["verdict"] == "pending")

    p9ok = json.loads(json.dumps(gr))
    p9ok["candidate"]["change"] = {"is_change": True, "target": "engine.py:weight()",
                                   "actual_files": ["engine.py", "risk.py"]}
    chk("P9 target 与实际改动文件一致 ⇒ 不违规",
        adjudicate(p9ok, [])["verdict"] == "adopt")

    p9bad = json.loads(json.dumps(gr))
    p9bad["candidate"]["change"] = {"is_change": True, "target": "engine.py:weight()",
                                    "actual_files": ["risk.py"]}
    vp9 = adjudicate(p9bad, [])
    chk(f"★ P9 声明改 engine.py 实际只改 risk.py ⇒ invalid（got={vp9['verdict']}）",
        vp9["verdict"] == "invalid" and any("P9" in s for s in vp9["protocol_violations"]))

    print("  自检结论：", "✅ 通过" if not fails else f"❌ 未通过 {fails}")
    return 0 if not fails else 1


# ---------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="量化交易Agent策略框架 v2.0 · 三方闭环 + 前向体检 + 催办引擎")
    ap.add_argument("--round", help="本轮输入 JSON（candidate/metrics/fwd/proponent/adversary/config）")
    ap.add_argument("--ledger", default="qta_ledger.jsonl", help="跨轮台账 JSONL")
    ap.add_argument("--out", help="判决书输出路径（默认 stdout）")
    ap.add_argument("--selftest", action="store_true", help="自检（必跑；不过则结论全部作废）")
    ap.add_argument("--no-nag", action="store_true", help="关闭催办（仅调试用；会破坏 P7 契约）")
    ap.add_argument("--explain", action="store_true", help="输出人类可读摘要")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.round:
        ap.error("--round 或 --selftest 必填其一")

    rnd = load_json(args.round)
    ledger = load_ledger(args.ledger)
    verdict = adjudicate(rnd, ledger, no_nag=args.no_nag)

    if args.explain:
        print(explain(verdict))

    txt = json.dumps(verdict, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(txt, encoding="utf-8")
        nr = verdict["next_round"]
        if verdict["verdict"] == "invalid":
            # ★ 协议违规轮不进台账：否则会污染 rounds_since_adopt / 同族计数 / 催办链
            print(f"verdict → {args.out}  (verdict=invalid ⇒ 本轮不进台账，修协议后重交)")
            return 0
        with open(args.ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "round_id": rnd.get("round_id"),
                "candidate": rnd.get("candidate"),
                "verdict": verdict["verdict"],
                "reason_bucket": verdict["reason_bucket"],
                "failed_gates": [k for k, g in verdict["gates"].items() if not g["pass"]],
                "failed_fwd": [k for k, g in verdict["fwd_gates"].items() if g.get("pass") is False],
                "fwd_summary": verdict["fwd_summary"],
                "nag_level": nr["coach"]["nag_level"],
                "next_round": {"proponent_tasks": nr["proponent_tasks"]},
                "ts": verdict["ts"],
            }, ensure_ascii=False) + "\n")
        print(f"verdict → {args.out}  (verdict={verdict['verdict']}, bucket={verdict['reason_bucket']}, "
              f"continue={nr['continue']}, nag={nr['coach']['nag_level']})")
    elif not args.explain:
        print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
