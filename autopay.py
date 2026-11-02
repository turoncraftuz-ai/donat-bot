"""Avtomatik to'lov aniqlash.

Bank (masalan Humo) "pul tushdi" xabarini yuboradigan Telegram botni sizning akkauntingiz orqali
o'qiydi (Telethon), summani topadi va mos to'lov so'rovini o'zi tasdiqlab, balansni to'ldiradi.
Faqat PAYMENT_BOT chatidagi kiruvchi xabarlar o'qiladi, boshqa chatlarga tegilmaydi.
"""
import html
import logging
import re

import config

log = logging.getLogger("autopay")

AMOUNT_RE = re.compile(
    r"([0-9][0-9\s\u00a0\u202f.,]*)\s*(?:UZS|uzs|so['’ʻ`]?m|сум|сўм|sum)", re.IGNORECASE)


def _normalize(raw: str):
    s = re.sub(r"[\s\u00a0\u202f]", "", raw).strip(".,")
    if re.search(r"[.,]\d{2}$", s):       # 10000.00 -> 10000
        s = s[:-3]
    s = re.sub(r"[.,]", "", s)
    return int(s) if s.isdigit() else None


def parse_amount(text: str, regex: str = ""):
    pattern = re.compile(regex) if regex else AMOUNT_RE
    m = pattern.search(text or "")
    return _normalize(m.group(1)) if m else None


def is_incoming(text: str) -> bool:
    low = (text or "").lower()
    if any(w in low for w in config.PAY_OUT_MARKERS):
        return False
    return any(w in low for w in config.PAY_IN_MARKERS)


async def _notify_admins(bot, text: str):
    for aid in config.ADMIN_IDS:
        try:
            await bot.send_message(aid, text)
        except Exception as e:
            log.warning("Adminga yuborilmadi (%s): %s", aid, e)


async def process_message(db, bot, chat_id: int, msg_id: int, text: str):
    text = text or ""
    if config.PAY_CARD_LAST4 and config.PAY_CARD_LAST4 not in text:
        return
    amount = parse_amount(text, config.PAY_AMOUNT_REGEX)
    if not await db.register_payment(chat_id, msg_id, amount or 0):
        return  # bu xabar allaqachon qayta ishlangan
    snippet = html.escape(text[:600])
    if config.PAY_DEBUG:
        await _notify_admins(bot, f"🛠 <b>Bank xabari (debug)</b>\n<pre>{snippet}</pre>\nO'qilgan summa: <b>{amount}</b>")
    if not is_incoming(text):
        return
    if amount is None:
        await _notify_admins(bot, f"⚠️ Kirim xabari topildi, lekin summani o'qib bo'lmadi:\n<pre>{snippet}</pre>")
        return
    row = await db.auto_approve(amount, config.AUTOPAY_GRACE_MIN)
    if row is None:
        await _notify_admins(
            bot,
            f"❓ <b>Noma'lum to'lov:</b> +{amount:,} so'm".replace(",", " ") +
            f"\nMos to'lov so'rovi topilmadi. Kerak bo'lsa qo'lda: <code>/qosh ID SUMMA</code>\n<pre>{snippet}</pre>")
        return
    user = await db.get_user(row["user_id"])
    credited = f"{row['amount']:,}".replace(",", " ")
    balance = f"{user['balance']:,}".replace(",", " ")
    try:
        await bot.send_message(
            row["user_id"],
            f"✅ <b>To'lov avtomatik tasdiqlandi!</b>\n\n+{credited} so'm\n💰 Balansingiz: <b>{balance} so'm</b>")
    except Exception as e:
        log.warning("Foydalanuvchiga yuborilmadi: %s", e)
    await _notify_admins(
        bot,
        f"✅ <b>Avto-to'lov #{row['id']}</b>\n{html.escape(user['full_name'] or '')} (<code>{user['user_id']}</code>)\n"
        f"Keldi: {amount:,} so'm → balansga: {credited} so'm".replace(",", " "))


async def start(bot, db):
    """Telethon klientni ishga tushiradi. Qaytaradi: client (to'xtatish uchun)."""
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(config.TG_SESSION), config.TG_API_ID, config.TG_API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("TG_SESSION yaroqsiz yoki eskirgan. gen_session.py ni qaytadan ishlating.")

    @client.on(events.NewMessage(chats=config.PAYMENT_BOT, incoming=True))
    async def _handler(event):
        try:
            await process_message(db, bot, event.chat_id, event.id, event.raw_text or "")
        except Exception:
            log.exception("Bank xabarini qayta ishlashda xato")

    log.info("Avto-to'lov yoqildi: @%s kuzatilyapti", config.PAYMENT_BOT)
    return client
