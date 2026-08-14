from datetime import datetime, timedelta

from sqlmodel import SQLModel
import pandas as pd


def shift_off_closed_day(date: datetime, closed_weekday: int | None) -> datetime:
    """休館日に当たる日付を前日にずらす（純粋関数）

    窓口でしか取り消せない施設は、休館日に期限が来ると取消に行けないため。
    closed_weekday は 0=月 … 6=日。None なら何もしない。
    """
    if closed_weekday is not None and date.weekday() == closed_weekday:
        return date - timedelta(days=1)
    return date


def court_label(court_number) -> str:
    """通知やログに出すコート名（純粋関数）

    予約一覧の面の識別子は、庭球場なら番号だけ（6）、番号が振られていない
    コートは名前そのもの（フットサル場B）。数字のときだけ「庭球場」を補う。
    """
    text = str(court_number)
    return f"庭球場{text}" if text.isdigit() else text


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
