"""参加人数に対して多すぎるコートの取消（ルールC）。

2面取ってあっても参加人数が少なければ1面で足りる。余った面を取り消す。
集客0・自分のみの取消は cancel（ルールB）が担当するので、こちらは
2面以上あるときに減らすことだけを見る。

残す面は swap_rules.yaml の優先順位に従い、良い番号（ブロックの端）を残す。
"""
from datetime import datetime, timedelta

import pandas as pd
import yaml

from netaichi.browser import NetAichi
from netaichi.browser.tennisbear import TennisBear
from netaichi.config import IS_HEADLESS, OGURI_ACCOUNT_ID, RULES_DIR
from netaichi.notify import notify
from netaichi.services.cancel import ReservationSlot, map_court
from netaichi.services.swap import court_rank, normalize_number
from netaichi.services.swap import load_rules as load_swap_rules

WEEKDAY = ["月", "火", "水", "木", "金", "土", "日"]


def load_rules() -> dict:
    with open(RULES_DIR / "shrink_rules.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def practice_capacity(date: datetime, conf: dict) -> int:
    """練習会の1面あたりの人数。夏は休憩が増えるぶん多くても回る"""
    if date.month in conf.get("summer_months", [7, 8]):
        return conf.get("summer_capacity", 4)
    return conf.get("practice_capacity", 3)


def required_courts(events: list[dict], capacity: int, lesson_courts: int = 1) -> int:
    """同じ時間帯の募集から必要な面数を出す（純粋関数）

    レッスンは人数によらず lesson_courts 面で開催する。練習会は capacity 人で1面。
    参加人数は募集をまたいで合計する。主催者が複数の募集で重複して数えられていても
    面が多めに残る側に倒れるので、練習場所が足りなくなることはない。
    """
    if not events:
        return 0
    if any(ev["is_lesson"] for ev in events):
        return lesson_courts if any(ev["participants"] > 0 for ev in events) else 0
    participants = sum(ev["participants"] for ev in events)
    if participants <= 1:
        return 0  # 自分だけなら開催しない（cancel が全面を取り消す）
    return -(-participants // capacity)  # 切り上げ


def required_courts_for_reservation(
    events: list[dict], capacity: int, lesson_courts: int = 1
) -> int:
    """予約時間全体で必要な面数（純粋関数）

    4時間の予約に2時間の募集が並ぶため、時間帯ごとに数えて多い方に合わせる。
    前半3人・後半5人なら2面残す。
    """
    by_start: dict[int, list[dict]] = {}
    for event in events:
        by_start.setdefault(event["start"], []).append(event)
    return max(
        (required_courts(evs, capacity, lesson_courts) for evs in by_start.values()),
        default=0,
    )


def group_reservations(
    reservations: pd.DataFrame,
) -> dict[tuple, list[ReservationSlot]]:
    """同じ施設・日付・時間帯の予約をまとめる（純粋関数）"""
    groups: dict[tuple, list[ReservationSlot]] = {}
    for row in reservations.itertuples():
        court_name = str(row.court)
        date = pd.Timestamp(row.date).to_pydatetime().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        start, end = int(row.start), int(row.end)
        groups.setdefault((court_name, date, start, end), []).append(
            ReservationSlot(
                date=date,
                start=start,
                end=end,
                court_name=court_name,
                court_number=str(row.court_number),
                court_keyword=court_name,
            )
        )
    return groups


def cancel_order(slots: list[ReservationSlot], swap_courts: dict) -> list[ReservationSlot]:
    """取り消す順（悪い番号から）に並べる（純粋関数）

    swap_rules.yaml の優先順位を使い、ブロックの端の面を残す。
    """
    def key(slot: ReservationSlot):
        priority = swap_courts.get(slot.court_name, {}).get("priority", [])
        number = normalize_number(slot.court_number) or 0
        return (-court_rank(number, priority), -number)

    return sorted(slots, key=key)


def find_surplus_courts(
    events: list[dict],
    reservations: pd.DataFrame,
    conf: dict,
    swap_courts: dict,
) -> list[tuple[ReservationSlot, int, int]]:
    """必要面数を超えた面を返す（純粋関数）

    Returns:
        (取り消す面, 必要面数, 現在の面数) のリスト
    """
    lesson_courts = conf.get("lesson_courts", 1)
    court_map = conf.get("court_map", {})
    surplus = []
    for (court_name, date, start, end), slots in group_reservations(reservations).items():
        if len(slots) <= 1:
            continue  # 1面だけなら cancel（ルールB）の担当
        if any(normalize_number(slot.court_number) is None for slot in slots):
            # フットサル等、予約一覧に面番号が出ないコートが混じる枠。
            # 面番号なしで取消を頼むと「庭球場」を含む別の面を掴んでしまうため触らない
            continue
        related = [
            event
            for event in events
            if event["date"].date() == date.date()
            and start <= event["start"] < end
            and map_court(event["court"], court_map) == court_name
        ]
        if not related:
            continue  # 募集が出ていない枠は判断材料がないので触らない
        needed = required_courts_for_reservation(
            related, practice_capacity(date, conf), lesson_courts
        )
        # 全面取消は cancel が募集削除・部分予約の取り直しまで含めて処理する。
        # shrink で先に消すと二重取消になり得るため、最低1面を残す場合だけ扱う。
        if needed <= 0:
            continue
        if needed >= len(slots):
            continue
        for slot in cancel_order(slots, swap_courts)[: len(slots) - needed]:
            surplus.append((slot, needed, len(slots)))
    return surplus


def format_message(cancelled: list[tuple[ReservationSlot, int, int]]) -> str:
    lines = ["✂️ 参加人数に対して多すぎるコートを取り消しました"]
    for slot, needed, current in cancelled:
        weekday = WEEKDAY[slot.date.weekday()]
        lines.append(
            f"・{slot.date:%m/%d}({weekday}) {slot.start}-{slot.end}時 "
            f"{slot.court_name} 庭球場{slot.court_number} を取消"
            f"（{current}面 → {needed}面）"
        )
    lines += ["", "テニスベアの募集が残っている場合は、面数に合っているか確認してください。"]
    return "\n".join(lines)


def format_failure_message(failed: list[tuple[ReservationSlot, int, int]]) -> str:
    lines = ["🚨 多すぎるコートの取消に失敗しました。手動で取り消してください"]
    for slot, needed, current in failed:
        weekday = WEEKDAY[slot.date.weekday()]
        lines.append(
            f"・{slot.date:%m/%d}({weekday}) {slot.start}-{slot.end}時 "
            f"{slot.court_name} 庭球場{slot.court_number}"
            f"（{current}面 → {needed}面にしたい）"
        )
    return "\n".join(lines)


def run(
    target_date: datetime | None = None,
    execute: bool = True,
    headless: bool = IS_HEADLESS,
) -> list[tuple[ReservationSlot, int, int]]:
    """参加人数に対して多すぎる面を取り消す。

    Returns:
        取り消した（execute=Falseなら取り消せる）面のリスト
    """
    conf = load_rules()
    swap_courts = load_swap_rules().get("courts", {})
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    date = target_date or today + timedelta(days=conf.get("days_before", 2))

    with TennisBear(headless) as tb:
        tb.login()
        events = [
            event
            for event in tb.list_organized_events()
            if event["date"].date() == date.date()
        ]
    if not events:
        return []

    cancelled: list[tuple[ReservationSlot, int, int]] = []
    failed: list[tuple[ReservationSlot, int, int]] = []
    with NetAichi(headless) as na:
        na.login(id=OGURI_ACCOUNT_ID)
        surplus = find_surplus_courts(events, na.get.reservation(), conf, swap_courts)
        for slot, needed, current in surplus:
            # 人数の数え方が実態と合っているかは、この行を見て調整する
            na.logger.info(
                f"{slot.date:%Y-%m-%d} {slot.start}-{slot.end}時 {slot.court_name}: "
                f"現在{current}面 → 必要{needed}面 "
                f"（庭球場{slot.court_number}を取消）"
            )
        if not execute:
            return surplus

        for item in surplus:
            slot = item[0]
            if na.cancel_reservation(
                slot.date, slot.start, slot.end, slot.court_keyword, slot.court_number
            ):
                cancelled.append(item)
            else:
                failed.append(item)

    if cancelled:
        notify(format_message(cancelled))
    if failed:
        notify(format_failure_message(failed))
    return cancelled
