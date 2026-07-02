from database import NetaichiDatabase, M_Account
from sqlmodel import select
from config import KOMADA_ACCOUNT_ID, OGURI_ACCOUNT_ID, KOMADA_GSS_ID, OGURI_GSS_ID
from helper import SpreadSheet, Headers


def main():

    update_accounts()


def update_loop(gss_id: str, master_id: str):
    db = NetaichiDatabase()
    ss = SpreadSheet(gss_id)
    ss_accounts = ss.get_all_accounts(master_id)
    with db.session() as session:
        db_accounts = session.exec(
            select(M_Account).where(
                M_Account.id == master_id)).all()
        for db_account in db_accounts:
            for ss_account in ss_accounts:
                if db_account.id != ss_account.id:
                    continue
                if ss_account[Headers.GROUP] != master_id:
                    db_account.is_use = False
                db_account.is_use = True if ss_account[Headers.GROUP] == master_id else False
                session.add(db_account)
        session.commit()


def update_accounts():
    ss_komada_accounts =
    with db.session() as session:
        db_komada_accounts = session.exec(select(M_Account).where(
            M_Account.id == OGURI_ACCOUNT_ID, M_Account.id))

    for db_account in db_komada_accounts:
        for ss_account in ss_komada_accounts:
            if db_account.id != ss_account.id:
                continue
            db_account


if __name__ == '__main__':
    main()
