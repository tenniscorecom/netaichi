from typing import Optional
from sqlmodel import Field, Session, SQLModel, create_engine  # 追加
from datetime import datetime
from sqlmodel.pool import StaticPool


class M_Account(SQLModel, table=True):
    name: str
    id: Optional[str] = Field(default=None, primary_key=True)
    password: str
    expiration_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
    updated_at: datetime = Field(
        default_factory=datetime.now, nullable=False,
        sa_column_kwargs={'onupdate': datetime.now})
    account_group: Optional[str] = None
    is_master: bool = Field(default=False)
    is_use: bool = Field(default=True)


class M_CourtProperty(SQLModel, table=True):
    name: Optional[str] = Field(default=None, primary_key=True)
    value: Optional[str] = Field(default=None, primary_key=True)
    start: int
    end: int
    span: int = Field(default=2)
    updated_at: datetime = Field(
        default_factory=datetime.now, nullable=False,
        sa_column_kwargs={'onupdate': datetime.now})


class T_LotteryData(SQLModel, table=True):
    value: str
    date: datetime
    start: int
    end: int
    amount: int = Field(default=1)
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
    account_group: str
    id: Optional[int] = Field(default=None, primary_key=True)  # 主キー制約


class T_LotteryStatus(SQLModel, table=True):
    count: int
    zone: int
    alltime: int
    created_at: datetime = Field(
        default_factory=datetime.now, nullable=False,
        sa_column_kwargs={'onupdate': datetime.now})
    account_id: str
    account_group: str
    id: Optional[int] = Field(default=None, primary_key=True)  # 主キー制約


class T_LotteryStatusDetail(SQLModel, table=True):
    name: str
    count: int
    value: str
    status_id: Optional[int] = Field(
        foreign_key='t_lotterystatus.id')
    id: Optional[int] = Field(default=None, primary_key=True)


class T_AvailableSlot(SQLModel, table=True):
    """空き状況チェックで発見済みの空き枠（通知の重複防止用）"""
    value: str
    date: datetime
    start: int
    end: int
    first_seen: datetime = Field(default_factory=datetime.now, nullable=False)
    id: Optional[int] = Field(default=None, primary_key=True)


class SessionFactory:

    @classmethod
    def sqlite(self, name, echo=True):
        this = SessionFactory()
        this.engine = create_engine(
            f'sqlite:///{name}.sqlite',
            echo=echo,
            connect_args={"check_same_thread": False, },
        )
        return this

    @classmethod
    def sqlite_memory(self, echo=True):
        this = SessionFactory()
        this.engine = create_engine(
            "sqlite://",
            echo=echo,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,  # in-memoryの使用
        )
        return this

    def create_tables(self):
        SQLModel.metadata.create_all(self.engine)

    def drop_tables(self):
        SQLModel.metadata.drop_all(self.engine)

    def drop_table(self, table: SQLModel):
        table.__table__.drop(self.engine)

    def get(self) -> Session:
        return Session(self.engine)
