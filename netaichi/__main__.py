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


if __name__ == "__main__":
    main()
