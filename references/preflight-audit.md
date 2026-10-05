# references/preflight-audit.md —— 上线 / 实盘 / 影子盘前的代码审计

> **一句话**：**接真实资金（或影子账本）之前，先把「已知会致命的 bug 形态」机械地扫一遍，
> 并且把「裁判审的就是要上线的那份代码」用指纹钉死。**
>
> 工具：`scripts/preflight_audit.py`（静态扫描 + 分级闸门）
> 闸门：`qta_loop.py` 的 **D0–D4**（部署审计组），未过 ⇒ `adopt` 降级为 `pending/deploy_blocked`

## 一、三条纪律（写死在代码里）

1. **P0 未清零 ⇒ 退出码 3**，调用方据此阻断上线（不是"提醒一下"）。
2. **报告必须携带被审代码的 sha256**；裁判（`qta_loop`）会**自己重算**再比对 ——
   防「审完又改」：拿一份通过的旧报告去上线另一份代码。
3. **宁可漏报，不可误报**：规则只收「命中即几乎必然是 bug」的形态；
   干净代码必须 0 命中（selftest 用 fixtures 双向验证）。**误报会让审计被整体无视，那比漏报更坏。**

## 二、D0–D4 闸门（引擎侧）

| 闸门 | 检查 | 不过的含义 |
|---|---|---|
| **D0** report_present | 审计报告存在且可解析 | 没审就想上 |
| **D1** code_fingerprint | ★裁判**自己重算** `deploy.code_paths` 的 sha256，与报告 `code_sha256` 逐位比对 | **审完又改** ⇒ 必须重审 |
| **D2** no_blocker | 报告 `p0_count == 0` 且 `passed == true` | 存在阻断级 bug |
| **D3** rollback_ready | `deploy.rollback_ready`（以当前声明为准，未声明才回落报告值） | 出事无法退 |
| **D4** report_fresh | 报告时间距今 ≤ `MAX_REPORT_AGE_DAYS`（默认 7 天） | 拿过期报告顶包 |

`deploy.target ∈ {shadow, live, prod}`；未声明 target ⇒ D 组不适用（向后兼容）。
**任一 D 闸门不过 ⇒ 不允许接真实资金或影子账本**，引擎派 `kind=preflight_fix` 的 blocking 任务给正方。

round.json 片段：

```json
"deploy": {
  "target": "live",
  "code_paths": ["/path/to/live_signal.py", "/path/to/engine.py"],
  "preflight": {"path": "/path/to/preflight_report.json"},
  "rollback_ready": true,
  "rollback_point": "backup: _backup_20261005 / git tag v1.8.10"
}
```

## 三、自动化能查什么（规则表）

**P0 · 阻断**（命中即禁止上线）

| 规则 | 形态 | 为什么致命 |
|---|---|---|
| `A01-shift-negative` | `.shift(-n)` | 取的是**未来**值 —— 典型前视 |
| `A01b-iloc-future` | `.iloc[i+1]` | 读到下一根（未来）数据 |
| `A02-return-nan` | `return float("nan")` | nan 比较**恒为 False** ⇒ 所有阈值闸被**静默绕过** |
| `A03-home-made-trading-calendar` | 自实现 `prev/next_trading_day` 且只跳周末 | **节后首日**算错前一交易日（同一条近似被复用到后果相反的两处） |
| `A04-threshold-vs-possible-nan` | 阈值比较 + 同文件存在**未被承认的** nan 源 | 缺数据 ⇒ 比较恒 False ⇒ 闸门放行 |

**P1 · 需逐条处置说明**

| 规则 | 形态 | 为什么危险 |
|---|---|---|
| `B01-bare-except-pass` | `except: pass` | 把故障隐藏成「正常但没数据」 |
| `B02-format-g` | `f"{x:g}"` | 静默丢精度 |
| `B03-stale-natural-days` | `(today - last).days > N` | 用**自然日**判陈旧 ⇒ 长假后必然误判（要用交易日间隔） |
| `B04-nonatomic-write` | `open(path, "w")` 直接覆盖 | 中途失败留下半个文件（台账/持仓/状态被写坏） |
| `B05-startswith-short-prefix` | `startswith("sh")` 之类短前缀 | 误伤非目标标的 ⇒ 应用精确集合或规范化后再比 |
| `B06-duplicate-implementation` | 同名函数在多个文件各自实现 | **两份同义实现 = 最危险的 bug**（先例 P-13） |

**P2 · 提示**：`C01` 硬编码成本/费率（口径未声明）｜`C02` TODO/FIXME 残留。

**抑制方式**：命中行或其上一行写 `# preflight-ok: <理由>`。被抑制的 nan 源**同时**不再连带触发 A04。

## 四、★ 自动化查不到什么（别把"审计通过"当成"没有 bug"）

静态扫描只覆盖**机械可判**的形态。下面这些**必须人工审查**，且往往更致命：

1. **口径错配**：复权 / 时点 / 成本 / 标的宇宙——四要素要显式声明；
   本项目真实事故：同一 parquet 服务两个冲突要求、ETF 未复权、口径错配凭空造出「分散化收益」。
2. **前视的业务定义**：`df["close"]` 收盘价信号当天建仓 —— 静态查不出。
   必须人工确认 `pos = signal.shift(1)`，并跑 `trading-pipeline-core` 的 `lookahead_lint.py`；
   用 `--external-json` 把外部结论并进同一份报告（外部判 fail ⇒ 直接进 P0）。
3. **策略逻辑自欺**：多重检验、选择偏差、数据可用性伪影、单笔独扛 ——
   这些是 `references/forward-first.md` 的 F0–F6 负责，**不是本审计器**。
4. **幂等 / 并发 / 状态一致性**：重复下单、状态文件与账本不一致、崩溃后恢复 ——
   仅能部分静态提示，上线前必须**跑一次 dry-run 并对拍账本**。
5. **数据新鲜度语义**：是否 fail-safe（拒出信号+告警）而不是"伪装空仓"。

**上线前人工必答清单**（逐条给"是/否 + 证据"）：

- [ ] 口径四要素（复权/时点/成本/宇宙）写在哪？指纹是多少？
- [ ] 信号与持仓错开一期了吗？用当根收盘做决策了吗？
- [ ] 数据陈旧时是**拒绝出信号 + 告警**，还是静默产出？
- [ ] 台账/持仓/状态文件是原子写 + 有备份吗？能回滚到哪个点？
- [ ] 重复执行同一天会不会重复下单/重复记账（幂等）？
- [ ] 出异常时的降级路径是什么？告警出口在哪（谁会在手机上收到）？
- [ ] 交易日历读的是权威源吗？长假前后各验一次？
- [ ] 这份代码的 sha256 与审计报告一致吗（`qta_loop` D1 会给答案）？

## 五、用法

```bash
PY=python3
D=~/.workbuddy/skills/quant-trading-agent

# 0) 审计器自检（必跑）
$PY $D/scripts/preflight_audit.py --selftest

# 1) 影子盘前（P0 阻断）
$PY $D/scripts/preflight_audit.py --mode shadow --targets <目录或文件...> --out-dir ./pf

# 2) 实盘/生产：必须给回滚点，否则直接阻断
$PY $D/scripts/preflight_audit.py --mode live --targets <目录或文件...> \
     --rollback-point "backup: _backup_20261005 / git tag v1.8.10" --out-dir ./pf

# 3) 并入外部审计（如 lookahead_lint）
$PY $D/scripts/preflight_audit.py --mode live --targets <...> --rollback-point "..." \
     --external-json external_lint.json --out-dir ./pf

# 4) 让裁判（引擎）判定这份代码能不能上
$PY $D/scripts/qta_loop.py --round round.json --ledger qta_ledger.jsonl --out verdict.json --explain
#    → 看 verdict.deploy.allowed / verdict.deploy_gates.D1_code_fingerprint
# 退出码：0 通过 ｜ 3 有 P0（阻断） ｜ 2 用法错误
```

## 六、`.preflightignore`（忽略机制）

在项目根放 `.preflightignore`，每行一个 glob（相对该文件所在目录），`#` 为注释：

```
# 审计工具的自检夹具（fixtures/ 、tests/ 已默认跳过，这里只是示范）
examples/fixtures/**
# 已下线的旧模块：迁移期临时保留（理由必须写清楚，写不出理由就是不该忽略）
legacy/deprecated_feed.py
```

**纪律**（★ 和"禁止事后改判据"同一级别）：

1. **每一条 ignore 必须写理由**，报告里会原样列出 `ignore_files` 与 `ignored_patterns`，
   所以它**不可能被偷偷掩盖**。
2. **指纹范围 = 审计范围**：被 ignore 的文件既不扫描、也不进 `code_sha256`（两者必须一致，
   否则 D1 会假性不一致）。selftest 已断言这一点。
3. **不许用 ignore 掩盖真问题**：ignore 的正当用途只有两类 ——
  ① 测试夹具/示例代码；② **有明确语义声明**的工具代码（如因子层的 nan 哨兵）。
   后者更推荐用行内 `# preflight-ok: <理由>`，因为它是**逐处**声明，而不是整文件开天窗。

## 七、它和 F0–F6 的分工

| 层 | 问的问题 | 谁负责 |
|---|---|---|
| **F0–F6**（前向体检） | 这个**结论**凭什么算数？（样本量/自由度/差异笔/单笔独扛） | `forward-first.md` |
| **D0–D4**（部署审计） | 这份**代码**有没有已知会致命的 bug？审完有没有被改？ | 本文档 |
| **G1–G9**（准入） | 这个**改动**该不该并入系统？ | `rubric.md` |

三者都过，才轮到"要不要接钱"。**审计通过 ≠ 没有 bug**，只等于"已知的致命形态没有出现"。

> 所有输出均为工程研究内容，**不构成投资建议**。
