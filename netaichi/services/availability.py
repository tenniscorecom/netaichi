"""空き状況チェック。

rules/availability_rules.yaml の条件で空き枠を検索し、
現在の空き枠をまとめて Discord に通知する。
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
    """コートごとの1時間刻みの空きを連続した時間帯にまとめる（純粋関数）"""
    groups: dict = {}
    for s in sorted(slots, key=lambda x: (x["value"], str(x["date"]), x.get("facility", ""), x["start"])):
        key = (s["value"], s["date"], s.get("facility", ""))
        groups.setdefault(key, [])
        ranges = groups[key]
        if ranges and ranges[-1]["end"] == s["start"]:
            ranges[-1]["end"] = s["end"]
        else:
            ranges.append({
                "value": s["value"],
                "date": s["date"],
                "facility": s.get("facility", ""),
                "start": s["start"],
                "end": s["end"],
            })
    return [slot for group in groups.values() for slot in group]


def in_time_ranges(slot: dict, ranges: list) -> bool:
    return any(slot["start"] < end and slot["end"] > start for start, end in ranges)


def diff_slots(
    current: list[dict], previous: list[dict]
) -> tuple[list[dict], list[dict]]:
    """現在の空きと前回の空きを比較し、(新規, 消滅) を返す（純粋関数）"""
    def key(s):
        return (s["value"], s["date"].strftime("%Y-%m-%d"), s.get("facility", ""), s["start"])

    current_keys = {key(s) for s in current}
    previous_keys = {key(s) for s in previous}
    new = [s for s in current if key(s) not in previous_keys]
    gone = [s for s in previous if key(s) not in current_keys]
    return new, gone


def format_message(slots: list[dict], fetch_time: datetime | None = None) -> str:
    ft = fetch_time or datetime.now()
    jst_str = ft.strftime("%m/%d %H:%M")
    lines = [f"🎾 現在の空き（{jst_str}時点）[{len(slots)}件]"]
    for s in sorted(slots, key=lambda x: (x["value"], x["date"], x["start"], x.get("facility", ""))):
        date = s["date"]
        week = WEEKDAY_LABELS[date.weekday()]
        facility = s.get("facility", "")
        court_str = f" {facility}" if facility else ""
        lines.append(f"・{s['value']} {date:%m/%d}({week}) {s['start']}-{s['end']}時{court_str}")
    return "\n".join(lines)


def check(
    notify_enabled: bool = True, headless: bool = IS_HEADLESS
) -> tuple[list[dict], list[dict]]:
    conf = load_rules()
    months_ahead = conf.get("months_ahead", 2)
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = today + relativedelta(months=months_ahead)

    fetch_time = datetime.now()
    slots = []
    with NetAichi(headless) as na:
        na.login(id=GROUP_IDS[conf["account"]])
        for rule in conf["rules"]:
            dates = []
            d = today + timedelta(days=1)
            while d <= end_date:
                if rule_applies({"days": rule["days"]}, d):
                    dates.append(d)
                d += timedelta(days=1)
            for park in rule["parks"]:
                park_slots = na.find_available_slots(
                    park["keyword"], dates, park.get("court_filter")
                )
                park_slots = [s for s in park_slots if in_time_ranges(s, rule["times"])]
                na.logger.info(
                    f"[{rule.get('name', '')}] {park['keyword']}: {len(park_slots)}件"
                )
                slots += park_slots

    current = merge_hour_slots(slots)

    ss = SpreadSheet(OGURI_GSS_ID)
    previous = ss.get_current_slots()
    _, gone = diff_slots(current, previous)

    if notify_enabled:
        if current:
            notify(format_message(current, fetch_time))
        elif gone:
            notify("❌ 現在空きなし")

    ss.set_current_slots(current)
    return current, gone
