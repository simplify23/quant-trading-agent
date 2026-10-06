# 论文写作心得（翻译整理）与本文审计

> 来源：Simon Peyton Jones（Microsoft Research）《How to Write a Great Research Paper》、
> Neel Nanda（Google DeepMind）、Andrej Karpathy、Google Research《How to Write a Research Paper》、
> 《How to write a Conference Paper》。下文为**翻译+提炼**，并逐条对照审计本文 `paper.tex`。

---

## 一、Simon Peyton Jones（微软研究院）：七条建议

> 原文出处：MSR Cambridge，*How to Write a Great Research Paper*（流传最广的写作指南之一）

### 1. Don't wait: write（别等，现在就写）
**两种模式**：① 想法 → 做研究 → 写论文；② 想法 → 写论文 → 做研究 → 再写论文。
**SPJ 主张第二种。** 理由：写作会迫使你清楚、聚焦、暴露你其实没搞懂的地方，
并打开与他人对话（现实检验、批评、合作）的通道。
★ 原话：*"Writing papers is a primary mechanism for doing research (not just for reporting it)."*
（写论文是**做研究**的主要机制，不只是汇报研究。）

### 2. Identify your key idea（锁定你的核心想法）
- **"one ping"**：一篇论文只应有一个清晰、锐利的主意。听不清"ping"就是没写好。
- **想法 = 可复用的洞见**，对读者有用。
- 必须 **100% 明确**写出来：*"The main idea of this paper is …"*
- 如果你有很多想法 → 写很多篇论文。

### 3. Tell a story（讲一个故事）
把论文写成**在白板上向同事解释**的样子。叙事流：
> 这里有（没解）一个**有趣**的问题 → 这里有我的**想法** → 想法**管用**（细节、数据）
> → 我的想法与**他人方案**相比如何

每一句都要让读者想读下一句；读者在任何位置停下，都应带走了有价值的东西。

### 4. Nail your contributions to the mast（把贡献钉在桅杆上）
- ★**先写贡献清单**——"贡献清单驱动整篇论文"，正文只有一个任务：**为这些主张提供证据**。
- 用**带前向引用的 bullet 列表**（读者扫读时，短句最抓眼）。
- ★**贡献必须是"可被推翻的"（refutable）主张**。原著给了 YES/NO 对照：
  - YES：可验证的具体声明
  - NO："我们研究了 X"（含糊，无法证伪）
- ★**不要写"本文结构如下：第 2 节…第 8 节结论"**——"没有人读这个"。

### 5. Related work：**不要紧跟在 Introduction 之后**
★★ 这条最反直觉，原文写的很直接：
> *"Early related work forms a barrier between your reader and your idea."*
> （过早的相关工作会在读者与你的想法之间竖起一道墙。）

因为读者此时**还没有**你的术语和记号（"no notational scaffolding"），读不懂在比较什么。
**建议位置：放在技术细节之后。** 当然，正文中随时可以引用相关工作。

### 6. （对应"用例子引路"）
- **Introduction 只做两件事：① 描述问题（用一个例子引出）② 列出贡献。仅此而已，一页。**
- ★**"Molehills not mountains"**（是土堆，不是高山）：不要夸大问题的重要性。
  反例：*"程序经常有 bug，消除 bug 非常重要[1,2]。很多研究者尝试过[3,4,5,6]。它真的非常重要。"*

### 7. 结构与读者留存（"每写一句，读者就死掉一批"）

| 部分 | 读者数 | 篇幅 |
|---|---|---|
| Title | 1000 | — |
| **Abstract（4 句话）** | 100 | — |
| **Introduction** | 100 | **1 页** |
| The problem | 10 | 1 页 |
| My idea | 10 | 2 页 |
| The details | 3 | 5 页 |
| Related work | 10 | 1–2 页 |
| Conclusions | — | 0.5 页 |

**摘要 = 四句话（Kent Beck）**：① 陈述问题 ② 说明为什么这个问题有趣 ③ 说明你的方案达成了什么
④ 说明由此带来什么。★ 原话：*"I usually write the abstract last."*（摘要最后写。）

---

## 二、Neel Nanda（Google DeepMind）：三支柱

> 原文：*"A paper is a short, rigorous, evidence-based technical story with a takeaway readers care about."*
> （论文是一个简短、严谨、基于证据的技术故事，且其结论是读者在乎的。）

| 支柱 | 要求 | 常见失败 |
|---|---|---|
| **The What** | 1–3 个**具体、新颖**、彼此构成连贯主题的主张 | "我们研究了 X"（含糊、无法证伪） |
| **The Why** | 严谨的实证证据支撑主张 | 只给"效果不错"，而非能**区分竞争假说**的实验 |
| **The So What** | 读者为什么在乎；与社区公认的重要问题关联 | 只罗列实验，不说明意义 |

★ **三支柱必须在引言结束时全部交代清楚。**

---

## 三、Andrej Karpathy：一句话贡献测试

> *"A paper is not a random collection of experiments you report on. The paper sells a single thing
> that was not obvious or present before."*

**实用推论：如果你无法用一句话说出你的贡献，你还没有一篇论文。**

补充（NeurIPS 官方指南）：*"originality does not necessarily require an entirely new method"* ——
对既有方法给出**新的理解**同样构成原创贡献。

---

## 四、Google Research：面向怀疑者写作（四条）

> 原文：*"Convince a skeptic that your work is trustworthy. The world is full of bad research; prove that yours is good."*

1. **Never assume anything, even if it's "obvious"** —— 任何论据都要给引用；给不出引用就自己取证。
2. **Admit your work's limitations** —— ★"Don't diminish or hide limitations. It is intellectually
   dishonest and, once detected, will make your reader question the validity of your work."
   （不要淡化或隐藏局限。这既不诚实，而且一旦被发现，读者会质疑你整篇工作的有效性。）
   **建议单设 Limitations 小节。**
3. **Compare fairly to related work** —— 先做文献检索（Google Scholar / 会议论文集 / 别人的 Related Work）；
   如果发现你不是第一个，看能否做得**更好、更快、更便宜、更大规模**。
4. **Provide all information the reader needs** —— 完整证明、问卷放附录；**尽量开源代码与数据**。

**格式约定（Google 版）**：
- 标题、作者序列、作者注（免责/利益冲突/致谢）
- 摘要应涵盖：**问题 → 重要性 → 贡献 → 发现 → 结论**
- ★**把重要数字放进图表**——"It's easier to spot key numbers in a table or graph than to have to
  read through the text"；★**"Good figures are essential"**，图不清楚可以构成拒稿理由
- 用 bullet 列表与加粗标签段落（便于扫读者定位）
- 结构对非英语母语者**尤其**重要

> 另一份 Google 文档《How to write a Conference Paper》补充：
> ★**不要把"描述方法"写进问题小节**；★**每个实验先说要回答什么问题**；
> ★**不要假设读者会自己看表格里的数字——你必须替他们解读，明确说明数字如何支持你的主张**。

---

## 五、★ 对本文 `paper.tex` 的逐条审计

| # | 原则 | 本文现状 | 判定 |
|---|---|---|---|
| 1 | **一句话贡献**（Karpathy） | "Gates raise decisional precision at a substantial cost in recall." | ✅ 有 |
| 2 | **The What / Why / So What**（Nanda）在引言末交代清楚 | §1.3 给了 What/Why；**So What 偏弱**（未点明"读者为什么在乎"） | ⚠️ **可加强** |
| 3 | **贡献可证伪**（SPJ） | 4 条贡献均带前向引用（\S2.4/\S5/\S5.3/\S5.4）且具体 | ✅ |
| 4 | **摘要 = 四句话**（SPJ/Kent Beck） | 130 词，含问题/协议/结果/核心发现 | ✅ 结构合规 |
| 5 | **Introduction ≤ 1 页** | 约 1.1 页（含贡献列表） | ✅ 基本达标 |
| 6 | **不要"本文结构如下"**（SPJ） | **未出现** | ✅ |
| 7 | **不要夸大问题**（Molehills not mountains） | 引 Ioannidis/HLZ/HXZ 的**真实数据**支撑，未空喊 | ✅ |
| 8 | **Related work 不挡在想法前**（SPJ） | §2 在 Introduction 之后 ⚠️；但 Introduction 已充分交代 idea 与贡献，未形成"墙"；且 ML/金融领域惯例是 §2 | ⚠️ 可接受，**但应更短** |
| 9 | ★**重要数字放进图表**（Google） | **7 张表、0 张图** | ❌ **最大缺口** |
| 10 | ★**"Good figures are essential"**（Google） | 无任何图 | ❌ **同上** |
| 11 | **替读者解读表格数字** | §5.1/§5.2 均有"Table X reports…"式解读 | ✅ |
| 12 | **单设 Limitations**（Google） | §6.3 有 5 条 | ✅ |
| 13 | **开源代码与数据**（Google） | `\thanks` 里给了 GitHub URL，仓库已含 paper/ 与 experiments/ | ✅ |
| 14 | **公平比较相关工作**（Google） | §2 逐支对比 + 定位表；未贬低他人 | ✅ |
| 15 | **每个实验先说要回答什么问题** | §4/§5 各小节以目的开头 | ✅ |
| 16 | **不要"我们做了 A，然后做了 B"式流水账**（SPJ 隐含） | 未见 | ✅ |

### 审计结论

**最重要的缺口是 #9/#10：全文没有一张图。** Google 的指南把"图"提到"essential"的高度
（图不清晰可构成拒稿理由），而本文 100% 依赖表格传达结果。这在两处特别吃亏：
① 三组对照的 FDR 随信号强度的变化，**用折线图比用表格直观一个量级**；
② 缺少一张**协议示意图**，读者需读完 §3 才能建立心理图像。

次要缺口是 #2（So What 偏弱）与 #8（Related Work 可再压缩）。

---

## 六、改写清单（本轮执行）

- [x] **新增 Figure 1：协议示意图**（注入真值 + 三类面板 + 三组对照）——纯 TikZ，无外部图片依赖
- [x] **新增 Figure 2：核心结果图**（FDR vs 训练段 t，A/B/C 三组）——pgfplots
- [x] **新增 Figure 3：判据拦截率**（诊断实验）——pgfplots
- [x] **§1.3 补强 So What**：点明"任何带准入层的自动化研究系统都依赖这个未经验证的假设"
- [x] **§2 压缩**：四支文献各压至 3–4 句，把篇幅让给图表
- [ ] （未做）Related Work 后移——与 ML/金融领域惯例冲突，保留 §2 但缩短

---

*本文件为写作方法整理与自我审计，非论文正文。*
