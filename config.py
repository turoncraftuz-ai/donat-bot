"""Barcha sozlamalar Railway Variables orqali o'qiladi."""
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
SHOP_NAME = os.getenv("SHOP_NAME", "TuronCraft")

# Vergul bilan ajratilgan Telegram ID lar: 7261358287,123456789
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()}

CARD_NUMBER = os.getenv("CARD_NUMBER", "").replace(" ", "")
CARD_HOLDER = os.getenv("CARD_HOLDER", "")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "").lstrip("@")

# Railway Volume'ni /data ga ulang, aks holda har deployda baza o'chib ketadi.
DB_PATH = os.getenv("DB_PATH", "/data/bot.db")

TOPUP_MIN = _int("TOPUP_MIN", 1000)
TOPUP_MAX = _int("TOPUP_MAX", 5_000_000)
TOPUP_TTL_MIN = _int("TOPUP_TTL_MIN", 30)

# Serverga yuboriladigan buyruqlar ({nick}, {group}, {amount} almashtiriladi)
RANK_COMMAND = os.getenv("RANK_COMMAND", "lp user {nick} parent add {group}")
TOKEN_COMMAND = os.getenv("TOKEN_COMMAND", "points give {nick} {amount}")

# RCON: har bir server uchun alohida (prefiks katalogda ko'rsatilgan)
def rcon_settings(prefix: str) -> dict:
    return {
        "host": os.getenv(f"{prefix}_RCON_HOST", ""),
        "port": _int(f"{prefix}_RCON_PORT", 25575),
        "password": os.getenv(f"{prefix}_RCON_PASSWORD", ""),
    }
