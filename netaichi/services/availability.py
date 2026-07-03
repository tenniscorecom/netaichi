"""空き状況チェック。

rules/availability_rules.yaml の条件で空き枠を検索し、
未通知の空きが見つかったら Discord に通知する。
"""
from datetime import datetime, timedelta

import yaml
from dateutil.relativedelta import relativedelta

from netaichi.browser import NetAichi
from netaichi.config import IS_HEADLESS, OGURI_GSS_ID, RULES_DIR
from netaichi.helper import SpreadSheet
from netaichi.notify import notify
from netaichi.services.lottery import GROUP_IDS, rule_applies

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


def merge_hour_slots(slots: list[dict]) -> list[dict]:
    """施設ごとの1時間刻みの空きを連続した時間帯にまとめ、
    施設違いの同一時間帯は1件に重複排除する（純粋関数）"""
    by_facility: dict = {}
    for s in sorted(slots, key=lambda x: (x["value"], str(x["date"]), x.get("facility", ""), x["start"])):
        key = (s["value"], s["date"], s.get("facility", ""))
        ranges = by_facility.setdefault(key, [])
        if ranges and ranges[-1]["end"] == s["start"]:
            ranges[-1]["end"] = s["end"]
        else:
            ranges.append(
                {"value": s["value"], "date": s["date"], "start": s["start"], "end": s["end"]}
            )

    merged = []
    seen = set()
    for ranges in by_facility.values():
        for r in ranges:
            key = (r["value"], r["date"], r["start"], r["end"])
            if key in seen:
                continue
            seen.add(key)
            merged.append(r)
    return merged


def in_time_ranges(slot: dict, ranges: list) -> bool:
    return any(slot["start"] < end and slot["end"] > start for start, end in ranges)


def diff_slots(
    current: list[dict], previous: list[dict]
) -> tuple[list[dict], list[dict]]:
    """現在の空きと前回の空きを比較し、(新規, 消滅) を返す（純粋関数）"""
    def key(s):
        return (s["value"], s["date"].strftime("%Y-%m-%d"), s["start"])

    current_keys = {key(s) for s in current}
    previous_keys = {key(s) for s in previous}
    new = [s for s in current if key(s) not in previous_keys]
    gone = [s for s in previous if key(s) not in current_keys]
    return new, gone


def format_message(slots: list[dict]) -> str:
    lines = ["🎾 コートの空きが見つかりました"]
    for s in sorted(slots, key=lambda x: (x["date"], x["start"])):
        date = s["date"]
        week = WEEKDAY_LABELS[date.weekday()]
        lines.append(f"・{date:%m/%d}({week}) {s['start']}-{s['end']}時 {s['value']}")
    return "\n".join(lines)


def format_gone_message(slots: list[dict]) -> str:
    lines = ["❌ コートが埋まりました"]
    for s in sorted(slots, key=lambda x: (x["date"], x["start"])):
        date = s["date"]
        week = WEEKDAY_LABELS[date.weekday()]
        lines.append(f"・{date:%m/%d}({week}) {s['start']}-{s['end']}時 {s['value']}")
    return "\n".join(lines)


def check(
    notify_enabled: bool = True, headless: bool = IS_HEADLESS
) -> tuple[list[dict], list[dict]]:
    conf = load_rules()
    dates = target_dates(conf)
    slots = []
    with NetAichi(headless) as na:
        na.login(id=GROUP_IDS[conf["account"]])
        for park in conf["parks"]:
            slots += na.find_available_slots(
                park["keyword"], dates, park.get("court_filter")
            )

    current = merge_hour_slots(slots)
    current = [s for s in current if in_time_ranges(s, conf["times"])]

    ss = SpreadSheet(OGURI_GSS_ID)
    previous = ss.get_current_slots()
    new, gone = diff_slots(current, previous)

    if notify_enabled:
        if new:
            notify(format_message(new))
        if gone:
            notify(format_gone_message(gone))

    ss.set_current_slots(current)
    return new, gone
