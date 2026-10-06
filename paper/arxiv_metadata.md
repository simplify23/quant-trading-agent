# arXiv 提交元数据（逐字段复制粘贴）

## 1. Title
On the Boundary of Admission Gates: An Injected-Truth Study of Falsification-First Selection in Quantitative Strategy Research

## 2. Authors
Tianlun Zheng
（arXiv 表单逐个录入作者；机构不在此表单填写，已写入论文正文。）

## 3. Abstract（纯文本，已去 LaTeX —— arXiv 摘要框不接受 LaTeX 命令）
Strategy research conflates two problems: finding a profitable rule, and establishing that the finding is not search luck. The latter calls for admission gates -- statistical criteria that must be satisfied before a conclusion is adopted -- yet whether gates work, and at what cost, remains untested. We introduce an injected-truth protocol with a random-admission control that adopts at the same rate as the gate; only if the gate beats this control does it carry information rather than merely raise a threshold. Across synthetic and real-calibrated panels, gates eliminate false discoveries in the weak-signal regime but cut adoption to 1--7%, and add nothing when signals are strong. Most importantly, criteria computed on absolute rather than excess returns silently reject every candidate, including true signals. Keywords: multiple testing, backtest overfitting, strategy admission, injected-truth validation, excess returns, false discovery rate

## 4. Comments
12 pages, 3 figures, 7 tables. Code and data to reproduce every result:
https://github.com/simplify23/quant-trading-agent

## 5. Primary category
q-fin.ST  (Statistical Finance)
备选：q-fin.PM（组合管理）／cs.CE（计算工程、金融与科学）

## 6. Cross-list categories
cs.AI（人工智能）、cs.CE（计算工程、金融与科学）
（1 个主分类 + 建议不超过 2 个交叉分类；过多会被编辑退回。）

## 7. Keywords（论文内已列，arXiv 表单通常不需要）
multiple testing, backtest overfitting, strategy admission, injected-truth validation, excess returns, false discovery rate

## 8. License
建议 arXiv 默认的 "arXiv.org perpetual, non-exclusive license"；
若希望允许再分发，可选 CC BY 4.0。

---

# 上传文件
`arxiv_submission.zip` —— 内含 **paper.tex 单文件**。
参考文献为内联 `thebibliography`，三张图为 TikZ/pgfplots，**无任何外部图片或 .bib 依赖**
⇒ arXiv 可直接编译，不会出现缺文件错误。

# 提交后 arXiv 会做的事
1. 自动编译 .tex 生成 PDF（你可在 "Process" 页看编译结果）；
2. 编译失败会显示 LaTeX 日志 ⇒ 本包已在本机 TeX Live 2023 上三遍编译通过（0 错误/0 警告）；
3. 需要你确认分类、许可，然后走 "Submit"；
4. 首次提交该分类需要 endorsement（若你的账号在 q-fin.ST 未被背书，arXiv 会要求一位已发表作者背书）。
