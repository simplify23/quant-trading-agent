# -*- coding: utf-8 -*-
"""s3_selfiter_20261009.py —— S3「下杀型估值修复」自学习迭代（训练/验证分离）
================================================================================
用户要求：对个股层 S3 做自学习迭代与优化，回测收益/回撤/夏普/卡玛。

★ 纪律（框架 v2.2 + 本项目惯例）：
  · 训练段 2019-01~2023-12 选优（选优键=事件组合 Calmar，组合级口径——
    吸取 10-08「信号级≠组合级」教训）；验证段 2024-01~2026-09 前向复核。
  · 网格 = 裁判派工的 BS-x 硬编码盲区（trials≈72，如实计入 DSR 语境）：
      深跌阈值 r1 ≤ {−6, −8} × PB 窗口 {250,500,1000} × PB 门槛 {30%,40%,60%,∞}
      × 持有期 {10,20,40} 日
  · 事件组合：T 收盘确认 → T+1 开盘买 → 持 hold 日收盘卖；重叠信号等权并列；
    无持仓日现金 RF=1.5%/年；成本 26bp 往返（买入日一次扣除）。
  · 前视防范：PB 分位 = rolling(w, min_periods=250).rank(pct=True)（因果）；
    信号矩阵全由 ≤T 数据构成；T+1 开盘买保证执行可行性。
  · 基准：793 只等权买入持有（同期）；验证段独立复核。
  · 幸存者偏差（现任成分）如实标注。
运行：python s3_selfiter_20261009.py
"""
from __future__ import annotations
import glob, os, json, time
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = "/Users/simplify/Desktop/自己/量化策略/错杀回归研究_20261008/data"
RF = 0.015 / 244
COST = 0.0026                       # 往返
PB_WINS = (250, 500, 1000)
PB_GATES = (0.30, 0.40, 0.60, None)
R1_TH = (-6.0, -8.0)
HOLDS = (10, 20, 40)
TRAIN = ("2019-01-01", "2023-12-31")
VALID = ("2024-01-01", "2026-09-30")


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


def perf(daily: pd.Series, cal_mask: pd.Series | None = None):
    d = daily.dropna()
    nav = (1 + d).cumprod()
    yrs = len(d) / 244
    ann = nav.iloc[-1] ** (1 / yrs) - 1
    vol = d.std() * np.sqrt(244)
    mdd = float((nav / nav.cummax() - 1).min())
    sh = (ann - 0.015) / vol if vol > 0 else float("nan")
    cal = ann / abs(mdd) if mdd < 0 else float("nan")
    return {"ann": round(float(ann), 4), "vol": round(float(vol), 4), "mdd": round(mdd, 4),
            "sharpe": round(float(sh), 3), "calmar": round(float(cal), 3), "n": int(len(d))}


def main():
    t0 = time.time()
    px, pb = load()
    codes = [c for c in px if c in pb and pb[c].notna().sum() > 250]
    print(f"[宇宙] {len(codes)} 只", flush=True)

    # 全局日历 = 等权指数日历
    eqret = pd.DataFrame({c: px[c]["close"].pct_change() for c in codes}).mean(axis=1)
    cal = eqret.dropna().index
    N = len(cal)
    cal_pos = {d: i for i, d in enumerate(cal)}
    eqnav = (1 + eqret.fillna(0)).cumprod()
    dd250 = eqnav / eqnav.rolling(250, min_periods=120).max() - 1
    bear = (dd250 <= -0.15)

    # 逐股预计算（hfq 日收益、当日开盘→收盘、PB 分位三窗口）
    print("[预计算] PB 分位 3 窗口 + 日收益结构…", flush=True)
    r1s, o2c, c2c, pbq = {}, {}, {}, {w: {} for w in PB_WINS}
    for c in codes:
        d = px[c]; b = pb[c]
        cl, op = d["close"], d["open"]
        r1s[c] = cl.pct_change() * 100
        o2c[c] = (cl / op - 1)                     # 当日开盘→收盘
        c2c[c] = cl.pct_change()                   # 收盘→收盘
        p = b.reindex(cl.index).ffill()
        for w in PB_WINS:
            pbq[w][c] = p.rolling(w, min_periods=250).rank(pct=True)

    # 股票日 → 全局日历位置
    gpos = {c: np.array([cal_pos.get(d, -1) for d in px[c].index]) for c in codes}

    def event_port(sig_masks: dict, hold: int) -> pd.Series:
        gsum = np.zeros(N); gcnt = np.zeros(N)
        for c, m in sig_masks.items():
            sp = np.where(m)[0]
            if len(sp) == 0: continue
            M = sp[:, None] + 1 + np.arange(hold)[None, :]
            M = M[M < len(px[c].index)].ravel()               # 拉平
            buy_day = np.repeat(sp + 1, hold)[:len(M)]        # 每元素的买入日索引
            gp = gpos[c][M]
            rr = np.where(M == buy_day, o2c[c].values[M] - COST, c2c[c].values[M])   # ★ 成本只扣买入日
            ok = gp >= 0
            gp, rr = gp[ok], rr[ok]                           # ★ 掩码统一在拉平后做
            gsum += np.bincount(gp, weights=rr, minlength=N)[:N]
            gcnt += np.bincount(gp, weights=np.ones(len(rr)), minlength=N)[:N]
        d = pd.Series(np.where(gcnt > 0, gsum / np.maximum(gcnt, 1), RF), index=cal)
        return d

    # ── 网格搜索（训练段选优）
    rows = []
    grid = []
    for r1t in R1_TH:
        for pw in PB_WINS:
            for pg in PB_GATES:
                for hold in HOLDS:
                    grid.append((r1t, pw, pg, hold))
    print(f"[网格] {len(grid)} 组合", flush=True)
    tr_mask = (cal >= pd.Timestamp(TRAIN[0])) & (cal <= pd.Timestamp(TRAIN[1]))
    va_mask = (cal >= pd.Timestamp(VALID[0])) & (cal <= pd.Timestamp(VALID[1]))

    best = None
    for gi, (r1t, pw, pg, hold) in enumerate(grid, 1):
        sig_masks = {}
        for c in codes:
            r1 = r1s[c]; pq = pbq[pw][c]
            m = (r1 <= r1t)
            if pg is not None:
                m = m & (pq <= pg)
            sig_masks[c] = m.reindex(px[c].index).fillna(False).to_numpy()
        daily = event_port(sig_masks, hold)
        tr = perf(daily[tr_mask]); va = perf(daily[va_mask])
        row = {"r1": r1t, "pb_win": pw, "pb_gate": pg, "hold": hold,
               "tr_calmar": tr["calmar"], "tr_ann": tr["ann"], "tr_mdd": tr["mdd"], "tr_sharpe": tr["sharpe"],
               "va_calmar": va["calmar"], "va_ann": va["ann"], "va_mdd": va["mdd"], "va_sharpe": va["sharpe"]}
        rows.append(row)
        if best is None or (np.isfinite(tr["calmar"]) and tr["calmar"] > best["tr_calmar"]):
            best = row
        if gi % 12 == 0:
            print(f"  进度 {gi}/{len(grid)}｜当前最优 训练Calmar {best['tr_calmar']}"
                  f"（r1≤{best['r1']} PBw{best['pb_win']} 门{best['pb_gate']} hold{best['hold']}）", flush=True)

    G = pd.DataFrame(rows).sort_values("tr_calmar", ascending=False)
    print("\n[训练段 Top8（按事件组合 Calmar）]")
    print(G.head(8).to_string(index=False))

    # ── 验证段复核：训练 Top5 + 直觉档（无 PB 条件对照）
    print("\n[验证段 2024-01~2026-09 前向复核]")
    chk = []
    for _, r in G.head(5).iterrows():
        chk.append(dict(r))
    # 无 PB 条件对照（同 r1=-6, hold=20）
    for pw in (250, 1000):
        sig_masks = {c: (r1s[c] <= -6).reindex(px[c].index).fillna(False).to_numpy() for c in codes}
        daily = event_port(sig_masks, 20)
        va = perf(daily[va_mask]); tr = perf(daily[tr_mask])
        chk.append({"r1": -6.0, "pb_win": pw, "pb_gate": None, "hold": 20,
                    "tr_calmar": tr["calmar"], "tr_ann": tr["ann"], "tr_mdd": tr["mdd"], "tr_sharpe": tr["sharpe"],
                    "va_calmar": va["calmar"], "va_ann": va["ann"], "va_mdd": va["mdd"], "va_sharpe": va["sharpe"]})
    C = pd.DataFrame(chk)
    print(C.to_string(index=False))

    # ── 最优组合深挖（训练+验证全段口径 + F6 + 噪声带）
    bb = best
    sig_masks = {}
    for c in codes:
        r1 = r1s[c]; pq = pbq[bb["pb_win"]][c]
        m = (r1 <= bb["r1"])
        if bb["pb_gate"] is not None:
            m = m & (pq <= bb["pb_gate"])
        sig_masks[c] = m.reindex(px[c].index).fillna(False).to_numpy()
    daily = event_port(sig_masks, int(bb["hold"]))
    full = perf(daily)
    trf = perf(daily[tr_mask]); vaf = perf(daily[va_mask])
    print(f"\n[最优组合全段] {json.dumps(full, ensure_ascii=False)}")
    print(f"[分段] 训练 {json.dumps(trf)}｜验证 {json.dumps(vaf)}")

    # F6：剔除最好信号日（按信号日笔均值）
    tr_list = []
    for d in pd.DataFrame({"d": daily.index, "v": daily.values}).itertuples():
        pass
    # 信号笔 = 每个 (code, 信号日) 的持有期收益：重新展开
    pen = []
    n_tr = 0
    for c, m in sig_masks.items():
        sp = np.where(m)[0]
        idx_arr = px[c].index
        for s in sp:
            b = s + 1; e = min(s + 1 + int(bb["hold"]), len(idx_arr))
            if b >= len(idx_arr): continue
            v = (px[c]["close"].iloc[min(e - 1, len(idx_arr) - 1)] /
                 px[c]["open"].iloc[min(b, len(idx_arr) - 1)] - 1) * 100 - COST * 100
            if np.isfinite(v):
                pen.append(v); n_tr += 1
    pen = np.array(pen)
    s = np.sort(pen)
    f6 = {"n": int(n_tr), "mean": round(float(pen.mean()), 3), "med": round(float(np.median(pen)), 3),
          "win": round(float((pen > 0).mean()), 3),
          "ex_best1": round(float(s[:-1].mean()), 3), "ex_best5": round(float(s[:-5].mean()), 3),
          "worst5": [round(float(x), 1) for x in s[:5]]}
    print(f"[F6 信号笔] {json.dumps(f6)}")

    # 噪声带：随机等量 (code,day) 事件 → 同持有期组合 Calmar 分布
    rng = np.random.default_rng(20261009)
    sims = []
    allcells = [(c, d) for c in codes for d in px[c].index[260:-int(bb['hold']) - 2]]
    for _ in range(120):
        pick = rng.choice(len(allcells), size=n_tr, replace=False)
        sm = {}
        by = {}
        for i in pick:
            by.setdefault(allcells[i][0], []).append(allcells[i][1])
        for c, ds in by.items():
            m = pd.Series(False, index=px[c].index)
            m.loc[pd.DatetimeIndex(ds)] = True
            sm[c] = m.to_numpy()
        dd = event_port(sm, int(bb["hold"]))
        sims.append(perf(dd[tr_mask & va_mask]) ["calmar"] if False else
                    perf(dd[(cal >= pd.Timestamp(TRAIN[0])) & (cal <= pd.Timestamp(VALID[1]))])["calmar"])
    sims = np.array([x for x in sims if np.isfinite(x)])
    real_cal = perf(daily[(cal >= pd.Timestamp(TRAIN[0])) & (cal <= pd.Timestamp(VALID[1]))])["calmar"]
    print(f"[噪声带] 随机事件 Calmar P50 {np.median(sims):.2f}｜P95 {np.percentile(sims,95):.2f}"
          f"｜真实(全段) {real_cal:.2f}｜随机跑赢 {100*(sims>=real_cal).mean():.0f}%")

    out = {"grid": rows, "best": bb, "best_full": full, "best_train": trf, "best_valid": vaf,
           "f6": f6, "noise": {"p50": round(float(np.median(sims)), 3),
                               "p95": round(float(np.percentile(sims, 95)), 3),
                               "real_full_calmar": real_cal,
                               "frac_ge": round(float((sims >= real_cal).mean()), 3)},
           "universe": len(codes), "window": [TRAIN[0], VALID[1]], "trials": len(grid)}
    json.dump(out, open(os.path.join(HERE, "s3_selfiter_结果.json"), "w"),
              ensure_ascii=False, indent=1, default=str)
    print(f"\n落盘 s3_selfiter_结果.json｜总耗时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
