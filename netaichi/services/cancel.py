"""集客0レッスンのコート取消＋募集削除（ルールB）。

レッスン日の前日（設定）に翌日のレッスンを確認し、参加者0人のものについて
ネットあいちのコート予約を取消し、成功したらテニスベアの募集も削除する。
コート予約を先に取り消し、成功分だけ募集を削除するので不整合が起きない。
"""
from datetime import datetime, timedelta

import yaml

from netaichi.browser import NetAichi
from netaichi.browser.tennisbear import TennisBear
from netaichi.config import IS_HEADLESS, OGURI_ACCOUNT_ID, RULES_DIR
from netaichi.notify import notify

WEEKDAY = ["月", "火", "水", "木", "金", "土", "日"]


def load_rules() -> dict:
    with open(RULES_DIR / "cancel_rules.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_empty_lessons(events: list[dict], target_date: datetime) -> list[dict]:
    """対象日のレッスンで参加者0人のものを返す（純粋関数）"""
    return [
        ev
        for ev in events
        if ev["is_lesson"]
        and ev["participants"] == 0
        and ev["date"].date() == target_date.date()
    ]


def find_solo_practices(events: list[dict], target_date: datetime) -> list[dict]:
    """対象日の練習会で自分のみ（参加者1人）のものを返す（純粋関数）"""
    return [
        ev
        for ev in events
        if ev["is_practice"]
        and ev["participants"] == 1
        and ev["date"].date() == target_date.date()
    ]


def map_court(bear_court: str, court_map: dict) -> str | None:
    """テニスベアのコート名をネットあいちの予約一覧でのコート名に変換する"""
    for key, netaichi_name in court_map.items():
        if key in bear_court:
            return netaichi_name
    return None


def format_message(cancelled: list[dict]) -> str:
    lines = ["🗑️ コート予約を取消しました（テニスベア募集も削除）"]
    for ev in cancelled:
        w = WEEKDAY[ev["date"].weekday()]
        kind = "レッスン(集客0)" if ev["is_lesson"] else "練習会(自分のみ)"
        lines.append(f"・{ev['date']:%m/%d}({w}) {ev['start']}時 {ev['court']}【{kind}】")
    return "\n".join(lines)


def run(
    target_date: datetime | None = None,
    execute: bool = True,
    headless: bool = IS_HEADLESS,
) -> list[dict]:
    """翌日の0人レッスンのコートを取消し、募集を削除する

    Args:
        target_date: 対象レッスン日（Noneなら days_before 先）
        execute: Falseなら検出のみ（取消・削除しない）

    Returns:
        取消・削除したレッスンのリスト
    """
    conf = load_rules()
    if target_date is None:
        target_date = datetime.today() + timedelta(days=conf.get("days_before", 1))

    with TennisBear(headless) as tb:
        tb.login()
        events = tb.list_organized_events()
        targets = find_empty_lessons(events, target_date) + find_solo_practices(events, target_date)
        if not targets:
            return []

        cancelled = []
        with NetAichi(headless) as na:
            na.login(id=OGURI_ACCOUNT_ID)
            for ev in targets:
                keyword = map_court(ev["court"], conf["court_map"])
                if keyword is None:
                    na.logger.warning(f"ネットあいち未対応コートのためスキップ: {ev['court']}")
                    continue
                if not execute:
                    cancelled.append(ev)
                    continue
                if na.cancel_reservation(ev["date"], ev["start"], keyword):
                    cancelled.append(ev)

        # コート取消に成功した分だけテニスベアの募集も削除する
        if execute:
            for ev in cancelled:
                tb.delete_event(ev["id"])

    if execute and cancelled:
        notify(format_message(cancelled))
    return cancelled
