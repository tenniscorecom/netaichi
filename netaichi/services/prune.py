"""シングルス練習が埋まった枠のレッスン募集を削除（ルールA）。

「シングルス練習」に自分を含め2人以上（＝他に1人以上申込）が集まった枠は、
同じ日時のレッスン募集（【初回割】シングルス実戦）が不要になるため削除する。
"""
import yaml

from netaichi.browser.tennisbear import TennisBear
from netaichi.config import IS_HEADLESS, RULES_DIR
from netaichi.notify import notify

WEEKDAY = ["月", "火", "水", "木", "金", "土", "日"]


def load_rules() -> dict:
    with open(RULES_DIR / "prune_rules.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_lessons_to_prune(events: list[dict], min_participants: int) -> list[dict]:
    """練習が min_participants 以上埋まった枠の、同日時レッスンを返す（純粋関数）

    照合は (日付, 開始時) 単位。
    """
    filled_slots = {
        (ev["date"], ev["start"])
        for ev in events
        if ev["is_practice"] and ev["participants"] >= min_participants
    }
    return [
        ev
        for ev in events
        if ev["is_lesson"] and (ev["date"], ev["start"]) in filled_slots
    ]


def format_message(pruned: list[dict]) -> str:
    lines = ["🗑️ 練習が埋まった枠のレッスン募集を削除しました"]
    for ev in pruned:
        w = WEEKDAY[ev["date"].weekday()]
        lines.append(f"・{ev['date']:%m/%d}({w}) {ev['start']}時 {ev['court']}")
    return "\n".join(lines)


def run(execute: bool = True, headless: bool = IS_HEADLESS) -> list[dict]:
    """練習が埋まった枠のレッスン募集を削除する

    Args:
        execute: Falseなら検出のみ（削除しない）

    Returns:
        削除対象のレッスンのリスト
    """
    conf = load_rules()
    min_participants = conf.get("min_participants", 2)

    with TennisBear(headless) as tb:
        tb.login()
        events = tb.list_organized_events()
        targets = find_lessons_to_prune(events, min_participants)
        if execute:
            for ev in targets:
                tb.delete_event(ev["id"])

    if execute and targets:
        notify(format_message(targets))
    return targets
