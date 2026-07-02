"""テニスベア募集自動作成。

ネットあいちの予約確定データを2時間枠に分割し、テニスベアに未掲載の枠だけ
「過去のイベントをコピー」機能で募集作成する。
二重掲載の判定は、テニスベアの実際の掲載状況（コピー元一覧の日時）で行う。
"""
from datetime import datetime, timedelta

import pandas as pd
import yaml

from netaichi.browser.tennisbear import TennisBear
from netaichi.config import IS_HEADLESS, RULES_DIR
from netaichi.services.reserve import collect_reservations


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


def select_events_to_post(
    events: list[dict], existing: set, today: datetime | None = None
) -> list[dict]:
    """未来かつテニスベア未掲載の枠だけ返す（純粋関数）

    existing: テニスベアの既存募集 (開始日, 開始時) の集合
    """
    if today is None:
        today = datetime.today()
    midnight = today.replace(hour=0, minute=0, second=0, microsecond=0)
    result = []
    for ev in events:
        if ev["date"] < midnight:
            continue
        if (ev["date"], ev["start"]) in existing:
            continue
        result.append(ev)
    return result


def run(submit: bool | None = None) -> list[dict]:
    """ネットあいちの予約のうち、テニスベアに未掲載の枠を募集作成する

    Args:
        submit: Noneの場合は bear_rules.yaml の設定に従う。
                Falseは確認モード（作成対象を返すが実際には作成しない）

    Returns:
        作成対象（＝ネットあいちにあってテニスベアにない）枠のリスト
    """
    conf = load_rules()
    if submit is None:
        submit = conf.get("submit", False)

    df = collect_reservations()
    events = reservations_to_events(df, conf)
    if not events:
        return []

    with TennisBear(IS_HEADLESS) as tb:
        if not tb.login():
            raise RuntimeError("テニスベアへのログインに失敗しました")
        existing = tb.list_existing_events()
        new = select_events_to_post(events, existing)

        if submit:
            for ev in new:
                start_dt = ev["date"].replace(hour=ev["start"], minute=0)
                end_dt = ev["date"].replace(hour=ev["end"], minute=0)
                deadline = start_dt - timedelta(days=conf["deadline_days_before"])
                if not tb.create_event_from_template(
                    template_title=conf["template_title"],
                    court_name=ev["bear_court"],
                    start=start_dt,
                    end=end_dt,
                    deadline=deadline,
                    submit=True,
                ):
                    tb.logger.warning(f"作成に失敗しました: {ev}")
    return new
