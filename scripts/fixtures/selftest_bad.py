"""fixtures/selftest_bad.py —— 故意埋入已知 bug 形态的样本（供 preflight_audit --selftest 用）。

★ 本目录（fixtures/）属默认跳过目录，不会污染对生产代码的审计。
"""
import datetime


def prev_trading_day(d):
    d = d - datetime.timedelta(days=1)
    while d.weekday() >= 5:            # 只跳周末 —— 节后首日必错
        d = d - datetime.timedelta(days=1)
    return d


def parse_score(s):
    if not s:
        return float("nan")            # nan 会静默绕过阈值闸
    return float(s)


def decide(score):
    if score >= 0.74:                  # ★ 吃到上面的 nan ⇒ 比较恒 False ⇒ 闸门静默放行
        return True
    return False


def load_close(df, i):
    fut = df["close"].shift(-1)        # 前视
    nxt = df["close"].iloc[i + 1]      # 前视
    return fut, nxt


def stale_check(today, last_date):
    return (today - last_date).days > 5     # 自然日：长假后必误判


def dump(rows, path):
    with open(path, "w") as f:         # 非原子覆盖写
        f.write("\n".join(rows))


def fmt_lossy(x):
    return f"{x:g}"                    # 丢精度


def g():
    try:
        return 1
    except: pass


COST_RATE = 0.0003
# TODO: 上线前确认交易路径是否受影响
