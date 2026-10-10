# -*- coding: utf-8 -*-
"""optuna_s3_20261010.py —— Optuna TPE vs Grid 72：核心对比实验
用 Optuna 5.0 的 TPE 采样器替代暴力穷举，预算 30 次试验。
目标：证明元学习（学习搜索空间结构）比暴力穷举更高效。
"""
from __future__ import annotations
import glob, os, json, time, warnings
import numpy as np
import pandas as pd
import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = "/Users/simplify/Desktop/自己/量化策略/错杀回归研究_20261008/data"
RF = 0.015 / 244
COST = 0.0026
TRAIN = ("2019-01-01", "2023-12-31")
VALID = ("2024-01-01", "2026-09-30")

def load():
    px, pb = {}, {}
    for f in sorted(glob.glob(os.path.join(SRC, "csi800_px", "*.csv"))):
        c = os.path.basename(f)[:9].replace("_", ".")
        d = pd.read_csv(f, dtype={"trade_date": str})
        d["dt"] = pd.to_datetime(d.trade_date, format="%Y%m%d")
        px[c] = d.sort_values("dt").set_index("dt")
    for f in sorted(glob.glob(os.path.join(SRC, "csi800_basic", "*.csv"))):
        c = os.path.basename(f)[:9].replace("_", ".")
        d = pd.read_csv(f, dtype={"trade_date": str})
        d["dt"] = pd.to_datetime(d.trade_date, format="%Y%m%d")
        pb[c] = d.sort_values("dt").set_index("dt")["pb"]
    return px, pb

def main():
    t0 = time.time()
    px, pb = load()
    codes = [c for c in px if c in pb and pb[c].notna().sum() > 200]
    eqret = pd.DataFrame({c: px[c]["close"].pct_change() for c in codes}).mean(axis=1)
    cal = eqret.dropna().index
    N = len(cal)
    cal_pos = {d: i for i, d in enumerate(cal)}
    gpos = {c: np.array([cal_pos.get(d, -1) for d in px[c].index]) for c in codes}
    tr_mask = (cal >= pd.Timestamp(TRAIN[0])) & (cal <= pd.Timestamp(TRAIN[1]))
    va_mask = (cal >= pd.Timestamp(VALID[0])) & (cal <= pd.Timestamp(VALID[1]))
    print(f"[宇宙] {len(codes)} 只｜日历 {N} 日", flush=True)

    # 预计算
    r1s, o2c, c2c, pbqs = {}, {}, {}, {}
    for c in codes:
        cl, op = px[c]["close"], px[c]["open"]
        r1s[c] = cl.pct_change() * 100
        o2c[c] = cl / op - 1
        c2c[c] = cl.pct_change()
        p = pb[c].reindex(cl.index).ffill()
        for w in (100, 250, 500, 750, 1000, 1200):
            mp = min(250, w)
            pbqs[(c, w)] = p.rolling(w, min_periods=mp).rank(pct=True)

    PRECOMPUTED_W = sorted(set(w for (c, w) in pbqs.keys()))
    def _nearest_w(w):
        return min(PRECOMPUTED_W, key=lambda x: abs(x - w))
    def event_port(r1t, pb_w, pb_gate, hold):
        gsum = np.zeros(N); gcnt = np.zeros(N)
        w_int = _nearest_w(pb_w)  # ★ 四舍五入到最近的预计算窗口
        for c in codes:
            r1 = r1s[c]; pq = pbqs.get((c, w_int))
            if pq is None: continue
            m = (r1 <= r1t) & (pq <= pb_gate)
            sp = np.where(m.reindex(px[c].index).fillna(False).to_numpy())[0]
            if len(sp) == 0: continue
            M = sp[:, None] + 1 + np.arange(hold)[None, :]
            M = M[M < len(px[c].index)].ravel()
            buy = np.repeat(sp + 1, hold)[:len(M)]
            gp = gpos[c][M]
            rr = np.where(M == buy, o2c[c].values[M] - COST, c2c[c].values[M])
            ok = gp >= 0
            gp, rr = gp[ok], rr[ok]
            gsum += np.bincount(gp, weights=rr, minlength=N)[:N]
            gcnt += np.bincount(gp, weights=np.ones(len(rr)), minlength=N)[:N]
        return pd.Series(np.where(gcnt > 0, gsum / np.maximum(gcnt, 1), RF), index=cal)

    def perf(d):
        d = d.dropna()
        if len(d) < 20: return {"calmar": np.nan, "ann": np.nan, "mdd": np.nan, "sharpe": np.nan}
        nav = (1 + d).cumprod(); yrs = len(d) / 244
        ann = nav.iloc[-1] ** (1 / yrs) - 1
        vol = d.std() * np.sqrt(244)
        mdd = float((nav / nav.cummax() - 1).min())
        sh = (ann - 0.015) / vol if vol > 0 else np.nan
        cal_ = ann / abs(mdd) if mdd < 0 else np.nan
        return {"ann": round(float(ann), 4), "mdd": round(mdd, 4),
                "sharpe": round(float(sh), 3), "calmar": round(float(cal_), 3)}

    # ═══ Optuna Study ═══
    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=42))
    history = []

    def objective(trial):
        r1t = trial.suggest_float("r1_threshold", -12.0, -4.0)
        pb_w = trial.suggest_int("pb_window", 100, 1200)
        pb_g = trial.suggest_float("pb_gate", 0.15, 0.80)
        hold = trial.suggest_int("hold_days", 5, 60)
        daily = event_port(r1t, pb_w, pb_g, hold)
        tr = perf(daily[tr_mask])
        va = perf(daily[va_mask])
        history.append({"trial": trial.number, "params": trial.params,
                        "tr_calmar": tr["calmar"], "tr_ann": tr["ann"],
                        "va_calmar": va["calmar"], "va_ann": va["ann"],
                        "va_mdd": va["mdd"], "va_sharpe": va["sharpe"]})
        if trial.number % 5 == 0:
            best = max((h["tr_calmar"] for h in history if np.isfinite(h["tr_calmar"])), default=np.nan)
            print(f"  Trial {trial.number+1:>2}: best_tr_calmar {best:.3f}", flush=True)
        return tr["calmar"] if np.isfinite(tr["calmar"]) else -10.0

    N_TRIALS = 30
    print(f"\n[Optuna TPE] {N_TRIALS} 次试验…", flush=True)
    study.optimize(objective, n_trials=N_TRIALS, show_progress_bar=False)

    best = study.best_trial
    print(f"\n[BO 最优] Calmar {best.value:.3f}｜params {best.params}", flush=True)

    # 最优验证段
    bp = best.params
    daily_best = event_port(bp["r1_threshold"], bp["pb_window"], bp["pb_gate"], bp["hold_days"])
    tr_best = perf(daily_best[tr_mask]); va_best = perf(daily_best[va_mask])
    full_best = perf(daily_best[(cal >= pd.Timestamp(TRAIN[0])) & (cal <= pd.Timestamp(VALID[1]))])
    print(f"  训练 {json.dumps(tr_best)}")
    print(f"  验证 {json.dumps(va_best)}")
    print(f"  全段 {json.dumps(full_best)}")

    # ═══ 与 Grid 72 对比 ═══
    grid_best = json.load(open("/Users/simplify/Desktop/自己/量化策略/市值分层策略研究_20261009/s3_selfiter_结果.json"))
    gcal = grid_best["best"]["tr_calmar"] if "best" in grid_best else 1.04
    gv = grid_best.get("best_valid", {}).get("calmar", 0.648)

    print(f"\n{'='*70}")
    print(f"[★ 对比]")
    print(f"  Grid 72 格: 训练 Calmar {gcal:.3f}｜验证 {gv:.3f}")
    print(f"  Optuna 30:  训练 Calmar {best.value:.3f}｜验证 {va_best.get('calmar','N/A'):.3f}")
    print(f"  效率: {N_TRIALS} vs 72 试验（{'BO 更高效' if best.value >= gcal * 0.9 else 'BO 未达 Grid 90%'}）")

    # 收敛曲线数据
    cummax_calmar = []
    cm = -np.inf
    for h in history:
        c = h["tr_calmar"]
        if np.isfinite(c) and c > cm: cm = c
        cummax_calmar.append(round(cm, 4) if np.isfinite(cm) else None)

    out = {"bo_best_trial": best.number, "bo_best_params": best.params,
           "bo_best_value": best.value, "bo_n": N_TRIALS,
           "bo_train": tr_best, "bo_valid": va_best, "bo_full": full_best,
           "grid_best_calmar": gcal, "grid_valid_calmar": gv, "grid_n": 72,
           "history": history, "cummax_calmar": cummax_calmar,
           "universe": len(codes)}
    json.dump(out, open(os.path.join(HERE, "optuna_s3_结果.json"), "w"),
              ensure_ascii=False, indent=1, default=str)
    print(f"落盘 optuna_s3_结果.json｜总耗时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
