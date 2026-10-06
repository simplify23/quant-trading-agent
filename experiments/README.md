# Experiments

Reproduction artefacts for the paper *On the Boundary of Admission Gates*
(`paper/paper.tex`).

| File | Purpose |
|---|---|
| `exp1_injected_gate_efficacy.py` | Synthetic panel (independent candidates), three arms + ablation |
| `exp2_real_based_validation.py` | Real-data-calibrated panel (`--panel-kind strategy`) and the asset-selection counter-example (`--panel-kind asset`) |
| `exp1_results.json` | Main results, Panel I |
| `sens_n{20,40,80}_results.json` | Sensitivity in candidate count |
| `exp2_strategy_{fixed,loose}_results.json` | Panel II at inter-strategy correlation 0.89 / 0.96 |

Requires `numpy` only.

```bash
python3 exp1_injected_gate_efficacy.py --reps 400
python3 exp2_real_based_validation.py --reps 400 --panel-kind strategy --sigma-e 0.007 \
        --alphas 0.00039 0.00059 0.00098 0.00156
```

Data anchor: `etf_panel_ts.frozen-20260930.json` (29 A-share ETFs, 746 days,
backward-adjusted). Every number in the paper traces back to these JSON files.
