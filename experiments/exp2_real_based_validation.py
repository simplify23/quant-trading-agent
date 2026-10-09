#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exp2_real_based_validation.py —— 真实数据标定的复核

exp1 用的是 i.i.d. 高斯噪声。真实金融收益有 **厚尾 + 波动率聚集 + 截面相关**，
这三样都可能改变判据行为（尤其「子样本稳定性」这类看分段符号的判据）。
⇒ 本实验把**真实的 29 只 ETF 日收益**当作噪声基底（统计特征原样保留），
   只随机给 K 只注入**已知 alpha** ⇒ 真值仍已知，但数据不再是玩具。

判据与汇总函数**直接从 exp1 导入**（不复制一份，避免两份同义实现 —— 先例 P-13）。

用法：
  python3 exp2_real_based_validation.py --reps 300 --k-true 5 --alpha 0.0008
"""
from __future__ import annotations

import argparse
import json
import os
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import exp1_injected_gate_efficacy as e1   # noqa: E402  ★ 复用判据与汇总，不复制

VERSION = "1.0.0"
# 数据锚点：29 只 A 股 ETF 面板（后复权，746 日）。
# ★ 已随仓库分发在 experiments/data/ 下；也可用 --panel 或环境变量 QTA_ETF_PANEL
#   指向你本地的副本（例如你自己从 tushare 拉的那一份）。
PANEL = Path(os.environ.get(
    "QTA_ETF_PANEL", str(HERE / "data" / "etf_panel_ts.frozen-20260930.json")))


def load_real_returns(path: Path, min_len: int) -> tuple[np.ndarray, list[str]]:
    """返回 (T×N 日收益矩阵, 代码列表)。取每个标的的收盘价算简单日收益。

    ★ 实际面板是 746 日 ⇒ 收益序列 745 个点（不是 exp1 用的 750），
      训练段仍取前 T_TRAIN=322 个点，留出段自动为 423 个点。
    """
    d = json.loads(path.read_text(encoding="utf-8"))
    codes, cols = [], []
    for code in sorted(d.keys()):
        node = d[code]
        kl = node["kline"] if isinstance(node, dict) and "kline" in node else node
        px = [float(r[2]) for r in kl]          # close
        if len(px) < min_len + 1:
            continue
        ret = [(px[i] / px[i - 1] - 1.0) for i in range(1, len(px))]
        codes.append(code)
        cols.append(ret)
    if not cols:
        raise SystemExit(f"没有任何标的满足 min_len={min_len}；检查面板长度")
    n = min(len(c) for c in cols)
    R = np.array([c[-n:] for c in cols], dtype=float).T   # T×N
    return R, codes


def make_strategy_panel(rng, R_real: np.ndarray, sigma_e: float):
    """★ 构造【同一个策略族的 N 组参数变体】—— 这才是 Triad 的真实用武之地。

    结构：r_jt = w_t + ε_jt
      w_t  = 真实 ETF 面板的等权市场收益（保留厚尾与波动聚集）
      ε_jt = 策略特有噪声（σ_e）
    ⇒ 策略之间高度相关（同一市场），真差异藏在 ε 里 ⇒ **训练段 Sharpe 排名几乎全是噪声**。
    这与"29 只不同 ETF"完全不同（那是选标的，候选差异来自真 alpha）。
    """
    w = R_real.mean(axis=1, keepdims=True)
    N = R_real.shape[1]
    return w + rng.normal(0.0, sigma_e, size=(R_real.shape[0], N))


def describe(R: np.ndarray) -> dict:
    x = R.ravel()
    x = x[np.isfinite(x)]
    mu, sd = x.mean(), x.std(ddof=1)
    skew = float(((x - mu) ** 3).mean() / sd ** 3)
    kurt = float(((x - mu) ** 4).mean() / sd ** 4)
    ac1 = float(np.corrcoef(R[:-1].ravel(), R[1:].ravel())[0, 1])
    # 截面平均相关
    C = np.corrcoef(R.T)
    n = C.shape[0]
    off = C[~np.eye(n, dtype=bool)]
    return {"mean": float(mu), "sd": float(sd), "skew": skew, "kurt": kurt,
            "autocorr1": ac1, "mean_cross_corr": float(np.nanmean(off)), "n_assets": n}


def one_run(rng, R_real: np.ndarray, alpha: float, k_true: int,
            alpha_mode: str = "constant", panel_kind: str = "asset",
            sigma_e: float = 0.007) -> dict:
    T, N = R_real.shape
    truth = np.zeros(N, dtype=bool)
    truth[rng.choice(N, k_true, replace=False)] = True
    R = (R_real.copy() if panel_kind == "asset"
         else make_strategy_panel(rng, R_real, sigma_e))
    # ★ 只注入 alpha，厚尾/波动聚集/截面相关原样保留。
    #   alpha_mode 决定 alpha 的**时间结构** —— 这才是搜索会不会犯错的关键：
    #     constant     每天都有效（太容易识别，训练段 Sharpe 完全代表未来）
    #     intermittent 只有 50% 的交易日有效（放大后保持平均 alpha 不变）
    #     regime       只在"市场上涨日"有效（真实的 alpha 往往是有条件的）
    #   后两者让【训练段表现】不再可靠地预测未来 ⇒ 这才是真实研究的处境。
    j_true = np.where(truth)[0]
    if alpha_mode == "constant":
        R[:, j_true] += alpha
    elif alpha_mode == "intermittent":
        mask = rng.random(T) < 0.5
        if mask.sum() > 0:
            R[np.ix_(mask, j_true)] += alpha * 2.0
    elif alpha_mode == "regime":
        mkt = R_real.mean(axis=1)
        mask = mkt > 0
        if mask.sum() > 0:
            R[np.ix_(mask, j_true)] += alpha * (T / mask.sum())
    else:
        raise ValueError(alpha_mode)

    tr, ho = R[:e1.T_TRAIN], R[e1.T_TRAIN:]
    sr_tr = np.array([e1.sharpe_daily(tr[:, j]) for j in range(N)])
    sr_ho = np.array([e1.sharpe_daily(ho[:, j]) for j in range(N)])

    out: dict = {}
    j_a = int(np.argmax(sr_tr))
    out["A"] = {"picked": j_a, "is_true": bool(truth[j_a]),
                "ho_sharpe": float(sr_ho[j_a]), "n_passed": 1}

    bench_tr = None if panel_kind == "asset" else R_real[:e1.T_TRAIN].mean(axis=1)
    for tag, use_ns in (("B_triad_gates", True), ("B_noNstar", False)):
        passed = [j for j in range(N) if e1.gates_pass(tr[:, j], use_ns, bench_tr)[0]]
        if passed:
            j_b = max(passed, key=lambda j: sr_tr[j])
            out[tag] = {"picked": j_b, "is_true": bool(truth[j_b]),
                        "ho_sharpe": float(sr_ho[j_b]), "n_passed": len(passed)}
        else:
            out[tag] = {"picked": None, "is_true": None, "ho_sharpe": None, "n_passed": 0}

    out["C"] = {}
    for keep in e1.C_FILTER_KEEP:
        key = f"k{int(keep*100):03d}"
        if rng.random() < keep:
            out["C"][key] = {"picked": j_a, "is_true": bool(truth[j_a]),
                             "ho_sharpe": float(sr_ho[j_a]), "n_passed": 1}
        else:
            out["C"][key] = {"picked": None, "is_true": None,
                             "ho_sharpe": None, "n_passed": 0}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default=None,
                    help="ETF 面板 JSON 路径（默认用 experiments/data/ 下的随仓库副本）")
    ap.add_argument("--reps", type=int, default=300)
    ap.add_argument("--k-true", type=int, default=5)
    ap.add_argument("--alphas", type=float, nargs="*",
                    default=[0.0004, 0.0008, 0.0016, 0.0032])
    ap.add_argument("--seed", type=int, default=20261006)
    ap.add_argument("--panel-kind", default="asset", choices=["asset", "strategy"],
                    help="asset=候选是不同标的；strategy=候选是同一策略族的高相关参数变体")
    ap.add_argument("--sigma-e", type=float, default=0.007, help="strategy 模式的策略特有噪声")
    ap.add_argument("--alpha-mode", default="constant",
                    choices=["constant", "intermittent", "regime"])
    ap.add_argument("--out", default=str(HERE))
    args = ap.parse_args()

    panel_path = Path(args.panel) if args.panel else PANEL
    if not panel_path.exists():
        raise SystemExit("面板不存在：%s\n  请用 --panel <path> 指定，或设置 QTA_ETF_PANEL。" % panel_path)
    R_real, codes = load_real_returns(panel_path, e1.T_TRAIN * 2)
    e1.N_CAND = R_real.shape[1]
    e1.K_TRUE = args.k_true
    stats = describe(R_real)

    print(f"exp2 真实数据标定复核  v{VERSION}")
    print(f"  数据：{panel_path.name}｜{R_real.shape[1]} 只 × {R_real.shape[0]} 个收益点（训练 {e1.T_TRAIN}／留出 {R_real.shape[0]-e1.T_TRAIN}）")
    print(f"  真实统计：日 sd={stats['sd']:.5f}｜偏度={stats['skew']:+.2f}｜峰度={stats['kurt']:.2f}"
          f"（正态=3）｜一阶自相关={stats['autocorr1']:+.3f}｜截面平均相关={stats['mean_cross_corr']:+.3f}")
    print(f"  真信号 {args.k_true}/{R_real.shape[1]} → 注入 α ∈ {args.alphas}"
          f"｜alpha 模式={args.alpha_mode}｜面板={args.panel_kind}｜重复 {args.reps}\n")

    results = {}
    for alpha in args.alphas:
        rng = np.random.default_rng(args.seed + int(alpha * 1e6) + 7)
        runs = [one_run(rng, R_real, alpha, args.k_true, args.alpha_mode,
                        args.panel_kind, args.sigma_e) for _ in range(args.reps)]
        block = {"alpha": alpha, "annualized_alpha": alpha * e1.PPY,
                 # ★ 标定基准必须与"信号相对于什么噪声"一致：
                 #   asset 模式看市场波动；strategy 模式看【策略特有噪声 σ_ε】
                 "train_t_of_true": alpha / (stats["sd"] if args.panel_kind == "asset"
                                             else args.sigma_e) * math.sqrt(e1.T_TRAIN),
                 "arms": {"A_pure_search": e1.summarize(runs, ("A",)),
                          "B_triad_gates": e1.summarize(runs, ("B_triad_gates",)),
                          "B_noNstar": e1.summarize(runs, ("B_noNstar",))}}
        for keep in e1.C_FILTER_KEEP:
            block["arms"][f"C_random_keep{int(keep*100):03d}"] = \
                e1.summarize(runs, ("C", f"k{int(keep*100):03d}"))
        results[str(alpha)] = block
        a, b = block["arms"]["A_pure_search"], block["arms"]["B_triad_gates"]
        print(f"  α={alpha:.4f} (t_true={block['train_t_of_true']:4.2f})"
              f" | A: FDR={a['fdr_on_picked']:.3f} hit={a['hit_rate']:.3f}"
              f" | B: FDR={b['fdr_on_picked'] if b['fdr_on_picked'] is not None else float('nan'):.3f}"
              f" hit={b['hit_rate']:.3f} abstain={b['abstain_rate']:.3f}")

    payload = {"version": VERSION, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
               "panel": panel_path.name, "panel_stats": stats,
               "n_assets": int(R_real.shape[1]), "t_total": int(R_real.shape[0]),
               "k_true": args.k_true, "reps": args.reps,
               "alpha_mode": args.alpha_mode, "panel_kind": args.panel_kind,
               "sigma_e": args.sigma_e, "results": results}
    jp = Path(args.out) / "exp2_results.json"
    jp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n→ {jp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
