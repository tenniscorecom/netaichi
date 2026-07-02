from dataclasses import dataclass, asdict
from enum import Enum


class PAGE_STATUS(Enum):
    MYPAGE = 1
    LOTTERY = 2
    LOTTERY_LIST = 3
    RESERVATION = 4
    RESERVATION_LIST = 5


@dataclass
class LotteryStatusDetail:
    name: str
    count: int
    value: int


@dataclass
class LotteryStatus:
    count: int
    zone: int
    alltime: int
    account_id: str
    account_group: str | None = None


@dataclass(frozen=True)
class CourtValues:
    ODAKA: str = "130"
    OBATA: str = "180"
    KENKOU: str = "310"
    KENKOU_N: str = "320"
    MORIKORO: str = "400"
    MORIKORO_F: str = "410"
    KOROGI_C: str = "530"
    KOROGI: str = "540"
    KOROGI_N: str = "550"
    SINRIN: str = "660"

    @staticmethod
    def items():
        return asdict(CourtValues()).values()
