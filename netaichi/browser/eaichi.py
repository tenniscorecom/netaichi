from netaichi.browser.netaichi import NetAichi
from netaichi.config import IS_HEADLESS


class EAichi(NetAichi):
    """あいち共同利用型施設予約システム（市町村施設、e-aichi）のサイト操作。

    ネットあいちと同じベンダーのシステムで、空き状況ページの構造
    （selectInfo / chkIcd / movePage / selectCalendarDate 等）も同一のため
    NetAichi を継承し、施設名検索への導線（自治体選択）だけ差し替える。
    空き状況の確認だけならログイン不要。
    """

    BASE_URL = "https://www.e-shisetsu.e-aichi.jp/user/rsvUTransInitialScreenBackAction.do"

    def __init__(
        self, municipality: str, is_headless=IS_HEADLESS, logger_name="EAichi"
    ):
        super().__init__(is_headless, logger_name)
        self.municipality = municipality

    def _go_name_search(self) -> bool:
        """施設名検索画面を開く。

        このシステムは画面遷移トークンを検証するため、途中でURLを直接開くと
        「遷移情報に誤りがあります」エラーになる。画面内のリンクだけで遷移する。
        """
        # 画面内のサイドバー「施設名から探す」があればそれで遷移（ネットあいちと同じ）
        if not super()._go_name_search():
            # 初回はトップ画面のメニュー「施設名から」画像リンクから入る
            if not self.get_elements_by_css('img[alt="施設名から"]'):
                self.go_page(self.BASE_URL)
                try:
                    self.wait_element_load_by_css('img[alt="施設名から"]')
                except Exception:
                    self.logger.error("「施設名から」メニューが見つかりません")
                    return False
            self.js_exec('document.querySelector(\'img[alt="施設名から"]\').closest("a").click();')
        # 検索画面が直接出るか、自治体選択画面が挟まるかのどちらか
        try:
            self.wait_element_load_by_css("#textKeyword")
        except Exception:
            links = self.get_elements_by_contains_text("//a", self.municipality)
            if not links:
                self.logger.error(f"自治体が見つかりません: {self.municipality}")
                return False
            links[0].click()
        return True
