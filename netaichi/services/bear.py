"""テニスベア募集自動作成。

ネットあいちの予約確定データを2時間枠に分割し、
未掲載分をテニスベアの「過去のイベントをコピー」機能で募集作成する。
"""
from datetime import datetime, timedelta

import pandas as pd
import yaml

from netaichi.browser.tennisbear import TennisBear
from netaichi.config import IS_HEADLESS, RULES_DIR
from netaichi.db import NetaichiDatabase, T_BearPost, select
from netaichi.services.reserve import collect_reservations

db = NetaichiDatabase(False)


def load_rules() -> dict:
    with open(RULES_DIR / "bear_rules.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def split_slots(start: int, end: int, hours: int) -> list[tuple[int, int]]:
    """予約時間帯をイベント枠に分割する（例: 13-17時, 2時間 → [(13,15), (15,17)]）"""
    slots = []
    s = start
    while s + hours <= end:
        slots.append((s, s + hours))
        s += hours
    return slots


def match_court(court: str, courts: dict) -> str | None:
    """予約のコート名から設定のキーを部分一致で探す"""
    for key in courts:
        if key in court:
            return key
    return None


def reservations_to_events(df: pd.DataFrame, conf: dict) -> list[dict]:
    """予約データをテニスベアのイベント枠に変換する（純粋関数）"""
    if df.empty:
        return []
    events = []
    for row in df.itertuples():
        key = match_court(row.court, conf["courts"])
        if key is None:
            continue
        for start, end in split_slots(int(row.start), int(row.end), conf["event_hours"]):
            events.append(
                {
                    "court": row.court,
                    "bear_court": conf["courts"][key],
                    "date": pd.Timestamp(row.date).to_pydatetime(),
                    "start": start,
                    "end": end,
                }
            )
    return events


def filter_new(events: list[dict]) -> list[dict]:
    """未掲載かつ未来のイベント枠だけ返す"""
    db.create_tables()
    today = datetime.today()
    new = []
    with db.session() as session:
        for ev in events:
            if ev["date"] < today.replace(hour=0, minute=0, second=0, microsecond=0):
                continue
            exists = session.exec(
                select(T_BearPost).where(
                    T_BearPost.court == ev["court"],
                    T_BearPost.date == ev["date"],
                    T_BearPost.start == ev["start"],
                )
            ).first()
            if exists is None:
                new.append(ev)
    return new


def record_post(ev: dict):
    with db.session() as session:
        session.add(
            T_BearPost(
                court=ev["court"], date=ev["date"], start=ev["start"], end=ev["end"]
            )
        )
        session.commit()


def run(submit: bool | None = None) -> list[dict]:
    """予約確定データから未掲載分の募集をテニスベアに作成する

    Args:
        submit: Noneの場合は bear_rules.yaml の設定に従う。
                Falseは確認モード（確定ボタンを押さない）
    """
    conf = load_rules()
    if submit is None:
        submit = conf.get("submit", False)

    df = collect_reservations()
    events = reservations_to_events(df, conf)
    new = filter_new(events)
    if not new:
        return []

    posted = []
    with TennisBear(IS_HEADLESS) as tb:
        if not tb.login():
            raise RuntimeError("テニスベアへのログインに失敗しました")
        for ev in new:
            start_dt = ev["date"].replace(hour=ev["start"], minute=0)
            end_dt = ev["date"].replace(hour=ev["end"], minute=0)
            deadline = start_dt - timedelta(hours=conf["deadline_hours_before"])
            ok = tb.create_event_from_template(
                template_title=conf["template_title"],
                court_name=ev["bear_court"],
                start=start_dt,
                end=end_dt,
                deadline=deadline,
                submit=submit,
            )
            if ok and submit:
                record_post(ev)
                posted.append(ev)
    return posted
