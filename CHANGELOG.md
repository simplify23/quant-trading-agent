# Changelog

本文件记录框架与论文的版本演进。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [2.2.1] — 2026-10-06

### Paper
- ★ **预印本上线：arXiv:[2610.07701](https://arxiv.org/abs/2610.07701)**（v1，Submitted 2026-10-06；cs.AI 主分类 / cs.CE 交叉；DOI `10.48550/arXiv.2610.07701`）。仓库与论文的双向引用已通：
  论文 Comments 字段指向本仓库，本仓库 README 与 `CITATION.cff` 指向论文。

### Added
- **`paper/`** —— 论文《On the Boundary of Admission Gates: An Injected-Truth Study of
  Falsification-First Selection in Quantitative Strategy Research》全文：
  `paper.tex` / `paper.pdf`（12 页，3 图 7 表，**无外部资源依赖**）、
  `arxiv_metadata.md`（arXiv 表单字段）、`review_checklist.md`（四轮形式审查）、
  `writing_notes_and_audit.md`（写作方法论整理 + 16 点自审）。
- **`experiments/`** —— 注入式实验的完整复现产物：`exp1_*`（合成面板）、`exp2_*`（真实标定面板）、
  6 个结果 JSON；论文中每个数字均可回溯。
- **`CITATION.cff`** —— GitHub「Cite this repository」元数据，`preferred-citation` **指向论文**
  而非软件（与 `quantumlib/tesseract-decoder` 同一惯例）。arXiv 编号待回填，**刻意留空而非放假链接**。
- **`README.zh-CN.md`** —— 中文说明（英文主 README 的国际惯例做法）。
- 三个核心脚本（`qta_loop.py` / `preflight_audit.py` / `overfit_metrics.py`）的 docstring
  增加**论文引用块**，使代码可追溯到论文。

### Changed
- **README 重构**：论文区块置顶（标题 + 四项发现表 + BibTeX）+ shields.io badges；
  新增「本仓库的两个身份」（论文代码／可运行框架）。
- **`references/rubric.md`**：新增必要条件「**判据必须建立在超额收益之上**」
  （在绝对收益上算 DSR/N\*/分段稳定性会静默拦掉全部候选，含 t=4.0 的真信号），
  并附**闸门有效性实测边界表**与逐判据拦截率自检动作。
- **`references/precedent.md`**：新增 **P-34…P-38**（超额收益空间／精度装置非收益装置／
  对照须能产生弃权／候选结构须匹配任务形态／冗余判据如实报告）。

## [2.2.0] — 2026-10-06

### Added
- G9 拆分为 **G9a DSR（硬闸）/ G9b PBO（软闸）/ G9c SPA**。
- **G10 新增量闸**：与已采纳结论集的最大 |ρ| ≤ 0.5。
- **G11 面板 IC**：截面 IC 的 t_adj ≥ 2。
- **P9 claim↔diff 绑定**：改动型候选须声明 `change.target`，与实际改动文件一致。
- `scripts/overfit_metrics.py` —— 纯标准库实现 **PBO/CSCV + Hansen SPA**，
  白噪声校准（40 次重复的 PBO 均值 0.501，**单次 sd ≈ 0.26** ⇒ 故 G9b 定为软闸）。

### Fixed
- `pass=None`（未提供/不适用）被 `soft_fail` 误判为「不过」，会把判决强行拉成 pending
  并误触 P1/P6 协议违规 ⇒ 改为严格判 `is False`。
- `protocol_checks()` 与 `decide()` 各自实现了一遍 adopt 条件（潜在漂移）⇒
  抽出 `would_adopt()` 单点实现，两处共用。

## [2.1.0] — 2026-10-05

### Added
- **D0–D4 部署审计**：上线 / 实盘 / 影子盘前的代码 bug 闸门（前视、返回 nan、自造交易日历、
  非原子写、跨文件同名实现），并以 **sha256 代码指纹**钉死「审的就是要上的」。
- `scripts/preflight_audit.py` —— 静态扫描 P0/P1/P2 + 代码指纹 + `.preflightignore`，
  **自带误报闸自检**（干净代码必须 0 命中）。

## [2.0.0] — 2026-10-05

### Added
- 三方闭环（正方 / 反方 / 中立裁判）合成一条可执行流水线。
- **裁判催办**状态机：上轮派工未响应 ⇒ L1 点名 ⇒ L2 停工清偿 ⇒ L3 终止迭代。
- **反方政委包**：除 `risk_register`（防守）外必须给 `opt_prescriptions`（进攻，四件套
  target / action / expected_delta / rollback）；只反对不开方 ⇒ 本轮 invalid。

## [1.0.0]

- 三方准入（G1–G8），通过即自动并入。

---

★ **未发布的东西不写在这里**。本文件只记录**已经进了仓库**的变更；
进行中的实验、待回填的 arXiv 编号等在 `README.md` 与 `paper/arxiv_metadata.md` 中显式标注为「待办」。

## v2.3 (2026-10-10)

### Added
- `references/masters.md`: M-1~M-12 rules distilled from Simons, Thorp, López de Prado, and top Chinese quant funds
- `references/selfiter.md`: RSI three-channel self-learning protocol (linguistic/procedural/structural + Channel D external evolution)
- `scripts/masters_checklist.py`: M-series soft checker with --selftest (PASS/WARN/MISS/FAIL, not counted in hard gates)
- "Never Satisfied" meta-rule at top of SKILL.md: on convergence/monthly/on-demand, search externally for superior skills/frameworks

### Changed
- SKILL.md version bumped to v2.3
- All selftests pass (qta_loop 40/40, preflight 25/25, masters_checklist good/bad samples)

### Lessons encoded
- M-1: Data hygiene (convertible bond close=0 incident, 2026-10-09)
- M-4: Kelly criterion + half-Kelly sizing (S3 worst5 -54%, individual investor cannot replicate)
- M-7: Meta-labelling / ranking key (PB percentile ordering = de Prado meta-labelling)
- M-9: Crowding self-assessment (2024-02 CSI microcap liquidity collapse, 2025-07 momentum factor crash)
- Temporal aggregation mismatch: signal-level +2.7pp ≠ portfolio-level (72-cell experiment, 2026-10-09)
