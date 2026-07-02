from database import NetaichiDatabase, M_Account, select, T_LotteryData
from config import OGURI_ACCOUNT_ID, KOMADA_ACCOUNT_ID, IS_HEADLESS, OGURI_GSS_ID
from browser import NetAichi
from sqlmodel import desc, delete
from jpholiday import is_holiday
from helper import sqmodel_to_df
import pandas as pd

db = NetaichiDatabase(False)


def oguri():
    add_lottery()
    with NetAichi() as na:
        with db.session() as session:
            oguri_accounts = session.exec(
                select(M_Account)
                .where(M_Account.account_group == OGURI_ACCOUNT_ID)
                .order_by(desc(M_Account.is_master))
            ).all()
        na.login(account=oguri_accounts[0])
        lottery_datas = na.update_lottery_data()
        for account in oguri_accounts[1:]:
            na.login(account=account)
            na.run_lottery(master_id=OGURI_ACCOUNT_ID, players=4)


def komada():
    with NetAichi(IS_HEADLESS) as na:
        # add_lottery()
        with db.session() as session:
            komada_accounts = session.exec(
                select(M_Account)
                .where(M_Account.account_group == KOMADA_ACCOUNT_ID)
                .order_by(desc(M_Account.is_master))
            ).all()

        # na.login(account=komada_accounts[5])

        na.login(account=komada_accounts[1])
        properties = na.update_court_propreties()
        na.login(account=komada_accounts[0])
        lottery_datas = na.update_lottery_data()
        # master_status = na.get.lottery_status()
        # master_status_de  taills = na.get.lottery_status_detaill()
        start_account_id = "01154051"
        flag = True
        for account in komada_accounts[1:]:
            if account.id == start_account_id or start_account_id == "":
                flag = False
            if flag or account.id == KOMADA_ACCOUNT_ID:
                continue
            na.login(account=account)
            status = na.get.lottery_status()
            if status.alltime == "240":
                continue
            # status = na.get.lottery_status()
            # status_detaills = na.get.lottery_status_detaill()

            na.run_lottery(master_id=KOMADA_ACCOUNT_ID, players=9)


def add_lottery():
    from browser.jsp.data import CourtValues

    values = CourtValues.items()
    temp = []
    for date in NetAichi().next_date():
        week = date.weekday()
        if week in [5, 6] or is_holiday(date):
            for value in values:
                accounts = [OGURI_ACCOUNT_ID]
                if value in [CourtValues.KENKOU, CourtValues.KENKOU_N]:
                    amount = 3
                    continue
                else:
                    amount = 1

                for account in accounts:
                    if value in [
                        CourtValues.KOROGI,
                        CourtValues.KOROGI_C,
                        CourtValues.KOROGI_N,
                    ]:
                        continue
                        if week == 6:
                            temp.append(
                                T_LotteryData(
                                    value=value,
                                    date=date,
                                    start=8,
                                    end=12,
                                    amount=amount,
                                    account_group=account,
                                )
                            )
                        temp.append(
                            T_LotteryData(
                                value=value,
                                date=date,
                                start=12,
                                end=16,
                                amount=amount,
                                account_group=account,
                            )
                        )
                        temp.append(
                            T_LotteryData(
                                value=value,
                                date=date,
                                start=16,
                                end=18,
                                amount=amount,
                                account_group=account,
                            )
                        )
                    else:
                        temp.append(
                            T_LotteryData(
                                value=value,
                                date=date,
                                start=9,
                                end=13,
                                amount=amount,
                                account_group=account,
                            )
                        )
                        temp.append(
                            T_LotteryData(
                                value=value,
                                date=date,
                                start=13,
                                end=17,
                                amount=amount,
                                account_group=account,
                            )
                        )
        if week in [0, 1, 3, 4] and is_holiday(date) is False:
            for value in [CourtValues.MORIKORO]:
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
    df = sqmodel_to_df(temp)

    for id, group in df.groupby("account_group"):
        with NetAichi() as na:
            na.login(id=id)

            na.add_lottery(group)
    return df
