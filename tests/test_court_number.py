"""予約一覧のコート名から面の識別子を取り出すロジックのテスト

表記は実際の予約一覧から採取したもの。
"""
from netaichi.browser.pages.get import court_number_of
from netaichi.helper import court_label


class TestCourtNumberOf:
    def test_tennis_court_returns_number(self):
        assert court_number_of("庭球場6(人工芝)") == "6"

    def test_two_digit_tennis_court(self):
        assert court_number_of("庭球場12(ハード)") == "12"

    def test_futsal_court_keeps_its_name(self):
        """フットサル場は番号が振られていないので名前ごと識別子にする"""
        assert court_number_of("フットサル場B") == "フットサル場B"

    def test_court_without_parentheses_keeps_last_character(self):
        """カッコが無いと末尾が欠けていた（第2コート16 → 第2コート1）"""
        assert court_number_of("第2コート16") == "第2コート16"

    def test_full_width_number(self):
        """全角数字も数字として扱う（実データはNFKD後なので通常は半角）"""
        assert court_number_of("庭球場１(人工芝)") == "１"


class TestCourtLabel:
    def test_number_gets_prefix(self):
        assert court_label("6") == "庭球場6"

    def test_name_is_used_as_is(self):
        assert court_label("フットサル場B") == "フットサル場B"

    def test_forest_court(self):
        assert court_label("第2コート16") == "第2コート16"
