from browser import NetAichi
from config import OGURI_ACCOUNT_ID, KOMADA_ACCOUNT_ID, IS_HEADLESS, OGURI_GSS_ID
from database import NetaichiDatabase, M_Account, select
import pandas as pd
from helper import SpreadSheet


def reserve():

    db = NetaichiDatabase()

    with NetAichi(IS_HEADLESS) as na:
        temp = pd.DataFrame()
        with db.session() as session:
            accounts = session.exec(select(M_Account)).all()
            for account in accounts:
                if account.account_group in [OGURI_ACCOUNT_ID]:
                    na.login(account=account)
                    reserve_df = na.get.reservation()

                    if account.account_group == KOMADA_ACCOUNT_ID:
                        if reserve_df.empty:
                            continue
                        reserve_df = reserve_df[reserve_df['court'].str.contains(
                            '大高緑地')]
                    temp = pd.concat([temp, reserve_df])
        temp.to_csv('./df.csv', header=True, index=False)
    ss = SpreadSheet(OGURI_GSS_ID)
    ss.replace_all(ss.reseve_sheet, temp)
