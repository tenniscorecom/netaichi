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

    sub.add_parser("reserve", help="予約情報を収集しスプレッドシートに反映")

    p_avail = sub.add_parser("availability", help="空き状況をチェックし新規の空きをDiscordに通知")
    p_avail.add_argument(
        "--no-notify", action="store_true", help="通知せず結果表示のみ（動作確認用）"
    )
    p_avail.add_argument(
        "--headless", action="store_true", help="ブラウザ画面を表示せず実行（定期実行用）"
    )

    p_bear = sub.add_parser("bear", help="予約確定分の募集をテニスベアに作成")
    p_bear.add_argument(
        "--submit", action="store_true",
        help="確定まで実行する（未指定時は bear_rules.yaml の submit 設定に従う）",
    )

    args = parser.parse_args()

    match args.command:
        case "init":
            from netaichi.services.db_init import db_init

            db_init()
        case "lottery":
            from netaichi.services.lottery import run_group

            run_group(args.group, dry_run=args.dry_run)
        case "reserve":
            from netaichi.services.reserve import reserve

            reserve()
        case "availability":
            from netaichi.services.availability import check

            new = check(notify_enabled=not args.no_notify, headless=args.headless)
            print(f"新規の空き: {len(new)}件")
            for slot in new:
                print(slot)
        case "bear":
            from netaichi.services.bear import run

            events = run(submit=True if args.submit else None)
            action = "作成" if args.submit else "作成対象（未掲載・確認のみ）"
            print(f"{action}: {len(events)}件")
            for ev in events:
                print(f"  {ev['date']:%m/%d} {ev['start']}-{ev['end']}時 {ev['bear_court']}（{ev['court']}）")


if __name__ == "__main__":
    main()
