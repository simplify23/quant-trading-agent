# PUBLISH.md —— Skill Hub 上传清单（只给发布者）

## 包信息

| 项 | 值 |
|---|---|
| 包 | `quant-trading-agent-v2.2.0-<日期>.zip`（由 `build.sh` 产出） |
| name / version | `quant-trading-agent` / `2.2.0` |
| display_name | 量化交易Agent策略框架 · 三方闭环 × 前向体检 × 上线前审计 |
| display_name_en | Quant Trading Agent Framework v2.1 |
| category | 量化研究 / 投资研究工具 |
| 作者 | 用户自填（LICENSE.txt 版权行 + SKILL.md frontmatter 可补 `author`/`author_url`） |

## 版本谱系（展示页建议写）

1.0 `strategy-adjudication`（静态准入，判完即停）
→ 并行沉淀 `forward-first-audit` 1.10（前向优先反自欺审计）
→ 合并为 **2.0 三方闭环**（判决书携带下一轮指令 + 裁判催办 + 反方政委包）
→ **2.1** 再加 **D0–D4 部署审计**（上线/实盘/影子盘前的代码 bug 闸门 + 代码指纹防「审完又改」）

## 上传前检查（`build.sh` 八步，全部通过）

- [x] 1/8 引擎自检 `qta_loop --selftest`（40 项）
- [x] 2/8 审计器自检 `preflight_audit --selftest`（25 项，含★误报闸：干净代码必须 0 命中）
- [x] 3/8 度量层自检 `overfit_metrics --selftest`（10 项：PBO/SPA 白噪声校准 + 方向性）
- [x] 4/8 因子层自检 `fps_factor --selftest`（13 项；缺 numpy/pandas 时明确标注「未测」而非「通过」）
- [x] 5/8 三类示例轮次给出预期判决（adopt / reject / invalid）
- [x] 6/8 端到端部署审计：真实跑 D0–D4 并断言裁判重算指纹与报告一致
- [x] 7/8 脱敏扫描（`.py/.md/.json` 内任何本机路径 / 凭据 / 账户信息一律拦截）
- [x] 8/8 打包 + 解包复验（release/ 与 `__pycache__` 必须排除）

## 待人工完成

- [ ] 上传渠道：WorkBuddy 客户端「技能」→ 上传自定义技能；或技能市场后台提交 zip
- [ ] 展示图标（512×512，可选；可用深色三角闭环 + 盾牌构图）
- [ ] 定价档位（免费版=本包全量；做付费版须按 `skill-package-release` §三 **物理切分**，勿只做标记）

## 已知边界（页面描述建议原样引用）

框架裁决三件事：**研究结论能不能并入系统 / 迭代该不该继续 / 这份代码能不能接真实资金**。
它**不产出买卖信号、不下单、不改生产文件、不给仓位**。
`pending` ≠ 无效（未检出）；**审计通过 ≠ 没有 bug**（只等于已知的致命形态未出现）。

## 免责

所有输出均为工程研究内容，**不构成投资建议**。
