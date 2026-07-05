"""テニスベア募集自動作成。

ネットあいち・eあいちの予約確定データを2時間枠に分割し、テニスベアに
未掲載の枠だけ「過去のイベントをコピー」機能で募集作成する。
二重掲載の判定は、主催・参加イベント一覧の日時＋コートで行う。
"""
from datetime import datetime, timedelta

import pandas as pd
import yaml

from netaichi.browser.tennisbear import TennisBear
from netaichi.config import IS_HEADLESS, RULES_DIR
from netaichi.services.reserve import collect_eaichi_reservations, collect_reservations


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


def deadline_days_for(court_key: str, conf: dict) -> int:
    """コートごとの締切日数を返す（deadline_overrides 優先、なければ既定値）"""
    overrides = conf.get("deadline_overrides", {})
    return overrides.get(court_key, conf.get("deadline_days_before", 2))


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
                    "deadline_days_before": deadline_days_for(key, conf),
                }
            )
    return events


def select_events_to_post(
    events: list[dict], existing: list[dict], today: datetime | None = None
) -> list[dict]:
    """未来かつテニスベア未掲載の枠だけ返す（純粋関数）

    existing: テニスベアの既存募集（date, start, court を持つdict）。
    同じ日時でもコートが違えば掲載対象とする。既存募集のコート名が
    取れていない場合は、二重掲載を避けるため同一コート扱いにする。
    """
    if today is None:
        today = datetime.today()
    midnight = today.replace(hour=0, minute=0, second=0, microsecond=0)

    def same_court(existing_court: str, bear_court: str) -> bool:
        if not existing_court:
            return True
        return existing_court in bear_court or bear_court in existing_court

    result = []
    for ev in events:
        if ev["date"] < midnight:
            continue
        if any(
            e["date"] == ev["date"]
            and e["start"] == ev["start"]
            and same_court(e["court"], ev["bear_court"])
            for e in existing
        ):
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

    df = pd.concat([collect_reservations(), collect_eaichi_reservations()])
    events = reservations_to_events(df, conf)
    if not events:
        return []

    with TennisBear(IS_HEADLESS) as tb:
        if not tb.login():
            raise RuntimeError("テニスベアへのログインに失敗しました")
        # 主催・参加イベント一覧はコート名も取れるため、日時＋コートで二重掲載を判定できる
        existing = tb.list_organized_events()
        new = select_events_to_post(events, existing)

        if submit:
            for ev in new:
                start_dt = ev["date"].replace(hour=ev["start"], minute=0)
                end_dt = ev["date"].replace(hour=ev["end"], minute=0)
                deadline = start_dt - timedelta(days=ev["deadline_days_before"])
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


def compute_deadline(
    date: datetime, start: int, participants: int, days_before: int,
    today: datetime | None = None,
) -> datetime:
    """既存イベントのあるべき申込期限を求める（純粋関数）

    - 参加者がいるイベントは締切を当日にして募集を継続する
    - 参加者0なら開催の days_before 日前
    - 0人でも締切が過去日になる場合は当日にする（過去は設定できないため）
    """
    if today is None:
        today = datetime.today()
    if participants > 0:
        deadline_date = date
    else:
        deadline_date = date - timedelta(days=days_before)
        if deadline_date.date() < today.date():
            deadline_date = date
    return deadline_date.replace(hour=start, minute=0, second=0, microsecond=0)


def sync_deadlines(submit: bool = False) -> list[dict]:
    """締切上書き対象コート（deadline_overrides）の既存イベントの締切を揃える

    Returns:
        対象イベントと目標締切のリスト（dict: id, court, date, start,
        participants, deadline）
    """
    conf = load_rules()
    overrides = conf.get("deadline_overrides", {})
    if not overrides:
        return []
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

    with TennisBear(IS_HEADLESS) as tb:
        if not tb.login():
            raise RuntimeError("テニスベアへのログインに失敗しました")
        events = tb.list_organized_events()
        targets = []
        for ev in events:
            key = match_court(ev["court"], overrides)
            if key is None:
                continue
            deadline = compute_deadline(
                ev["date"], ev["start"], ev["participants"], overrides[key], today
            )
            targets.append({**ev, "deadline": deadline})

        if submit:
            for t in targets:
                if not tb.update_deadline(t["id"], t["deadline"], submit=True):
                    tb.logger.warning(f"締切変更に失敗しました: {t['id']}")
    return targets
