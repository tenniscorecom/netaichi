"""集客0レッスンのコート取消＋募集削除（ルールB）。

レッスン日の前日（設定）に翌日のレッスンを確認し、参加者0人のものについて
ネットあいちのコート予約を取消し、成功したらテニスベアの募集も削除する。
コート予約を先に取り消し、成功分だけ募集を削除するので不整合が起きない。
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd
import yaml

from netaichi.browser import NetAichi
from netaichi.browser.tennisbear import TennisBear
from netaichi.config import IS_HEADLESS, OGURI_ACCOUNT_ID, RULES_DIR
from netaichi.notify import notify
from netaichi.services.event_times import fill_event_ends

WEEKDAY = ["月", "火", "水", "木", "金", "土", "日"]


@dataclass(frozen=True)
class ReservationSlot:
    date: datetime
    start: int
    end: int
    court_name: str
    court_number: str
    court_keyword: str


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


def find_reservation(
    event: dict,
    court_keyword: str,
    reservations: pd.DataFrame,
) -> ReservationSlot | None:
    """テニスベアの2時間枠を内包するネットあいち予約を返す"""
    for row in reservations.itertuples():
        reservation_date = pd.Timestamp(row.date).to_pydatetime().replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        reservation_start = int(row.start)
        reservation_end = int(row.end)
        if (
            reservation_date.date() == event["date"].date()
            and reservation_start <= event["start"] < reservation_end
            and court_keyword in str(row.court)
        ):
            return ReservationSlot(
                date=reservation_date,
                start=reservation_start,
                end=reservation_end,
                court_name=str(row.court),
                court_number=str(row.court_number),
                court_keyword=court_keyword,
            )
    return None


def event_matches_reservation(
    event: dict,
    reservation: ReservationSlot,
    court_map: dict,
) -> bool:
    """テニスベア募集が指定のネットあいち予約時間内に属するか判定する"""
    return (
        event["date"].date() == reservation.date.date()
        and reservation.start <= event["start"] < reservation.end
        and map_court(event["court"], court_map) == reservation.court_keyword
    )


def merge_event_ranges(
    events: list[dict],
    event_hours: int,
    reservation_end: int,
) -> list[tuple[int, int]]:
    """連続するテニスベア募集を取り直す時間帯にまとめる

    練習会は4時間1本で募集することがあるため、end が補完済みならそれを使う。
    end が無いイベントはレッスン1枠分（event_hours）とみなす。
    """
    ranges: list[tuple[int, int]] = []
    for event in sorted(events, key=lambda item: item["start"]):
        start = event["start"]
        end = min(event.get("end") or start + event_hours, reservation_end)
        if ranges and start <= ranges[-1][1]:
            previous_start, previous_end = ranges[-1]
            ranges[-1] = (previous_start, max(previous_end, end))
        else:
            ranges.append((start, end))
    return ranges


def format_message(cancelled: list[dict]) -> str:
    lines = ["🗑️ 不要枠をキャンセルしました（テニスベア募集削除・コート予約調整）"]
    for ev in cancelled:
        w = WEEKDAY[ev["date"].weekday()]
        kind = "レッスン(集客0)" if ev["is_lesson"] else "練習会(自分のみ)"
        lines.append(f"・{ev['date']:%m/%d}({w}) {ev['start']}時 {ev['court']}【{kind}】")
    return "\n".join(lines)


def format_warning_message(targets: list[dict]) -> str:
    lines = ["⚠️ 明日キャンセル予定（現時点で集客なし）"]
    for ev in targets:
        w = WEEKDAY[ev["date"].weekday()]
        kind = "レッスン(0人)" if ev["is_lesson"] else "練習会(自分のみ)"
        lines.append(f"・{ev['date']:%m/%d}({w}) {ev['start']}時 {ev['court']}【{kind}】")
    return "\n".join(lines)


def format_held_message(targets: list[dict]) -> str:
    lines = ["🚨 テニスベアの削除に失敗（申込みが入った可能性）手動で確認してください"]
    for ev in targets:
        w = WEEKDAY[ev["date"].weekday()]
        lines.append(f"・{ev['date']:%m/%d}({w}) {ev['start']}時 {ev['court']}")
    return "\n".join(lines)


def format_partial_rebook_message(
    rebooked: list[tuple[ReservationSlot, int, int]],
) -> str:
    lines = ["♻️ 長時間のコート予約を分割し、開催枠だけ取り直しました"]
    for reservation, kept_start, kept_end in rebooked:
        weekday = WEEKDAY[reservation.date.weekday()]
        lines.append(
            f"・{reservation.date:%m/%d}({weekday}) "
            f"{reservation.start}-{reservation.end}時 → "
            f"{kept_start}-{kept_end}時 "
            f"{reservation.court_name} 庭球場{reservation.court_number}"
        )
    return "\n".join(lines)


def format_rollback_message(rolled_back: list[ReservationSlot]) -> str:
    lines = ["⚠️ 部分予約の取り直しに失敗したため、元の予約時間を復元しました"]
    for reservation in rolled_back:
        weekday = WEEKDAY[reservation.date.weekday()]
        lines.append(
            f"・{reservation.date:%m/%d}({weekday}) "
            f"{reservation.start}-{reservation.end}時 "
            f"{reservation.court_name} 庭球場{reservation.court_number}"
        )
    return "\n".join(lines)


def format_rebook_failure_message(failed: list[ReservationSlot]) -> str:
    lines = ["🚨 コート予約の取り直し・元時間への復元ともに失敗しました。至急手動で確保してください"]
    for reservation in failed:
        weekday = WEEKDAY[reservation.date.weekday()]
        lines.append(
            f"・{reservation.date:%m/%d}({weekday}) "
            f"{reservation.start}-{reservation.end}時 "
            f"{reservation.court_name} 庭球場{reservation.court_number}"
        )
    return "\n".join(lines)


def format_processing_failure_message(failed: list[ReservationSlot]) -> str:
    lines = ["🚨 コート取消の自動処理に失敗しました。手動で予約状況を確認してください"]
    for reservation in failed:
        weekday = WEEKDAY[reservation.date.weekday()]
        lines.append(
            f"・{reservation.date:%m/%d}({weekday}) "
            f"{reservation.start}-{reservation.end}時 "
            f"{reservation.court_name} 庭球場{reservation.court_number}"
        )
    return "\n".join(lines)


def format_post_cancel_failure_message(failed: list[ReservationSlot]) -> str:
    lines = [
        "🚨 コートを取り消したまま取り直せていない可能性があります。"
        "至急手動で確保してください"
    ]
    for reservation in failed:
        weekday = WEEKDAY[reservation.date.weekday()]
        lines.append(
            f"・{reservation.date:%m/%d}({weekday}) "
            f"{reservation.start}-{reservation.end}時 "
            f"{reservation.court_name} 庭球場{reservation.court_number}"
        )
    return "\n".join(lines)


def run(
    target_date: datetime | None = None,
    execute: bool = True,
    headless: bool = IS_HEADLESS,
) -> tuple[list[dict], list[dict]]:
    """翌日の0人レッスン・自分のみ練習会のコートを取消し、募集を削除する。
    2日後が対象の場合は通知のみ行う。

    Returns:
        (取消・削除したイベント, 2日後の警告対象イベント)
    """
    conf = load_rules()
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

    with TennisBear(headless) as tb:
        tb.login()
        events = tb.list_organized_events()

        # days_before日後（テニスベア締切と同日）: キャンセル実行
        days_before = conf.get("days_before", 2)
        cancel_date = target_date if target_date else today + timedelta(days=days_before)
        targets = find_empty_lessons(events, cancel_date) + find_solo_practices(events, cancel_date)

        # その1日先: 通知のみ（target_date指定時はスキップ）
        warn_targets = []
        if target_date is None:
            warn_date = today + timedelta(days=days_before + 1)
            warn_targets = find_empty_lessons(events, warn_date) + find_solo_practices(events, warn_date)

        cancelled = []
        partial_rebooked: list[tuple[ReservationSlot, int, int]] = []
        rolled_back: list[ReservationSlot] = []
        rebook_failed: list[ReservationSlot] = []
        processing_failed: list[ReservationSlot] = []
        post_cancel_failed: list[ReservationSlot] = []
        if targets:
            with NetAichi(headless) as na:
                na.login(id=OGURI_ACCOUNT_ID)
                reservations = na.get.reservation()
                reservation_groups: dict[ReservationSlot, list[dict]] = {}
                for ev in targets:
                    keyword = map_court(ev["court"], conf["court_map"])
                    if keyword is None:
                        na.logger.warning(f"ネットあいち未対応コートのためスキップ: {ev['court']}")
                        continue
                    reservation = find_reservation(ev, keyword, reservations)
                    if reservation is None:
                        na.logger.warning(
                            f"対応するコート予約が見つからないためスキップ: "
                            f"{ev['date']:%Y-%m-%d} {ev['start']}時 {ev['court']}"
                        )
                        continue
                    reservation_groups.setdefault(reservation, []).append(ev)

                target_ids = {ev["id"] for ev in targets}
                event_hours = conf.get("event_hours", 2)
                for reservation, reservation_targets in reservation_groups.items():
                    is_cancelled = False
                    try:
                        related_events = [
                            ev
                            for ev in events
                            if event_matches_reservation(ev, reservation, conf["court_map"])
                        ]
                        retained_events = [
                            ev for ev in related_events if ev["id"] not in target_ids
                        ]
                        # 残す練習会は4時間1本のことがあり、取り直す長さを誤ると
                        # 後半がコート無しになるため実際の終了時刻を取りに行く
                        fill_event_ends(
                            tb,
                            [ev for ev in retained_events if ev["is_practice"]],
                            event_hours,
                        )
                        retained_ranges = merge_event_ranges(
                            retained_events,
                            event_hours,
                            reservation.end,
                        )
                        if len(retained_ranges) > 1:
                            na.logger.warning(
                                f"取り直す時間帯が分断されているため自動処理をスキップ: "
                                f"{reservation.date:%Y-%m-%d} "
                                f"{reservation.start}-{reservation.end}時 "
                                f"{reservation.court_keyword}"
                            )
                            continue
                        if not execute:
                            cancelled.extend(reservation_targets)
                            continue
                        if not na.cancel_reservation(
                            reservation.date,
                            reservation.start,
                            reservation.end,
                            reservation.court_keyword,
                            reservation.court_number,
                        ):
                            continue
                        is_cancelled = True

                        if not retained_ranges:
                            cancelled.extend(reservation_targets)
                            continue

                        kept_start, kept_end = retained_ranges[0]
                        if na.reserve_available_slot(
                            reservation.date,
                            kept_start,
                            kept_end,
                            reservation.court_name,
                            reservation.court_number,
                        ):
                            partial_rebooked.append((reservation, kept_start, kept_end))
                            cancelled.extend(reservation_targets)
                            continue

                        is_reset = na.reset_reservation_session()
                        if is_reset and na.reserve_available_slot(
                            reservation.date,
                            reservation.start,
                            reservation.end,
                            reservation.court_name,
                            reservation.court_number,
                        ):
                            rolled_back.append(reservation)
                            cancelled.extend(reservation_targets)
                        else:
                            rebook_failed.append(reservation)
                    except Exception:
                        na.logger.error(
                            "予約グループの自動処理に失敗: %s %s-%s時 %s",
                            reservation.date.strftime("%Y-%m-%d"),
                            reservation.start,
                            reservation.end,
                            reservation.court_keyword,
                            exc_info=True,
                        )
                        if is_cancelled:
                            post_cancel_failed.append(reservation)
                        else:
                            processing_failed.append(reservation)

        # コート取消に成功した分だけテニスベアの募集も削除する。
        # 削除に失敗した場合（申込みが入った等）は保留にして別途通知する
        held = []
        if execute:
            for ev in cancelled:
                try:
                    ok = tb.delete_event(ev["id"])
                except Exception as e:
                    tb.logger.error(f"テニスベア削除エラー {ev['id']}: {e}")
                    ok = False
                if not ok:
                    held.append(ev)

    if execute and cancelled:
        notify(format_message(cancelled))
    if execute and held:
        notify(format_held_message(held))
    if execute and partial_rebooked:
        notify(format_partial_rebook_message(partial_rebooked))
    if execute and rolled_back:
        notify(format_rollback_message(rolled_back))
    if execute and rebook_failed:
        notify(format_rebook_failure_message(rebook_failed))
    if execute and processing_failed:
        notify(format_processing_failure_message(processing_failed))
    if execute and post_cancel_failed:
        notify(format_post_cancel_failure_message(post_cancel_failed))
    if execute and warn_targets:
        notify(format_warning_message(warn_targets))
    return cancelled, warn_targets
