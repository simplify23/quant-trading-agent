#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
overfit_metrics.py —— 多重检验 / 过拟合度量（纯标准库）

为什么单独一个文件
------------------
`qta_loop.py` 的 G 组闸门要判「这个结论是不是试出来的」，需要 PBO 与 SPA 两个量。
把它们**内联**进引擎会让引擎膨胀且难自检；**引入 numpy** 又会破坏「引擎层零第三方依赖」。
⇒ 单独成模块，纯标准库实现，引擎只读它算出的**数字**。

算法来源与忠实度
----------------
- **PBO（组合对称交叉验证 CSCV）**：Bailey, Borwein, López de Prado & Zhu (2014)；
  实现口径与本工作区既有的 `自迭代研究/autoresearch_v1/ar_judge.py::pbo_cscv` **逐条对齐**
  （S 块、C(S,S/2) 枚举、IS 取最优列、OOS 升序排名 w=rank/(N+1)、logit、PBO=P(logit≤0)）。
- **SPA（Hansen 2005）/ White's Reality Check**：同样对齐 `ar_judge.py::reality_check`
  （有效集阈值 t > −√(2·ln ln T)、stationary block bootstrap、V=max√T·mean）。

★ 与 numpy 版**不会逐位相同**的唯一原因：随机数发生器不同（`random.Random` vs `default_rng`）。
  因此 bootstrap 类结果存在**蒙特卡洛误差**，报数时必须带 `n_boot`。PBO 在 `max_splits ≥ C(S,S/2)`
  时是**确定性**的（枚举全部切分），这部分应逐位一致。

性能：PBO 预计算每块的 (n, Σ, Σ²) ⇒ 每次切分只需聚合块统计量，复杂度从 O(T·N) 降到 O(S·N)。

用法：
  python3 overfit_metrics.py --selftest
  python3 overfit_metrics.py --pbo matrix.json  --S 16 --max-splits 4000 --out pbo.json
  python3 overfit_metrics.py --spa spa.json     --n-boot 2000 --block 20 --out spa.json
  输入 JSON：matrix.json = {"matrix": [[r11, r12, ...], ...]}          # T×N（N 条候选，T 个时点）
             spa.json    = {"bench": [...], "models": [[...], ...]}     # bench 长度 T；models 为 T×K
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import sys
import time

VERSION = "1.0.0"


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


# ---------------------------------------------------------------- PBO / CSCV
def pbo_cscv(R: list[list[float]], S: int = 16, max_splits: int = 4000, seed: int = 0) -> dict:
    """组合对称交叉验证：PBO = P(IS 最优列在 OOS 排名落到后半)。

    R : T×N 收益矩阵。纯噪声下 PBO ≈ 0.5。
    """
    T = len(R)
    N = len(R[0]) if T else 0
    if N < 2 or T < 4 * S or S < 2 or S % 2:
        return {"PBO": None, "why": f"维度不足（T={T} N={N} S={S}；要求 S 偶数且 T≥4S）"}

    bounds = [i * T // S for i in range(S + 1)]
    stats: list[list[tuple[int, float, float]]] = []
    for b in range(S):
        lo, hi = bounds[b], bounds[b + 1]
        row = []
        for j in range(N):
            vals = [R[i][j] for i in range(lo, hi) if _finite(R[i][j])]
            n = len(vals)
            row.append((n, sum(vals), sum(v * v for v in vals)))
        stats.append(row)

    def sharpe_of(blocks: list[int]) -> list[float | None]:
        out: list[float | None] = []
        for j in range(N):
            n = sum(stats[b][j][0] for b in blocks)
            if n < 2:
                out.append(None)
                continue
            s = sum(stats[b][j][1] for b in blocks)
            ss = sum(stats[b][j][2] for b in blocks)
            mu = s / n
            var = (ss - s * s / n) / (n - 1)
            out.append(mu / math.sqrt(var) if var > 0 else None)
        return out

    half = S // 2
    combos = list(itertools.combinations(range(S), half))
    truncated = len(combos) > max_splits
    if truncated:
        combos = random.Random(seed).sample(combos, max_splits)

    logits: list[float] = []
    for comb in combos:
        cs = set(comb)
        rest = [b for b in range(S) if b not in cs]
        s_is = sharpe_of(list(comb))
        best_j, best_v = None, None
        for j, v in enumerate(s_is):
            if v is not None and (best_v is None or v > best_v):
                best_j, best_v = j, v
        if best_j is None:
            continue
        s_oos = sharpe_of(rest)
        arr = sorted(((v if v is not None else float("-inf"), j) for j, v in enumerate(s_oos)))
        if len(arr) < 2:
            continue
        rank = next((k for k, (_v, j) in enumerate(arr, 1) if j == best_j), None)
        if rank is None:
            continue
        w = min(max(rank / (N + 1.0), 1e-6), 1 - 1e-6)
        logits.append(math.log(w / (1 - w)))

    if not logits:
        return {"PBO": None, "why": "全部切分无效"}
    m = sum(logits) / len(logits)
    sd = math.sqrt(sum((x - m) ** 2 for x in logits) / (len(logits) - 1)) if len(logits) > 1 else 0.0
    pbo = sum(1 for x in logits if x <= 0) / len(logits)
    # ★ 切分之间【不独立】（共享块）⇒ 这个 se 只是乐观下界。
    #   实测（见 selftest）：T≈256、N≈12 时【单次 PBO 的标准差 ≈ 0.2】，
    #   故 PBO 只能作【辅助诊断】，绝不能当硬闸单独否决。
    se_naive = math.sqrt(max(pbo * (1 - pbo), 1e-12) / len(logits))
    return {"PBO": pbo, "pbo_se_naive": se_naive,
            "n_splits": len(logits), "S": S, "N": N, "T": T,
            "logits_mean": m, "logits_std": sd, "truncated": truncated}


# ---------------------------------------------------------------- SPA / Reality Check
def spa_test(bench: list[float], models: list[list[float]], n_boot: int = 2000,
             block: int = 20, seed: int = 0) -> dict:
    """White's Reality Check + Hansen SPA：对「一族模型里最好的那个」做多重检验校正。

    bench : T 维基准收益　　models : T×K 候选收益
    返回 SPA_p（与 RC_p）—— **p 小 ⇒ 最好的那个确实优于基准**。
    """
    T = len(bench)
    K = len(models[0]) if models else 0
    if K < 1 or len(models) != T or T < 2 * block:
        return {"SPA_p": None, "RC_p": None,
                "why": f"维度不足（T={T} K={K} block={block}；要求 T≥2·block）"}

    D = [[((models[t][j] - bench[t]) if (_finite(models[t][j]) and _finite(bench[t])) else 0.0)
          for j in range(K)] for t in range(T)]
    dbar = [sum(D[t][j] for t in range(T)) / T for j in range(K)]
    V_obs = math.sqrt(T) * max(dbar)

    sd = []
    for j in range(K):
        mu = dbar[j]
        var = sum((D[t][j] - mu) ** 2 for t in range(T)) / (T - 1)
        sd.append(math.sqrt(var))
    thr = -math.sqrt(2 * math.log(math.log(T))) if T > math.e else 0.0
    tstat = [(dbar[j] / (sd[j] / math.sqrt(T))) if sd[j] > 0 else float("nan") for j in range(K)]
    gs = [j for j in range(K) if _finite(tstat[j]) and tstat[j] > thr]
    if not gs:
        return {"SPA_p": None, "RC_p": None, "V_obs": V_obs, "K_a": 0, "K": K,
                "why": "无模型进入 SPA 有效集"}

    Db = [[D[t][j] - dbar[j] for j in range(K)] for t in range(T)]
    rng = random.Random(seed)
    nb = math.ceil(T / block)
    V_rc: list[float] = []
    V_spa: list[float] = []
    for _ in range(n_boot):
        idx: list[int] = []
        for _ in range(nb):
            st = rng.randrange(T)
            idx.extend((st + o) % T for o in range(block))
        idx = idx[:T]
        db = [sum(Db[i][j] for i in idx) / T for j in range(K)]
        V_rc.append(math.sqrt(T) * max(db))
        V_spa.append(max(0.0, math.sqrt(T) * max(db[j] for j in gs)))
    return {"SPA_p": sum(1 for v in V_spa if v >= V_obs) / len(V_spa),
            "RC_p": sum(1 for v in V_rc if v >= V_obs) / len(V_rc),
            "V_obs": V_obs, "K_a": len(gs), "K": K, "T": T,
            "n_boot": len(V_spa), "block": block}


# ---------------------------------------------------------------- selftest
def selftest() -> int:
    fails: list[str] = []

    def chk(name, cond):
        print(f"  {'✅' if cond else '❌'} {name}")
        if not cond:
            fails.append(name)

    print(f"overfit_metrics selftest  v{VERSION}")
    T, N = 256, 12
    rng = random.Random(20261006)

    # ★ 校准不能只看一次：单次 PBO 的 sd ≈ 0.2，必须看多次重复的【均值】。
    #   区间取 0.5±0.15 —— 这不是"放水"，而是按实测噪声定的 5σ 带；
    #   它仍能抓住"PBO 恒为 0 / 恒为 1"这类真 bug。
    reps = []
    for k in range(40):
        r = random.Random(5000 + k)
        M = [[r.gauss(0, 0.01) for _ in range(N)] for _ in range(T)]
        p = pbo_cscv(M, S=8)["PBO"]
        if p is not None:
            reps.append(p)
    mu = sum(reps) / len(reps)
    chk(f"纯噪声 PBO 的 40 次均值 ≈ 0.5（got={mu:.3f}，单次 sd≈"
        f"{math.sqrt(sum((x-mu)**2 for x in reps)/(len(reps)-1)):.2f}）",
        0.35 <= mu <= 0.65)
    chk(f"PBO 返回带不确定性（pbo_se_naive）",
        pbo_cscv([[rng.gauss(0, .01) for _ in range(N)] for _ in range(T)], S=8)
        .get("pbo_se_naive") is not None)

    # 方向性检验：含真信号列时 PBO 必须显著更低（这才是有判别力的那条）
    sig = [[rng.gauss(0.004 if j == 3 else 0.0, 0.01) for j in range(N)] for _ in range(T)]
    r_sig = pbo_cscv(sig, S=8)
    chk(f"含真信号列 ⇒ PBO 远低于噪声均值（got={r_sig['PBO']:.3f} vs 均值 {mu:.3f}）",
        r_sig["PBO"] is not None and r_sig["PBO"] < mu - 0.2)

    chk(f"维度不足返回 None 而非崩溃（T=20）",
        pbo_cscv([[0.0, 0.1]] * 20, S=8)["PBO"] is None)
    noise = [[rng.gauss(0, 0.01) for _ in range(N)] for _ in range(T)]
    chk("S 为奇数时拒绝（返回 None）", pbo_cscv(noise, S=7)["PBO"] is None)
    chk("确定性：同输入两次结果一致（S=8 枚举全部切分）",
        pbo_cscv(noise, S=8)["PBO"] == pbo_cscv(noise, S=8)["PBO"])

    bench = [rng.gauss(0.0, 0.01) for _ in range(T)]
    m_null = [[rng.gauss(0.0, 0.01) for _ in range(6)] for _ in range(T)]
    r_null = spa_test(bench, m_null, n_boot=400, block=10)
    chk(f"纯噪声 SPA 不显著（p={r_null['SPA_p']:.3f} > 0.05）",
        r_null["SPA_p"] is not None and r_null["SPA_p"] > 0.05)

    m_true = [[rng.gauss(0.0, 0.01) for _ in range(6)] for _ in range(T)]
    for t in range(T):
        m_true[t][2] = rng.gauss(0.010, 0.005)
    r_true = spa_test(bench, m_true, n_boot=400, block=10)
    chk(f"含真优势模型 ⇒ SPA 显著（p={r_true['SPA_p']:.3f} ≤ 0.05）",
        r_true["SPA_p"] is not None and r_true["SPA_p"] <= 0.05)

    chk("SPA 维度不足返回 None", spa_test([0.0] * 10, [[0.1]] * 10, block=20)["SPA_p"] is None)
    chk("SPA 带 K_a 有效集信息", isinstance(r_null.get("K_a"), int))

    print("  自检结论：", "✅ 通过" if not fails else f"❌ 未通过 {fails}")
    return 0 if not fails else 1


# ---------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="多重检验 / 过拟合度量（PBO · SPA）")
    ap.add_argument("--pbo", help="PBO 输入 JSON：{\"matrix\": [[...], ...]}（T×N）")
    ap.add_argument("--spa", help="SPA 输入 JSON：{\"bench\": [...], \"models\": [[...], ...]}")
    ap.add_argument("--S", type=int, default=16, help="CSCV 块数（偶数，默认 16）")
    ap.add_argument("--max-splits", type=int, default=4000)
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--block", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", help="结果 JSON 输出路径")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.pbo and not args.spa:
        ap.error("--pbo / --spa / --selftest 至少给一个")

    t0 = time.time()
    out: dict = {"version": VERSION, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    if args.pbo:
        d = json.loads(open(args.pbo, encoding="utf-8").read())
        out["pbo"] = pbo_cscv(d["matrix"], S=args.S, max_splits=args.max_splits, seed=args.seed)
    if args.spa:
        d = json.loads(open(args.spa, encoding="utf-8").read())
        out["spa"] = spa_test(d["bench"], d["models"], n_boot=args.n_boot,
                              block=args.block, seed=args.seed)
    out["elapsed_sec"] = round(time.time() - t0, 3)

    txt = json.dumps(out, ensure_ascii=False, indent=1)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(txt)
        print(f"→ {args.out}")
    else:
        print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
