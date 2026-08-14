"""コート乗り換え。

抽選で当たったコートは番号を選べないため、予約済みの枠と同じ日時により良い番号が
空いていたら移動する。良し悪しの基準は rules/swap_rules.yaml で宣言する。

必ず「移動先を予約 → 予約一覧で成功を確認 → 元を取消」の順で実行する。
逆順にすると取り直しに失敗したとき枠そのものを失う。この順序を崩さないこと。
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from unicodedata import normalize

import pandas as pd
import yaml
from dateutil.relativedelta import relativedelta

from netaichi.browser import NetAichi
from netaichi.config import IS_HEADLESS, RULES_DIR, default_pw
from netaichi.db import M_Account
from netaichi.notify import notify
from netaichi.services.availability import merge_hour_slots
from netaichi.services.lottery import GROUP_IDS, get_group_accounts

WEEKDAY = ["月", "火", "水", "木", "金", "土", "日"]
DEFAULT_PREFIX = "庭球場"


@dataclass(frozen=True)
class SwapTarget:
    account_id: str
    park: str
    prefix: str
    date: datetime
    start: int
    end: int
    from_number: int
    to_number: int
    from_rank: int
    to_rank: int


def load_rules() -> dict:
    with open(RULES_DIR / "swap_rules.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def court_rank(number: int | None, priority: list[list[int]]) -> int:
    """優先順位表での順位を返す（小さいほど良い）

    表に載っていない番号は最下位扱い。移動先には選ばれず、そこからは移動できる。
    """
    for rank, numbers in enumerate(priority):
        if number in numbers:
            return rank
    return len(priority)


def parse_court_number(name: str, prefix: str) -> int | None:
    """「庭球場１４（人工芝）」のようなコート名から面番号を取り出す（全角も可）"""
    matched = re.search(rf"{re.escape(prefix)}\s*(\d+)", normalize("NFKC", str(name)))
    return int(matched.group(1)) if matched else None


def normalize_number(value) -> int | None:
    """予約一覧の面番号（全角のことがある）を整数にする"""
    digits = re.search(r"\d+", normalize("NFKC", str(value)))
    return int(digits.group()) if digits else None


def covers(slot: dict, start: int, end: int) -> bool:
    """空き枠が予約時間を完全に覆うか

    部分的にしか空いていないコートへ移ると枠が分断されるので、覆えるときだけ移動する。
    """
    return slot["start"] <= start and slot["end"] >= end


def find_swap_targets(
    reservations: list[dict],
    slots: list[dict],
    courts_conf: dict,
) -> list[SwapTarget]:
    """予約ごとに、同じ日時でより順位の高い空きコートを探す（純粋関数）

    改善幅の大きいものから確定させ、同じ空きコートを複数の予約が奪い合わないようにする。
    """
    options: list[SwapTarget] = []
    for reservation in reservations:
        conf = courts_conf.get(reservation["park"])
        if conf is None:
            continue
        priority = conf["priority"]
        prefix = conf.get("prefix", DEFAULT_PREFIX)
        from_rank = court_rank(reservation["number"], priority)
        for slot in slots:
            if slot["value"] != reservation["park"]:
                continue
            if slot["date"].date() != reservation["date"].date():
                continue
            if not covers(slot, reservation["start"], reservation["end"]):
                continue
            number = parse_court_number(slot["facility"], prefix)
            if number is None or number == reservation["number"]:
                continue
            to_rank = court_rank(number, priority)
            if to_rank >= from_rank:
                continue
            options.append(
                SwapTarget(
                    account_id=reservation["account_id"],
                    park=reservation["park"],
                    prefix=prefix,
                    date=reservation["date"],
                    start=reservation["start"],
                    end=reservation["end"],
                    from_number=reservation["number"],
                    to_number=number,
                    from_rank=from_rank,
                    to_rank=to_rank,
                )
            )

    targets: list[SwapTarget] = []
    moved: set[tuple] = set()
    occupied: dict[tuple, list[tuple[int, int]]] = {}
    # 改善幅が大きい順。同じ改善幅なら、より良い番号を先に割り当てる
    for target in sorted(options, key=lambda t: (t.to_rank - t.from_rank, t.to_rank)):
        source = (
            target.account_id,
            target.park,
            target.date.date(),
            target.start,
            target.end,
            target.from_number,
        )
        if source in moved:
            continue
        court = (target.park, target.date.date(), target.to_number)
        if any(
            target.start < taken_end and target.end > taken_start
            for taken_start, taken_end in occupied.get(court, [])
        ):
            continue
        moved.add(source)
        occupied.setdefault(court, []).append((target.start, target.end))
        targets.append(target)
    return targets


def target_accounts(group_name: str) -> list[M_Account]:
    """対象アカウントの一覧を返す

    DBはリポジトリに含めていないため、GitHub Actions のような環境では
    アカウント一覧を引けない。その場合はマスターだけを対象にする。
    予約の大半はマスターが持っているので、これでも大半は拾える。
    """
    group_id = GROUP_IDS[group_name]
    accounts = get_group_accounts(group_id)
    if accounts:
        return accounts
    return [M_Account(name="", id=group_id, password=default_pw)]


def collect_reservations(
    browser: NetAichi,
    accounts: list,
    courts_conf: dict,
    start_date: datetime,
    end_date: datetime,
) -> list[dict]:
    """対象施設・対象期間の予約をアカウント横断で集める"""
    reservations = []
    for account in accounts:
        browser.login(account=account)
        for row in browser.get.reservation().itertuples():
            park = str(row.court)
            if park not in courts_conf:
                continue
            date = pd.Timestamp(row.date).to_pydatetime().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            if not start_date <= date <= end_date:
                continue
            number = normalize_number(row.court_number)
            if number is None:
                continue  # フットサル等、予約一覧に面番号が出ないコートは対象外
            reservations.append(
                {
                    "account_id": account.id,
                    "park": park,
                    "date": date,
                    "start": int(row.start),
                    "end": int(row.end),
                    "number": number,
                }
            )
    return reservations


def collect_slots(
    browser: NetAichi, reservations: list[dict], courts_conf: dict
) -> list[dict]:
    """予約がある日だけ空き状況を見る（全日走査は無駄なので絞る）"""
    slots = []
    for park, conf in courts_conf.items():
        dates = sorted({r["date"] for r in reservations if r["park"] == park})
        if not dates:
            continue
        slots += browser.find_available_slots(
            park, dates, [conf.get("prefix", DEFAULT_PREFIX)]
        )
    return merge_hour_slots(slots)


def format_message(targets: list[SwapTarget]) -> str:
    lines = ["🔄 より良いコートへ移動しました"]
    for target in targets:
        weekday = WEEKDAY[target.date.weekday()]
        lines.append(
            f"・{target.date:%m/%d}({weekday}) {target.start}-{target.end}時 "
            f"{target.park} {target.prefix}{target.from_number}"
            f" → {target.prefix}{target.to_number}"
        )
    return "\n".join(lines)


def format_orphan_message(targets: list[SwapTarget]) -> str:
    """移動先は取れたが元の取消に失敗した状態。何をすればいいかまで書く"""
    lines = [
        "🚨 コート乗り換えの後始末に失敗しました",
        "同じ枠を2面持ったままです。このままだと2面分の料金がかかります。",
        "",
        "【手動で取り消してください】",
    ]
    for target in targets:
        weekday = WEEKDAY[target.date.weekday()]
        lines.append(
            f"・{target.date:%m/%d}({weekday}) {target.start}-{target.end}時 "
            f"{target.park} {target.prefix}{target.from_number}"
            f"（アカウント: {target.account_id}）"
        )
    lines += ["", "【こちらは残す】"]
    for target in targets:
        weekday = WEEKDAY[target.date.weekday()]
        lines.append(
            f"・{target.date:%m/%d}({weekday}) {target.start}-{target.end}時 "
            f"{target.park} {target.prefix}{target.to_number}"
        )
    lines += [
        "",
        "手順: ネットあいちにログイン → マイページ → 予約状況の一覧 "
        "→ 上の面を選択 → 取消",
    ]
    return "\n".join(lines)


def run(execute: bool = True, headless: bool = IS_HEADLESS) -> list[SwapTarget]:
    """予約済みの枠を、より良い番号のコートへ移動する。

    Returns:
        移動した（execute=Falseなら移動できる）枠のリスト
    """
    conf = load_rules()
    courts_conf = conf["courts"]
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = today + timedelta(days=conf.get("min_days_ahead", 2))
    end_date = today + relativedelta(months=conf.get("months_ahead", 2))
    accounts = target_accounts(conf.get("group", "oguri"))

    swapped: list[SwapTarget] = []
    orphaned: list[SwapTarget] = []
    with NetAichi(headless) as na:
        reservations = collect_reservations(
            na, accounts, courts_conf, start_date, end_date
        )
        na.logger.info(
            f"対象の予約: {len(reservations)}件"
            f"（{start_date:%m/%d}〜{end_date:%m/%d} / "
            f"{'・'.join(courts_conf)}）"
        )
        if not reservations:
            return []

        slots = collect_slots(na, reservations, courts_conf)
        targets = find_swap_targets(reservations, slots, courts_conf)
        na.logger.info(f"乗り換え候補: {len(targets)}件")
        if not execute:
            return targets

        for account in accounts:
            account_targets = [t for t in targets if t.account_id == account.id]
            if not account_targets:
                continue
            na.login(account=account)
            for target in account_targets:
                if not _swap_one(na, target, orphaned):
                    continue
                swapped.append(target)

    if swapped:
        notify(format_message(swapped))
    if orphaned:
        notify(format_orphan_message(orphaned))
    return swapped


def _swap_one(
    browser: NetAichi, target: SwapTarget, orphaned: list[SwapTarget]
) -> bool:
    """1枠を移動する。移動先を確保できてから元を取り消す"""
    weekday = WEEKDAY[target.date.weekday()]
    label = (
        f"{target.date:%m/%d}({weekday}) {target.start}-{target.end}時 "
        f"{target.park} {target.prefix}{target.from_number}"
        f"→{target.prefix}{target.to_number}"
    )
    try:
        if not browser.reserve_available_slot(
            target.date,
            target.start,
            target.end,
            target.park,
            str(target.to_number),
        ):
            # 先に他の人へ取られただけなので実害はない。元の予約はそのまま残る
            browser.logger.info(f"移動先を確保できませんでした: {label}")
            browser.reset_reservation_session()
            return False
    except Exception:
        browser.logger.error(f"移動先の予約でエラー: {label}", exc_info=True)
        browser.reset_reservation_session()
        return False

    try:
        if browser.cancel_reservation(
            target.date,
            target.start,
            target.end,
            target.park,
            str(target.from_number),
        ):
            browser.logger.info(f"コートを移動しました: {label}")
            return True
    except Exception:
        browser.logger.error(f"元の予約の取消でエラー: {label}", exc_info=True)

    # 移動先を押さえたまま元を手放せていない。放置すると2面分の料金がかかる
    browser.logger.error(f"元の予約を取り消せず2面持ちになりました: {label}")
    orphaned.append(target)
    return False
