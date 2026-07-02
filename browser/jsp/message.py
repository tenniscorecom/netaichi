from dataclasses import dataclass


@dataclass
class SystemMessage:
    ERROR_BOT = (
        "不正な操作によりログイン処理に失敗しました。最初から処理をやり直してください。"
    )
    ERROR_INCORECT = "利用者番号、またはパスワードが誤っています。再度入力して下さい。"
    ERROR_EXPIRATION = "アカウントの有効期限が切れています。多機能版の上部「利用者登録」メニューの「利用者登録の有効期限並びに更新について」を参照し、有効期限の更新手続を行ってください。"


@dataclass
class ErrorMessage:
    INCORRECT = "Failed Incorrect user number or password. Please re-enter."
    RESERVATION_DATA = "There are a few discrepancies in date and court information"
    PROPERTY_MULTIPLE_TIME = "Multiple time zones. {}: {}"


@dataclass
class InfoMessage:
    LOGIN = "Success loggin of ID : {}"
    LOGIN_START = "Start login."
    LOGGED_ACCOUNT = "{} Already logged. Start Logging out."
    LOGOUT = "Success Logged out of ID : {}"

    LOTTERY_DATA_DETAILS = "{}: {} {}時～{}時まで {}面"
    PROPERTY_COURT = "Get court information. VALUE:{}"
