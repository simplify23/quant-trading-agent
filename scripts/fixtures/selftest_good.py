"""fixtures/selftest_good.py —— 干净样本：审计器对它必须 0 命中（误报闸）。"""
import json
import os
import tempfile


def load_trade_cal(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def prev_trade_day(d, cal):
    prev = [x for x in cal if x < d.isoformat()]
    return prev[-1]


def parse_score_strict(s):
    if s is None or s == "":
        raise ValueError("score 缺失")
    v = float(s)
    if v != v:
        raise ValueError("score 非有限值")
    return v


def atomic_write(path, text):
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def fmt(x):
    return f"{x:.4f}"
