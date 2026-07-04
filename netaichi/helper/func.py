from sqlmodel import SQLModel
import pandas as pd
def sqlmodel_to_df(objs: list[SQLModel]) -> pd.DataFrame:
    """Convert a SQLModel objects into a pandas DataFrame."""
    records = [i.model_dump() for i in objs]
    df = pd.DataFrame.from_records(records)
    return df


def filter_applied(df, applied: list[dict]):
    """申込済みの (コート, 日付, 開始時) と重複する行を除外する（純粋関数）"""
    if df.empty or not applied:
        return df
    applied_keys = {
        (str(a["value"]), a["date"].strftime("%Y-%m-%d"), int(a["start"]))
        for a in applied
    }
    mask = df.apply(
        lambda r: (str(r["value"]), r["date"].strftime("%Y-%m-%d"), int(r["start"]))
        not in applied_keys,
        axis=1,
    )
    return df[mask]
