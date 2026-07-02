"""空き状況チェック。

rules/availability_rules.yaml の条件で空き枠を検索し、
未通知の空きが見つかったら Discord に通知する。
"""
from datetime import datetime, timedelta

import yaml
from dateutil.relativedelta import relativedelta

from netaichi.browser import NetAichi
from netaichi.browser.pages.data import COURT_NAMES
from netaichi.config import IS_HEADLESS, RULES_DIR
from netaichi.db import NetaichiDatabase, T_AvailableSlot, select
from netaichi.notify import notify
from netaichi.services.lottery import GROUP_IDS, rule_applies

db = NetaichiDatabase(False)

WEEKDAY_LABELS = ["月", "火", "水", "木", "金", "土", "日"]


def load_rules() -> dict:
    with open(RULES_DIR / "availability_rules.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def target_dates(conf: dict, today: datetime | None = None) -> list[datetime]:
    """明日から months_ahead ヶ月先までの、条件に合う日付を返す"""
    if today is None:
        today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    end = today + relativedelta(months=conf.get("months_ahead", 2))
    dates = []
    d = today + timedelta(days=1)
    while d <= end:
        if rule_applies({"days": conf["days"]}, d):
            dates.append(d)
        d += timedelta(days=1)
    return dates


def in_time_ranges(slot: dict, ranges: list) -> bool:
    return any(slot["start"] < end and slot["end"] > start for start, end in ranges)


def filter_new(slots: list[dict]) -> list[dict]:
    """発見済みテーブルに無い空きだけ返し、テーブルに登録する"""
    db.create_tables()
    new = []
    with db.session() as session:
        for slot in slots:
            exists = session.exec(
                select(T_AvailableSlot).where(
                    T_AvailableSlot.value == slot["value"],
                    T_AvailableSlot.date == slot["date"],
                    T_AvailableSlot.start == slot["start"],
                )
            ).first()
            if exists is None:
                session.add(T_AvailableSlot(**slot))
                new.append(slot)
        session.commit()
    return new


def format_message(slots: list[dict]) -> str:
    lines = ["🎾 コートの空きが見つかりました"]
    for s in sorted(slots, key=lambda x: (x["date"], x["start"])):
        date = s["date"]
        week = WEEKDAY_LABELS[date.weekday()]
        court = COURT_NAMES.get(s["value"], s["value"])
        lines.append(f"・{date:%m/%d}({week}) {s['start']}-{s['end']}時 {court}")
    return "\n".join(lines)


def check(notify_enabled: bool = True) -> list[dict]:
    conf = load_rules()
    dates = target_dates(conf)
    with NetAichi(IS_HEADLESS) as na:
        na.login(id=GROUP_IDS[conf["account"]])
        slots = na.find_available_slots(conf["courts"], dates)

    slots = [s for s in slots if in_time_ranges(s, conf["times"])]
    new = filter_new(slots)
    if new and notify_enabled:
        notify(format_message(new))
    return new
