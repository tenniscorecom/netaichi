"""抽選申込サービス。

申込ルールは rules/lottery_rules.yaml で宣言し、
build_lottery_data()（純粋関数）で申込データに変換する。
"""
from datetime import datetime

import yaml
from dateutil.relativedelta import relativedelta
from jpholiday import is_holiday
from sqlmodel import desc

from netaichi.browser import NetAichi
from netaichi.config import (
    IS_HEADLESS,
    KOMADA_ACCOUNT_ID,
    OGURI_ACCOUNT_ID,
    RULES_DIR,
)
from netaichi.db import M_Account, NetaichiDatabase, T_LotteryData, select
from netaichi.helper import sqlmodel_to_df

db = NetaichiDatabase(False)

# YAML上のグループ名 → ネットあいちのアカウントグループID
GROUP_IDS = {
    "oguri": OGURI_ACCOUNT_ID,
    "komada": KOMADA_ACCOUNT_ID,
}


def load_rules() -> dict:
    with open(RULES_DIR / "lottery_rules.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def lottery_month_dates(base: datetime | None = None, months: int = 3) -> list[datetime]:
    """抽選対象月（base + months）の全日付を返す"""
    if base is None:
        base = datetime.today().replace(day=1)
    first = base + relativedelta(months=months)
    dates = []
    d = first
    while d.month == first.month:
        dates.append(d)
        d += relativedelta(days=1)
    return dates


def rule_applies(rule: dict, date: datetime) -> bool:
    """ルールの days 指定が日付に合致するか"""
    days = rule["days"]
    if days == "weekend_holiday":
        return date.weekday() in (5, 6) or is_holiday(date)
    return date.weekday() in days and not is_holiday(date)


def build_lottery_data(
    rules: list[dict], dates: list[datetime], account_group: str
) -> list[T_LotteryData]:
    """申込ルールと対象日付から抽選申込データを生成する（純粋関数）"""
    data = []
    for date in dates:
        for rule in rules:
            if not rule_applies(rule, date):
                continue
            for value in rule["courts"]:
                for start, end in rule["times"]:
                    data.append(
                        T_LotteryData(
                            value=str(value),
                            date=date,
                            start=start,
                            end=end,
                            amount=rule.get("amount", 1),
                            account_group=account_group,
                        )
                    )
    return data


def get_group_accounts(group_id: str) -> list[M_Account]:
    with db.session() as session:
        return session.exec(
            select(M_Account)
            .where(M_Account.account_group == group_id)
            .order_by(desc(M_Account.is_master))
        ).all()


def add_lottery(rules: list[dict], group_id: str, dry_run: bool = False):
    """マスターアカウントでルール分の抽選を申し込む"""
    data = build_lottery_data(rules, lottery_month_dates(), group_id)
    if not data:
        return
    df = sqlmodel_to_df(data)
    with NetAichi(IS_HEADLESS, dry_run=dry_run) as na:
        na.login(id=group_id)
        na.add_lottery(df)


def run_group(name: str, dry_run: bool = False):
    """グループの全アカウントで抽選申込を実行する"""
    conf = load_rules()["groups"][name]
    group_id = GROUP_IDS[name]
    accounts = get_group_accounts(group_id)
    if not accounts:
        raise RuntimeError(f"アカウントが未登録です（グループ: {name}）。先に init を実行してください")

    rules = conf.get("rules") or []
    if rules:
        add_lottery(rules, group_id, dry_run)

    with NetAichi(IS_HEADLESS, dry_run=dry_run) as na:
        if conf.get("update_court_properties"):
            na.login(account=accounts[1])
            na.update_court_properties()

        # マスターの申込内容をDBへ取り込み、他アカウントが同じ内容を申し込む
        na.login(account=accounts[0])
        na.update_lottery_data()

        start_account_id = conf.get("start_account_id")
        skip = bool(start_account_id)
        for account in accounts[1:]:
            if skip and account.id == start_account_id:
                skip = False
            if skip or account.id == group_id:
                continue
            na.login(account=account)
            if conf.get("skip_alltime"):
                status = na.get.lottery_status()
                if status.alltime == str(conf["skip_alltime"]):
                    continue
            na.run_lottery(master_id=group_id, players=conf.get("players", 4))


# 旧CLI互換
def oguri():
    run_group("oguri")


def komada():
    run_group("komada")
