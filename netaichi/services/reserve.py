from netaichi.browser import NetAichi
from netaichi.config import OGURI_ACCOUNT_ID, IS_HEADLESS, OGURI_GSS_ID
from netaichi.db import NetaichiDatabase, M_Account, select
import pandas as pd
from netaichi.helper import SpreadSheet

db = NetaichiDatabase(False)


def collect_reservations(group_id: str = OGURI_ACCOUNT_ID) -> pd.DataFrame:
    """グループ全アカウントの予約情報を収集する

    columns: court, court_number, date, start, end, account
    """
    temp = pd.DataFrame()
    with NetAichi(IS_HEADLESS) as na:
        with db.session() as session:
            accounts = session.exec(
                select(M_Account).where(M_Account.account_group == group_id)
            ).all()
        for account in accounts:
            na.login(account=account)
            reserve_df = na.get.reservation()
            temp = pd.concat([temp, reserve_df])
    return temp


def reserve():
    df = collect_reservations()
    ss = SpreadSheet(OGURI_GSS_ID)
    ss.replace_all(ss.reserve_sheet, df)
    return df
