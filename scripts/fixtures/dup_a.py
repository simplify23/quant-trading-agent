"""fixtures/dup_a.py —— 与 dup_b.py 同名函数，用于验证「跨文件重复实现」检出。"""


def shared_rule(x):
    return x
