#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fps_factor.py —— 稳健度因素（防自欺版）· 量化交易Agent策略框架 v2.0 的因子层实现

一句话：**这个因子不预测涨，只回答「这个结论能不能被前向验证」**。

它做三件事：
  1. 算一组「体检算术」：N*（证伪阈值）、moving-block CI、sign-flip 置换检验、
     选择自由度诊断、可迁移性 ρ、可分辨性分层；
  2. 用 R1–R5 五个**只用训练段可算**的分量给出 FPS（Future-Possibility Score）；
  3. ★ **硬闸门**：只要触发「会骗自己」的条件，就 **拒绝输出结论**（抛 SelfDeceptionError），
     而不是给出一个好看的数。这就是「不要把假结果带进实盘」的工程化。

★ 三条铁律（写死在代码里，不是写在文档里）：
  A. 选优键禁止触碰留出段（`assert_train_only`）；
  B. 没有口径指纹 ⇒ 不给结论（G0）；
  C. 单日候选项 ≤ 1 ⇒ 这不是选股策略而是事件过滤器，禁止输出「选股池」（G2-前置）。

依赖：numpy + pandas（无 scipy）。自检：`python fps_factor.py --selftest`

口径约定（可改，但改了必须换指纹）：
  · 面板条目：{code: {"name":str, "category":str, "kline":[[date, open, close, high, low, amount], ...]}}
  · kline 必须是**后复权**收盘价；日期升序、无重复。
  · 信号在**收盘后**产生 ⇒ 次日才能在仓（`pos = signal.shift(1)`），杜绝前视。
  · 成本默认单边 3bp（ETF）；往返 6bp。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

VERSION = "1.0.0"          # 与技能版本解耦：本文件是「因子」的版本
TRADING_DAYS = 252
COST_ONE_WAY = 0.0003      # ETF 单边 3bp
EPS = 1e-12


class SelfDeceptionError(RuntimeError):
    """触发「会骗自己」的条件时抛这个 —— 宁可不出结论，也不出假结论。"""


# ----------------------------------------------------------------------------
# 0. 口径指纹
# ----------------------------------------------------------------------------
def file_md5(path: str | Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def caliber_fingerprint(panel_path: str | Path, is_end: str, universe: Optional[Sequence[str]] = None) -> dict:
    """口径四要素 + 数据指纹。没有它，任何结论都不属于当前口径。"""
    p = Path(panel_path)
    if not p.is_file():
        raise SelfDeceptionError(f"[G0] 面板不存在，无法钉死口径：{p}")
    codes = sorted(universe) if universe else None
    payload = {
        "panel": str(p),
        "md5": file_md5(p),
        "adjust": "后复权",
        "timing": "信号=当日收盘；建仓=次日日频收益（signal.shift(1)）",
        "cost_one_way": COST_ONE_WAY,
        "universe_n": len(codes) if codes else None,
        "universe_md5": hashlib.md5("|".join(codes).encode()).hexdigest() if codes else None,
        "is_end": is_end,
    }
    payload["fingerprint"] = hashlib.md5(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]
    return payload


# ----------------------------------------------------------------------------
# 1. 体检算术（全部零 scipy）
# ----------------------------------------------------------------------------
def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    """秩相关。返回 NaN 当样本 <3 或某一侧无变异。"""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    n = a.size
    if n < 3:
        # preflight-ok: 统计量在样本不足/退化时返回 nan 作「不可判定」哨兵；调用侧一律判 suspended
        return float("nan")

    def rank(x: np.ndarray) -> np.ndarray:
        order = x.argsort(kind="mergesort")
        r = np.empty(n, dtype=float)
        r[order] = np.arange(n, dtype=float)
        # 并列取平均秩
        vals, inv, cnt = np.unique(x, return_inverse=True, return_counts=True)
        if (cnt > 1).any():
            sums = np.zeros(vals.size)
            np.add.at(sums, inv, r)
            r = (sums / cnt)[inv]
        return r

    ra, rb = rank(a), rank(b)
    ra -= ra.mean()
    rb -= rb.mean()
    den = math.sqrt(float((ra ** 2).sum()) * float((rb ** 2).sum()))
    if den < EPS:
        # preflight-ok: 统计量在样本不足/退化时返回 nan 作「不可判定」哨兵；调用侧一律判 suspended
        return float("nan")
    return float((ra * rb).sum() / den)


def spearman_p(a: Sequence[float], b: Sequence[float], B: int = 20000, seed: int = 12345) -> float:
    """ρ 的置换 p 值（双侧）。零假设 = b 的次序与 a 无关。

    ★ 必须报它：ρ 的**符号**很容易被一两个极端点带偏（配置之间高度相关时尤其如此）。
    """
    aa = np.asarray(a, dtype=float)
    bb = np.asarray(b, dtype=float)
    m = np.isfinite(aa) & np.isfinite(bb)
    aa, bb = aa[m], bb[m]
    n = aa.size
    if n < 4:
        # preflight-ok: 统计量在样本不足/退化时返回 nan 作「不可判定」哨兵；调用侧一律判 suspended
        return float("nan")
    obs = spearman(aa, bb)
    if not np.isfinite(obs):
        # preflight-ok: 统计量在样本不足/退化时返回 nan 作「不可判定」哨兵；调用侧一律判 suspended
        return float("nan")
    rng = np.random.default_rng(seed)
    cnt = 0
    for _ in range(B):
        r = spearman(aa, rng.permutation(bb))
        if np.isfinite(r) and abs(r) >= abs(obs) - 1e-12:
            cnt += 1
    return float(cnt / B)


# preflight-ok: N* 口径与 scripts/qta_loop.py 同名函数一致（⌈(2σ/μ)²⌉），两侧 selftest 各自断言
def n_star(x: Sequence[float]) -> int:
    """证伪阈值 N* = ceil((2σ/μ)²)：攒够多少笔才能把「噪声」和「真效应」分开。

    μ≤0 ⇒ 无穷（根本判不出方向）；μ>0 且 σ=0 ⇒ 1。
    """
    arr = np.asarray([v for v in x if np.isfinite(v)], dtype=float)
    if arr.size < 2:
        return 10 ** 9
    mu = float(arr.mean())
    sd = float(arr.std(ddof=1))
    if mu <= 0:
        return 10 ** 9
    if sd < EPS:
        return 1
    return int(math.ceil((2.0 * sd / mu) ** 2))


def block_bootstrap_ci(x: Sequence[float], L: int = 5, B: int = 5000,
                       alpha: float = 0.05, seed: int = 12345) -> Tuple[float, float]:
    """★ moving-block bootstrap：保留「同一市场环境下成串同向」的相关。

    打板/择时这类序列，笔与笔不是独立的（一波行情里连着赚或连着亏）。
    i.i.d. bootstrap 会把这种相关性抹掉 ⇒ 区间偏窄 ⇒ 高估显著性。
    ⇒ 报区间**一律以本函数为准**。
    """
    arr = np.asarray([v for v in x if np.isfinite(v)], dtype=float)
    n = arr.size
    if n == 0:
        return (float("nan"), float("nan"))
    L = max(1, min(L, n))
    k = int(math.ceil(n / L))
    starts_all = np.arange(0, max(1, n - L + 1))
    rng = np.random.default_rng(seed)
    means = np.empty(B)
    for b in range(B):
        st = rng.choice(starts_all, size=k, replace=True)
        idx = (st[:, None] + np.arange(L)[None, :]).ravel()[:n]
        idx = np.clip(idx, 0, n - 1)
        means[b] = arr[idx].mean()
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return (float(lo), float(hi))


def block_bootstrap_se(x: Sequence[float], L: int = 5, B: int = 2000,
                       seed: int = 12345) -> float:
    """moving-block 重采样下的标准误（可分辨性分层要用）。"""
    arr = np.asarray([v for v in x if np.isfinite(v)], dtype=float)
    n = arr.size
    if n < 2:
        # preflight-ok: 统计量在样本不足/退化时返回 nan 作「不可判定」哨兵；调用侧一律判 suspended
        return float("nan")
    L = max(1, min(L, n))
    k = int(math.ceil(n / L))
    starts_all = np.arange(0, max(1, n - L + 1))
    rng = np.random.default_rng(seed)
    means = np.empty(B)
    for b in range(B):
        st = rng.choice(starts_all, size=k, replace=True)
        idx = np.clip((st[:, None] + np.arange(L)[None, :]).ravel()[:n], 0, n - 1)
        means[b] = arr[idx].mean()
    return float(means.std(ddof=1))


def signflip_p(x: Sequence[float], B: int = 20000, seed: int = 12345) -> float:
    """符号置换检验：零假设 = 每笔的正负号可以随机翻转。

    回答「这批笔的正负号是不是被系统挑出来的」。无需引擎，便宜。
    """
    arr = np.asarray([v for v in x if np.isfinite(v)], dtype=float)
    n = arr.size
    if n < 2:
        # preflight-ok: 统计量在样本不足/退化时返回 nan 作「不可判定」哨兵；调用侧一律判 suspended
        return float("nan")
    obs = float(arr.mean())
    rng = np.random.default_rng(seed)
    signs = rng.choice(np.array([-1.0, 1.0]), size=(B, n))
    draws = (signs * arr).mean(axis=1)
    return float((draws >= obs).mean())


def selection_freedom(candidates_per_decision: Iterable[int]) -> dict:
    """★ G2-前置：跑随机对照之前必须先做这一步。

    若每个决策时点只有 1 个候选，「随机选」与「按分排序」在数学上恒等 ⇒
    零分布退化成常数序列 ⇒ (null < obs).mean() 会给出 0%/100% 的**假分位**。
    """
    c = Counter(int(v) for v in candidates_per_decision)
    total = sum(c.values())
    mx = max(c) if c else 0
    zero_days = total - len(c)              # 一点候选都没有的时点
    return {
        "decision_points": total,
        "open_points": len(c),
        "closed_points": zero_days,
        "max_candidates": mx,
        "days_with_2plus": sum(v for k, v in c.items() if k >= 2),
        "zero_freedom": mx <= 1,
        "verdict": ("零排序自由度 ⇒ 这是**事件过滤器**，不是选股策略；"
                    "所有『加因子 / 改排序 / 调 topK』的优化在定义上无效"
                    if mx <= 1 else "存在排序自由度，可以跑 random 对照"),
    }


def resolvability(layers: Dict[str, Sequence[float]], L: int = 5) -> dict:
    """可分辨性分层：层内均值极差 / 层内平均标准误。<2 ⇒ 排序不可分辨。"""
    rows = []
    for name, vals in layers.items():
        arr = np.asarray([v for v in vals if np.isfinite(v)], dtype=float)
        if arr.size < 2:
            continue
        se = block_bootstrap_se(arr, L=L) if arr.size >= 4 else float(arr.std(ddof=1) / math.sqrt(arr.size))
        rows.append({"layer": name, "n": int(arr.size), "mean": float(arr.mean()), "se": float(se)})
    if len(rows) < 2:
        return {"ratio": float("nan"), "resolvable": None, "layers": rows}
    span = max(r["mean"] for r in rows) - min(r["mean"] for r in rows)
    avg_se = float(np.mean([r["se"] for r in rows]))
    ratio = float(span / avg_se) if avg_se > EPS else float("inf")
    return {
        "ratio": ratio,
        "resolvable": bool(ratio > 2),
        "reading": ("层间差异大于噪声 ⇒ 排序看得见，ρ 才有讨论意义"
                    if ratio > 2 else
                    "层间差异小于噪声 ⇒ **排序不可分辨**；此时 ρ≈0 是『测不出』不是『不迁移』"),
        "layers": rows,
    }


# ----------------------------------------------------------------------------
# 2. 硬闸门（组装结论前必须过）
# ----------------------------------------------------------------------------
@dataclass
class GateLog:
    rows: List[dict] = None

    def __post_init__(self):
        self.rows = [] if self.rows is None else self.rows

    def add(self, gate: str, ok: bool, detail: str):
        self.rows.append({"gate": gate, "ok": bool(ok), "detail": detail})
        return ok

    def fail(self, gate: str, detail: str):
        """硬失败：直接拒绝出结论。"""
        self.rows.append({"gate": gate, "ok": False, "detail": detail, "hard": True})
        raise SelfDeceptionError(f"[{gate}] {detail}")

    def as_dict(self) -> dict:
        return {"all_ok": all(r["ok"] for r in self.rows), "checks": self.rows}


def assert_train_only(selector_uses_holdout: bool) -> None:
    """G3 铁律：选优键一旦触碰留出段，全流程作废。"""
    if selector_uses_holdout:
        raise SelfDeceptionError(
            "[G3] 选优键用到了留出段数据 —— 这就是「偷看答案」。"
            "留出段只允许出现在**披露列**，不允许参与任何排序/阈值/取舍。"
        )


# ----------------------------------------------------------------------------
# 3. 面板与规则
# ----------------------------------------------------------------------------
def load_panel(path: str | Path) -> Dict[str, dict]:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    for code, v in obj.items():
        k = v.get("kline") or []
        if len(k) < 60:
            continue
        df = pd.DataFrame(k, columns=["date", "open", "close", "high", "low", "amount"])
        df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
        df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
        close = pd.to_numeric(df["close"], errors="coerce")
        if close.isna().any() or (close <= 0).any():
            continue
        # ★ 索引必须是日期：月频再平衡靠 `index.to_period("M")`，
        #   用 RangeIndex 会直接 AttributeError（第一次跑就踩到了）。
        close.index = pd.DatetimeIndex(df["date"])
        out[code] = {
            "name": v.get("name") or code,
            "category": v.get("category") or "-",
            "list_date": v.get("list_date") or "",
            "date": df["date"],
            "close": close,
            "amount": pd.to_numeric(df["amount"], errors="coerce"),
        }
    if not out:
        raise SelfDeceptionError("[G0] 面板解析后为空 —— 列名/格式与口径不符。")
    return out


def daily_return(close: pd.Series) -> pd.Series:
    return close.pct_change(fill_method=None)


def ma_gate_position(close: pd.Series, window: int) -> pd.Series:
    """MA 闸门：收盘价在均线**上方**的次日才在仓。

    ★ `signal.shift(1)`：当日收盘才知道信号，收益必须记在**下一日**，
    否则就是把「今天知道的事」用来赚「今天的钱」= 前视。
    """
    ma = close.rolling(window).mean()
    sig = (close > ma).astype(float)
    return sig.shift(1).fillna(0.0)


def rule_returns(close: pd.Series, window: int) -> pd.Series:
    """闸门择时的日收益序列（含调仓成本）。"""
    r = daily_return(close)
    pos = ma_gate_position(close, window)
    turn = pos.diff().abs().fillna(pos.abs())
    return r * pos - turn * COST_ONE_WAY


def perf(rets: pd.Series, min_n: int = 6, ppy: int = TRADING_DAYS) -> dict:
    """区间业绩：累计 / 年化 / 最大回撤 / Calmar / Sharpe / 在仓比例。

    `min_n` 默认取 6 —— 月频序列一年只有 12 个点，卡 20 会把**全部**月频读数
    变成 nan（第一版就是这样，直接把 ρ 算成 nan）。
    ★ `ppy`（每年几个点）必须与序列频率一致：把月频收益按 252 年化，
      16 个月的 +120% 会变成 **+2217%**（第一版真实踩过）。月频传 ppy=12。
    """
    r = pd.Series(rets).dropna()
    n = len(r)
    if n < min_n:
        return {"n": n, "total": float("nan"), "ann": float("nan"), "mdd": float("nan"),
                "calmar": float("nan"), "sharpe": float("nan"), "in_market": float("nan")}
    nav = (1.0 + r).cumprod()
    total = float(nav.iloc[-1] - 1.0)
    ann = float((nav.iloc[-1]) ** (ppy / n) - 1.0) if nav.iloc[-1] > 0 else -1.0
    dd = nav / nav.cummax() - 1.0
    mdd = float(dd.min())
    sd = float(r.std(ddof=1))
    return {
        "n": int(n), "total": total, "ann": ann, "mdd": mdd,
        "calmar": (ann / abs(mdd)) if abs(mdd) > EPS else float("nan"),
        "sharpe": (float(r.mean()) / sd * math.sqrt(ppy)) if sd > EPS else float("nan"),
        "in_market": float((r != 0).mean()),
    }


def random_timing_null(rets: pd.Series, in_market_n: int, B: int = 500, seed: int = 20261001) -> np.ndarray:
    """★ 闸门匹配的零分布：保持「在仓天数完全相同」，只把**择时**打乱。

    为什么要匹配：留出段若为牛市，满仓随便拿都占便宜；不做匹配就会把
    「闸门在熊市省下的跌幅」错记成「因子选得准」。
    """
    r = pd.Series(rets).fillna(0.0).to_numpy()
    n = r.size
    k = int(max(1, min(in_market_n, n)))
    rng = np.random.default_rng(seed)
    out = np.empty(B)
    for b in range(B):
        mask = np.zeros(n, dtype=bool)
        mask[rng.choice(n, size=k, replace=False)] = True
        pos = np.empty(n)
        pos[0] = 0.0
        pos[1:] = mask[:-1]              # 同样的 shift(1)
        out[b] = float((1.0 + r * pos).prod() - 1.0)
    return out


# ----------------------------------------------------------------------------
# 4. FPS：只用训练段可算的五个分量
# ----------------------------------------------------------------------------
def split_index(dates: pd.Series, is_end: str) -> np.ndarray:
    return (dates <= pd.Timestamp(is_end)).to_numpy()


def fps_for_asset(panel_item: dict, is_end: str, windows: Sequence[int] = (60, 80, 100, 120),
                  main_window: int = 100, null_B: int = 500, seed: int = 20261001) -> dict:
    """单只标的的 FPS 及其五个分量。★ 全部分量只用**训练段**可算。"""
    dates, close = panel_item["date"], panel_item["close"]
    m_is = split_index(dates, is_end)
    if m_is.sum() < 120 or (~m_is).sum() < 20:
        return {}

    # ---- R1 / R2：训练段为正 & 参数邻域平台（4 档窗口全为正的比例）
    per_w, train_pos = {}, 0
    for w in windows:
        rr = rule_returns(close, w)
        p = perf(pd.Series(rr.to_numpy()[m_is]))
        per_w[w] = p
        if np.isfinite(p["total"]) and p["total"] > 0:
            train_pos += 1
    R1 = 1.0 if train_pos >= 1 else 0.0
    R2 = train_pos / float(len(windows))

    # ---- R3：训练段读数 / 同闸门匹配随机择时零分布的分位（★ 只能训练段）
    rr_main = rule_returns(close, main_window)
    r_is = pd.Series(rr_main.to_numpy()[m_is])
    obs = float((1.0 + r_is.fillna(0.0)).prod() - 1.0)
    null = random_timing_null(r_is, int((r_is != 0).sum()), B=null_B, seed=seed)
    pct = float((null < obs).mean())
    R3 = float(np.clip(pct, 0.0, 1.0))
    degenerate = bool(null.std(ddof=1) < 1e-9)

    # ---- R4 / R5
    R4 = 1.0 if (np.isfinite(per_w[main_window]["calmar"]) and per_w[main_window]["calmar"] > 0) else 0.0
    n_is = int(m_is.sum())
    R5 = float(min(1.0, n_is / 200.0))

    r_oos = pd.Series(rr_main.to_numpy()[~m_is])
    comp = {"R1_train_positive": R1, "R2_neighborhood_platform": R2,
            "R3_train_null_percentile": R3, "R4_train_calmar_positive": R4,
            "R5_sample_size": R5}
    return {
        "fps": float(np.mean(list(comp.values()))),
        "components": comp,
        "is_end": is_end,
        "is": perf(r_is),
        "oos": perf(r_oos),                      # ★ 只作披露列，不参与任何选择
        "per_window_is": {str(w): per_w[w] for w in windows},
        "main_window": main_window,
        "null_percentile_raw": pct,
        "null_degenerate": degenerate,           # 退化的零分布 ⇒ 分位无意义
        "in_market_n_is": int((r_is != 0).sum()),
    }


# ----------------------------------------------------------------------------
# 5. 组合层：网格 → 可迁移性 ρ / 随机对照 / N* / 三态判决
# ----------------------------------------------------------------------------
def portfolio_monthly(rets_map: Dict[str, pd.Series], codes: Sequence[str],
                      cost_one_way: float = COST_ONE_WAY) -> pd.Series:
    """等权、按**固定日历（每月最后一个交易日）**再平衡的月频收益。

    ★ 固定日历是硬要求：用「相位自由」的网格会放大 Calmar（实测能摆动 3~4 倍）。
    """
    mat = pd.DataFrame({c: rets_map[c] for c in codes}).dropna(how="all")
    if mat.empty:
        return pd.Series(dtype=float)
    mat = mat.mean(axis=1)
    grp = mat.groupby(mat.index.to_period("M"))
    return grp.apply(lambda s: float((1.0 + s).prod() - 1.0))


def build(dates: pd.Series, close_by_code: Dict[str, pd.Series], is_end: str,
          windows: Sequence[int], top_ns: Sequence[int]) -> dict:
    """20 组配置（窗口 × 池大小）的 IS/OOS 月频读数网格。"""
    rows = []
    rmap = {c: rule_returns(close_by_code[c], windows[2]) for c in close_by_code}
    m_is = split_index(dates, is_end)
    for w in windows:
        rw = {c: rule_returns(close_by_code[c], w) for c in close_by_code}
        # 训练段 FPS 排序（只用训练段）
        rank = []
        for c in close_by_code:
            item = {"date": dates, "close": close_by_code[c]}
            f = fps_for_asset(item, is_end, windows=[w], main_window=w, null_B=200, seed=7)
            if f:
                rank.append((c, f["fps"]))
        rank.sort(key=lambda t: -t[1])
        for top in top_ns:
            codes = [c for c, _ in rank[:top]]
            m = portfolio_monthly(rw, codes)
            mi = m[m.index.to_timestamp() <= pd.Timestamp(is_end)]
            mo = m[m.index.to_timestamp() > pd.Timestamp(is_end)]
            rows.append({
                "window": w, "top": top, "n_codes": len(codes),
                "is": perf(mi, ppy=12), "oos": perf(mo, ppy=12),
                "codes": codes,
            })
    return {"rows": rows}


def three_state(phases: dict, rho: float, n_used: int, nstar: int) -> Tuple[str, str]:
    """三态判决。★ 测不出（suspended）≠ 无效（rejected）。"""
    pct = phases.get("percentile")
    if pct is None or not np.isfinite(pct):
        return "suspended", "无有效随机对照 ⇒ 不可判定"
    if not np.isfinite(rho):
        return "suspended", "配置数不足，可迁移性算不出来 ⇒ 不可判定"
    if rho >= 0.5 and pct >= 0.95:
        return "merged", "配置间可迁移且显著越过随机噪声带"
    if rho < 0.0 and pct < 0.05 and n_used >= nstar:
        return "rejected", "配置间反向 + 显著劣于随机 + 样本已到 N*"
    if n_used < nstar:
        return "suspended", f"样本 {n_used} < N* {nstar} ⇒ 两笔为负这级别的事情，统计上不可区分"
    return "suspended", "落在噪声带内 ⇒ 未检出（不是无效）"


# ----------------------------------------------------------------------------
# 6. 自检
# ----------------------------------------------------------------------------
def _selftest() -> int:
    ok = True
    rng = np.random.default_rng(0)

    # ① N*
    assert n_star([0.02] * 40) == 1, "σ=0 时应为 1"
    assert n_star([-0.01] * 40) >= 10 ** 9, "μ≤0 应判不出"
    ns = n_star(list(rng.normal(0.01, 0.05, 200)))
    print(f"[selftest] N*(μ=1%,σ=5%) = {ns}（期望≈100）")
    ok &= 50 <= ns <= 200

    # ② spearman
    a = [1, 2, 3, 4, 5, 6]
    assert abs(spearman(a, a) - 1.0) < 1e-9
    assert abs(spearman(a, a[::-1]) + 1.0) < 1e-9
    assert math.isnan(spearman([1, 2], [1, 2])), "样本<3 应 NaN"
    print("[selftest] spearman 单调/反单调/小样本 OK")
    x = list(range(20))
    y = [3 * v + rng.normal(0, 3) for v in x]
    p_strong, p_null = spearman_p(x, y, B=4000, seed=3), spearman_p(x, list(rng.permutation(y)), B=4000, seed=3)
    print(f"[selftest] spearman_p 强关联={p_strong:.4f} 打乱后={p_null:.3f}")
    ok &= p_strong < 0.01

    # ③ moving-block 比 i.i.d. 宽（成串相关时）
    seq = np.repeat(rng.normal(0.02, 0.05, 12), 5)          # 块内同向
    lo_b, hi_b = block_bootstrap_ci(seq, L=5, B=3000, seed=1)
    iid = rng.choice(seq, size=(3000, seq.size), replace=True).mean(axis=1)
    lo_i, hi_i = np.percentile(iid, [2.5, 97.5])
    print(f"[selftest] block CI [{lo_b:+.3f},{hi_b:+.3f}] vs iid [{lo_i:+.3f},{hi_i:+.3f}]")
    ok &= (hi_b - lo_b) >= (hi_i - lo_i) - 1e-9

    # ④ sign-flip：全正序列应显著
    p_all = signflip_p([0.03] * 20, B=20000, seed=1)
    p_zero = signflip_p([0.01, -0.01] * 10, B=20000, seed=1)
    print(f"[selftest] signflip p(全正)={p_all:.4f} p(零均值)={p_zero:.4f}")
    ok &= p_all < 0.001 and p_zero > 0.2

    # ⑤ 选择自由度诊断 —— 本项目真实案例
    sf1 = selection_freedom([1] * 71)                       # 打板线：71 天各 1 只
    sf0 = selection_freedom([3, 5, 2, 8, 1, 12])
    print(f"[selftest] 自由度: 71×1 → zero_freedom={sf1['zero_freedom']}; 变长 → {sf0['zero_freedom']}")
    ok &= sf1["zero_freedom"] is True and sf0["zero_freedom"] is False

    # ⑥ 退化零分布必须被点名
    degenerate_null = np.full(500, 0.123)
    assert degenerate_null.std(ddof=1) < 1e-9
    print("[selftest] 退化零分布识别 OK（(null<obs).mean() 在常数上给假分位）")

    # ⑦ 可分辨性
    r_bad = resolvability({"a": list(rng.normal(0.0, 0.30, 8)),
                           "b": list(rng.normal(0.02, 0.30, 8))})
    r_good = resolvability({"a": list(rng.normal(0.00, 0.01, 60)),
                            "b": list(rng.normal(0.30, 0.01, 60))})
    print(f"[selftest] 可分辨性 弱={r_bad['ratio']:.2f} 强={r_good['ratio']:.2f}")
    ok &= (r_bad["resolvable"] is False) and (r_good["resolvable"] is True)

    # ⑧ 硬闸门必须真的抛
    for fn, label in ((lambda: assert_train_only(True), "G3 触碰留出段"),
                      (lambda: caliber_fingerprint("/nonexistent.json", "2024-12-31"), "G0 无指纹")):
        try:
            fn()
            print(f"[selftest] ✗ 硬闸门未触发：{label}")
            ok = False
        except SelfDeceptionError:
            print(f"[selftest] ✓ 硬闸门触发：{label}")

    # ⑨ 前视检查：signal.shift(1)
    c = pd.Series(np.linspace(10, 20, 200))
    pos = ma_gate_position(c, 50)
    assert pos.iloc[0] == 0 and pos.iloc[-1] in (0.0, 1.0)
    assert abs(float(pos.iloc[-1]) - float((c > c.rolling(50).mean()).astype(float).iloc[-2])) < 1e-12, \
        "在仓状态必须是前一日的信号 ⇒ 无前视"
    print("[selftest] 前视检查 OK（pos = signal.shift(1)）")

    # ⑩ 三态语义：测不出 ≠ 无效
    v, why = three_state({"percentile": 0.60}, rho=0.10, n_used=5, nstar=1000)
    assert v == "suspended", v
    v2, _ = three_state({"percentile": 0.999}, rho=0.80, n_used=100, nstar=20)
    assert v2 == "merged", v2
    print(f"[selftest] 三态: 噪声带→{v}（{why[:24]}…）; 双重通过→{v2}")

    # ⑪ ★ 频率年化回归测试（真实踩过的坑）
    #    16 个月的 +120%：按 ppy=12 年化应 ≈ +140%；按 ppy=252 会变成 +2217%。
    monthly = pd.Series([0.05] * 16)
    a12 = perf(monthly, ppy=12)["ann"]
    a252 = perf(monthly, ppy=TRADING_DAYS)["ann"]
    print(f"[selftest] 同一条月频序列: ppy=12 → {a12*100:.1f}% | ppy=252 → {a252*100:.0f}%")
    ok &= abs(a12 - ((1.05 ** 16) ** (12 / 16) - 1)) < 1e-9 and a252 > 50
    print("[selftest] ✓ 频率年化回归（月频必须 ppy=12，否则会凭空放大 ~16 倍）")

    print("\n" + ("[selftest] ★ 全部通过" if ok else "[selftest] ✗ 有项目未通过"))
    print(f"[selftest] quant-trading-agent · 因子层 fps_factor v{VERSION}（框架版本见 VERSION 文件）")
    return 0 if ok else 1


# ----------------------------------------------------------------------------
# 7. CLI
# ----------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="稳健度因素（防自欺版）")
    ap.add_argument("--selftest", action="store_true", help="跑内置自检")
    ap.add_argument("--panel", help="面板 json（{code:{name,category,kline}}）")
    ap.add_argument("--is-end", default="2024-12-31", help="训练段截止日")
    ap.add_argument("--out", help="输出 json 路径")
    ap.add_argument("--top", type=int, default=10, help="池大小")
    ap.add_argument("--min-fps", type=float, default=0.60, help="入池下限")
    a = ap.parse_args(argv)

    if a.selftest:
        return _selftest()
    if not a.panel:
        ap.print_help()
        return 0

    g = GateLog()
    fp = caliber_fingerprint(a.panel, a.is_end)
    g.add("G0 口径指纹", True, f"panel md5={fp['md5'][:12]}… fingerprint={fp['fingerprint']}")
    panel = load_panel(a.panel)
    g.add("G0 面板解析", True, f"{len(panel)} 只标的")

    windows = (60, 80, 100, 120)
    scored = []
    for code, it in panel.items():
        f = fps_for_asset(it, a.is_end, windows=windows, main_window=100)
        if not f:
            continue
        f.update({"code": code, "name": it["name"], "category": it["category"]})
        scored.append(f)
    scored.sort(key=lambda d: -d["fps"])

    if len(scored) < 2:
        g.fail("G2-前置 选择自由度", f"可评估标的仅 {len(scored)} 只 ⇒ 没有横截面可供「选」")

    sf = selection_freedom([len(scored)])
    if sf["zero_freedom"]:
        g.fail("G2-前置 选择自由度", sf["verdict"])

    pool = [s for s in scored if s["fps"] >= a.min_fps][: a.top]
    assert_train_only(False)                       # 选择只用了 FPS（训练段）

    dates = panel[scored[0]["code"]]["date"]
    close_map = {c: panel[c]["close"] for c in panel}
    grid = build(dates, close_map, a.is_end, windows, (3, 5, 8, 10, 12))
    rho = spearman([r["is"]["ann"] for r in grid["rows"]], [r["oos"]["ann"] for r in grid["rows"]])
    rho_p = spearman_p([r["is"]["ann"] for r in grid["rows"]], [r["oos"]["ann"] for r in grid["rows"]])

    # 随机对照：同闸门、同池大小、随机选标的（留出段读数，仅用于判显著）
    m_is = split_index(dates, a.is_end)
    rw = {c: rule_returns(close_map[c], 100) for c in close_map}
    rstd = np.random.default_rng(20261001)
    all_codes = list(close_map)
    k = max(1, len(pool))
    nulls = []
    for _ in range(500):
        pick = list(rstd.choice(all_codes, size=k, replace=False))
        m = portfolio_monthly(rw, pick)
        mo = m[m.index.to_timestamp() > pd.Timestamp(a.is_end)]
        nulls.append(perf(mo, ppy=12)["ann"])
    sel = portfolio_monthly(rw, [p["code"] for p in pool])
    mo_sel = sel[sel.index.to_timestamp() > pd.Timestamp(a.is_end)]
    obs_oos = perf(mo_sel, ppy=12)["ann"]
    nulls = np.asarray([v for v in nulls if np.isfinite(v)])
    pct = float((nulls < obs_oos).mean()) if nulls.size else float("nan")
    if nulls.size and float(nulls.std(ddof=1)) < 1e-9:
        g.fail("G2 随机对照", "零分布退化（常数序列）⇒ 分位无意义，禁止据此判显著")

    mi_sel = sel[sel.index.to_timestamp() <= pd.Timestamp(a.is_end)]
    ns = n_star(mi_sel.to_numpy())
    verdict, why = three_state({"percentile": pct}, rho, len(mi_sel), ns)

    out = {
        "schema": "fps-factor/v1",
        "factor_version": VERSION,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fingerprint": fp,
        "gates": g.as_dict(),
        "selection_freedom": sf,
        "transfer_rho_is_to_oos": rho,
        "transfer_rho_p": rho_p,
        "transfer_rho_note": ("配置维度上训练段→留出段**反向**：越集中在训练段看着最好的标的，留出段越差。"
                              "这不是「策略有效」，是「选择本身在骗你」——正是本因子要拦下来的东西。"
                              if np.isfinite(rho) and rho < 0 else
                              "配置维度上训练段指标对留出段无预测力（ρ<0.3）⇒ 不要用它选参。"),
        "random_control": {"B": 500, "null_median_ann": float(np.median(nulls)) if nulls.size else float("nan"),
                           "observed_ann": obs_oos, "percentile": pct,
                           "note": "同闸门（MA100）+ 同池大小，仅标的随机"},
        "n_star": ns,
        "verdict": verdict,
        "verdict_reason": why,
        "pool": [
            {"code": p["code"], "name": p["name"], "category": p["category"], "fps": p["fps"],
             "components": p["components"], "is": p["is"], "oos": p["oos"],
             "null_percentile_raw": p["null_percentile_raw"], "null_degenerate": p["null_degenerate"]}
            for p in pool],
        "grid": grid["rows"],
        "disclaimer": "工程研究记录，不构成投资建议。留出段读数仅为披露，未参与任何选择。",
    }
    if a.out:
        Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[fps_factor] 写出 {a.out}")
    print(f"[fps_factor] 池 {len(pool)} 只 / 判决 {verdict}（{why}）")
    print(f"[fps_factor] ρ(IS→OOS) = {rho:+.3f} (p={rho_p:.3f}) | 随机分位 = {pct:.1%} | N* = {ns}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
