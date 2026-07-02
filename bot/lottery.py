from database import NetaichiDatabase, M_Account, select, T_LotteryData
from config import OGURI_ACCOUNT_ID, KOMADA_ACCOUNT_ID, IS_HEADLESS
from browser import NetAichi
from browser.jsp.data import CourtValues
from sqlmodel import desc
from jpholiday import is_holiday
from helper import sqlmodel_to_df

db = NetaichiDatabase(False)

# 土日祝に申し込むコート（9-13時・13-17時、各1面）
WEEKEND_COURTS = [
    CourtValues.ODAKA,
    CourtValues.OBATA,
    CourtValues.MORIKORO,
    CourtValues.MORIKORO_F,
    CourtValues.SINRIN,
]
# 平日（月火木金）の夜に申し込むコート（19-21時、1面）
WEEKNIGHT_COURTS = [CourtValues.MORIKORO]


def oguri():
    add_lottery()
    with NetAichi() as na:
        accounts = get_group_accounts(OGURI_ACCOUNT_ID)
        na.login(account=accounts[0])
        na.update_lottery_data()
        for account in accounts[1:]:
            na.login(account=account)
            na.run_lottery(master_id=OGURI_ACCOUNT_ID, players=4)


def komada():
    with NetAichi(IS_HEADLESS) as na:
        accounts = get_group_accounts(KOMADA_ACCOUNT_ID)
        na.login(account=accounts[1])
        na.update_court_properties()
        na.login(account=accounts[0])
        na.update_lottery_data()

        # このIDのアカウントから処理を再開する（空文字なら先頭から）
        start_account_id = "01154051"
        skip = True
        for account in accounts[1:]:
            if account.id == start_account_id or start_account_id == "":
                skip = False
            if skip or account.id == KOMADA_ACCOUNT_ID:
                continue
            na.login(account=account)
            status = na.get.lottery_status()
            if status.alltime == "240":
                continue
            na.run_lottery(master_id=KOMADA_ACCOUNT_ID, players=9)


def get_group_accounts(group_id: str) -> list[M_Account]:
    with db.session() as session:
        return session.exec(
            select(M_Account)
            .where(M_Account.account_group == group_id)
            .order_by(desc(M_Account.is_master))
        ).all()


def build_lottery_data() -> list[T_LotteryData]:
    """申込ルールから抽選申込データを生成する"""
    temp = []
    for date in NetAichi().next_date():
        week = date.weekday()
        if week in [5, 6] or is_holiday(date):
            for value in WEEKEND_COURTS:
                for start, end in [(9, 13), (13, 17)]:
                    temp.append(
                        T_LotteryData(
                            value=value,
                            date=date,
                            start=start,
                            end=end,
                            amount=1,
                            account_group=OGURI_ACCOUNT_ID,
                        )
                    )
        if week in [0, 1, 3, 4] and not is_holiday(date):
            for value in WEEKNIGHT_COURTS:
                temp.append(
                    T_LotteryData(
                        value=value,
                        date=date,
                        start=19,
                        end=21,
                        amount=1,
                        account_group=OGURI_ACCOUNT_ID,
                    )
                )
    return temp


def add_lottery():
    df = sqlmodel_to_df(build_lottery_data())
    for id, group in df.groupby("account_group"):
        with NetAichi() as na:
            na.login(id=id)
            na.add_lottery(group)
    return df
