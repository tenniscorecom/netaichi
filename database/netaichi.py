from config.netaichi import DB_PATH
from .models import SessionFactory
from sqlmodel import SQLModel


class NetaichiDatabase:
    ECHO = None

    def __init__(self, echo=True):
        self.ECHO = echo
        self.sqlite = SessionFactory.sqlite(DB_PATH, self.ECHO)

    def memory_sqlite(self):
        self.sqlite = SessionFactory.sqlite_memory(self.ECHO)
        return self

    def session(self):
        return self.sqlite.get()

    def create_tables(self):
        self.sqlite.create_tables()

    def drop_tables(self):
        self.sqlite.drop_tables()

    def drop_table(self, table: SQLModel):
        self.sqlite.drop_table(table)
