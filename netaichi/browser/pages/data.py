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


# 表示用コート名（value → 名前）
COURT_NAMES = {
    "130": "大高緑地",
    "180": "小幡緑地",
    "310": "健康の森",
    "320": "健康の森(ナイター)",
    "400": "モリコロパーク",
    "410": "モリコロパーク(410)",
    "530": "口論義(センター)",
    "540": "口論義",
    "550": "口論義(ナイター)",
    "660": "森林公園",
}
