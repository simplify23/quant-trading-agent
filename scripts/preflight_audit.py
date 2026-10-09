#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preflight_audit.py —— 上线 / 实盘 / 影子盘前的代码审计（静态扫描 + 分级闸门）

─── 与论文的关系 ───────────────────────────────────────────────────────────────
本文件是论文《On the Boundary of Admission Gates: An Injected-Truth Study of
Falsification-First Selection in Quantitative Strategy Research》(Zheng, 2026) 所述
框架的参考实现之一。若你在研究中使用本实现或其判据，请引用该论文（首选）或本仓库：
  @article{zheng2026admissiongates,
    title  = {On the Boundary of Admission Gates: An Injected-Truth Study of
              Falsification-First Selection in Quantitative Strategy Research},
    author = {Zheng, Tianlun}, year = {2026},
    note   = {Code: https://github.com/simplify23/quant-trading-agent}
  }

定位：**在把代码接上真实资金或影子账本之前，先把「已知会致命的 bug 形态」机械地扫一遍。**
它只做**机械可判**的部分；语义级的前视/口径审查（"今天收盘的信号赚今天的钱"这类）仍需人工 +
`trading-pipeline-core` 的 lookahead_lint，可用 `--external-json` 把外部结论并进同一份报告。

★ 三条纪律（写死在代码里）：
  1. **P0 未清零 ⇒ 退出码 3**，调用方（qta_loop 的 D 组闸门）据此阻断上线；
  2. **报告必须携带被审代码的 sha256**（`code_sha256`）——裁判会**自己重算**再比对，防「审完又改」；
  3. **宁可漏报，不可误报**：规则只收「命中即几乎必然是 bug」的形态；干净代码必须 0 命中（selftest 验）。
     误报会让审计失去可信度，进而被整体无视 —— 那是比漏报更坏的结局。

抑制方式：在命中行的**同一行或上一行**写 `# preflight-ok: <理由>`。

用法：
  PY=python3
  $PY scripts/preflight_audit.py --selftest
  $PY scripts/preflight_audit.py --mode live --targets <目录或文件...> \
       --rollback-point "backup dir / git tag" --out-dir ./preflight_out
  # 退出码：0 通过 ｜ 3 有 P0（阻断） ｜ 2 用法错误
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, asdict
from pathlib import Path

VERSION = "1.0.0"
SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules", ".mypy_cache",
             ".idea", ".vscode", "fixtures", "tests", "testdata"}
IGNORE_FILE = ".preflightignore"     # 每行一个 glob（相对该文件所在目录）；# 为注释
MAX_REPORT_AGE_DAYS = 7              # 报告最大可接受年龄（qta_loop 的 D4 用它）
SUPPRESS = re.compile(r"#\s*preflight-ok\s*:", re.I)


# ---------------------------------------------------------------- 数据结构
@dataclass
class Finding:
    rule: str
    severity: str          # P0 / P1 / P2
    file: str
    line: int
    snippet: str
    why: str
    fix: str


@dataclass
class Rule:
    rid: str
    severity: str
    pattern: re.Pattern
    why: str
    fix: str
    body_check: str | None = None      # "calendar_weekend_only" 之类需要看函数体的附加校验


RULES: list[Rule] = [
    # ---------------- P0：命中即阻断上线 ----------------
    Rule("A01-shift-negative", "P0", re.compile(r"\.shift\(\s*-\s*\d"),
         "shift(负数) 取的是【未来】的值 —— 典型前视",
         "改成 shift(正数)（正数=向过去取）；确认信号与持仓错开一期（pos = signal.shift(1)）"),
    Rule("A01b-iloc-future", "P0", re.compile(r"\.iloc\[\s*[^\]\n]*\+\s*1\s*[^\]\n]*\]"),
         "iloc[i+1] 读到下一根（未来）数据",
         "若用于前瞻收益标签，只能在【评估侧】使用，绝不可进入建仓决策路径"),
    Rule("A02-return-nan", "P0", re.compile(r"return\s+(?:float\(\s*['\"]nan['\"]\s*\)|np\.nan|math\.nan)"),
         "解析函数返回 nan ⇒ 下游所有阈值比较恒为 False，闸门被【静默绕过】",
         "解析失败一律抛错；入口显式剔除 nan（isnan 守卫）；绝不返回 nan"),
    Rule("A03-home-made-trading-calendar", "P0",
         re.compile(r"^\s*def\s+(?:prev|next)_trading_day\s*\("),
         "自实现交易日历：若只跳周末，【节后首日】会算错前一交易日",
         "改读权威交易日历（tushare trade_cal / trade_cal.json）；同一条近似别复用到后果相反的两处",
         body_check="calendar_weekend_only"),
    Rule("A04-threshold-vs-possible-nan", "P0",
         re.compile(r"(?:ratio|pct|score|chg|gap|qty|amount)\w*\s*(?:>=|<=|<|>)\s*[\d.]+"),
         "阈值比较左侧可能为 nan（同文件存在返回 nan 的解析函数 / 缺数据 / 除零）"
         "⇒ 比较恒 False ⇒ 闸门被【静默绕过】",
         "入口先剔除 nan、断言有限；解析函数 raise 而不是返回 nan"),
    # ---------------- P1：需逐条处置说明 ----------------
    Rule("B01-bare-except-pass", "P1", re.compile(r"except[^:]*:\s*pass\s*$"),
         "静默吞异常 ⇒ 故障被隐藏成「正常但没数据」",
         "至少记日志 + 计数；故障路径必须能被上游观测到（fail-safe 要有告警出口）"),
    Rule("B02-format-g", "P1", re.compile(r"f['\"][^'\"]*:\s*g[}\"]"),
         "f\"{x:g}\" 会静默丢精度（大数/小数被截断成有效位数）",
         "改用固定小数位（:.4f）或显式 int()；序列化一律保留原始精度"),
    Rule("B03-stale-natural-days", "P1",
         re.compile(r"(?:stale|fresh|last_date|lag|since)[^\n]*\.days\s*[<>]"),
         "用【自然日】判断数据陈旧 ⇒ 长假后首个交易日必然误判",
         "改用交易日间隔（数交易日根数），或直接与权威交易日历比对"),
    Rule("B04-nonatomic-write", "P1", re.compile(r"(?<![.\w])open\(\s*[^,)]+,\s*['\"]w['\"]"),
         "直接覆盖写生产文件：中途失败会留下半个文件（台账/持仓/状态被写坏）",
         "先写同目录临时文件再 os.replace() 原子替换；关键文件写前备份（.bak-<date>-<tag>）"),
    Rule("B05-startswith-short-prefix", "P1", re.compile(r"startswith\(\s*\(?\s*['\"][a-z]{2,3}['\"]"),
         "用短前缀（'sh'/'sz' 之类）判断代码前缀/类型 ⇒ 容易误伤非目标标的",
         "用精确集合成员判断，或按代码长度+市场后缀规范化后再比"),
    # ---------------- P2：提示 ----------------
    Rule("C01-hardcoded-cost", "P2",
         re.compile(r"(?:cost|fee|commission|slippage|rate)\w*\s*=\s*0?\.\d+", re.I),
         "硬编码成本/费率：口径未声明，跨市场复用会静默算错",
         "成本写进口径声明（复权/时点/成本/宇宙四要素），并按载体分流（ETF/个股费率不同）"),
    Rule("C02-todo", "P2", re.compile(r"#\s*(?:TODO|FIXME|XXX|HACK)\b"),
         "遗留 TODO/FIXME：上线前需确认是否影响交易路径",
         "逐条确认：影响交易路径的必须在上线前解决或降级为显式告警"),
]

# 跨文件重复实现（B06）单独扫，不用行正则
DUP_IMPL_MIN = 2
# 模板性重名（每个脚本都有自己的 CLI / 自检），不是「两份同义实现」，不算信号
DUP_IGNORE_NAMES = {"main", "selftest", "chk", "run", "fmt", "load_json", "save_json",
                    "atomic_write", "parse_args", "setup", "teardown", "wrap", "log",
                    "scan", "scan_file", "render_md"}


# ---------------------------------------------------------------- 文件收集与指纹
def find_ignore_files(paths: list[str]) -> list[Path]:
    """从每个被审路径向上（最多 4 层）搜 .preflightignore，外加 cwd 一份。"""
    cands: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        base = p.resolve() if p.is_dir() else p.resolve().parent
        for _ in range(4):
            f = base / IGNORE_FILE
            if f.exists():
                cands.append(f)
            if base.parent == base:
                break
            base = base.parent
    cwd_f = Path.cwd() / IGNORE_FILE
    if cwd_f.exists():
        cands.append(cwd_f)
    seen, out = set(), []
    for c in cands:
        r = c.resolve()
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def parse_ignore(files: list[Path]) -> list[str]:
    """把 .preflightignore 里的 glob 展开成【绝对路径模式】。"""
    pats: list[str] = []
    for f in files:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            p = Path(line)
            pats.append(str(p) if p.is_absolute() else str((f.parent / p).resolve()))
    return pats


def _ignored(p: Path, patterns: list[str]) -> bool:
    s = str(p)
    return any(fnmatch.fnmatch(s, pat) for pat in patterns)


def collect_files(paths: list[str], ignore: list[str] | None = None) -> list[Path]:
    seen: dict[Path, None] = {}
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_file():
            seen[p.resolve()] = None
        elif p.is_dir():
            for f in sorted(p.rglob("*.py")):
                if any(part in SKIP_DIRS for part in f.parts):
                    continue
                if ignore and _ignored(f.resolve(), ignore):
                    continue
                seen[f.resolve()] = None
    return sorted(seen.keys())


def code_fingerprint(paths: list[str], ignore: list[str] | None = None) -> tuple[str, list[str]]:
    """被审代码集的 sha256。★ 裁判（qta_loop）会用自己的同一实现重算再比对。

    口径：按【绝对路径】排序，逐个 update(路径 + \\0 + 内容 + \\0)。
    路径变更 ⇒ 指纹变更（这是刻意的：换了目录就等于换了被审对象）。
    ★ 指纹范围必须与审计范围【完全一致】（否则 ignored 文件会造成假不一致）。"""
    files = collect_files(paths, ignore)
    h = hashlib.sha256()
    for f in files:
        h.update(str(f).encode("utf-8"))
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest(), [str(f) for f in files]


# ---------------------------------------------------------------- 抑制与函数体
def _suppressed(lines: list[str], idx: int) -> bool:
    if SUPPRESS.search(lines[idx]):
        return True
    return idx > 0 and bool(SUPPRESS.search(lines[idx - 1]))


def _function_body(lines: list[str], start: int) -> str:
    """从 def 行起，取函数体（直到出现缩进不深于 def 的非空行）。"""
    base = len(lines[start]) - len(lines[start].lstrip())
    out = []
    for ln in lines[start + 1:]:
        if not ln.strip():
            out.append(ln)
            continue
        indent = len(ln) - len(ln.lstrip())
        if indent <= base:
            break
        out.append(ln)
    return "\n".join(out)


def _calendar_weekend_only(body: str) -> bool:
    """只跳周末、且没有任何权威日历读取迹象 ⇒ 判为近似实现。"""
    looks_like_calendar = ("weekday()" in body) or ("timedelta(days=1)" in body
                                                   or "timedelta(1)" in body)
    reads_calendar = any(k in body for k in
                         ("trade_cal", "trading_days", "calendar", "is_open", "is_trading_day"))
    return looks_like_calendar and not reads_calendar


# ---------------------------------------------------------------- 扫描
def scan_file(p: Path) -> list[Finding]:
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    # A04 只在「同文件存在【未被承认的】nan 源」时才成立 ——
    # 否则变量名叫 score 的比较遍地都是，会刷屏误报；
    # 而已经用 # preflight-ok 声明过的 nan 哨兵，不应再连带触发 A04。
    _nan_re = re.compile(r"return\s+(?:float\(\s*['\"]nan['\"]\s*\)|np\.nan|math\.nan)")
    has_nan_source = any(_nan_re.search(ln) and not _suppressed(lines, i)
                         for i, ln in enumerate(lines))
    out: list[Finding] = []
    for i, line in enumerate(lines):
        if _suppressed(lines, i):
            continue
        for r in RULES:
            if r.rid.startswith("A04") and not has_nan_source:
                continue
            if not r.pattern.search(line):
                continue
            if r.body_check == "calendar_weekend_only" and not _calendar_weekend_only(
                    _function_body(lines, i)):
                continue
            out.append(Finding(r.rid, r.severity, str(p), i + 1, line.strip()[:160], r.why, r.fix))
    return out


DEF_RE = re.compile(r"^\s*def\s+([a-zA-Z_]\w*)\s*\(")


def scan_dup_impl(files: list[Path]) -> list[Finding]:
    """跨文件同名函数定义 ⇒ 最常见也最危险的 bug 形态（两份同义实现各自演进）。"""
    where: dict[str, list[tuple[str, int]]] = {}
    for p in files:
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, ln in enumerate(lines):
            m = DEF_RE.match(ln)
            if m and not m.group(1).startswith("_") and m.group(1) not in DUP_IGNORE_NAMES:
                if _suppressed(lines, i):      # 抑制注释同样适用于跨文件重名检查
                    continue
                where.setdefault(m.group(1), []).append((str(p), i + 1))
    out = []
    for fn, locs in sorted(where.items()):
        if len(locs) >= DUP_IMPL_MIN:
            fileset = {f for f, _ in locs}
            if len(fileset) < 2:
                continue
            detail = "；".join(f"{f}:{n}" for f, n in locs[:6])
            for f, n in locs:
                out.append(Finding(
                    "B06-duplicate-implementation", "P1", f, n, f"def {fn}(...)",
                    f"同名函数在 {len(fileset)} 个文件中各自实现 ⇒ 两份同义实现必然各自演进（本项目 P-13 先例）",
                    f"合并为单一实现并让其他处 import；现状：{detail}"))
    return out


def load_external(path: str | None) -> list[dict]:
    if not path:
        return []
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return [{"name": "external", "status": "error", "detail": f"读取失败：{e}"}]
    return d if isinstance(d, list) else [d]


def audit(targets: list[str], mode: str = "shadow", rollback_point: str | None = None,
          external_json: str | None = None, ignore_file: str | None = None) -> dict:
    ig_files = find_ignore_files(targets)
    if ignore_file:
        p = Path(ignore_file).expanduser()
        if p.exists():
            ig_files = [p.resolve()] + ig_files
    ignore = parse_ignore(ig_files)

    files = collect_files(targets, ignore)
    sha, names = code_fingerprint(targets, ignore)
    findings: list[Finding] = []
    for p in files:
        findings.extend(scan_file(p))
    findings.extend(scan_dup_impl(files))
    findings.sort(key=lambda f: ({"P0": 0, "P1": 1, "P2": 2}[f.severity], f.rule, f.file, f.line))

    ext = load_external(external_json)
    for e in ext:
        if e.get("status") in ("fail", "error"):
            findings.append(Finding(
                f"X-{e.get('name', 'external')}", "P0", e.get("path", "<external>"), 0,
                str(e.get("detail", ""))[:160],
                "外部审计工具（如 lookahead_lint）判定不通过",
                "先修外部工具报出的问题；外部结论与静态扫描同等有效"))
    findings.sort(key=lambda f: ({"P0": 0, "P1": 1, "P2": 2}[f.severity], f.rule, f.file, f.line))

    p0 = [f for f in findings if f.severity == "P0"]
    p1 = [f for f in findings if f.severity == "P1"]
    p2 = [f for f in findings if f.severity == "P2"]

    blockers = []
    if p0:
        blockers.append(f"存在 {len(p0)} 条 P0 阻断项 ⇒ 禁止上线/实盘/影子盘")
    if mode in ("live", "prod") and not rollback_point:
        blockers.append("live/prod 模式必须提供 --rollback-point（回滚点），否则出事无法退")

    return {
        "schema": "preflight-report/1.0", "version": VERSION,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "targets": [str(Path(t).expanduser()) for t in targets],
        "files_scanned": len(files), "files": names,
        "code_sha256": sha,
        "ignore_files": [str(x) for x in ig_files],
        "ignored_patterns": ignore,
        "p0_count": len(p0), "p1_count": len(p1), "p2_count": len(p2),
        "findings": [asdict(f) for f in findings],
        "external": ext,
        "rollback_point": rollback_point,
        "rollback_ready": bool(rollback_point),
        "blockers": blockers,
        "passed": not blockers,
    }


# ---------------------------------------------------------------- 报告输出
def render_md(rep: dict) -> str:
    L = [f"# 上线前代码审计报告（preflight v{rep['version']}）", ""]
    L.append(f"- 生成时间：{rep['ts']}　模式：**{rep['mode']}**")
    L.append(f"- 扫描文件：{rep['files_scanned']} 个　代码指纹 `{rep['code_sha256'][:16]}…`")
    L.append(f"- 结论：{'✅ **通过**' if rep['passed'] else '❌ **阻断**'}　"
             f"P0={rep['p0_count']} / P1={rep['p1_count']} / P2={rep['p2_count']}")
    if rep.get("rollback_point"):
        L.append(f"- 回滚点：{rep['rollback_point']}")
    if rep["blockers"]:
        L += ["", "## ⛔ 阻断项", ""]
        L += [f"- {b}" for b in rep["blockers"]]
    if rep["findings"]:
        L += ["", "## 明细", "", "| 级别 | 规则 | 位置 | 证据 | 为什么 | 怎么修 |", "|---|---|---|---|---|---|"]
        for f in rep["findings"]:
            loc = f"{Path(f['file']).name}:{f['line']}" if f["line"] else Path(f["file"]).name
            L.append(f"| **{f['severity']}** | `{f['rule']}` | `{loc}` | `{f['snippet']}` | "
                     f"{f['why']} | {f['fix']} |")
    else:
        L += ["", "无命中：机械可判的已知 bug 形态均未出现。",
              "", "> ⚠️ 这不等于「没有 bug」：语义级问题（口径错配、前视的业务定义、"
              "策略逻辑本身的自欺）仍需人工审查，见 `references/preflight-audit.md`。"]
    L += ["", "> 所有输出均为工程研究内容，**不构成投资建议**。"]
    return "\n".join(L)


def write_report(rep: dict, out_dir: str | None) -> tuple[Path, Path]:
    d = Path(out_dir).expanduser() if out_dir else Path.cwd() / "preflight_out"
    d.mkdir(parents=True, exist_ok=True)
    jp = d / "preflight_report.json"
    mp = d / "preflight_report.md"
    jp.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    mp.write_text(render_md(rep), encoding="utf-8")
    return jp, mp


# ---------------------------------------------------------------- selftest


def selftest() -> int:
    fails: list[str] = []

    def chk(name, cond):
        print(f"  {'✅' if cond else '❌'} {name}")
        if not cond:
            fails.append(name)

    print(f"preflight_audit selftest  v{VERSION}")
    fix = Path(__file__).resolve().parent / "fixtures"
    if not fix.is_dir():
        print(f"  ❌ 缺夹具目录：{fix}")
        return 1
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        # ★ 样本来自 scripts/fixtures/（默认跳过目录），不再内嵌 ——
        #   否则审计器审自己时会把这些「故意埋的 bug」当成真 bug 报出来。
        for name in ("selftest_bad.py", "selftest_good.py", "dup_a.py", "dup_b.py"):
            shutil.copy2(fix / name, d / name)

        rep = audit([str(d)], mode="shadow")
        hits = {f["rule"] for f in rep["findings"]}

        # 1) 每条 P0 规则都被命中（bad 样本里各埋了一个）
        for rid in ("A01-shift-negative", "A01b-iloc-future", "A02-return-nan",
                    "A03-home-made-trading-calendar", "A04-threshold-vs-possible-nan"):
            chk(f"命中 P0 规则 {rid}", rid in hits)
        # 2) 每条 P1 规则都被命中
        for rid in ("B01-bare-except-pass", "B02-format-g", "B03-stale-natural-days",
                    "B04-nonatomic-write", "B06-duplicate-implementation"):
            chk(f"命中 P1 规则 {rid}", rid in hits)
        chk("命中 P2 规则 C01-hardcoded-cost", "C01-hardcoded-cost" in hits)
        chk("命中 P2 规则 C02-todo", "C02-todo" in hits)

        # 3) ★ 误报闸：干净样本必须 0 命中
        clean = [f for f in rep["findings"] if "selftest_good.py" in f["file"]]
        chk(f"干净代码 0 误报（got={len(clean)}）", len(clean) == 0)
        # 4) 跨文件重复实现必须点到两个文件
        dupfiles = {Path(f["file"]).name for f in rep["findings"]
                    if f["rule"] == "B06-duplicate-implementation"}
        chk(f"重复实现跨文件定位（{sorted(dupfiles)}）",
            {"dup_a.py", "dup_b.py"}.issubset(dupfiles))
        # 5) P0 存在 ⇒ 阻断 + 退出语义
        chk(f"P0 存在 ⇒ passed=False 且 blockers 非空（p0={rep['p0_count']}）",
            rep["passed"] is False and bool(rep["blockers"]))
        # 6) live 模式缺回滚点 ⇒ 追加阻断
        rep_live = audit([str(d)], mode="live", rollback_point=None)
        chk("live 模式缺 --rollback-point ⇒ 阻断",
            any("rollback-point" in b for b in rep_live["blockers"]))
        rep_live2 = audit([str(d)], mode="live", rollback_point="backup dir A")
        chk("live 模式有回滚点 ⇒ rollback_ready=True",
            rep_live2["rollback_ready"] is True and
            not any("rollback-point" in b for b in rep_live2["blockers"]))

        # 7) 指纹：确定性 + 内容变即变
        s1, _ = code_fingerprint([str(d)])
        s2, _ = code_fingerprint([str(d)])
        chk("代码指纹可复现", s1 == s2)
        (d / "selftest_good.py").write_text(
            (d / "selftest_good.py").read_text(encoding="utf-8") + "\n# touched\n", encoding="utf-8")
        s3, _ = code_fingerprint([str(d)])
        chk("★ 内容改动 ⇒ 指纹变化（防『审完又改』）", s3 != s1)

        # 8) 抑制注释生效
        suppress = d / "suppressed.py"
        suppress.write_text(
            "def h(df):\n"
            "    x = df['c'].shift(-1)   # preflight-ok: 仅用于评估侧标签，不参与建仓\n"
            "    return x\n", encoding="utf-8")
        rep_s = audit([str(suppress)], mode="shadow")
        chk("抑制注释 preflight-ok 生效", len(rep_s["findings"]) == 0)

        # 9) 干净目录整体通过
        clean_dir = d / "clean_only"
        clean_dir.mkdir()
        shutil.copy2(fix / "selftest_good.py", clean_dir / "a.py")
        rep_c = audit([str(clean_dir)], mode="shadow", rollback_point="tag v1")
        chk(f"干净目录 ⇒ passed（P0={rep_c['p0_count']}）", rep_c["passed"] is True)

        # 10) ★ .preflightignore：被忽略的文件既不扫描、也不进指纹（两者必须一致）
        ig = d / "proj_with_ignore"
        ig.mkdir()
        shutil.copy2(fix / "selftest_bad.py", ig / "legacy_bad.py")
        rep_before = audit([str(ig)], mode="shadow")
        chk(f"未忽略时检出 P0（got={rep_before['p0_count']}）", rep_before["p0_count"] > 0)
        (ig / IGNORE_FILE).write_text(
            "# 已下线的旧模块，不参与生产审计（理由：迁移期临时保留）\nlegacy_bad.py\n",
            encoding="utf-8")
        rep_ig = audit([str(ig)], mode="shadow")
        chk(f".preflightignore 生效：0 命中且 0 文件（files={rep_ig['files_scanned']}）",
            len(rep_ig["findings"]) == 0 and rep_ig["files_scanned"] == 0)
        chk("被忽略后指纹随之变化（审计范围 = 指纹范围）",
            rep_ig["code_sha256"] != rep_before["code_sha256"])

        # 10) 报告可渲染且含关键字段
        md = render_md(rep)
        chk("报告含阻断段与明细表", "阻断项" in md and "| 级别 | 规则 |" in md)

    print("  自检结论：", "✅ 通过" if not fails else f"❌ 未通过 {fails}")
    return 0 if not fails else 1


# ---------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="上线/实盘/影子盘前的代码审计（静态扫描 + 分级闸门）")
    ap.add_argument("--targets", nargs="*", help="被审目录或文件（可多个）")
    ap.add_argument("--mode", choices=["shadow", "live", "prod"], default="shadow")
    ap.add_argument("--rollback-point", help="回滚点（live/prod 必填）：备份目录 / git tag / 版本号")
    ap.add_argument("--external-json", help="外部审计结果（如 lookahead_lint）并入报告")
    ap.add_argument("--out-dir", help="报告输出目录（默认 ./preflight_out）")
    ap.add_argument("--json", action="store_true", help="stdout 打印 JSON")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.targets:
        ap.error("--targets 或 --selftest 必填其一")

    rep = audit(args.targets, args.mode, args.rollback_point, args.external_json)
    jp, mp = write_report(rep, args.out_dir)

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        icon = "✅ 通过" if rep["passed"] else "❌ 阻断"
        print(f"{icon}  mode={rep['mode']}  P0={rep['p0_count']} P1={rep['p1_count']} "
              f"P2={rep['p2_count']}  指纹={rep['code_sha256'][:16]}…")
        for f in rep["findings"][:20]:
            loc = f"{Path(f['file']).name}:{f['line']}" if f["line"] else Path(f["file"]).name
            print(f"  [{f['severity']}] {f['rule']} {loc} — {f['snippet'][:70]}")
        if len(rep["findings"]) > 20:
            print(f"  …… 其余 {len(rep['findings']) - 20} 条见报告")
        for b in rep["blockers"]:
            print(f"  ⛔ {b}")
        print(f"报告：{mp}\n      {jp}")
    return 0 if rep["passed"] else 3


if __name__ == "__main__":
    sys.exit(main())
