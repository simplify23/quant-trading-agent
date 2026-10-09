# quant-trading-agent

> **面向量化策略选择的「证伪优先」研究框架。**
> 三方闭环（正方 / 反方 / 中立裁判）× 前向优先反自欺审计 × 上线前代码审计。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE.txt)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB.svg)](https://www.python.org/)
[![Version](https://img.shields.io/badge/version-2.2.1-informational.svg)](VERSION)
[![arXiv](https://img.shields.io/badge/arXiv-2610.07701-b31b1b.svg)](https://arxiv.org/abs/2610.07701)
[![Paper](https://img.shields.io/badge/paper-PDF%20%2812pp%29-lightgrey.svg)](paper/paper.pdf)

[English](README.md) · [复现产物](experiments/) · [论文源码](paper/)

---

## 📄 论文

### 《准入闸门的有效性边界：一项基于注入式真值与真实数据标定的实证研究》

**郑天伦**（复旦大学）· 2026 · 12 页（英文正文）· **arXiv:[2610.07701](https://arxiv.org/abs/2610.07701)** [cs.AI；cs.CE]

🔗 **[arXiv:2610.07701](https://arxiv.org/abs/2610.07701)** ｜ 📕 **[阅读 PDF](paper/paper.pdf)** ｜ 📝 [LaTeX 源码](paper/paper.tex) ｜
🔍 [投稿前形式审查](paper/review_checklist.md) ｜ 🧪 [实验](experiments/)

**问题**：任何「会采纳结论」的自动化研究流程，都必须决定**何时不再相信自己的输出**。
准入闸门就是这个决定所依赖的仪器——但它的有效性通常**被假设，而非被测量**。本文测量它。

**结论**：

| 发现 | 结果 |
|---|---|
| **闸门不只是「更保守」** | 在**相同采纳率**下，闸门的假发现率显著低于抛硬币对照（ΔFDR = 0.10–0.60，7 个场景中 5 个成立） |
| **但它的价值有边界** | 只在训练段 $t < 2.5$ 时体现，代价是采纳率降至 **1–7%** |
| **超过 $t \approx 2.5$ 就是纯负担** | 纯搜索本身几乎不会错，开闸只降低采纳率 |
| **★ 一条必要条件** | 判据若建立在**绝对收益**而非**超额收益**上，会**静默拦掉全部候选**——包括训练段 $t=4.0$ 的真信号 |

**为什么重要**：若闸门比假设的更弱，依赖它的流程就继承了无界的假发现风险；
若它只是保守，那些流程就在静默丢弃真实发现。**两种失效从外部都看不出来。**

```bibtex
@article{zheng2026admissiongates,
  title         = {On the Boundary of Admission Gates: An Injected-Truth Study of
                   Falsification-First Selection in Quantitative Strategy Research},
  author        = {Zheng, Tianlun},
  year          = {2026},
  eprint        = {2610.07701},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  doi           = {10.48550/arXiv.2610.07701},
  url           = {https://arxiv.org/abs/2610.07701}
}
```


---

## 本仓库的两个身份

**① 论文的代码与实验**。协议端到端可复现：

```bash
python3 experiments/exp1_injected_gate_efficacy.py --reps 400
python3 experiments/exp2_real_based_validation.py --reps 400 \
        --panel-kind strategy --sigma-e 0.007 \
        --alphas 0.00039 0.00059 0.00098 0.00156
```

论文中每个数字都可回溯到 `experiments/*_results.json`。
数据锚点：29 只 A 股 ETF 面板（746 日，后复权）——29 只 / 745 个收益点 /
峰度 7.84 / 截面平均相关 0.504。

**② 可运行的框架**。同一套三方闭环，可以直接指向你自己的项目。

| 它回答 | 靠什么 |
|---|---|
| 「这个结论凭什么算数？」 | 样本量算术 $N^*$、选择自由度诊断、差异笔审计、留一笔、DSR 试错折减、随机对照零分布 |
| 「研究跑到哪了、下一步做什么？」 | 判决书必须携带下一轮指令；裁判**催办**正方，连续不响应 ⇒ 停工清偿 ⇒ 终止迭代 |
| 「反方除了说不行，还会什么？」 | 政委包：`risk_register`（防守）＋ `opt_prescriptions`（进攻，四件套：target 文件:函数 / action / expected_delta / rollback） |
| 「★ 这份代码能不能接钱？」 | 上线前审计 D0–D4：前视、返回 nan、自造交易日历、非原子写、跨文件同名实现 —— 并**自己重算 sha256** 与审计报告比对 |

**它不做**：不产出买卖信号、不下单、不改生产文件、不给仓位建议。

---

## 快速上手

```bash
PY=python3
D=.

# 0) 一键自检（必跑：引擎 40 + 审计 25 + 度量 10 + 因子 13 = 88）
$PY $D/scripts/selftest_all.py

# 1) 跑一轮三方：round.json → verdict.json
$PY $D/scripts/qta_loop.py --round examples/round_good.json \
     --ledger qta_ledger.jsonl --out verdict.json --explain

# 2) ★ 上线/实盘/影子盘前：先审代码，再让裁判（D 组）判定能不能接钱
$PY $D/scripts/preflight_audit.py --mode live --targets <代码路径…> \
     --rollback-point "<回滚点>" --out-dir ./pf      # 退出码 3 = 有 P0，阻断
# 把 ./pf/preflight_report.json 路径填进 round.json 的 deploy.preflight.path

# 3) 分发前验收 + 打包
PY=$PY bash $D/build.sh
```

**三类示例轮次**（可直接跑）：`examples/round_good.json` → adopt｜
`examples/round_reject_with_commissar.json` → reject｜`examples/round_bad_protocol.json` → invalid。

**环境要求**：Python ≥ 3.9 —— 引擎层、审计层、度量层**只用标准库、零第三方依赖**；
只有因子层 `fps_factor.py` 需要 `numpy + pandas`，缺了会被标为「**未测**」而非「失败」。
无网络访问、无外部 API、无需任何密钥。

---

## 版本谱系

| 版本 | 一句话 | 缺什么 |
|---|---|---|
| 2.0 | 三方闭环 + 催办 / 政委包两条硬契约 | 只管研究结论，不管代码能不能接钱 |
| 2.1 | 再加 **D0–D4 部署审计**（代码 bug 闸门 + 指纹防「审完又改」） | 判据只有 DSR 一项多重检验校正 |
| **2.2** | 再加 **四项度量升级**：G9 拆 G9a/b/c（DSR+PBO+SPA）、**G10 新增量闸**、**G11 面板 IC**、**P9 claim↔diff 绑定** | — |
| **2.2.1** | 回写注入式实验结论：**判据必须建立在超额收益上**（必要条件）+ 闸门有效性实测边界 | — |

---

## 目录

```
quant-trading-agent/
├── CITATION.cff                 ★ 「Cite this repository」元数据（指向论文）
├── SKILL.md                     框架主入口：三角色 / 闭环协议 / P 系列契约 / 三组判据
├── README.md / README.zh-CN.md  英文 / 中文说明
├── VERSION                      2.2.1
├── build.sh                     八步分发验收 + 打包
├── paper/                       ★ 论文（tex + pdf + arXiv 元数据 + 形式审查）
├── experiments/                 ★ 复现产物（脚本 + 结果 JSON）
├── references/                  roles / protocol / rubric / forward-first /
│                                preflight-audit / precedent（P-01…P-38）
├── scripts/                     qta_loop · preflight_audit · overfit_metrics ·
│                                fps_factor · selftest_all
└── examples/                    三类示例轮次
```

---

## 边界与免责

- adopt 的自动并入须由宿主项目提供 apply / verify / revert；**无 revert 的候选即使全过也降级 pending**。
- D 组只判「能不能接真实资金」，**不判策略好坏**；**审计通过 ≠ 没有 bug**。
- 样本量与试验次数不足时，正确输出是 `pending` + 「还差什么」，不是 `reject`。
  **「未检出」不等于「无效」。**
- 所有输出均为工程研究内容，**不构成投资建议**。

## 许可

MIT —— 见 [LICENSE.txt](LICENSE.txt)。
