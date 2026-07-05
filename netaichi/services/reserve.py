from netaichi.browser import EAichi, NetAichi
from netaichi.config import (
    EAICHI_ACCOUNT_ID,
    EAICHI_PW,
    IS_HEADLESS,
    OGURI_ACCOUNT_ID,
    OGURI_GSS_ID,
)
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


def collect_eaichi_reservations() -> pd.DataFrame:
    """eあいち（日進市）アカウントの予約情報を収集する（アカウント未設定なら空）

    columns: collect_reservations と同じ
    """
    if not EAICHI_ACCOUNT_ID:
        return pd.DataFrame()
    with EAichi("日進市", IS_HEADLESS) as ea:
        if not ea.login(id=EAICHI_ACCOUNT_ID, password=EAICHI_PW):
            return pd.DataFrame()
        return ea.get.reservation()


def reserve():
    df = collect_reservations()
    ss = SpreadSheet(OGURI_GSS_ID)
    ss.replace_all(ss.reserve_sheet, df)
    return df
