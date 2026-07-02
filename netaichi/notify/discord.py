"""Discord Webhook 通知"""
import requests

from netaichi.config import DISCORD_WEBHOOK_URL


def notify(message: str) -> None:
    if not DISCORD_WEBHOOK_URL:
        raise RuntimeError("DISCORD_WEBHOOK_URL が .env に設定されていません")
    res = requests.post(
        DISCORD_WEBHOOK_URL, json={"content": message}, timeout=10
    )
    res.raise_for_status()
