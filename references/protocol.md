# references/protocol.md —— 轮次与判决书契约（v2.0）

## 一、round.json（每轮输入：正方 + 反方产出，裁判独立复核）

```json
{
  "round_id": 7,
  "candidate": {
    "id": "BS-1-factor-weight",
    "name": "因子两档权重 → 连续风险预算权重",
    "family": "weighting",                       // 同族候选共享 family，跨轮族级计数用
    "kind": "single_key",                        // 与 metrics.context 各分册的键对齐
    "uses": ["ret20", "log_mv"],                 // G5 只查这些变量的覆盖率
    "change": {"is_change": true, "target": "engine.py:weight()",
               "actual_files": ["engine.py", "risk.py"]}   // ★P9：改动指向 + 实际改动文件（对不上 ⇒ invalid）
  },
  "metrics": {
    "baseline":  {"ann": 0.100, "mdd": -0.300, "n": 480, "sharpe": 0.62},
    "candidate": {"ann": 0.300, "mdd": -0.200, "n": 500, "sharpe": 2.00,
                  "skew": 0.0, "kurt": 3.0},
    "context": {
      "anchors_ok": true,                        // G1 口径锚点复验
      "coverage": {"ret20": 96.2, "log_mv": 100.0},
      "region": {"single_key": 6},               // G6 连续优区格数（密集网格扫描产出）
      "removed_by_year": {"single_key": {"2023": 120, "2024": 110, "2025": 100}},
      "base_by_year":    {"2023": 160, "2024": 170, "2025": 170},
      "no_lookahead":    {"single_key": {"ann": 0.250}},   // G8 阈值只用 ≤t 信息重算
      "trials": 3,                               // G9a 台账累计训练段候选数（★含被你忘掉的那些）
      "ppy": 242,                                // 年化周期（A股242 / 美股252 / BTC365）
      "pbo": 0.31,                               // G9b 过拟合概率（overfit_metrics.py --pbo）★软闸
      "spa_p": 0.012,                            // G9c Hansen SPA p 值（overfit_metrics.py --spa）
      "novelty": {"max_rho": 0.22, "against": ["BS-3", "BS-7"]},   // G10 与已采纳结论集的相关性
      "panel_ic": {"ic": 0.031, "t_adj": 3.1, "ir": 0.62, "n_days": 322}  // G11 面板级截面 IC
    }
  },
  "fwd": {                                       // ★ v2.0 新增：前向优先体检段（缺 ⇒ 判决封顶 pending）
    "coverage": "full",                          // full | partial | none
    "panel_md5": "3fe4b466698bfe84be3a4be49e1f5258",
    "caliber": {"adjust": "后复权", "asof": "D−1 收盘",
                "cost": "单边 3bp", "universe": "29 只场内 ETF"},
    "n_obs": 500, "mean": 0.0125, "sd": 0.06,    // F1 算 N*
    "per_day_max_candidates": 5,                 // F2 选择自由度诊断
    "rank_key_source": "train",                  // F3 train | holdout | full（后两者 ⇒ invalid）
    "is_change": true,                           // 改动型候选 ⇒ F5 必填
    "diff_trades": {                             // F5 差异笔集合审计
      "added":   {"n": 60, "mean": 0.0318, "ci": [0.005, 0.0505], "p": 0.021},
      "removed": {"n": 20, "mean": -0.0146, "ci": [-0.032, -0.001], "p": 0.038}
    },
    "loo": {"total": 30.0, "best_trade": 8.0, "ex_best": 12.0}   // F6 留一笔
  },
  "proponent": {
    "claims": [{"claim": "机制：风险预算优于打分加权", "evidence": "E-x118 §3"}],
    "failure_conditions": ["若 G6 连续优区 <4 格 ⇒ 承认为切点挑选"],
    "responded_tasks": ["T-6-1"],                // ★ P7：上一轮 blocking 任务的回应（不回填 = 未响应）
    "code_opt_points": [                         // ★ P7b：代码级硬编码盲区清单
      {"id": "BS-7", "locus": "engine.py:weight()",
       "why_hardcoded": "持仓权重只有 {0.5,1.0} 两档，从未进过搜索自由度"}
    ]
  },
  "adversary": {
    "objections": [{"objection": "mdd 改善可能只是低敞口的副产品",
                    "prereg": "若 Calmar 未上移 ⇒ 是稀释而非改善"}],
    "directions": [{"direction": "逆波动加权替代两档权重", "mechanism": "风险预算",
                    "prereg": "Calmar ≥ 基线 + 0.1", "cost": "low", "priority": 1}],
    "commissar_pack": {                          // ★ P6：非采纳轮必填（四要素齐）
      "risk_register": [
        {"risk": "收益集中在单一年份", "trigger": "影响集单年占比 > 50%",
         "action": "分年拆解 + 留一笔复核", "severity": "high"}
      ],
      "opt_prescriptions": [
        {"target": "engine.py:weight()",
         "action": "w∈{0.5,1.0} → clamp(σ_target/σ_i, 0.2, 1.0)",
         "mechanism": "风险预算：按下行波动反向给权重", "expected_delta": "Calmar +0.15",
         "cost": "low", "priority": 1, "rollback": "恢复 w∈{0.5,1.0} 并删掉 σ_target"}
      ]
    },
    "unrefuted_focus": ["基线的 mdd 优势是否只是低敞口的副产品"]
  },
  "deploy": {                                    // ★ v2.1：上线/实盘/影子盘前的代码审计（未声明 target ⇒ D 组不适用）
    "target": "live",                            // shadow | live | prod
    "code_paths": ["/abs/path/live_signal.py", "/abs/path/engine.py"],
    "preflight": {"path": "/abs/path/preflight_report.json"},   // 由 preflight_audit.py 产出
    "rollback_ready": true,
    "rollback_point": "backup: _backup_20261005 / git tag v1.8.10"
  },
  "blueocean": {"dims": ["ETF 折溢价 / 份额流"]},   // 蓝海探测透传，可空
  "config": {"metric_key": "ann", "risk_key": "mdd", "budget_left": 5, "max_rounds": 12}
}
```

## 二、verdict.json（判决书，裁判产出）

```json
{
  "schema": "qta-verdict/2.0", "version": "2.0.0",
  "round_id": 7, "candidate_id": "BS-1-factor-weight", "ts": "2026-10-05 21:00:00",
  "verdict": "adopt | reject | pending | invalid",
  "reason_bucket": "effective | evidence_pending | not_detected | evidence_against | protocol_invalid",
  "gates":     {"G1_anchors": {"pass": true, "detail": "…"}, "…": {}},
  "fwd_gates": {"F1_nstar":   {"pass": false, "detail": "N*=93，n=33 ⇒ 未检出"}, "…": {}},
  "deploy_gates": {"D1_code_fingerprint": {"pass": false, "detail": "裁判重算 … vs 报告 …⇒ 不一致"}, "…": {}},
  "deploy": {"applicable": true, "target": "live", "allowed": false,
             "blockers": ["D1_code_fingerprint"],
             "fingerprint_now": "…", "fingerprint_report": "…",
             "report_path": "…", "report_ts": "…", "report_age_days": 0.1, "notes": []},
  "fwd_summary": {"coverage": "full", "Nstar": 93, "n_obs": 33, "mean": 0.0125, "sd": 0.06,
                  "inconclusive": true, "selection_dof": "present",
                  "single_trade_carried": false, "diff_undecided": [], "notes": []},
  "protocol_violations": [],
  "protocol_warnings": [],
  "criteria_sha": "16 位指纹（判据 + 阈值 + 常量）",
  "next_round": {
    "continue": true, "stop_reason": null,
    "rounds_since_adopt": 2, "budget_left": 4,
    "hold_new_candidates": false,
    "proponent_tasks": [
      {"id": "T-8-1", "kind": "code_optimization", "blocking": true, "due_round": 8,
       "task": "继续挖代码级硬编码盲区并提交 BS-x 清单", "why": "P12：纯搜索边际增量为零",
       "priority": 1}
    ],
    "adversary_focus": ["下一轮优先击穿未被反驳的主张：…"],
    "commissar_directives": [
      {"to": "adversary", "demand": "政委包四件套：target + action + expected_delta + rollback", "priority": 1}
    ],
    "blueocean_dims": ["ETF 折溢价 / 份额流"],
    "coach": {
      "nag_level": 1,
      "nag_message": "⚠️ 催办 L1：正方未响应上一轮派工（1 条）…",
      "must_do": [{"task_id": "T-8-1", "kind": "code_optimization", "blocking": true}],
      "code_backlog_open": 2,
      "escalation": null
    }
  }
}
```

## 三、裁决逻辑（真值表）

| 情形 | verdict | reason_bucket | 下一轮派工 |
|---|---|---|---|
| 协议违规（P1/P3/P6/P8） | **invalid** | protocol_invalid | 修协议再交；**本轮不进台账** |
| 硬闸全过 + 软闸全过 + F 组全过 + 已到 N\* | **adopt** | effective | 巩固（邻域/成本/执行可行性）+ **代码优化** |
| 硬闸全过、软闸或 F 组有缺 | **pending** | evidence_pending | 补缺失判据的证据 + 反方修 F 缺口 |
| 硬闸全过，但 F1 未到 N\* | **pending** | **not_detected** | 补样本 / 改面板级检验（★不许判死） |
| 硬闸未过，且 F1 未到 N\*（或未做体检） | **pending** | **not_detected** | ★同上 —— **测不出 ≠ 无效** |
| 硬闸未过，且样本已到 N\* | **reject** | evidence_against | 反方 directions Top3 + 政委处方 + 代码优化 |
| 以上皆过，但 D 组部署审计未过 | **pending** | **deploy_blocked** | ★修阻断项 → 重跑 `preflight_audit` → 用新报告重开一轮 |

**收敛四闸**（任一 ⇒ `continue=false`）：
`budget_left ≤ 0` ｜ `rounds_since_adopt ≥ 3` ｜ `round_id ≥ max_rounds` ｜ ★`nag_level ≥ 3`。

**催办状态机**：

```
nag=0 ──(上轮派工未响应)──> nag=1 ──(再未响应)──> nag=2 [hold_new_candidates=true]
  ^                            │                      │
  └────(responded_tasks 覆盖)──┘                      └──(再未响应)──> nag=3 [收敛停止]
```

## 四、台账（qta_ledger.jsonl）

**只在给出 `--out` 时追加**；`invalid` 轮**不写**（否则污染 `rounds_since_adopt` / 同族计数 / 催办链）。
每行记录：`round_id / candidate / verdict / reason_bucket / failed_gates / failed_fwd /
fwd_summary / nag_level / next_round.proponent_tasks / ts`。

## 五、CLI

```bash
PY=python3
D=~/.workbuddy/skills/quant-trading-agent

$PY $D/scripts/qta_loop.py --selftest                       # 自检（必跑）
$PY $D/scripts/qta_loop.py --round r.json --ledger l.jsonl --out v.json --explain
$PY $D/scripts/qta_loop.py --round r.json --no-nag --explain   # 关催办（仅调试，会破坏 P7）

# ★ 上线/实盘/影子盘前：先生成审计报告，再让裁判（D 组）判定
$PY $D/scripts/preflight_audit.py --mode live --targets <代码路径…> \
     --rollback-point "<回滚点>" --out-dir ./pf      # 退出码 3 = 有 P0，阻断
# 把 ./pf/preflight_report.json 的路径填进 round.json 的 deploy.preflight.path 即可
```

## 六、宿主项目接入（adopt 的自动执行）

沿用 1.0 的 apply/verify/revert 契约：adopt ⇒ apply → verify →（失败自动 revert）；
**候选无 revert ⇒ 即使全过也降级 pending**。本引擎只负责裁决与派工，**不负责改生产文件**。
