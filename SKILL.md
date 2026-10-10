---
name: quant-trading-agent
display_name: 量化交易Agent策略框架
display_name_en: Quant Trading Agent Framework v2.3 (Triad Loop × Admission Gates × M-Series Masters Rules × RSI Self-Learning)
version: 2.3.0
author: simplify23
description: 量化交易 Agent 策略框架 v2.1 —— 把「三方闭环迭代」「前向优先反自欺审计」「上线前代码审计」合成一条可执行流水线。正方（探索 / 代码优化实现者）· 反方（政委：风险登记 + 优化处方四件套）· 中立裁判（独立取证 + G1–G9/F0–F6/D0–D4 逐条裁定 + 派工 + ★催办正方去做代码优化）。当用户说「跑一轮三方」「三方裁决」「让框架推进迭代」「催正方去改代码」「反方给优化处方」「策略该不该采纳并继续深挖」「这个结论凭什么算数」「我能测出来吗」「研究收敛了吗」「还能不能再优化」「已证伪的有哪些」「哪些结论经得起实盘」时使用；也用于「上线/实盘/影子盘前审一下代码有没有 bug」「这份代码能不能接钱」「审计一下会不会重复下单/写坏台账」。
description_en: A triad closed-loop research framework for quantitative strategies — proponent (exploration / code-level optimization) × adversary (risk register + executable optimization prescriptions) × neutral judge (independent re-runs + G1–G9 admission gates, F0–F6 forward-first anti-self-deception audit, D0–D4 pre-deployment code audit with a SHA256 code fingerprint that binds the audit to the exact build). Use it for "run a triad round", "should we adopt this strategy", "is this backtest conclusion trustworthy", "can this effect even be detected" (N* sample-size arithmetic, moving-block CI, diff-trade audit, leave-one-out), "audit this code before going live or paper trading", "which conclusions were already falsified". Enforces — no adoption before sample size reaches N*; "not detected" is never reported as "invalid"; the adversary must deliver executable prescriptions, not just objections; the judge must coach the proponent until code-level optimizations actually land; passing an audit is not the same as being bug-free.
tags: [量化, 三方裁决, agent框架, 前向验证, 多重检验, 闭环迭代, DSR, 自欺防御, 策略准入, 反过拟合, 上线前审计]
agent_created: true
---

> ★ **永不自满元规则**（2026-10-10 用户指令）：本框架永远不是最优的。**每次收敛四闸触发、
> 每月例行、或用户要求时**，必须先按 `references/selfiter.md` **通道 D** 去 WebSearch 外部优秀
> 技能/框架/大师分享，模仿、翻译成可检查规则或脚本、演化进本框架——再谈下一步。
> （先例：2026-10-10 M-1~M-12 即由此而来。）

> ★ **实验目录管理规则**：做量化实验时，自动扫描工作区根目录下的实验内容。
> 凡是文件名含 `_研究`、`_实验`、`_2026` 且不属于核心策略目录
> （潮汐策略/AI链策略/ETF轮动策略/holdings_timing）的，
> 自动移入 `实验/` 文件夹归拢。效果不好可直接删除整个 `实验/` 不影响主策略。

# 量化交易Agent策略框架 v2.3

> **一句话**：**判决不是终点，下一轮才是。** 裁判必须把活派下去、并盯着正方把代码改完；
> 反方必须既看住风险、又交出「怎么改」的处方；任何结论进台账之前，先过一遍「你能测出来吗」；
> 任何代码接真实资金（或影子账本）之前，先过一遍「已知会致命的 bug 形态扫干净了吗、审完有没有被改」。

**它管什么**：研究结论能不能并入系统、迭代该不该继续、**下一轮具体做什么**、
以及**这份代码能不能上线**。
**它不管什么**：不产出买卖信号、不下单、不改生产文件、不给仓位。

## 一、版本谱系

| 版本 | 载体 | 一句话 | 缺什么 |
|---|---|---|---|
| 1.0 | `strategy-adjudication` | 三方准入：G1–G8 判据，通过即自动并入 | 判完就停，不产生下一轮 |
| — | `forward-first-audit` 1.10 | 前向优先反自欺审计（六道闸门 + FPS 因子） | 是体检手册，不驱动迭代 |
| — | `quant-agent-framework` 3.0（开发线） | 判决书携带「下一轮指令」的三方闭环 | 派了工但**不催**；反方只反对、**不给怎么改** |
| **2.0** | 本框架 | 合并上述全部，补上【裁判催办】与【反方政委包】两条硬契约 | 只管研究结论，不管代码能不能接钱 |
| **2.1** | 本框架 | 再加 **D0–D4 部署审计**（上线/实盘/影子盘前的代码 bug 闸门 + 代码指纹防「审完又改」） | 判据只有 DSR 一项多重检验校正；无「新增量」闸 |
| **2.2** | （已并入 v2.3） | 再加 **四项度量升级**：G9 拆 **G9a/b/c**（DSR + PBO + SPA）｜**G10 新增量闸**（与已采纳结论 ρ≤0.5）｜**G11 面板 IC**（t_adj≥2）｜**P9 claim↔diff 绑定** | — |
| **2.3** | **本框架（现役）** | 再加 **M 系列大师规则**（M-1~M-12，来自 Simons/Thorp/de Prado/国内头部，软检查不计硬闸）＋ **RSI 三通道自学习协议**（语言/过程/结构/外部演化）＋ **masters_checklist.py** 软检查器 ＋ **永不自满元规则**（收敛/每月/用户要求 ⇒ 外部搜索→模仿→翻译→演化） | — |

**v2.2 的四项升级各来自哪里**（不是自创口号，每条都有出处）：
- **G9b/G9c（PBO/SPA）** ← MinervaScore 把 DSR+PBO+SPA 组合成分级的做法；本项目 `ar_judge.py` 早有实现，此前**没接进闸门**。
- **G10 新增量** ← FactorMiner 的「与已有因子 ρ>0.5 淘汰」；本项目同型事故是**两份同义实现各自演进**（先例 P-13）。
- **G11 面板 IC** ← QuantaAlpha / FactorMiner / AlphaAgent 全部以 IC/ICIR 为通用语言；面板级样本效率比逐笔高一个量级。
- **P9 claim↔diff** ← AlphaAgent 的「假设—实现语义一致性」；防「说改 A 实际改 B」。

v2.0 补的两个执行缺口（**引擎机械强制，不靠自觉**）：
1. ★**裁判催办**：判决书必带 `coach`（nag_level / must_do / escalation）；正方不响应派工 ⇒ 逐级升级，到停工清偿、直至终止迭代。
2. ★**反方政委包**：非采纳轮不仅要有反对意见，还必须有**可执行的优化处方**（改哪个函数 / 怎么改 / 预期读数 / 怎么回退）。

v2.1 再补第三个缺口：
3. ★**上线前代码审计**：`deploy.target` 一旦声明（shadow/live/prod），D0–D4 全部必过；
   **D1 由裁判自己重算 sha256** —— 防「审完又改」（拿通过的旧报告去上线另一份代码）。

## 二、三个角色（硬契约）

| 角色 | 基础职责 | **硬契约** |
|---|---|---|
| **正方**（探索 / 代码优化实现者） | 主张采纳、挂实验 ID、声明失效条件 | ① 回填 `responded_tasks` 响应上一轮派工；② 每轮交付**代码级优化点** `code_opt_points`（BS-x：写死在代码里、从未进过搜索自由度的东西），先于调参；③ 要上线就得先出审计报告并保证代码不再变动 |
| **反方**（政委） | 针对性质疑、挂预注册预期 | ★**政委包 `commissar_pack`**：`risk_register`（风险/触发/处置/严重度）+ `opt_prescriptions`（**target 文件:函数 / action 可执行动作 / expected_delta 预期读数 / rollback 回退口径**）。非采纳轮缺处方 ⇒ 本轮 **invalid** |
| **中立裁判** | 独立取证（二手数据=传声筒）、逐条裁定、归档先例 | ★**派工 + 催办 + 部署审计 + 收敛**：`next_round` 必带 `proponent_tasks`（含 kind/blocking/due_round）、`adversary_focus`、`commissar_directives`、`coach`；`deploy` 声明时**自己重算代码指纹**；四闸触发即宣布收敛 |

**裁定三态语义**：`adopt`=证据充分且可执行｜`reject`=证据否决（进先例）｜`pending`=**未检出 ≠ 无效**，写明"还差什么"｜`invalid`=协议违规，本轮不进台账。

## 三、闭环协议

```
① 正方提交   round.json：候选 + 指标 + 主张(挂证据) + 响应上一轮派工 + 代码级优化点 BS-x
② 反方质证   反对意见(挂预注册预期) + ★政委包（风险登记 + 优化处方四件套）
③ 裁判取证   独立复跑（二手数据=传声筒）→ G1–G9 准入组 + F0–F6 前向组 逐条裁定
             ＋ 声明了 deploy.target 时，再跑 D0–D4 部署审计（★自己重算代码指纹）
④ 判决+派工  verdict ∈ {adopt, reject, pending, invalid}
             next_round = {proponent_tasks[], adversary_focus[], commissar_directives[],
                           blueocean_dims[], coach{nag_level,must_do,escalation}, continue, stop_reason}
⑤ 正方执行   下一轮必须回填 responded_tasks（台账可查）；未响应 ⇒ nag_level+1
⑥ 收敛四闸   预算用尽 ｜ 连续 3 轮无采纳 ｜ 达 max_rounds ｜ ★正方连续 3 轮不响应派工
```

**P 系列契约**（违反 ⇒ 本轮作废 / 计入警告）：

| # | 契约 | 后果 |
|---|---|---|
| P1 | 裁决 ≠ adopt ⇒ 反方 `directions` 非空 | invalid |
| P3 | 正方主张挂证据 ID；反方反对挂预注册预期 | invalid |
| **P6** | ★裁决 ≠ adopt ⇒ 政委 `opt_prescriptions` ≥1 条且四要素齐 | invalid |
| **P7** | ★正方须回填 `responded_tasks`；未响应 ⇒ nag+1 | 升级至停工清偿（`hold_new_candidates`） |
| **P7b** | ★裁判每轮必派 ≥1 条 `kind=code_optimization` | 裁判失职 |
| **P8** | ★选优键 `rank_key_source` ∈ {holdout, full} | invalid（作弊键） |
| **P9** | ★改动型候选须声明 `change.target`；若给了 `actual_files`，目标文件必须在其内 | invalid（**主张与实现不符**） |
| P4 | 收敛四闸任一触发 ⇒ `continue=false` 并写明 stop_reason | 停止迭代 |
| P5 | 判据文件 SHA256 指纹随判决落盘 | 事后偷改可检出 |

**催办三级升级**（`coach.nag_level`）：
`L1` 明确点名欠账任务 + 要求把 BS-x 推到实验 ｜ `L2` **停工清偿**：不再受理新候选，先还账 ｜ `L3` 终止迭代（先修作业面再谈策略）。

## 四、判据（两组，逐条独立成败，不加权）

**G1–G11 准入组**：G1 锚点自校验｜G2 主指标优于基线｜G3 风险不劣化｜G4 影响样本 ≥8
｜G5 变量覆盖率 ≥90%｜G6 连续优区 ≥4 格｜G7 影响不与单一自然年重合｜G8 无前视口径同样通过
｜**G9a DSR ≥0.95**（试错折减）｜**G9b PBO ≤0.5**（软闸：单次 sd≈0.26，只作辅助诊断）
｜**G9c SPA p ≤0.05**（族内最优 vs 基准）｜**G10 与已采纳结论最大 \|ρ\| ≤0.5**（新增量）
｜**G11 截面 IC 的 t_adj ≥2**（按日聚类后除 √h）。
⇒ 硬闸 = G1/G2/G3/G4/G8/**G9a**；软闸缺（含 G9b/G9c/G10/G11 明确不过）⇒ pending；
**`pass=None`（未提供）既不算过也不算不过**。

**F0–F6 前向体检组**（没做体检 ⇒ 判决封顶 pending）：
F0 口径指纹（panel_md5 + 复权/时点/成本/宇宙）｜**F1 样本量算术 N\* = ⌈(2σ/μ)²⌉**（n < N\* ⇒ **只许「未检出」**）
｜F2 选择自由度诊断（单日候选 ≤1 ⇒ 这是事件过滤器，**排序/加权类优化在定义上无效**）｜F3 选优键只用训练段
｜F4 参数平台（=G6）｜**F5 差异笔集合审计**（改动"新增/去掉"的笔 CI 含 0 ⇒ 改动未被证明）｜**F6 留一笔**（剔最好一笔后翻负 ⇒ 单笔独扛，不得当规律）。

**D0–D4 部署审计组**（v2.1 新增；声明了 `deploy.target` 才适用，但一旦适用就是硬闸）：
D0 报告存在｜**D1 代码指纹一致（★裁判自己重算 sha256 比对 ⇒ 防「审完又改」）**｜D2 无 P0 阻断项
｜D3 回滚就绪｜D4 报告未过期（≤7 天）。
⇒ 任一不过 ⇒ `adopt` 降级为 `pending/deploy_blocked`，**禁止接真实资金或影子账本**。
扫描规则：P0 前视（`shift(-n)`/`iloc[i+1]`）、返回 nan、自造交易日历、阈值×nan 源；
P1 `except: pass`、`f"{x:g}"`、自然日陈旧判据、非原子覆盖写、短前缀判定、跨文件同名实现。

## 五、用法

```bash
PY=python3
D=~/.workbuddy/skills/quant-trading-agent

# 0) 自检（必跑；不过 ⇒ 后面全部结论作废）
$PY $D/scripts/qta_loop.py --selftest          # 40 项：噪声识破 / 三态 / 政委 / 催办 / 部署审计 / 新增量 / PBO / IC / nan / 指纹 …
$PY $D/scripts/preflight_audit.py --selftest   # 25 项：规则命中 + ★误报闸（干净代码必须 0 命中）
$PY $D/scripts/overfit_metrics.py --selftest   # 10 项：PBO / SPA 的白噪声校准与方向性（纯标准库）
$PY $D/scripts/fps_factor.py --selftest        # 因子层 13 项（需 numpy+pandas）
# 或一键：$PY $D/scripts/selftest_all.py

# 1) 一轮闭环（给 --out 才会落台账）
$PY $D/scripts/qta_loop.py --round round.json --ledger qta_ledger.jsonl --out verdict.json --explain

# 2) ★ 上线 / 实盘 / 影子盘前：先审计代码，再让裁判判定能不能接钱
$PY $D/scripts/preflight_audit.py --mode live --targets <代码路径…> \
     --rollback-point "<回滚点>" --out-dir ./pf      # 退出码 3 = 有 P0，阻断上线
# 把 ./pf/preflight_report.json 的路径填进 round.json 的 deploy.preflight.path

# 3) 读判决书：verdict / reason_bucket / gates / fwd_gates / deploy_gates / fwd_summary
#    verdict.deploy.allowed=false ⇒ ⛔ 禁止上线（看 deploy.blockers）
#    next_round.coach.nag_message（催办语） / next_round.proponent_tasks（派工）
#    continue=false ⇒ 收敛，向用户汇报 stop_reason，禁止硬开第 N+1 轮
```

示例轮次（可直接跑）：`examples/round_good.json`（全过 ⇒ adopt）、
`examples/round_reject_with_commissar.json`（驳回 + 政委包）、`examples/round_bad_protocol.json`（违规 ⇒ invalid）。

## 六、九条铁律

1. **裁判必须独立取证**：自己跑实验/复算指标，不采信任何一方转述的数字。
2. **判决必须携带下一轮指令**：给正方任务、给反方重点、给收敛判定。判完即停 = 1.0 的老毛病。
3. **反方必须给"怎么改"**：只反对不给处方 ⇒ 本轮作废。风控与优化同权重。
4. **驳回后先证伪机制、再谈调参**：同族候选被驳 ≥2 次 ⇒ 下一轮锁定「机制证伪实验」。
5. **「未检出」≠「无效」**：n 未到 N\* ⇒ 只许 `pending/not_detected`，禁止判死，也禁止判活。
6. **一个前视变量足以造出「单调＋显著＋四年全正」的完整伪结论** ⇒ F0–F3、G8 不可跳过。
7. **不许用低等级证据推翻高等级证据**：短训练段上测不出 ⇒ 说"证不出"，不说"它没用"。
8. **收敛 ≠ 没有 alpha**：只说明「继续搜的期望产出低于成本」，汇报须附 trials 总数与 DSR 带宽。
9. ★**审计通过 ≠ 没有 bug**：静态扫描只覆盖已知的致命**形态**；口径错配、前视的业务定义、
   策略逻辑自欺、幂等/并发一致性 —— 这些必须人工过一遍
   （`references/preflight-audit.md` §四 的上线前必答清单）。**不许用 `.preflightignore` 掩盖真问题**。

## 七、边界

- 本框架裁决的是「研究结论能不能并入系统 / 迭代该不该继续 / 下一轮做什么 / **这份代码能不能接钱**」，
  **不产出买卖信号、不下单、不改生产文件**。
- adopt 的自动并入须由宿主项目提供 apply/verify/revert；**无 revert 的候选即使全过也降级 pending**。
- **D 组只判「能不能接真实资金」**（审计 + 指纹 + 回滚 + 新鲜度），不判策略好坏；
  审计通过也**不等于没有 bug**（见铁律 9）。
- 只回答两个问题：**「这个结论，凭什么算数？」**「**这份代码，凭什么能接钱？**」
  所有输出均为工程研究内容，**不构成投资建议**。

## 八、目录

- `references/roles.md` 三角色职责与举证要求（含政委包字段细则、裁判的部署审计职责）
- `references/protocol.md` round.json / verdict.json 完整 schema、P 系列、催办状态机、deploy 段
- `references/rubric.md` G1–G9 + F0–F6 + D0–D4 判据、阈值、DSR/N\* 公式与已知局限
- `references/forward-first.md` 前向优先手册（六道闸门 + 18 个踩坑 + 十一条不许）
- `references/preflight-audit.md` ★上线前代码审计：规则表 + **自动化查不到什么** + 上线前必答清单
- `references/precedent.md` 先例案卷 P-01…P-38（接入新项目前先对表）
- `references/masters.md` ★ M 系列规则（大师经验→框架软检查 12 条，2026-10-10 新增）
- `references/selfiter.md` ★ 自学习流程协议 v1.1（RSI 三通道：语言/过程/结构演化，2026-10-10 新增）
- `references/masters.md` ★ M 系列规则（大师经验→框架软检查 12 条，2026-10-10 新增）
- `references/selfiter.md` ★ 自学习流程协议 v1.1（RSI 三通道：语言/过程/结构演化，2026-10-10 新增）
- `scripts/qta_loop.py` 主引擎（裁决 + 派工 + 催办 + 部署审计 + 收敛 + 自检，纯标准库）
- `scripts/preflight_audit.py` ★代码审计器（静态扫描 P0/P1/P2 + 代码指纹 + `.preflightignore`）
- `scripts/overfit_metrics.py` ★多重检验度量（**PBO / CSCV + Hansen SPA**，纯标准库，白噪声校准）
- `scripts/fps_factor.py` 稳健度因子（N\* / moving-block CI / sign-flip / 选择自由度 / FPS）
- `scripts/selftest_all.py` 一键自检（引擎 + 审计 + 度量 + 因子）
- `scripts/masters_checklist.py` ★ M 系列软检查器（M-1~M-12 PASS/WARN/MISS，--selftest；不计硬闸，作裁判人工审阅附件）
- `references/selfiter.md` 协议要点：失败→三元组入 precedent（语言）；手工动作≥2次⇒固化为脚本（过程）；同类问题≥2轮⇒允许改协议（结构）；结构突变每季度复盘防规则通胀
- `scripts/masters_checklist.py` ★ M 系列软检查器（M-1~M-12 PASS/WARN/MISS，--selftest；不计硬闸，作裁判人工审阅附件）
- `references/selfiter.md` 协议要点：失败→三元组入 precedent（语言）；手工动作≥2次⇒固化为脚本（过程）；同类问题≥2轮⇒允许改协议（结构）；结构突变每季度复盘防规则通胀
- `examples/` 合规、驳回、违规三类 round.json（selftest 之外的第二层自证）
