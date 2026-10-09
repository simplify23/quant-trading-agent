# quant-trading-agent

> **A falsification-first research framework for quantitative strategy selection.**
> A triad closed loop — proponent / adversary / neutral judge — wrapped around a
> forward-first anti-self-deception audit and a pre-deployment code audit.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE.txt)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB.svg)](https://www.python.org/)
[![Version](https://img.shields.io/badge/version-2.2.1-informational.svg)](VERSION)
[![arXiv](https://img.shields.io/badge/arXiv-2610.07701-b31b1b.svg)](https://arxiv.org/abs/2610.07701)
[![Paper](https://img.shields.io/badge/paper-PDF%20%2812pp%29-lightgrey.svg)](paper/paper.pdf)
[![Self-tests](https://img.shields.io/badge/self--tests-88%20passing-brightgreen.svg)](scripts/selftest_all.py)

[中文说明](README.zh-CN.md) · [Reproduction artefacts](experiments/) · [Paper source](paper/)

---

## 📄 Paper

### On the Boundary of Admission Gates: An Injected-Truth Study of Falsification-First Selection in Quantitative Strategy Research

**Tianlun Zheng** (Fudan University) · 2026 · 12 pages · **arXiv:[2610.07701](https://arxiv.org/abs/2610.07701)** [cs.AI; cs.CE]

🔗 **[arXiv:2610.07701](https://arxiv.org/abs/2610.07701)** ｜ 📕 **[Read the PDF](paper/paper.pdf)** ｜ 📝 [LaTeX source](paper/paper.tex) ｜
🔍 [Pre-submission audit](paper/review_checklist.md) ｜ 🧪 [Experiments](experiments/)

**The question.** Every automated research pipeline that admits conclusions must decide
*when to stop believing its own output*. Admission gates are the instrument that decision
rests on — yet their effectiveness is usually **assumed rather than measured**. We measure it.

**What we find.**

| Finding | Result |
|---|---|
| **Gates are not just "more conservative"** | At an **equal adoption rate**, the gate's false-discovery rate is well below a coin-flip control (ΔFDR = 0.10–0.60, holding in 5 of 7 settings) |
| **But their value has a boundary** | It materialises only for training-period $t < 2.5$; the cost is an adoption rate of **1–7%** |
| **Beyond $t \approx 2.5$ they are pure overhead** | Pure search already errs essentially never, and gating only lowers the adoption rate |
| **★ A necessary condition** | Criteria computed on **absolute** rather than **excess** returns **silently reject every candidate** — including a ground-truth signal with $t = 4.0$ |

**Why it matters.** If gates are weaker than assumed, the pipelines relying on them inherit an
unbounded false-discovery risk; if they are merely conservative, those pipelines silently
discard real findings. **Neither failure is visible from the outside.**

**Cite it**

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

## What this repository contains

This repository serves two purposes at once:

**① The code and experiments behind the paper.** The protocol is reproducible end to end:

```bash
python3 experiments/exp1_injected_gate_efficacy.py --reps 400          # synthetic panel
python3 experiments/exp2_real_based_validation.py --reps 400 \
        --panel-kind strategy --sigma-e 0.007 \
        --alphas 0.00039 0.00059 0.00098 0.00156                       # real-calibrated
```

Every number in the paper traces back to the `*_results.json` files in
[`experiments/`](experiments/). The data anchor is a 29-ETF A-share panel (746 days,
backward-adjusted): 29 assets, 745 return points, kurtosis 7.84, mean cross-sectional
correlation 0.504.

**② A runnable framework** — the same triad loop used to generate the paper's negative
results, packaged so you can point it at your own project.

| It answers | How |
|---|---|
| *"Does this conclusion deserve to be believed?"* | Sample-size arithmetic $N^*$, selection-degree-of-freedom diagnostics, difference-trade auditing, leave-one-out, DSR trial deflation, random-control null distributions |
| *"Where is the research and what is next?"* | Every verdict carries next-round directives; the judge **nags** the proponent, escalating to work stoppage, then termination |
| *"Can the adversary do more than say no?"* | A commissar pack: `risk_register` (defence) **plus** `opt_prescriptions` (offence) — each with target `file:function`, an executable action, an expected delta, and a rollback path |
| *"★ Can this code take real money?"* | Pre-deployment audit (D0–D4): look-ahead, `nan` returns, home-made trading calendars, non-atomic writes, cross-file duplicate implementations — with a **recomputed sha256 fingerprint** so the judge verifies what was audited is what ships |

**It does not** produce trading signals, place orders, modify production files, or give
position advice.

---

## Quick start

```bash
PY=python3
D=.

# 0) Self-tests — must pass first (engine 40 + audit 25 + metrics 10 + factor 13 = 88)
$PY $D/scripts/selftest_all.py

# 1) Run one triad round: round.json → verdict.json
$PY $D/scripts/qta_loop.py --round examples/round_good.json \
     --ledger qta_ledger.jsonl --out verdict.json --explain

# 2) ★ Before going live / paper-trading: audit the code, then let the judge rule
$PY $D/scripts/preflight_audit.py --mode live --targets <code paths...> \
     --rollback-point "<rollback point>" --out-dir ./pf      # exit 3 = P0 present, blocks
# then put ./pf/preflight_report.json into round.json's deploy.preflight.path

# 3) Distribution check + packaging
PY=$PY bash $D/build.sh
```

**Three example rounds** you can run immediately:
`examples/round_good.json` → adopt ｜ `examples/round_reject_with_commissar.json` → reject ｜
`examples/round_bad_protocol.json` → invalid.

**Requirements.** Python ≥ 3.9. The engine, audit and metrics layers use the
**standard library only** — zero third-party dependencies. Only the factor layer
(`fps_factor.py`) needs `numpy + pandas`, and if they are missing it is reported as
**not measured**, never as a failure. No network access, no API keys; scripts read and
write only the paths you pass them.

---

## Repository layout

```
quant-trading-agent/
├── CITATION.cff                 ★ "Cite this repository" metadata (points at the paper)
├── SKILL.md                     Framework entry: roles / loop protocol / P-contracts / gates
├── README.md                    This file
├── README.zh-CN.md              Chinese version
├── VERSION                      2.2.1
├── build.sh                     Eight-step distribution check + packaging
├── LICENSE.txt                  MIT
├── paper/                       ★ The paper
│   ├── paper.tex / paper.pdf    12 pages, compile with pdflatex (no external assets)
│   ├── arxiv_metadata.md        Copy-paste fields for the arXiv submission form
│   ├── review_checklist.md      Pre-submission format audit (4 rounds)
│   └── writing_notes_and_audit.md  Digested writing advice + 16-point self-audit
├── experiments/                 ★ Reproduction artefacts (see above)
├── references/
│   ├── roles.md                 Role duties, commissar-pack schema, nag state machine
│   ├── protocol.md              round.json / verdict.json schemas, verdict truth table
│   ├── rubric.md                G1–G11 + F0–F6 + D0–D4 thresholds; N*/DSR/PBO/SPA limits
│   ├── forward-first.md         Forward-first handbook: six gates + 18 pitfalls
│   ├── preflight-audit.md       ★ Pre-deployment audit: rule table + what it cannot catch
│   └── precedent.md             Case file P-01…P-38 (check against it before adopting)
├── scripts/
│   ├── qta_loop.py              Main engine (verdict + dispatch + nag + deploy audit)
│   ├── preflight_audit.py       ★ Code auditor (P0/P1/P2 + code fingerprint)
│   ├── overfit_metrics.py       ★ PBO/CSCV + Hansen SPA, stdlib-only, noise-calibrated
│   ├── fps_factor.py            Robustness factor (N* / block CI / sign-flip / FPS)
│   └── selftest_all.py          One-shot self-test
└── examples/                    Three sample rounds
```

---

## Scope and disclaimer

- Automatic adoption of an `adopt` verdict requires the host project to provide
  apply / verify / revert; **a candidate with no rollback path is downgraded to `pending`
  even if it passes everything else**.
- The deploy gates judge only *"can this take real money"*, **not whether the strategy is
  good**. **Passing an audit is not the same as being bug-free.**
- When sample size or trial count is insufficient, the correct output is
  `pending` + "what is still missing" — never `reject`. **"Not detected" is not "invalid".**
- All output is engineering research. **Not investment advice.**

## License

MIT — see [LICENSE.txt](LICENSE.txt).
