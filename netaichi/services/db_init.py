from netaichi.helper import SpreadSheet
from netaichi.config import OGURI_GSS_ID, KOMADA_GSS_ID, KOMADA_ACCOUNT_ID, OGURI_ACCOUNT_ID, IS_HEADLESS


def db_init():
    from netaichi.db import NetaichiDatabase
    db = NetaichiDatabase()
    account(db)


def account(db):
    db.drop_tables()
    db.create_tables()
    komada_ss = SpreadSheet(KOMADA_GSS_ID)
    komada_accounts = komada_ss.get_use_accounts(KOMADA_ACCOUNT_ID)
    oguri_ss = SpreadSheet(OGURI_GSS_ID)
    oguri_accounts = oguri_ss.get_use_accounts(OGURI_ACCOUNT_ID)
    with db.session() as session:
        session.add_all(komada_accounts)
        session.add_all(oguri_accounts)
        session.commit()
