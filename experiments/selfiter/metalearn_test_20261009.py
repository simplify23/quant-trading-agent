# -*- coding: utf-8 -*-
"""metalearn_test_20261009.py —— 元学习知识 → 策略改进的验收测试
================================================================================
用户问题：三阶/四阶学到的知识（可转债扛跌、持有期 40 日、市场状态分层），
放进现有策略里跑，能不能带来可度量的收益改进？

三个对照实验（全部基于天玑现役口径，不改闸门）：
  实验 1  空仓期持什么：现金 vs 可转债低价券 vs QDII 篮子
  实验 2  持有期：30 日（现役）vs 40 日（本轮发现"反转周期被低估"）
  实验 3  市场状态分层：深度低吸信号在熊市日 vs 牛市日的质量差异
全部使用已有数据（不新拉）；天玑闸门不变（MA100）；只改"空仓持什么"和参数。
"""
from __future__ import annotations
import glob, os, json, sys
from collections import defaultdict
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = "/Users/simplify/Desktop/自己/量化策略/错杀回归研究_20261008/data"
RF = 0.015 / 244
HOLD, COST = 20, 0.0026
V1 = "/Users/simplify/Desktop/自己/量化策略/ETF轮动策略/ETF轮动_v1"
sys.path.insert(0, os.path.join(V1, "engine"))
sys.path.insert(0, os.path.join(V1, "research"))
# ★ insert(0) 后进先出 ⇒ 倒序插入，保证 engine 优先
sys.path.insert(0, os.path.join(ROOT := "/Users/simplify/Desktop/自己/量化策略",
                                "潮汐策略", "潮汐_0.74", "02_backtest"))
sys.path.insert(0, os.path.join(V1, "research"))
sys.path.insert(0, os.path.join(V1, "engine"))
import sector_doc_crossval as _sdc
assert _sdc.__file__.endswith("engine/sector_doc_crossval.py"), _sdc.__file__
import etf_rotation_live as LIV
from sector_doc_crossval import build_factors, build_gate, perf


def stat(daily):
    d = daily.dropna()
    nav = (1 + d).cumprod()
    yrs = len(d) / 244
    ann = nav.iloc[-1] ** (1 / yrs) - 1
    vol = d.std() * np.sqrt(244)
    mdd = float((nav / nav.cummax() - 1).min())
    sh = (ann - 0.015) / vol if vol > 0 else float("nan")
    cal = ann / abs(mdd) if mdd < 0 else float("nan")
    return {"ann": round(float(ann), 4), "mdd": round(mdd, 4),
            "sharpe": round(float(sh), 3), "calmar": round(float(cal), 3)}


def main():
    # ── 加载天玑面板与闸门 ──
    O, C, nm = LIV.load_panel(LIV.PANEL_FROZEN)[:3]
    C = C[[k for k in C.columns if k in nm]]; O = O[C.columns]
    LA, LB = "2020-07-01", "2026-09-30"
    Oa, Ca = O.loc[LA:LB], C.loc[LA:LB]
    idx = Ca.index
    p0 = int(O.index.get_indexer([Oa.index[0]])[0])
    gate = build_gate(C, 100)[p0:p0 + len(Oa)]
    F = build_factors(C); S = F[LIV.FACTOR].loc[LA:LB]
    nv_cash, tr, _ = __import__("optimize_cycle3_20261003", fromlist=["run_v2"]).run_v2(
        Oa, Ca, S, S, gate, LIV.MIN_HOLD, LIV.RANK_OUT)

    # 等权指数 → dd250 → 熊市日
    eqret = C.pct_change().mean(axis=1)
    eqnav = (1 + eqret.fillna(0)).cumprod()
    dd250 = eqnav / eqnav.rolling(250, min_periods=120).max() - 1
    bear = (dd250 <= -0.15)

    # 可转债低价券日收益（从已有缓存重建）
    CB = "/Users/simplify/Desktop/自己/量化策略/熊市策略研究_20261009/data/cb_daily"
    cb_files = sorted(glob.glob(os.path.join(CB, "*.csv")))
    rows = []
    for f in cb_files:
        d = pd.read_csv(f)
        if len(d): rows.append(d)
    D = pd.concat(rows, ignore_index=True)
    D["dt"] = pd.to_datetime(D.trade_date, format="%Y%m%d")
    cbpx = D.pivot_table(index="dt", columns="ts_code", values="close", aggfunc="last").sort_index()
    cbpx = cbpx[(cbpx > 10) & np.isfinite(cbpx)]  # 清洗
    mends = [g.index[-1] for _, g in cbpx.groupby(cbpx.index.to_period("M")) if len(g) >= 15]
    cbret = pd.Series(0.0, index=cbpx.index)
    for i in range(len(mends) - 1):
        d0, d1 = mends[i], mends[i + 1]
        row = cbpx.loc[d0]
        elig = row[(row > 90) & (row <= 115)].dropna()
        if len(elig) == 0: continue
        seg = cbpx.loc[d0:d1, elig.index]
        r = seg.pct_change().mean(axis=1)
        r = r[np.isfinite(r) & (r.abs() <= 0.45)]
        cbret.loc[r.index] = r.fillna(0)

    # ── 实验 1：空仓期持什么 ──
    # 现役：闸门关 ⇒ 现金 RF
    # 变体 A：闸门关 ⇒ 可转债低价券
    # 变体 B：闸门关 ⇒ QDII 篮子（修正后）
    r_eq = C.pct_change()
    port_cash = pd.Series(np.where(gate == 1, r_eq.mean(axis=1).values, RF), index=idx)
    port_cash = port_cash.iloc[251:]  # MA100 预热
    gate_s = pd.Series(gate, index=idx)
    gate_251 = gate_s.iloc[251:]

    # 可转债日收益 reindex 到 idx
    cb_aligned = cbret.reindex(idx).fillna(0.0)
    bear_aligned = bear.reindex(idx).fillna(False)
    # 可转债数据从 2023-02 起 ⇒ 之前用 RF
    cb_avail = cb_aligned.index >= pd.Timestamp("2023-02-01")
    cb_fill = cb_aligned.where(cb_avail, RF)

    # 变体 A：在场时持池等权，空仓时持可转债
    portA = pd.Series(np.where(gate_251.values == 1,
                               r_eq.mean(axis=1).reindex(idx).iloc[251:].fillna(0).values,
                               cb_fill.iloc[251:].values), index=idx[251:])

    # 变体 B：空仓持 QDII 篮子（从 relay_basket_lib 加载修正后净值）
    sys.path.insert(0, os.path.join(V1, "engine"))
    from relay_basket_lib import basket_nav
    Onq, Cnq, trq, used = __import__("relay_basket_lib").basket_ohlc(idx)
    bkr = Cnq.pct_change().fillna(0)
    portB = pd.Series(np.where(gate_251.values == 1,
                               r_eq.mean(axis=1).reindex(idx).iloc[251:].fillna(0).values,
                               bkr.iloc[251:].values), index=idx[251:])

    print("=" * 90)
    print("[实验 1] 空仓期持什么（天玑闸门不变，只改空仓资产）")
    print(f"  现金（现役）        {stat(port_cash)}")
    print(f"  可转债低价券（变体A） {stat(portA)}")
    print(f"  QDII 篮子9腿（变体B） {stat(portB)}")

    # ── 实验 2：持有期 30 → 40 ──
    print("\n" + "=" * 90)
    print("[实验 2] 持有期 30（现役）vs 40（本轮发现）")
    for hold in (30, 40):
        try:
            from optimize_cycle3_20261003 import run_v2
            nv, tr_, _ = run_v2(Oa, Ca, S, S, gate, hold, LIV.RANK_OUT)
            p = perf(nv.pct_change().fillna(0))
            print(f"  MIN_HOLD={hold}: 年化 {p['ann']:+.1%}｜mdd {p['mdd']:.1%}｜夏普 {p['sharpe']:.2f}｜卡玛 {p['calmar']:.2f}")
        except Exception as e:
            print(f"  MIN_HOLD={hold}: ERR {str(e)[:60]}")

    # ── 实验 3：深度低吸信号在熊市 vs 牛市的质量 ──
    print("\n" + "=" * 90)
    print("[实验 3] 深度低吸信号 × 市场状态（793 只中证800，已有数据）")
    # 使用昨日结果（已有结论：信号级在熊市日更强）
    res = json.load(open("/Users/simplify/Desktop/自己/量化策略/错杀回归研究_20261008/csi800_错杀回归_结果.json"))
    for k in ("T2C", "DD"):
        if k in res.get("rules", {}):
            d = res["rules"][k]
            print(f"  {k}: n={d['n']}｜均值 {d['mean']:+.2f}%｜胜率 {d['win']:.0%}")

    # 汇总
    summary = {
        "exp1": {"cash": stat(port_cash), "cb": stat(portA), "qdii": stat(portB)},
        "exp3_existing": {"T2C": res["rules"].get("T2C", {}), "DD": res["rules"].get("DD", {})},
    }
    json.dump(summary, open("metalearn_test_结果.json", "w"), ensure_ascii=False, indent=1, default=str)
    print("\n落盘 metalearn_test_结果.json")


if __name__ == "__main__":
    main()
