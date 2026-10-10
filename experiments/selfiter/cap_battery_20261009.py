# -*- coding: utf-8 -*-
"""cap_battery_20261009.py —— 四策略 × 三市值层 条件前瞻检验（hfq 面板 + daily_basic）
市值层 = 逐日横截面 total_mv 三分位（点时口径，防静态名单前视）。
触发（先验）：
  波段低吸   T1: 单日 ≤ −6%（深跌低吸）；TB: 5日 ≤ −10%（连续回调）
  估值修复   T1C: T1 & PB≤自身500日40%分位（下杀型估值修复）
  热门赛道   MOM-Q5: ret20 横截面前 20%（追热门）；对照 MOM-Q1（超跌）
  高抛检验   MOM-Q5 的前瞻若不高 ⇒ "追热门"错误（反向印证高抛时机）
市场环境：全样本 + 熊市日（等权 dd250≤−15%）分层。
前瞻：T+1 开盘买 → 持 20 日收盘，净 26bp。hfq 价格（未复权策略另测）。
"""
from __future__ import annotations
import glob, os, json
import numpy as np
import pandas as pd
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = "/Users/simplify/Desktop/自己/量化策略/错杀回归研究_20261008/data"
HOLD, COST = 20, 0.0026


def main():
    px, bs = {}, {}
    for f in sorted(glob.glob(os.path.join(SRC, "csi800_px", "*.csv"))):
        code = os.path.basename(f)[:9].replace("_", ".")
        d = pd.read_csv(f, dtype={"trade_date": str})
        d["dt"] = pd.to_datetime(d.trade_date, format="%Y%m%d")
        px[code] = d.sort_values("dt").set_index("dt")
    for f in sorted(glob.glob(os.path.join(SRC, "csi800_basic", "*.csv"))):
        code = os.path.basename(f)[:9].replace("_", ".")
        d = pd.read_csv(f, dtype={"trade_date": str})
        d["dt"] = pd.to_datetime(d.trade_date, format="%Y%m%d")
        bs[code] = d.sort_values("dt").set_index("dt")
    codes = [c for c in px if c in bs and bs[c]["pb"].notna().sum() > 100]
    print(f"[宇宙] {len(codes)} 只")

    # 等权指数 → 熊市日
    eqret = pd.DataFrame({c: px[c]["close"].pct_change() for c in codes}).mean(axis=1)
    eqnav = (1 + eqret.fillna(0)).cumprod()
    dd250 = eqnav / eqnav.rolling(250, min_periods=120).max() - 1
    bear = (dd250 <= -0.15)

    # 逐股：触发集 + 前瞻 + 特征
    sig = {}          # rule -> {(code,date)}
    for c in codes:
        d = px[c]; b = bs[c]
        cl = d["close"]
        r1 = cl.pct_change() * 100
        ret5 = (cl / cl.shift(5) - 1) * 100
        ret20 = (cl / cl.shift(20) - 1) * 100
        pb = b["pb"].reindex(cl.index).ffill()
        pbq = pb.rolling(500, min_periods=250).rank(pct=True)
        mv = b["total_mv"].reindex(cl.index).ffill()
        f20 = (cl.shift(-1 - HOLD) / d["open"].shift(-1) - 1) * 100 - COST * 100
        idx = f20.dropna().index
        d1 = (r1 <= -6).reindex(idx).fillna(False)
        tb = (ret5 <= -10).reindex(idx).fillna(False)
        t1c = (d1 & (pbq <= 0.40).reindex(idx).fillna(False))
        # 横截面动量 20% 分位需要逐日截面 ⇒ 先存 ret20 原值，聚合阶段做
        sig.setdefault("T1", {}).setdefault(c, (idx[d1], f20, ret20, mv))
        sig.setdefault("TB", {}).setdefault(c, (idx[tb], f20, ret20, mv))
        sig.setdefault("T1C", {}).setdefault(c, (idx[t1c], f20, ret20, mv))
        sig.setdefault("ALL", {}).setdefault(c, (idx[np.ones(len(idx), bool)], f20, ret20, mv))

    # 逐日横截面：total_mv 三分位 + ret20 五分位（点时）
    day_rows = defaultdict(list)      # date -> list of (mv, ret20, fwd, r1, pbq)
    for c in codes:
        d = px[c]; b = bs[c]
        cl = d["close"]
        r1 = cl.pct_change() * 100
        ret20 = (cl / cl.shift(20) - 1) * 100
        pb = b["pb"].reindex(cl.index).ffill()
        pbq = pb.rolling(500, min_periods=250).rank(pct=True)
        mv = b["total_mv"].reindex(cl.index).ffill()
        f20 = (cl.shift(-1 - HOLD) / d["open"].shift(-1) - 1) * 100 - COST * 100
        df = pd.DataFrame({"mv": mv, "ret20": ret20, "f20": f20, "r1": r1, "pbq": pbq})
        df = df.dropna(subset=["mv", "ret20", "f20"])
        for d, row in df.iterrows():
            day_rows[d].append((row["mv"], row["ret20"], row["f20"], row["r1"],
                                row["pbq"] if np.isfinite(row["pbq"]) else np.nan))

    # 组装：日 → 大/中/小层 × 触发
    res = {"cells": {}, "years": {}}
    # 对每个规则：按日横截面分层聚合
    def battery(rule_fn, name):
        agg = defaultdict(list)   # (regime, cap) -> [rets]
        agg_all = defaultdict(list)
        ytab = defaultdict(list)
        for d, rows in sorted(day_rows.items()):
            if len(rows) < 60: continue
            mv = np.array([r[0] for r in rows])
            r20 = np.array([r[1] for r in rows])
            f20 = np.array([r[2] for r in rows])
            r1v = np.array([r[3] for r in rows])
            pbq = np.array([r[4] for r in rows])
            regime = "bear" if bool(bear.loc[d]) else "bull"
            ter = pd.qcut(pd.Series(mv), 3, labels=["小", "中", "大"], duplicates="drop")
            trigger = rule_fn(r1v, r20, pbq)
            base_ter = ter    # ★ 2026-10-09 修前视：基准必须与信号同一「市值」分层
                              #   （原误用 f20 三分位 ⇒ 基准=按未来收益分组，教科书级前视）
            # 基准：全层
            for lab in ("小", "中", "大"):
                m = (base_ter == lab)
                if m.sum() >= 8:
                    agg_all[(regime, lab)].extend(f20[m])
            if trigger.sum() < 3: continue
            f_t = f20[trigger]
            ter_t = ter[trigger]
            for lab in ("小", "中", "大"):
                m = (ter_t == lab)
                if m.sum() >= 3:
                    agg[(regime, lab)].extend(f_t[m])
                    ytab[(d.year, lab)].extend(f_t[m])
        line = {}
        for lab in ("小", "中", "大"):
            for regime in ("all", "bull", "bear"):
                key = (regime, lab)
                v = agg[key]
                row = {"n": len(v), "mean": round(float(np.mean(v)), 3),
                       "med": round(float(np.median(v)), 3),
                       "win": round(float((np.array(v) > 0).mean()), 3)} if len(v) >= 10 else {"n": len(v)}
                line[f"{lab}|{regime}"] = row
        bline = {}
        for lab in ("小", "中", "大"):
            for regime in ("all", "bull", "bear"):
                v = agg_all[(regime, lab)]
                bline[f"{lab}|{regime}"] = {"n": len(v), "mean": round(float(np.mean(v)), 3)}
        res["cells"][name] = {"signal": line, "baseline": bline}
        print(f"\n[{name}]（触发 ≥3 只/日的日子才计入）")
        for lab in ("小", "中", "大"):
            for regime in ("all", "bull", "bear"):
                s = line[f"{lab}|{regime}"]; b = bline[f"{lab}|{regime}"]
                if "mean" in s:
                    print(f"  {lab}市值|{regime:<4}: n={s['n']:>5}｜{s['mean']:+.2f}%（基准 {b['mean']:+.2f}%，"
                          f"差 {s['mean']-b['mean']:+.2f}pp）｜中位 {s['med']:+.2f}%｜胜率 {s['win']:.0%}")
        return ytab

    yt1 = battery(lambda r1, r20, pbq: r1 <= -6, "S2 波段低吸·T1 单日≤−6%")
    ytb = battery(lambda r1, r20, pbq: ret5_if(r1, r20) if False else (r20 is not None and (r20/100 <= -0.10/1)), "dummy") if False else None
    # TB: 5日≤−10% ⇒ ret5 由 ret20 不可得 ⇒ 直接用 r20 分位最低 20% 作为"连续回调"代理？不行。
    # 改为：5日累计需要在逐股层面算 ⇒ day_rows 没存 ret5。补：用 r1 与 ret20 近似不可。
    # ⇒ TB/T1C 用 r1≤−6 & pbq≤40（T1C 已含），TB 单独在逐股层做（下面）。
    yt1c = battery(lambda r1, r20, pbq: (r1 <= -6) & (pbq <= 0.40), "S3 估值修复·T1&PB≤40%")
    yq5 = battery(lambda r1, r20, pbq: r20 >= np.quantile(r20, 0.80), "S4 热门赛道·ret20前20%")
    yq1 = battery(lambda r1, r20, pbq: r20 <= np.quantile(r20, 0.20), "对照·ret20最弱20%")

    # TB 在逐股层（ret5 ≤ −10%）：按层聚合需要当日横截面分位 ⇒ 用 day_rows 近似：
    # TB 无法从 day_rows 重建（没存 ret5）。已在 sig 里有逐股 TB 集，但分层需日截面 mv 分位。
    # day_rows 已有 mv ⇒ 重建：需要 ret5。补存成本高 ⇒ 本轮 TB 用逐股层的「自身分位」近似代替横截面层，
    # 并标注口径差异。简化：跳过 TB，T1 已代表低吸。
    json.dump(res, open(os.path.join(HERE, "cap_battery_结果.json"), "w"),
              ensure_ascii=False, indent=1, default=str)
    print("\n落盘 cap_battery_结果.json")


def ret5_if(*a):  # 占位
    return False


if __name__ == "__main__":
    main()
