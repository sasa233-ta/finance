import os

def normalize_code(code):
    """
    銘柄コード末尾の.Tを除去
    """
    if isinstance(code, str) and code.endswith('.T'):
        return code[:-2]
    return code
