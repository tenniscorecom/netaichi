"""アプリ設定。認証情報・IDは .env から読み込む。"""
import os
from pathlib import Path

from anti_useragent import UserAgent
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]

load_dotenv(ROOT_DIR / '.env')

# ネットあいち アカウント
default_pw = os.environ['NETAICHI_DEFAULT_PW']
OGURI_ACCOUNT_ID = os.environ['OGURI_ACCOUNT_ID']
KOMADA_ACCOUNT_ID = os.environ['KOMADA_ACCOUNT_ID']

# Google スプレッドシート
OGURI_GSS_ID = os.environ['OGURI_GSS_ID']
KOMADA_GSS_ID = os.environ['KOMADA_GSS_ID']
GSS_KEYFILE = ROOT_DIR / 'config' / 'json' / 'authorized_user.json'

# Discord 通知
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL', '')

IS_HEADLESS = False
DB_PATH = str(ROOT_DIR / 'netaichi2024')
LOGS_DIR = ROOT_DIR / 'logs'
RULES_DIR = ROOT_DIR / 'rules'

# ChromeDriver 起動オプション
OPTIONS = (
    # 拡張機能の更新、セーフブラウジングサービス、アップグレード検出、翻訳、UMAを含む様々なバックグラウンドネットワークサービスを無効にする。
    "--disable-background-networking",
    # navigator.webdriver=false となる設定。確認⇒　driver.execute_script("return navigator.webdriver
    "--disable-blink-features=AutomationControlled",
    # デフォルトアプリのインストールを無効にする。
    "--disable-default-apps",
    # ディスクのメモリスペースを使う。DockerやGcloudのメモリ対策でよく使われる。
    "--disable-dev-shm-usage",
    # 拡張機能をすべて無効にする。
    "--disable-extensions",
    # ダウンロードが完了したときの通知を吹き出しから下部表示(従来の挙動)にする。
    "--disable-features=DownloadBubble",
    # `--incognito`を使うとき、ダイアログ(名前を付けて保存)を非表示にする。
    '--disable-features=DownloadBubbleV2',
    # Chromeの翻訳を無効にする。右クリック・アドレスバーから翻訳の項目が消える。
    "--disable-features=Translate",
    # ポップアップブロックを無効にする。
    "--disable-popup-blocking",
    # スクロールバーを隠す。
    "--hide-scrollbars",
    # SSL認証(この接続ではプライバシーが保護されません)を無効
    "--ignore-certificate-errors",
    # シークレットモードで起動する。
    "--incognito",
    # すべてのオーディオをミュートする。
    "--mute-audio",
    # アドレスバー下に表示される「既定のブラウザとして設定」を無効にする。
    "--no-default-browser-check",
    # Chromeに表示される青いヒント(？)を非表示にする。
    "--propagate-iph-for-testing",
    # アドレスバー下に表示される「Chrome for Testing~~」を非表示にする。
    "--test-type=gpu",
    # ユーザーエージェントの指定。
    "--user-agent=" + str(UserAgent("windows.chrome")),
    # ウィンドウの初期位置を指定する。--start-maximizedとは併用不可
    "--window-position=100,100",
    # ウィンドウの初期サイズを設定する。--start-maximizedとは併用不可
    "--window-size=1600,1024",
    # SSL認証無効
    '--ignore-ssl-errors',
)
