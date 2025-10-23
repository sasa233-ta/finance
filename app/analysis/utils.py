import pandas as pd

def get_latest(df, date_col):
    """
    指定した日付カラムで最新行を返す
    """
    if date_col in df.columns:
        df = df.sort_values(date_col)
        return df.iloc[-1]
    return None
