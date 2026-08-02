"""テニスベア募集の終了時刻を補う。

主催イベント一覧には開始時刻しか出ないため、練習会のように4時間1本で
募集している枠は長さが分からない。必要なイベントだけ編集画面を開いて補う。
"""
from netaichi.browser.tennisbear import TennisBear


def fill_event_ends(
    tb: TennisBear, events: list[dict], default_hours: int
) -> None:
    """events の end を埋める（既に end があるものは開かない）

    読み取れなかった場合は default_hours の長さにフォールバックする。
    """
    for ev in events:
        if ev.get("end"):
            continue
        times = tb.get_event_time_range(ev["id"])
        fallback_end = ev["start"] + default_hours
        if times is None:
            ev["end"] = fallback_end
            continue

        start, end = times
        if start != ev["start"] or not start < end <= 24:
            tb.logger.warning(
                "開催時間が一覧と整合しないため既定時間を使います: "
                f"{ev['id']} list={ev['start']} edit={start}-{end}"
            )
            ev["end"] = fallback_end
            continue
        ev["end"] = end
