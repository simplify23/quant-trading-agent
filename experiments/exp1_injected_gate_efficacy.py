#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exp1_injected_gate_efficacy.py —— 注入式实验：Triad 准入闸门到底有没有用？

────────────────────────────────────────────────────────────────────────────
为什么是这个设计（而不是"拿三条腿跑个对照"）
────────────────────────────────────────────────────────────────────────────
功效前置检查（见运行输出）已经算清：本机 ETF 面板训练段只有 322 个交易日，
一条最短持有 30 日的腿最多 10~13 笔，而 N* 中位在 300 笔量级 ⇒ **组合级对照不可判定**
（要靠组合级分出效应需要约 37 年数据）。

⇒ 改用**注入式（synthetic + 已知真值）**：在面板里埋入已知数量的真信号因子，
  真值已知 ⇒ 不受样本量限制，可直接度量 **假发现率 / 命中率 / 弃权率**。

────────────────────────────────────────────────────────────────────────────
三组对照（★ 只差"准入规则"，其余全同：同一批候选、同一段训练数据）
────────────────────────────────────────────────────────────────────────────
  A 纯搜索      取训练段 Sharpe 最高的因子（必然选 1 个）
  B Triad 闸门  逐因子过判据，取通过者中训练段 Sharpe 最高的（**允许弃权**）
  C 单阈值加严  训练段 Sharpe > θ，θ 标定到与 B 组相近的通过率
                ⇒ 用来回答那个最要命的反问：「闸门有效，还是只是更保守？」

★ C 组是这套设计的关键。没有 C 组，任何"闸门更好"的结论都可能只是"选得更少"。

────────────────────────────────────────────────────────────────────────────
B 组用的四条判据（全部可在合成面板上实现，且逐条对应 Triad 的判据）
────────────────────────────────────────────────────────────────────────────
  G6 平台    训练段分 4 个子段，≥3 段为正（对应"参数平台：要连续正向区间"）
  F6 留一笔  剔掉最好的 5 天后，训练段均值仍 > 0（对应"单笔独扛"检查）
  F1 N*      样本量必须 ≥ 该因子自身的 N* = ⌈(2σ/μ)²⌉（未到 ⇒ 判"未检出"）
  G9a DSR    试错 40 次折减后仍 ≥ 0.95（对应多重检验校正）

用法：
  python3 exp1_injected_gate_efficacy.py [--reps 200] [--out .]
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np

VERSION = "1.0.0"
PPY = 252
N_CAND = 40          # 候选因子数
K_TRUE = 5           # 其中真信号数
T_TOTAL = 750        # 总天数（≈ 本机面板 746 日）
T_TRAIN = 322        # 训练段（≈ 本机 ETF 面板 2023-09~2024-12）
SIGMA = 0.01         # 日波动
TRIALS = 40          # 声称的试错次数（用于 DSR）
ALPHAS = [0.0004, 0.0008, 0.0016, 0.0032]   # 日均 alpha 扫描（弱 → 强）
# ★ C 组必须能与 B 组区分才有意义。原设计用"Sharpe 分位阈值"失败：
#   通过者集合总是包含训练段第一名 ⇒ "取通过者中最高"恒等于 A 组（实测 FDR 逐档相同）。
#   改用【随机过滤】对照：在同样的保留比例下，B 组用判据筛、C 组随机筛。
#   若 B 组优于 C 组 ⇒ 判据携带信息，而不是"只是更保守"。
C_FILTER_KEEP = [0.02, 0.05, 0.10, 0.20, 0.40, 0.60, 1.00]


# ---------------------------------------------------------------- 统计工具
def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p):
    lo, hi = -8.0, 8.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if _norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def sharpe_daily(x: np.ndarray) -> float:
    sd = x.std(ddof=1)
    return float(x.mean() / sd) if sd > 0 else 0.0


def dsr_pass(col: np.ndarray, trials: int = TRIALS, min_dsr: float = 0.95) -> bool:
    """G9a：试错 trials 次折减后，DSR ≥ min_dsr。"""
    T = col.size
    if trials < 2 or T < 10:
        return False
    mu, sd = col.mean(), col.std(ddof=1)
    if sd <= 0 or mu <= 0:
        return False
    sr_ann = mu / sd * math.sqrt(PPY)
    g = 0.5772156649
    z1, z2 = _norm_ppf(1 - 1 / trials), _norm_ppf(1 - 1 / (trials * math.e))
    sr0_ann = ((1 - g) * z1 + g * z2) / math.sqrt(T - 1) * math.sqrt(PPY)
    sr_po, sr0_po = sr_ann / math.sqrt(PPY), sr0_ann / math.sqrt(PPY)
    return _norm_cdf((sr_po - sr0_po) * math.sqrt(T - 1)) >= min_dsr


def gates_pass(col: np.ndarray, use_nstar: bool = True,
               benchmark: np.ndarray | None = None) -> tuple[bool, list[str]]:
    """B 组的四条判据。返回 (是否通过, 未过的判据名)。

    ★ benchmark：给了就一律在【超额收益 col − benchmark】上判 —— 这是必须的：
      策略收益 =「市场 + alpha」时，市场波动会放大总波动，
      用绝对收益算 DSR/N*/分段稳定性会把【所有】候选都拦掉（实测连 t=4.0 的真信号也 100% 被拦）。

    use_nstar=False 用于★消融：去掉 F1（样本量 N*）这一条，看它的边际贡献。
    """
    col = col if benchmark is None else (col - benchmark)
    T = col.size
    failed = []

    segs = np.array_split(col, 4)
    if sum(1 for s in segs if s.mean() > 0) < 3:
        failed.append("G6_plateau")

    if np.delete(col, np.argsort(col)[-5:]).mean() <= 0:
        failed.append("F6_loo")

    mu, sd = col.mean(), col.std(ddof=1)
    if mu <= 0 or sd <= 0:
        failed.append("F1_nstar")
    elif use_nstar:
        n_star = math.ceil((2 * sd / mu) ** 2)
        if T < n_star:
            failed.append("F1_nstar")

    if not dsr_pass(col):
        failed.append("G9a_DSR")

    return (len(failed) == 0), failed


# ---------------------------------------------------------------- 单次实验
def one_run(rng: np.random.Generator, alpha: float) -> dict:
    truth = np.zeros(N_CAND, dtype=bool)
    truth[rng.choice(N_CAND, K_TRUE, replace=False)] = True
    R = rng.normal(0.0, SIGMA, size=(T_TOTAL, N_CAND)).astype(float)
    R[:, truth] += alpha

    tr, ho = R[:T_TRAIN], R[T_TRAIN:]
    sr_tr = np.array([sharpe_daily(tr[:, j]) for j in range(N_CAND)])
    sr_ho = np.array([sharpe_daily(ho[:, j]) for j in range(N_CAND)])

    out: dict = {"n_true": int(truth.sum())}

    # ---- A 纯搜索：训练段 Sharpe 最高 ----
    j_a = int(np.argmax(sr_tr))
    out["A"] = {"picked": j_a, "is_true": bool(truth[j_a]), "ho_sharpe": float(sr_ho[j_a]),
                "n_passed": 1}   # A 组无闸门 ⇒ 必然"通过"1 个

    # ---- B Triad 闸门：过判据者中取训练段 Sharpe 最高；无通过者则弃权 ----
    for tag, use_ns in (("B_triad_gates", True), ("B_noNstar", False)):
        passed = [j for j in range(N_CAND) if gates_pass(tr[:, j], use_ns)[0]]
        if passed:
            j_b = max(passed, key=lambda j: sr_tr[j])
            out[tag] = {"picked": j_b, "is_true": bool(truth[j_b]),
                        "ho_sharpe": float(sr_ho[j_b]), "n_passed": len(passed)}
        else:
            out[tag] = {"picked": None, "is_true": None, "ho_sharpe": None, "n_passed": 0}

    # ---- C 随机采纳对照：以概率 keep 采纳训练段第一名，否则弃权 ----
    #      ★ 这才是与 B 组可比的对照：两组的【采纳率】相同，只差"凭什么采纳"。
    #        （前两版设计都失败：① 分位阈值 ⇒ 通过集合必含第一名，退化成 A 组；
    #          ② 保留 k 个再取最高 ⇒ 必选 1 个，pick_rate 恒为 1，无法对齐保守度。）
    out["C"] = {}
    for keep in C_FILTER_KEEP:
        key = f"k{int(keep*100):03d}"
        if rng.random() < keep:
            out["C"][key] = {"picked": j_a, "is_true": bool(truth[j_a]),
                             "ho_sharpe": float(sr_ho[j_a]), "n_passed": 1}
        else:
            out["C"][key] = {"picked": None, "is_true": None,
                             "ho_sharpe": None, "n_passed": 0}
    return out


# ---------------------------------------------------------------- 汇总
def summarize(runs: list[dict], key_path: tuple) -> dict:
    """key_path 例如 ("A",) 或 ("B",) 或 ("C","p05")。"""
    recs = []
    for r in runs:
        d = r
        for k in key_path:
            d = d[k]
        recs.append(d)
    picked = [x for x in recs if x["picked"] is not None]
    n = len(recs)
    n_pick = len(picked)
    hits = sum(1 for x in picked if x["is_true"])
    return {
        "n_runs": n,
        "abstain_rate": (n - n_pick) / n,
        "pick_rate": n_pick / n,
        "hit_rate": hits / n,                                  # 全样本口径：选中真信号
        "fdr_on_picked": (n_pick - hits) / n_pick if n_pick else None,   # 选中者中噪声占比
        "precision": hits / n_pick if n_pick else None,
        "ho_sharpe_mean": float(np.mean([x["ho_sharpe"] for x in picked])) if picked else None,
        "n_passed_mean": float(np.mean([x["n_passed"] for x in recs])),
    }


def main() -> int:
    global N_CAND, K_TRUE      # ★ 必须在任何 N_CAND/K_TRUE 引用之前声明
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument("--n-cand", type=int, default=N_CAND, help="候选因子数（敏感性扫描用）")
    ap.add_argument("--k-true", type=int, default=K_TRUE, help="真信号数（敏感性扫描用）")
    ap.add_argument("--alphas", type=float, nargs="*", default=ALPHAS)
    ap.add_argument("--seed", type=int, default=20261006)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent))
    args = ap.parse_args()

    N_CAND, K_TRUE = args.n_cand, args.k_true
    alphas = list(args.alphas)

    t0 = time.time()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"exp1 注入式闸门有效性  v{VERSION}")
    print(f"  候选 {N_CAND} 个（真信号 {K_TRUE} 个，占 {K_TRUE/N_CAND:.1%}）｜"
          f"T={T_TOTAL}（训练 {T_TRAIN}）｜重复 {args.reps} 次｜α ∈ {alphas}")

    results = {}
    for alpha in alphas:
        rng = np.random.default_rng(args.seed + int(alpha * 1e6))
        runs = [one_run(rng, alpha) for _ in range(args.reps)]
        block = {
            "alpha": alpha,
            "annualized_alpha": alpha * PPY,
            "signal_to_noise_daily": alpha / SIGMA,
            "train_t_of_true": alpha / SIGMA * math.sqrt(T_TRAIN),
            "arms": {
                "A_pure_search": summarize(runs, ("A",)),
                "B_triad_gates": summarize(runs, ("B_triad_gates",)),
                "B_noNstar": summarize(runs, ("B_noNstar",)),
            },
        }
        for keep in C_FILTER_KEEP:
            block["arms"][f"C_random_keep{int(keep*100):03d}"] = summarize(runs, ("C", f"k{int(keep*100):03d}"))
        results[str(alpha)] = block

        a, b, bn = (block["arms"]["A_pure_search"], block["arms"]["B_triad_gates"],
                    block["arms"]["B_noNstar"])
        print(f"  a={alpha:.4f} (t_true={block['train_t_of_true']:4.2f})"
              f" | A: FDR={a['fdr_on_picked']:.3f} hit={a['hit_rate']:.3f}"
              f" | B: FDR={b['fdr_on_picked'] if b['fdr_on_picked'] is not None else float('nan'):.3f}"
              f" hit={b['hit_rate']:.3f} abstain={b['abstain_rate']:.3f}"
              f" | B-noN*: FDR={bn['fdr_on_picked'] if bn['fdr_on_picked'] is not None else float('nan'):.3f}"
              f" hit={bn['hit_rate']:.3f} abstain={bn['abstain_rate']:.3f}")

    payload = {"version": VERSION, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
               "config": {"n_cand": N_CAND, "k_true": K_TRUE, "t_total": T_TOTAL,
                          "t_train": T_TRAIN, "sigma": SIGMA, "reps": args.reps,
                          "trials_for_dsr": TRIALS, "alphas": alphas,
                          "c_filter_keep": C_FILTER_KEEP},
               "results": results, "elapsed_sec": round(time.time() - t0, 2)}
    jp = out_dir / "exp1_results.json"
    jp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n→ {jp}  （{payload['elapsed_sec']}s）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
