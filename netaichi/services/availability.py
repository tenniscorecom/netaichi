"""空き状況チェック。

rules/availability_rules.yaml の条件で空き枠を検索し、
現在の空き枠をまとめて Discord に通知する。
"""
from datetime import datetime, timedelta

import yaml
from dateutil.relativedelta import relativedelta

from netaichi.browser import EAichi, NagoyaSporec, NetAichi
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
        # 連続・重複する時間帯はまとめる（コート名なし運用では同時間帯が重複しうる）
        if ranges and s["start"] <= ranges[-1]["end"]:
            ranges[-1]["end"] = max(ranges[-1]["end"], s["end"])
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


SITE_LABELS = {"netaichi": "県営", "eaichi": "日進", "nagoya": "名古屋"}


def format_message(
    slots: list[dict], fetch_time: datetime | None = None, label: str = ""
) -> str:
    ft = fetch_time or datetime.now()
    jst_str = ft.strftime("%m/%d %H:%M")
    lines = [f"🎾 現在の空き{label}（{jst_str}時点）[{len(slots)}件]"]
    for s in sorted(slots, key=lambda x: (x["value"], x["date"], x["start"], x.get("facility", ""))):
        date = s["date"]
        week = WEEKDAY_LABELS[date.weekday()]
        facility = s.get("facility", "")
        court_str = f" {facility}" if facility else ""
        lines.append(f"・{s['value']} {date:%m/%d}({week}) {s['start']}-{s['end']}時{court_str}")
    return "\n".join(lines)


def _rule_dates(rule: dict, today: datetime, end_date: datetime) -> list[datetime]:
    dates = []
    d = today + timedelta(days=1)
    while d <= end_date:
        if rule_applies({"days": rule["days"]}, d):
            dates.append(d)
        d += timedelta(days=1)
    return dates


def _collect_rule_slots(browser, rule: dict, dates: list[datetime]) -> list[dict]:
    slots = []
    for park in rule["parks"]:
        park_slots = browser.find_available_slots(
            park["keyword"], dates, park.get("court_filter")
        )
        park_slots = [s for s in park_slots if in_time_ranges(s, rule["times"])]
        if not park.get("show_court", True):
            for s in park_slots:
                s["facility"] = ""
        browser.logger.info(
            f"[{rule.get('name', '')}] {park['keyword']}: {len(park_slots)}件"
        )
        slots += park_slots
    return slots


def check(
    notify_enabled: bool = True,
    headless: bool = IS_HEADLESS,
    sites: list[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """空き状況をチェックして通知する。

    Args:
        sites: チェックするサイトのリスト（例: ["netaichi"]）。
               Noneなら全サイト。ワークフローを分割して並列実行するために使う。
               サイトごとに状態保存シートを分けているので並列実行しても競合しない。
    """
    conf = load_rules()
    months_ahead = conf.get("months_ahead", 2)
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = today + relativedelta(months=months_ahead)

    rules = conf["rules"]
    if sites is not None:
        rules = [r for r in rules if r.get("site", "netaichi") in sites]

    fetch_time = datetime.now()
    netaichi_rules = [r for r in rules if r.get("site", "netaichi") == "netaichi"]
    eaichi_rules = [r for r in rules if r.get("site") == "eaichi"]
    nagoya_rules = [r for r in rules if r.get("site") == "nagoya"]

    slots = []
    if netaichi_rules:
        with NetAichi(headless) as na:
            na.login(id=GROUP_IDS[conf["account"]])
            for rule in netaichi_rules:
                slots += _collect_rule_slots(na, rule, _rule_dates(rule, today, end_date))

    if eaichi_rules:
        # e-aichi（市町村施設）は空き確認だけならログイン不要
        with EAichi(eaichi_rules[0]["municipality"], headless) as ea:
            for rule in eaichi_rules:
                ea.municipality = rule["municipality"]
                slots += _collect_rule_slots(ea, rule, _rule_dates(rule, today, end_date))

    if nagoya_rules:
        # 名古屋市スポレクもログイン不要。施設はコード指定で照会する
        with NagoyaSporec(headless) as ns:
            for rule in nagoya_rules:
                dates = _rule_dates(rule, today, end_date)
                for park in rule["parks"]:
                    park_slots = ns.find_available_slots(
                        park["code"], park["keyword"], dates
                    )
                    park_slots = [s for s in park_slots if in_time_ranges(s, rule["times"])]
                    ns.logger.info(
                        f"[{rule.get('name', '')}] {park['keyword']}: {len(park_slots)}件"
                    )
                    slots += park_slots

    current = merge_hour_slots(slots)

    sheet_name = "通知済み空き" + (f"({'+'.join(sorted(sites))})" if sites else "")
    label = (
        "【" + "・".join(SITE_LABELS.get(s, s) for s in sorted(sites)) + "】"
        if sites else ""
    )
    ss = SpreadSheet(OGURI_GSS_ID)
    previous = ss.get_current_slots(sheet_name)
    _, gone = diff_slots(current, previous)

    if notify_enabled:
        if current:
            notify(format_message(current, fetch_time, label))
        elif gone:
            notify(f"❌ 現在空きなし{label}")

    ss.set_current_slots(current, sheet_name)
    return current, gone
