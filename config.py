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


# ---------------------------------------------------------------- Avto-to'lov (Telethon)
def _int0(name: str) -> int:
    try:
        return int(os.getenv(name, "0"))
    except ValueError:
        return 0


TG_API_ID = _int0("TG_API_ID")
TG_API_HASH = os.getenv("TG_API_HASH", "").strip()
TG_SESSION = os.getenv("TG_SESSION", "").strip()          # gen_session.py chiqargan satr
PAYMENT_BOT = os.getenv("PAYMENT_BOT", "HUMOcardbot").lstrip("@").strip()
AUTOPAY_ENABLED = bool(TG_API_ID and TG_API_HASH and TG_SESSION)

# Kirim/chiqim xabarini ajratish (vergul bilan, kichik harfda solishtiriladi)
PAY_IN_MARKERS = [x.strip().lower() for x in os.getenv(
    "PAY_IN_MARKERS", "➕,пополнение,popolnenie,to'ldirish,kirim,tushdi,поступление,received").split(",") if x.strip()]
PAY_OUT_MARKERS = [x.strip().lower() for x in os.getenv(
    "PAY_OUT_MARKERS", "➖,списание,chiqim,xarajat").split(",") if x.strip()]
PAY_AMOUNT_REGEX = os.getenv("PAY_AMOUNT_REGEX", "").strip()  # ixtiyoriy: 1-guruh = summa
PAY_CARD_LAST4 = os.getenv("PAY_CARD_LAST4", "").strip()      # ixtiyoriy: faqat shu karta xabarlari
PAY_DEBUG = os.getenv("PAY_DEBUG", "0") == "1"                # 1 bo'lsa, bank botidan kelgan hamma xabar adminga ham yuboriladi
AUTOPAY_GRACE_MIN = _int("AUTOPAY_GRACE_MIN", 15)             # muddat tugagach ham necha daqiqa kutiladi
TOPUP_OFFSET_MAX = _int("TOPUP_OFFSET_MAX", 99) if AUTOPAY_ENABLED else 0  # avto-to'lov o'chiq bo'lsa summa o'zgarmaydi               # summaga qo'shiladigan noyob so'm (1..99)
