from dataclasses import dataclass


@dataclass
class Selecter:
    # GO
    GO_LOGIN = "#login"
    GO_MYPAGE = 'table[width="850"] td>a'  # [1]
    GO_RESERVATION = "#goNameSearch"
    GO_LOTTERY = "#goLotSerach"
    GO_LIST = ".s-241m>a"

    # LOGIN
    LOGIN_ID = 'input[name="userId"]'
    LOGIN_PW = "#passwd"
    LOGIN_ERROR_MESSAGE = "#allMessages2"

    # LIST
    LIST_NEXT = "#goNextPager"
    # RESERVE_LIST
    RESERVE_DATA_DATE = ".tablebg2 .s-243m:not(:has(div)):nth-of-type(1)"
    RESERVE_DATA_COURT = ".tablebg2 .s-243m:not(:has(div)):nth-of-type(2)"
    # LOTTERY_LIST
    LOTTERY_LIST_NEXT = "#goNextPager"
    LOTTERY_LIST_DELETE = ".s-243m > a"
    AMOUNT_RESERVE = "#lotNum"
    AMOUNT_LOTTERY = "#lotNum"

    # BTN
    BTN_LOGIN = 'input[value="ログイン"]'
    BTN_COURT = 'input[value="対象館一覧を表示"]'
    BTN_AREA = 'input[value="施設決定"]'
    BTN_APPLY = 'input[value="申込みを確定する"]'
    BTN_CECHK = 'input[value="抽選内容を確認する"]'
    BTN_CONFIRM = 'input[value="抽選を申込む"]'
    BTN_DELETE = 'input[value="取消"]'
    BTN_RESELECT_DATE = 'input[value="日時を選びなおす"]'
    BTN_ANOTHER_DATE = 'input[value="別の日時を申込む"]'
    BTN_REVERSE = 'input[value="施設を選びなおす"]'
    BTN_REVERSE2 = 'input[value="条件の選びなおし"]'
    BTN_LOGOUT = 'input[value="ログアウト"]'
    # STATUS

    STATUS_COUNT = "#allCount"  # 件数
    STATUS_ZONE = "#allTzonecnt"  # 時間帯
    STATUS_ALL = "#allTimeLabel"  # 合計時間
    # SELECT
    TIMES = "#komanamem"
    SELECT_AMOUNT = "#selectFieldCnt"
    SELECT_CHECKBOX = 'input[name="selectKomaNo"]'
    SELECT_SPORTS = "#selectPurpose"
    SELECT_PLAYERS = "#applyPepopleNum"

    drawChekcks = ".tablebg2 .s-243m"

    # LOTTERY_DATA
    LOTTERY_DATA_DATE = "#useymdLabel"
    LOTTERY_DATA_START = "#stimeLabel"
    LOTTERY_DATA_END = "#etimeLabel"
    LOTTERY_DATA_COURT = "#clsnamem"
    LOTTERY_DATA_AMOUNT = "#field"

    # LOTTERY_CHECK
    LOTTERY_CHECK_DATE = ".in-table td:has(span#targetLabel)"
    LOTTERY_CHECK_COURT = LOTTERY_DATA_COURT
    LOTTERY_CHECK_AMOUNT = SELECT_AMOUNT
    LOTTERY_CHECK_PLAYERS = "#applycnt"
