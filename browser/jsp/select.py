from .selector import Selector
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Jsp


class JspSelect:
    def __init__(self, jsp) -> None:
        self.jsp: Jsp = jsp

    def court(self, value: str):
        self.jsp.select_radio_by_value(value)
        r = self.jsp.click(Selector.BTN_COURT)
        if r is False:
            return False
        # 施設によって細分化されてる場合はここから分岐
        r = self.jsp.click(Selector.BTN_AREA)
        if r is False:
            return False

    def time(self, start, end, span=2):
        times = self.jsp.get.times()

        start_i = times.index(start)
        end_i = times.index(end - span)
        checks = [i for i in range(start_i, end_i + 1)]
        check_boxs = self.jsp.get_elements_by_css(Selector.SELECT_CHECKBOX)
        selected_boxs = [c.is_selected() for c in check_boxs]
        is_enabled = [c.is_enabled() for c in check_boxs]

        if any(is_enabled) is False:
            return False
        if any(selected_boxs):
            for i in range(len(selected_boxs)):
                if selected_boxs[i]:
                    check_boxs[i].click()

        for c in checks:
            if is_enabled[c]:
                check_box = check_boxs[c]
                check_box.click()
            else:
                print(f"checks {checks}")
                print(f"is_enabled[c] {is_enabled[c]}")
                return False
        return True

    def date(self, date):
        self.jsp.js_exec(
            f"javascript:selectCalendarDate({date.year},{date.month},{date.day})"
        )

    def amount(self, amount):
        self.jsp.select_pulldown(Selector.SELECT_AMOUNT, amount)

    def sports(self):
        self.jsp.select_by_value(
            self.jsp.get_element_by_css(Selector.SELECT_SPORTS), "1000-10000010"
        )

    def players(self, num):
        self.jsp.send_form(Selector.SELECT_PLAYERS, num)
