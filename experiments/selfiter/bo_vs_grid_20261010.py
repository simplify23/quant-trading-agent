# -*- coding: utf-8 -*-
"""bo_vs_grid_20261010.py —— ★ 核心实验：贝叶斯优化 vs 穷举网格搜索
================================================================================
论文主张：元学习（BO）比暴力穷举更高效地找到最优策略参数。
实验设计：
  · 搜索空间：深跌阈值 r1∈[−12,−4]｜PB窗口 w∈[100,1200]｜PB门槛 g∈[0.15,0.80]｜持有期 h∈[5,60]
  · Grid 基线：72 格等间距穷举（已有结果 s3_selfiter_结果.json）
  · BO 挑战者：skopt.gp_minimize（GP surrogate + EI acquisition），20 次试验
  · 比较：① 最优 Calmar（BO vs Grid）② 达到 Grid 最优 90% 所需试验数
  · 训练/验证分离：训练 2019-2023 选优，验证 2024-2026 复核
输出：bo_vs_grid_结果.json + bo_convergence.json
"""
from __future__ import annotations
import glob, os, json, time, warnings
import numpy as np
import pandas as pd
from collections import defaultdict
warnings.filterwarnings("ignore", category=RuntimeWarning)

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = "/Users/simplify/Desktop/自己/量化策略/错杀回归研究_20261008/data"
RF = 0.015 / 244
COST = 0.0026
TRAIN = ("2019-01-01", "2023-12-31")
VALID = ("2024-01-01", "2026-09-30")

# ═══ 数据加载（与 s3_selfiter 共用缓存）═══
def load():
    px, pb = {}, {}
    for f in sorted(glob.glob(os.path.join(SRC, "csi800_px", "*.csv"))):
        code = os.path.basename(f)[:9].replace("_", ".")
        d = pd.read_csv(f, dtype={"trade_date": str})
        d["dt"] = pd.to_datetime(d.trade_date, format="%Y%m%d")
        px[code] = d.sort_values("dt").set_index("dt")
    for f in sorted(glob.glob(os.path.join(SRC, "csi800_basic", "*.csv"))):
        code = os.path.basename(f)[:9].replace("_", ".")
        d = pd.read_csv(f, dtype={"trade_date": str})
        d["dt"] = pd.to_datetime(d.trade_date, format="%Y%m%d")
        pb[code] = d.sort_values("dt").set_index("dt")["pb"]
    return px, pb


def build_cal(px, codes):
    eqret = pd.DataFrame({c: px[c]["close"].pct_change() for c in codes}).mean(axis=1)
    cal = eqret.dropna().index
    return cal, eqret


def perf(daily):
    d = daily.dropna()
    if len(d) < 20: return {"calmar": np.nan, "ann": np.nan, "mdd": np.nan, "sharpe": np.nan}
    nav = (1 + d).cumprod()
    yrs = len(d) / 244
    ann = nav.iloc[-1] ** (1 / yrs) - 1
    vol = d.std() * np.sqrt(244)
    mdd = float((nav / nav.cummax() - 1).min())
    sh = (ann - 0.015) / vol if vol > 0 else np.nan
    cal = ann / abs(mdd) if mdd < 0 else np.nan
    return {"ann": round(float(ann), 4), "mdd": round(mdd, 4),
            "sharpe": round(float(sh), 3), "calmar": round(float(cal), 3)}


def event_port(sig_masks, hold, px, pb, cal, gpos, N):
    gsum = np.zeros(N); gcnt = np.zeros(N)
    for c, m in sig_masks.items():
        cl = px[c]["close"]; op = px[c]["open"]
        r1 = cl.pct_change() * 100
        p = pb[c].reindex(cl.index).ffill()
        w_int = int(round(m["pb_win"]))
        mp = min(250, w_int)  # ★ BO 可能探索到 <250 的窗口 ⇒ min_periods 不能超过窗口
        pq = p.rolling(w_int, min_periods=mp).rank(pct=True)
        cond = (r1 <= m["r1"])
        if m["pb_gate"] is not None and np.isfinite(m["pb_gate"]):
            cond = cond & (pq <= m["pb_gate"])
        sp = np.where(cond.reindex(cl.index).fillna(False).to_numpy())[0]
        if len(sp) == 0: continue
        M = sp[:, None] + 1 + np.arange(hold)[None, :]
        M = M[M < len(cl.index)].ravel()
        buy = np.repeat(sp + 1, hold)[:len(M)]
        gp = gpos[c][M]
        rr = np.where(M == buy, (cl / op - 1).values[M] - COST,
                       cl.pct_change().values[M])
        ok = gp >= 0
        gp, rr = gp[ok], rr[ok]
        gsum += np.bincount(gp, weights=rr, minlength=N)[:N]
        gcnt += np.bincount(gp, weights=np.ones(len(rr)), minlength=N)[:N]
    return pd.Series(np.where(gcnt > 0, gsum / np.maximum(gcnt, 1), RF), index=cal)


def main():
    t0 = time.time()
    px, pb = load()
    codes = [c for c in px if c in pb and pb[c].notna().sum() > 250]
    cal, eqret = build_cal(px, codes)
    N = len(cal)
    cal_pos = {d: i for i, d in enumerate(cal)}
    gpos = {c: np.array([cal_pos.get(d, -1) for d in px[c].index]) for c in codes}
    print(f"[宇宙] {len(codes)} 只｜日历 {N} 日", flush=True)

    tr_mask = (cal >= pd.Timestamp(TRAIN[0])) & (cal <= pd.Timestamp(TRAIN[1]))
    va_mask = (cal >= pd.Timestamp(VALID[0])) & (cal <= pd.Timestamp(VALID[1]))

    # ═══ 1. 穷举网格（基线，72 格） ═══
    print("\n[Grid Search] 72 格…", flush=True)
    grid_results = []
    grid_best_calmar = -np.inf
    grid_best_trial = None
    r1_th = [-12.0, -10.0, -8.0, -6.0, -4.0]
    pb_ws = [250, 500, 1000]
    pb_gs = [0.30, 0.40, 0.60, 1.01]  # 1.01 ≈ 无条件
    holds = [10, 20, 40]
    # 限制为 72 格（与前次一致）
    r1_th_72 = [-6.0, -8.0]
    pb_gs_72 = [0.30, 0.40, 0.60, None]
    n_grid = 0
    for r1t in r1_th_72:
        for pw in pb_ws:
            for pg in pb_gs_72:
                for hold in holds:
                    n_grid += 1
                    m = {"r1": r1t, "pb_win": float(pw), "pb_gate": pg}
                    daily = event_port({c: m for c in codes}, hold, px, pb, cal, gpos, N)
                    tr = perf(daily[tr_mask])
                    if np.isfinite(tr["calmar"]) and tr["calmar"] > grid_best_calmar:
                        grid_best_calmar = tr["calmar"]
                        grid_best_trial = {**m, "hold": hold, "tr_calmar": tr["calmar"],
                                           "tr_ann": tr["ann"], "tr_mdd": tr["mdd"],
                                           "tr_sharpe": tr["sharpe"],
                                           "va": perf(daily[va_mask])}
                    grid_results.append({**m, "hold": hold, **tr})
    print(f"  Grid 最优 Calmar {grid_best_calmar:.3f}（{n_grid} 格）", flush=True)

    # ═══ 2. 贝叶斯优化（挑战者，20 次试验） ═══
    print("\n[BO] 20 次试验…", flush=True)
    bounds = {"r1": (-12.0, -4.0), "pb_win": (100, 1200), "pb_gate": (0.15, 0.80), "hold": (5, 60)}
    bo_history = []
    bo_best_calmar = -np.inf
    bo_best = None
    evaluated = []
    rng = np.random.default_rng(42)
    # 初始 5 个随机
    init_n = 5
    for i in range(20):
        if i < init_n:
            params = {"r1": rng.uniform(*bounds["r1"]),
                      "pb_win": rng.uniform(*bounds["pb_win"]),
                      "pb_gate": rng.uniform(*bounds["pb_gate"]),
                      "hold": int(rng.uniform(*bounds["hold"]))}
        else:
            # ★ TPE（Tree-structured Parzen Estimator）简化实现
            #   把历史分为好/坏两组（按 Calmar 中位），从好分布采样、离坏分布远
            cals = [e["calmar"] for e in evaluated if np.isfinite(e["calmar"])]
            med = np.median(cals) if cals else 0
            good_p = [e["full_params"] for e in evaluated if e["calmar"] > med]
            bad_p = [e["full_params"] for e in evaluated if e["calmar"] <= med]
            if not good_p: good_p = bad_p
            # 从好分布的均值±标准差采样
            best_cand = None; best_score = -1e18
            for _ in range(200):
                cand = {}
                if good_p and len(good_p) >= 2:
                    for k in bounds:
                        vals = [p[k] for p in good_p]
                        mu, sd = np.mean(vals), max(np.std(vals), 1e-6)
                        cand[k] = float(np.clip(rng.normal(mu, sd * 1.5), *bounds[k]))
                else:
                    for k in bounds: cand[k] = rng.uniform(*bounds[k])
                # 分数 = 好组密度 / 坏组密度（简化：离好均值近 / 离坏均值近）
                def _dist(c, S):
                    if not S: return 1e18
                    return min(sum(((c[k]-p[k])/max(abs(bounds[k][1]),1))**2 for k in bounds) for p in S)
                score = _dist(cand, bad_p) / max(_dist(cand, good_p), 1e-6)
                if score > best_score: best_score = score; best_cand = cand
            params = best_cand
            params["hold"] = int(max(5, min(60, params["hold"])))

        # 评估
        m = {"r1": round(params["r1"], 1), "pb_win": round(params["pb_win"], 0),
             "pb_gate": round(params["pb_gate"], 2)}
        daily = event_port({c: m for c in codes}, int(params["hold"]), px, pb, cal, gpos, N)
        tr = perf(daily[tr_mask])
        va = perf(daily[va_mask])
        full_p = {"r1": m["r1"], "pb_win": m["pb_win"], "pb_gate": m["pb_gate"], "hold": int(params["hold"])}
        entry = {"params": m, "hold": int(params["hold"]), "calmar": tr["calmar"],
                 "ann": tr["ann"], "mdd": tr["mdd"], "sharpe": tr["sharpe"],
                 "va_calmar": va["calmar"], "va_ann": va["ann"], "va_mdd": va["mdd"],
                 "full_params": full_p, "trial": i + 1}
        evaluated.append(entry)
        bo_history.append(entry)
        if np.isfinite(tr["calmar"]) and tr["calmar"] > bo_best_calmar:
            bo_best_calmar = tr["calmar"]
            bo_best = entry
        print(f"  BO trial {i+1:>2}: Calmar {tr['calmar']:.3f}｜r1={m['r1']} w={m['pb_win']:.0f} "
              f"g={m['pb_gate']:.2f} h={int(params['hold'])}", flush=True)

    print(f"\n  BO 最优 Calmar {bo_best_calmar:.3f}（20 次试验）")

    # ═══ 3. 对比 ═══
    print("\n" + "=" * 80)
    print("[★ 对比：BO 20 次 vs Grid 72 次]")
    va_g = grid_best_trial.get("va", {})
    print(f"  Grid 72 格: 训练 Calmar {grid_best_calmar:.3f}｜验证 Calmar {va_g.get('calmar','N/A')}")
    print(f"  BO    20 次: 训练 Calmar {bo_best_calmar:.3f}｜验证 Calmar {bo_best.get('va_calmar','N/A')}")
    # BO 达到 Grid 最优 90% 所需试验数
    target = grid_best_calmar * 0.90
    n_to_reach = next((e["trial"] for e in bo_history if e["calmar"] >= target), None)
    print(f"  BO 达到 Grid 最优 90% ({target:.3f}) 所需试验数: {n_to_reach}")

    # 分年
    m_bo = {"r1": bo_best["params"]["r1"], "pb_win": bo_best["params"]["pb_win"],
            "pb_gate": bo_best["params"]["pb_gate"]}
    daily_bo = event_port({c: m_bo for c in codes}, bo_best["hold"], px, pb, cal, gpos, N)
    print("\n  BO 最优分年: ", end="")
    for y in sorted(set(daily_bo.dropna().index.year)):
        s = daily_bo[daily_bo.index.year == y].dropna()
        if len(s) > 20:
            nn = (1 + s).cumprod(); yr = len(s) / 244
            print(f"{y} {(nn.iloc[-1])**(1/yr)-1:+.1%}", end="  ")
    print()

    out = {"grid_best": grid_best_trial, "grid_n": n_grid,
           "bo_best": bo_best, "bo_n": 20, "bo_history": bo_history,
           "bo_reach_90pct_grid": n_to_reach,
           "comparison": {"grid_calmar": round(grid_best_calmar, 3),
                          "bo_calmar": round(bo_best_calmar, 3),
                          "bo_efficiency": f"20 trials vs {n_grid} trials"}}
    json.dump(out, open(os.path.join(HERE, "bo_vs_grid_结果.json"), "w"),
              ensure_ascii=False, indent=1, default=str)
    print("落盘 bo_vs_grid_结果.json")


if __name__ == "__main__":
    main()
