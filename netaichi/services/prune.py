"""シングルス練習が埋まった枠のレッスン募集を削除（ルールA）。

「シングルス練習」に自分を含め2人以上（＝他に1人以上申込）が集まった枠は、
その時間帯のレッスン募集（【初回割】シングルス実戦）が不要になるため削除する。
練習は4時間1本、レッスンは2時間×2枠のことがあるため時間帯で照合する。
"""
import yaml

from netaichi.browser.tennisbear import TennisBear
from netaichi.config import IS_HEADLESS, RULES_DIR
from netaichi.notify import notify
from netaichi.services.event_times import fill_event_ends

WEEKDAY = ["月", "火", "水", "木", "金", "土", "日"]


def load_rules() -> dict:
    with open(RULES_DIR / "prune_rules.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def same_court(a: str, b: str) -> bool:
    """コート名が同じ施設を指すか（表記ゆれは部分一致で吸収）

    一覧からコート名を取れなかった場合は、別施設の募集を誤削除しないよう不一致にする。
    """
    if not a or not b:
        return False
    return a in b or b in a


def find_filled_practices(events: list[dict], min_participants: int) -> list[dict]:
    """min_participants 以上集まった練習を返す（純粋関数）"""
    return [
        ev
        for ev in events
        if ev["is_practice"] and ev["participants"] >= min_participants
    ]


def find_lessons_to_prune(events: list[dict], min_participants: int) -> list[dict]:
    """練習が min_participants 以上埋まった時間帯に重なるレッスンを返す（純粋関数）

    練習会は4時間1本で募集する一方、レッスンは2時間×2枠に分かれるため、
    開始時刻の一致だけで照合すると後半のレッスンが消し漏れる。
    練習の時間帯に開始が含まれるレッスンをすべて対象にする。
    練習の end は fill_event_ends で補完しておくこと。
    """
    filled = find_filled_practices(events, min_participants)
    return [
        ev
        for ev in events
        if ev["is_lesson"]
        and any(
            ev["date"] == p["date"]
            and same_court(ev["court"], p["court"])
            and p["start"] <= ev["start"] < p["end"]
            for p in filled
        )
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
    default_hours = conf.get("default_event_hours", 2)

    with TennisBear(headless) as tb:
        tb.login()
        events = tb.list_organized_events()
        # 削除判定に練習の終了時刻が要る。開くのは埋まった練習だけ
        fill_event_ends(
            tb, find_filled_practices(events, min_participants), default_hours
        )
        targets = find_lessons_to_prune(events, min_participants)
        if execute:
            for ev in targets:
                tb.delete_event(ev["id"])

    if execute and targets:
        notify(format_message(targets))
    return targets
