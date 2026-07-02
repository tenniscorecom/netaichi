
from database import T_LotteryData
from browser import NetAichi
from datetime import date
netaichi = NetAichi()


def format_lottery_dict(value: str, date: date, start: int, end: int, amount: int, master_id: str):
    return {
        'value': value,
        'date': date,
        'start': start,
        'end': end,
        'amount': amount,
        'account_group': master_id
    }


def add_weekend_lottery_data(date: date, master_id: str) -> dict[str, T_LotteryData]:
    weekend_lottery_data = []
    for

    return weekend_lottery_data


def add_night_lottery_data(date: date, master_id: str) -> dict[str, T_LotteryData]:
    night_lottery_data = []

    d = {
        'value': value,
        'date': date,
        'start': start,
        'end': end,
        'amount': amount,
        'account_group': master_id
    }
    T_LotteryData(
        value=value,
        date=date,
        start=9,
        end=13,
        amount=amount,
        account_group=master_id
    )

    return {master_id: night_lottery_data}


def add_lottery_data():

    for date in netaichi.next_date():
        data = add_weekend_lottery_data(date) | add_night_lottery_data(date)

        for d in data:


def main():
    '''
    駒田と自分のアカウントに絶対抽選するものを追加する
    駒田: 大高緑地(130) 9-13,13-17
    自分: 大高緑地(130) 9-13,13-17 1面
         小幡緑地(180) 9-13,13-17 2面
         健康の森(310,320) 9-17 3面
         モリコロ(400,410) 9-13,13-17,平日19-21 1面
         口論義(530,540) 9-13,13-17 1面
         口論義ナイター(550), 9-13,13-17 平日19-21 1面

    '''
    pass
    add_datas = [
        {'value': 130, 'start': 9, 'end': 13}
    ]


if __name__ == '__main__':
    main()
