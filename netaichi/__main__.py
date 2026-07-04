"""CLI エントリポイント。

使い方: python -m netaichi <command>
"""
import argparse


def main():
    parser = argparse.ArgumentParser(prog="netaichi", description="ネットあいち自動抽選ボット")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="DBを初期化しスプレッドシートからアカウントを取り込む")

    p_lottery = sub.add_parser("lottery", help="抽選申込を実行")
    p_lottery.add_argument("group", choices=["oguri", "komada"], help="対象グループ")
    p_lottery.add_argument(
        "--dry-run", action="store_true", help="確認画面まで進むが確定しない"
    )

    p_lcancel = sub.add_parser("lottery-cancel", help="条件一致の抽選申込をグループ全アカウントで取消")
    p_lcancel.add_argument("group", choices=["oguri", "komada"], help="対象グループ")
    p_lcancel.add_argument("--court", required=True, help="コートの施設値（例: 400）")
    p_lcancel.add_argument("--start", type=int, help="開始時（例: 19）。省略時は時間を問わず対象")
    p_lcancel.add_argument("--dry-run", action="store_true", help="対象の表示のみ（取り消さない）")

    sub.add_parser("reserve", help="予約情報を収集しスプレッドシートに反映")

    p_avail = sub.add_parser("availability", help="空き状況をチェックし新規の空きをDiscordに通知")
    p_avail.add_argument(
        "--no-notify", action="store_true", help="通知せず結果表示のみ（動作確認用）"
    )
    p_avail.add_argument(
        "--headless", action="store_true", help="ブラウザ画面を表示せず実行（定期実行用）"
    )
    p_avail.add_argument(
        "--sites", help="チェックするサイト（カンマ区切り: netaichi,eaichi,nagoya。省略時は全サイト）"
    )
    p_avail.add_argument(
        "--days-ahead", type=int,
        help="今日からこの日数先までに限定してチェック（直近の高頻度チェック用）",
    )

    p_bear = sub.add_parser("bear", help="予約確定分の募集をテニスベアに作成")
    p_bear.add_argument(
        "--submit", action="store_true",
        help="確定まで実行する（未指定時は bear_rules.yaml の submit 設定に従う）",
    )

    p_cancel = sub.add_parser(
        "cancel", help="翌日の集客0レッスンのコートを取消し、募集も削除"
    )
    p_cancel.add_argument(
        "--dry-run", action="store_true", help="検出のみ（取消・削除しない）"
    )
    p_cancel.add_argument(
        "--headless", action="store_true", help="ブラウザ画面を表示せず実行（定期実行用）"
    )

    p_prune = sub.add_parser(
        "prune", help="練習が埋まった枠のレッスン募集を削除"
    )
    p_prune.add_argument(
        "--dry-run", action="store_true", help="検出のみ（削除しない）"
    )
    p_prune.add_argument(
        "--headless", action="store_true", help="ブラウザ画面を表示せず実行（定期実行用）"
    )

    p_daily = sub.add_parser(
        "daily", help="毎日の処理: prune（練習埋まりでレッスン削除）→ cancel（0人でコート取消）",
    )
    p_daily.add_argument(
        "--headless", action="store_true", help="ブラウザ画面を表示せず実行（定期実行用）"
    )

    args = parser.parse_args()

    match args.command:
        case "init":
            from netaichi.services.db_init import db_init

            db_init()
        case "lottery":
            from netaichi.services.lottery import run_group

            run_group(args.group, dry_run=args.dry_run)
        case "lottery-cancel":
            from netaichi.services.lottery import cancel_group

            results = cancel_group(
                args.group, args.court, args.start, dry_run=args.dry_run
            )
            action = "取消対象" if args.dry_run else "取消済み"
            for account_id, items in results.items():
                print(f"{account_id}: {action} {len(items)}件")
                for item in items:
                    date = item["date"] if isinstance(item["date"], str) else f"{item['date']:%m/%d}"
                    print(f"  {date} {item['start']}時")
        case "reserve":
            from netaichi.services.reserve import reserve

            reserve()
        case "availability":
            from netaichi.services.availability import check

            sites = args.sites.split(",") if args.sites else None
            new, gone = check(
                notify_enabled=not args.no_notify,
                headless=args.headless,
                sites=sites,
                days_ahead=args.days_ahead,
            )
            print(f"新規の空き: {len(new)}件")
            for slot in new:
                print(f"  {slot['date']:%m/%d} {slot['start']}-{slot['end']}時 {slot['value']}")
            print(f"埋まった枠: {len(gone)}件")
            for slot in gone:
                print(f"  {slot['date']:%m/%d} {slot['start']}-{slot['end']}時 {slot['value']}")
        case "bear":
            from netaichi.services.bear import run

            events = run(submit=True if args.submit else None)
            action = "作成" if args.submit else "作成対象（未掲載・確認のみ）"
            print(f"{action}: {len(events)}件")
            for ev in events:
                print(f"  {ev['date']:%m/%d} {ev['start']}-{ev['end']}時 {ev['bear_court']}（{ev['court']}）")
        case "cancel":
            from netaichi.services.cancel import run

            cancelled, warned = run(execute=not args.dry_run, headless=args.headless)
            action = "検出" if args.dry_run else "取消・削除"
            print(f"{action}(1日後): {len(cancelled)}件")
            for ev in cancelled:
                print(f"  {ev['date']:%m/%d} {ev['start']}時 {ev['court']}")
            print(f"通知のみ(2日後): {len(warned)}件")
            for ev in warned:
                print(f"  {ev['date']:%m/%d} {ev['start']}時 {ev['court']}")
        case "prune":
            from netaichi.services.prune import run

            result = run(execute=not args.dry_run, headless=args.headless)
            action = "検出" if args.dry_run else "削除"
            print(f"{action}: {len(result)}件")
            for ev in result:
                print(f"  {ev['date']:%m/%d} {ev['start']}時 {ev['court']}")
        case "daily":
            # 順序が重要: 先にprune（練習ありのレッスンを消す）→後にcancel
            # （逆だと練習で使うコートをcancelが取り消してしまう恐れがある）
            from netaichi.services import cancel, prune

            pruned = prune.run(headless=args.headless)
            print(f"prune 削除: {len(pruned)}件")
            cancelled, _ = cancel.run(headless=args.headless)
            print(f"cancel 取消・削除: {len(cancelled)}件")


if __name__ == "__main__":
    main()
