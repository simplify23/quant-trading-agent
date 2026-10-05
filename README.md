# 量化交易Agent策略框架 v2.1（quant-trading-agent）

> **判决不是终点，下一轮才是。**
> 三方闭环迭代（正方 / 反方 / 中立裁判）× 前向优先反自欺审计（F0–F6）× **上线前代码审计（D0–D4）**，
> 合成一条可执行流水线；并补上三个执行缺口：
> ★**裁判催办**（盯着正方把代码优化做完）、★**反方政委包**（风控之外必须给"怎么改"）、
> ★**部署审计**（接钱之前先扫已知致命 bug，并用代码指纹钉死"审的就是要上的"）。

## 一、它解决什么

1. **「这个结论凭什么算数？」**
   样本量算术 N\*、选择自由度诊断、差异笔审计、留一笔、DSR 试错折减、随机对照零分布。
   测不出来的时候，说「有效」和「无效」都是错的，正确答案是「**未检出**」。
2. **「研究跑到哪了、下一步做什么？」**
   判决书必须携带下一轮指令；裁判**催办**正方，连续不响应 ⇒ 停工清偿 ⇒ 终止迭代。
3. **「反方除了说不行，还会什么？」**
   政委包：`risk_register`（防守）+ `opt_prescriptions`（进攻，四件套：
   target 文件:函数 / action 可执行动作 / expected_delta 预期读数 / rollback 回退口径）。
4. **★「这份代码能不能接钱？」**（v2.1）
   上线/实盘/影子盘前扫 P0 前视、返回 nan、自造交易日历、非原子写、跨文件同名实现……
   并**自己重算代码 sha256** 与审计报告比对 —— 防「审完又改」。

**它不做**：不产出买卖信号、不下单、不改生产文件、不给仓位建议。

## 二、版本谱系

| 版本 | 载体 | 一句话 | 缺什么 |
|---|---|---|---|
| 1.0 | `strategy-adjudication` | 三方准入：G1–G8，通过即自动并入 | 判完就停，不产生下一轮 |
| — | `forward-first-audit` 1.10 | 前向优先反自欺审计（六道闸门 + FPS 因子） | 是体检手册，不驱动迭代 |
| — | `quant-agent-framework` 3.0（开发线） | 判决书携带「下一轮指令」的三方闭环 | 派了工但**不催**；反方只反对、**不给怎么改** |
| **2.0** | 本框架 | 合并上述全部 + 催办 / 政委包两条硬契约 | 只管研究结论，不管代码能不能接钱 |
| **2.1** | **本框架（现役）** | 再加 **D0–D4 部署审计** | — |

> 旧的两个 skill 已整合进本包并移除。对应关系：
> `forward-first-audit` 的六道闸门与 18 个踩坑 → `references/forward-first.md`；
> 其技术结论 → `references/precedent.md` 的 P-16…P-33；
> `quant-agent-framework` 的三方闭环协议 → 引擎 `qta_loop.py`；
> 它的 `build.sh` 五步验收 → 本包 `build.sh` 的七步验收。

## 三、环境要求与快速上手

**环境**：Python ≥ 3.9 —— 引擎层与审计层**只用标准库、零第三方依赖**；因子层 `fps_factor.py`
需要 `numpy + pandas`（缺了只会跳过这一层，其余照常）；`build.sh` 需要 `bash` + `zip` + `grep`（可选，仅分发时用）。
**无网络访问、无外部 API、无需任何密钥**；所有脚本都只在你显式指定/调用的路径上读写。

```bash
PY=python3
D=~/.workbuddy/skills/quant-trading-agent

# 0) 一键自检（必跑：引擎 33 + 审计 25 + 因子 13）
$PY $D/scripts/selftest_all.py

# 1) 跑一轮三方：round.json → verdict.json
$PY $D/scripts/qta_loop.py --round round.json --ledger qta_ledger.jsonl --out verdict.json --explain

# 2) ★ 上线/实盘/影子盘前：先审代码，再让裁判（D 组）判定能不能接钱
$PY $D/scripts/preflight_audit.py --mode live --targets <代码路径…> \
     --rollback-point "<回滚点>" --out-dir ./pf      # 退出码 3 = 有 P0，阻断
# 把 ./pf/preflight_report.json 路径填进 round.json 的 deploy.preflight.path

# 3) 分发前验收 + 打包
PY=$PY bash $D/build.sh
```

**示例轮次**（可直接跑）：`examples/round_good.json` → adopt｜
`examples/round_reject_with_commissar.json` → reject｜`examples/round_bad_protocol.json` → invalid。

## 四、目录

```
quant-trading-agent/
├── SKILL.md                     主入口：三角色 / 闭环协议 / P 系列契约 / 三组判据 / 九条铁律
├── README.md                    本文件
├── VERSION                      2.1.0
├── build.sh                     七步分发验收 + 打包 + 解包复验
├── references/
│   ├── roles.md                 三角色职责、政委包字段细则、催办状态机、部署审计职责
│   ├── protocol.md              round.json / verdict.json 完整 schema、裁决真值表、台账格式
│   ├── rubric.md                G1–G9 + F0–F6 + D0–D4 判据、阈值清单、N*/DSR/FPS 公式与局限
│   ├── forward-first.md         前向优先手册：六道闸门 + 18 个踩坑 + 十一条不许
│   ├── preflight-audit.md       ★上线前代码审计：规则表 + 自动化查不到什么 + 上线前必答清单
│   └── precedent.md             先例案卷 P-01…P-33（接入新项目前先对表）
├── scripts/
│   ├── qta_loop.py              主引擎（裁决 + 派工 + 催办 + 部署审计 + 收敛 + 自检，纯标准库）
│   ├── preflight_audit.py       ★代码审计器（P0/P1/P2 + 代码指纹 + .preflightignore）
│   ├── fps_factor.py            稳健度因子（N* / block CI / sign-flip / 自由度 / FPS）
│   ├── selftest_all.py          一键自检
│   └── fixtures/                审计器自检夹具（默认跳过，不参与生产审计）
├── examples/                    三类 round.json + 驳回带政委包示例
└── release/                     打包产物与上传清单（不入包）
```

## 五、边界与免责

- adopt 的自动并入须由宿主项目提供 apply / verify / revert；**无 revert 的候选即使全过也降级 pending**。
- D 组只判「能不能接真实资金」，**不判策略好坏**；**审计通过 ≠ 没有 bug**。
- 样本量与试验次数不足时，正确输出是 `pending` + 「还差什么」，不是 `reject`。
- 所有输出均为工程研究内容，**不构成投资建议**。

## 六、许可

见 `LICENSE.txt`。
