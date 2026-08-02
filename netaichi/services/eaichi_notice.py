"""窓口でしか取り消せない施設の、取消期限前通知（ルールC）。

日進市（えあいち）の上納池スポーツ公園はネットからキャンセルできず、
取消期限までに窓口へ行く必要がある。集客0のまま通知日になったら知らせる。
通知日が施設の休館日（月曜）に当たる場合は前日に前倒しする。

コート取消も募集削除も自動ではできないため、この処理は通知だけを行う。
"""
from datetime import datetime, timedelta

import yaml

from netaichi.browser.tennisbear import TennisBear
from netaichi.config import IS_HEADLESS, RULES_DIR
from netaichi.helper import shift_off_closed_day
from netaichi.notify import notify

WEEKDAY = ["月", "火", "水", "木", "金", "土", "日"]


def load_rules() -> dict:
    with open(RULES_DIR / "eaichi_notice_rules.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def match_court(court: str, courts: dict) -> str | None:
    """コート名から設定のキーを部分一致で探す（純粋関数）"""
    for key in courts:
        if key in court:
            return key
    return None


def is_unwanted(event: dict) -> bool:
    """開催しない枠か（集客0のレッスン、自分だけの練習会）（純粋関数）"""
    return (event["is_lesson"] and event["participants"] == 0) or (
        event["is_practice"] and event["participants"] == 1
    )


def notice_date(
    lesson_date: datetime, days_before: int, closed_weekday: int | None = None
) -> datetime:
    """窓口へ行く日を返す（純粋関数）

    休館日に当たる場合は前日に前倒しする。
    """
    return shift_off_closed_day(
        lesson_date - timedelta(days=days_before), closed_weekday
    )


def find_notice_targets(
    events: list[dict], conf: dict, today: datetime
) -> list[dict]:
    """今日が窓口へ行く日にあたる、開催しない枠を返す（純粋関数）"""
    targets = []
    for ev in events:
        key = match_court(ev["court"], conf["courts"])
        if key is None or not is_unwanted(ev):
            continue
        rule = conf["courts"][key]
        visit_date = notice_date(
            ev["date"], rule["days_before"], rule.get("closed_weekday")
        )
        if visit_date.date() != today.date():
            continue
        limit = ev["date"] - timedelta(days=rule["limit_days_before"])
        targets.append({**ev, "limit": limit})
    return targets


def format_message(targets: list[dict]) -> str:
    lines = ["🏢 窓口でコートを取り消してください（ネット取消不可・本日中に）"]
    for ev in targets:
        w = WEEKDAY[ev["date"].weekday()]
        limit_w = WEEKDAY[ev["limit"].weekday()]
        kind = "レッスン(0人)" if ev["is_lesson"] else "練習会(自分のみ)"
        lines.append(
            f"・{ev['date']:%m/%d}({w}) {ev['start']}時 {ev['court']}【{kind}】"
            f" 取消期限 {ev['limit']:%m/%d}({limit_w})"
        )
    lines.append("※ 取り消したらテニスベアの募集も手動で削除してください")
    return "\n".join(lines)


def run(
    today: datetime | None = None,
    execute: bool = True,
    headless: bool = IS_HEADLESS,
) -> list[dict]:
    """窓口取消が必要な枠を検出し、通知する

    Args:
        today: 判定の基準日（省略時は今日）
        execute: Falseなら検出のみ（通知しない）

    Returns:
        通知対象のイベントのリスト
    """
    conf = load_rules()
    if not conf.get("courts"):
        return []
    base = today or datetime.today()
    base = base.replace(hour=0, minute=0, second=0, microsecond=0)

    with TennisBear(headless) as tb:
        tb.login()
        events = tb.list_organized_events()

    targets = find_notice_targets(events, conf, base)
    if execute and targets:
        notify(format_message(targets))
    return targets
