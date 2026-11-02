import asyncio
import html
import logging
import re
import time

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (CallbackQuery, InlineKeyboardMarkup, KeyboardButton, Message,
                           ReplyKeyboardMarkup)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from catalog import CATEGORIES, SERVERS, get_item
from db import DB
from rcon import RconError, rcon_command

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("shop")

router = Router()
db: DB = None  # main() da yaratiladi
bot: Bot = None

BTN_BALANCE = "💰 Balansni ko'rish"
BTN_TOPUP = "➕ Balans to'ldirish"
BTN_BUY = "🛍 Sotib olish"
BTN_ORDERS = "📦 Xaridlarim"
BTN_HELP = "ℹ️ Yordam"
MENU_TEXTS = {BTN_BALANCE, BTN_TOPUP, BTN_BUY, BTN_ORDERS, BTN_HELP}

AMOUNTS = [5000, 10000, 25000, 50000, 100000, 200000]
NICK_RE = re.compile(r"^[A-Za-z0-9_.]{3,16}$")
FAIL_WORDS = ("unknown command", "could not be found", "unable to find", "not found", "no player",
              "no user", "usage:", "error", "does not exist", "doesn't exist", "cannot find",
              "can't find", "invalid", "unknown or incomplete")


class TopUp(StatesGroup):
    amount = State()
    proof = State()


class Buy(StatesGroup):
    nick = State()


# ---------------------------------------------------------------- yordamchilar
def esc(s) -> str:
    return html.escape(str(s or ""))


def money(n: int) -> str:
    return f"{int(n):,}".replace(",", " ") + " so'm"


def card_fmt() -> str:
    c = config.CARD_NUMBER
    return " ".join(c[i:i + 4] for i in range(0, len(c), 4))


def is_admin(uid: int) -> bool:
    return uid in config.ADMIN_IDS


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_BALANCE), KeyboardButton(text=BTN_TOPUP)],
            [KeyboardButton(text=BTN_BUY), KeyboardButton(text=BTN_ORDERS)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
    )


async def render(target, text: str, kb: InlineKeyboardMarkup = None):
    """CallbackQuery bo'lsa xabarni tahrirlaydi, Message bo'lsa yangi xabar yuboradi."""
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            pass
    else:
        await target.answer(text, reply_markup=kb)


async def notify_admins(text: str, kb: InlineKeyboardMarkup = None):
    for aid in config.ADMIN_IDS:
        try:
            await bot.send_message(aid, text, reply_markup=kb)
        except Exception as e:
            log.warning("Adminga yuborib bo'lmadi (%s): %s", aid, e)


# ---------------------------------------------------------------- yetkazib berish
def build_command(purchase) -> str:
    item = get_item(purchase["server"], purchase["category"], purchase["item_key"])
    if item is None:
        raise RconError("Katalogda mahsulot topilmadi")
    tpl = config.RANK_COMMAND if item.kind == "rank" else config.TOKEN_COMMAND
    return tpl.format(nick=purchase["nick"], group=item.value, amount=item.value)


async def deliver(purchase) -> tuple:
    """(muvaffaqiyatli_mi, server_javobi/xato) qaytaradi."""
    try:
        cmd = build_command(purchase)
        prefix = SERVERS[purchase["server"]]["rcon_prefix"]
        s = config.rcon_settings(prefix)
        resp = await rcon_command(s["host"], s["port"], s["password"], cmd)
    except RconError as e:
        return False, str(e)
    except Exception as e:  # kutilmagan xato
        log.exception("deliver xatosi")
        return False, f"Kutilmagan xato: {e}"
    low = resp.lower()
    if any(w in low for w in FAIL_WORDS):
        return False, f"Server javobi: {resp[:300]}"
    return True, resp


def admin_fail_kb(pid: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔁 Qayta yuborish", callback_data=f"pf:retry:{pid}")
    b.button(text="💰 Pulni qaytarish", callback_data=f"pf:refund:{pid}")
    b.adjust(1)
    return b.as_markup()


# ---------------------------------------------------------------- /start va menyu
@router.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    u = await db.upsert_user(m.from_user.id, m.from_user.username, m.from_user.full_name)
    await m.answer(
        f"👋 Salom, <b>{esc(m.from_user.first_name)}</b>!\n"
        f"Assalomu alaykum <b>{esc(config.SHOP_NAME)}</b> donat do'koniga xush kelibsiz.\n\n"
        f"💰 Balansingiz: <b>{money(u['balance'])}</b>\n\n"
        f"Kerakli bo'limni tanlang 👇",
        reply_markup=main_kb(),
    )


@router.message(F.text == BTN_BALANCE)
async def show_balance(m: Message, state: FSMContext):
    await state.clear()
    u = await db.upsert_user(m.from_user.id, m.from_user.username, m.from_user.full_name)
    b = InlineKeyboardBuilder()
    b.button(text="➕ Balans to'ldirish", callback_data="topup")
    b.button(text="📜 To'lovlar tarixi", callback_data="tophist")
    b.adjust(2)
    await m.answer(
        f"👤 <b>{esc(m.from_user.full_name)}</b>\n\n"
        f"💰 Balans: <b>{money(u['balance'])}</b>\n"
        f"🆔 Hisob raqamingiz: <code>{u['user_id']}</code>\n"
        f"🎮 Nik: <b>{esc(u['nick']) if u['nick'] else 'kiritilmagan'}</b>",
        reply_markup=b.as_markup(),
    )


@router.message(F.text == BTN_HELP)
async def show_help(m: Message, state: FSMContext):
    await state.clear()
    sup = f"@{esc(config.SUPPORT_USERNAME)}" if config.SUPPORT_USERNAME else "adminga yozing"
    await m.answer(
        "📖 <b>Qo'llanma</b>\n\n"
        "💰 <b>Balansni to'ldirish</b>\n"
        "«Balans to'ldirish» → summa → kartaga o'tkazma → chek (skrinshot) yuborish. "
        "Admin tasdiqlagach, pul balansingizga tushadi.\n\n"
        "🛍 <b>Qanday sotib olinadi?</b>\n"
        "«Sotib olish» → server → kategoriya → mahsulot. Mahsulot o'yindagi nikingizga avtomatik beriladi.\n\n"
        "⚠️ Nik serverga kamida bir marta kirgan bo'lishi va aniq yozilishi kerak (katta-kichik harf muhim).\n\n"
        f"❓ Savollar uchun: {sup}",
    )


@router.message(F.text == BTN_ORDERS)
async def show_orders(m: Message, state: FSMContext):
    await state.clear()
    rows = await db.list_purchases(m.from_user.id, 10)
    if not rows:
        await m.answer("📦 Hali xarid qilmagansiz.")
        return
    icons = {"delivered": "✅", "processing": "⏳", "failed": "⚠️ admin hal qiladi", "refunded": "↩️ qaytarilgan"}
    lines = []
    for r in rows:
        srv = SERVERS.get(r["server"], {}).get("title", r["server"])
        lines.append(f"<b>#{r['id']}</b> {srv} — {esc(r['title'])} — {money(r['price'])} {icons.get(r['status'], '')}")
    await m.answer("📦 <b>So'nggi xaridlaringiz</b>\n\n" + "\n".join(lines))


# ---------------------------------------------------------------- balans to'ldirish
async def show_topup_menu(target, state: FSMContext):
    await state.set_state(TopUp.amount)
    b = InlineKeyboardBuilder()
    for a in AMOUNTS:
        b.button(text=f"{a:,}".replace(",", " "), callback_data=f"ta:{a}")
    b.adjust(3)
    await render(
        target,
        "⚡ <b>Balans to'ldirish</b>\n\n"
        "Summani yozing yoki tugmalardan tanlang.\n"
        f"Eng kam: <b>{money(config.TOPUP_MIN)}</b>\n"
        "Masalan: <code>15000</code>",
        b.as_markup(),
    )


@router.message(F.text == BTN_TOPUP)
async def msg_topup(m: Message, state: FSMContext):
    await db.upsert_user(m.from_user.id, m.from_user.username, m.from_user.full_name)
    await show_topup_menu(m, state)


@router.callback_query(F.data == "topup")
async def cb_topup(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await db.upsert_user(c.from_user.id, c.from_user.username, c.from_user.full_name)
    await show_topup_menu(c, state)


async def create_topup_request(target, user_id: int, amount: int, state: FSMContext):
    if amount < config.TOPUP_MIN or amount > config.TOPUP_MAX:
        text = f"❌ Summa {money(config.TOPUP_MIN)} dan {money(config.TOPUP_MAX)} gacha bo'lishi kerak."
        await render(target, text)
        return
    tid = await db.create_topup(user_id, amount, config.TOPUP_TTL_MIN)
    await state.set_state(TopUp.proof)
    await state.update_data(topup_id=tid)
    b = InlineKeyboardBuilder()
    b.button(text="❌ Bekor qilish", callback_data=f"tc:{tid}")
    msg = (
        "⚡ <b>To'lov yaratildi!</b>\n\n"
        f"💳 Karta: <code>{card_fmt()}</code>\n"
        f"👤 Karta egasi: <b>{esc(config.CARD_HOLDER)}</b>\n"
        f"💰 O'tkazma summasi: <b>{money(amount)}</b>\n\n"
        "❗ Aynan shu summani o'tkazing.\n"
        "📸 To'lovdan so'ng <b>chekni (skrinshotni)</b> shu chatga yuboring.\n\n"
        f"⏳ Muddat: {config.TOPUP_TTL_MIN} daqiqa"
    )
    if isinstance(target, CallbackQuery):
        await target.message.answer(msg, reply_markup=b.as_markup())
    else:
        await target.answer(msg, reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("ta:"))
async def cb_amount(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await create_topup_request(c, c.from_user.id, int(c.data.split(":")[1]), state)


@router.message(TopUp.amount, F.text)
async def typed_amount(m: Message, state: FSMContext):
    digits = re.sub(r"[\s,._]", "", m.text)
    if not digits.isdigit():
        await m.answer("❌ Iltimos, summani raqam bilan yozing. Masalan: <code>15000</code>")
        return
    await create_topup_request(m, m.from_user.id, int(digits), state)


@router.callback_query(F.data.startswith("tc:"))
async def cb_cancel_topup(c: CallbackQuery, state: FSMContext):
    ok = await db.cancel_topup(int(c.data.split(":")[1]), c.from_user.id)
    await state.clear()
    await c.answer("Bekor qilindi" if ok else "Bu to'lovni bekor qilib bo'lmaydi", show_alert=not ok)
    if ok:
        try:
            await c.message.edit_text("❌ To'lov bekor qilindi.")
        except TelegramBadRequest:
            pass


@router.message(TopUp.proof, F.photo | F.document)
async def got_proof(m: Message, state: FSMContext):
    data = await state.get_data()
    tid = data.get("topup_id")
    if m.photo:
        file_id, is_photo = m.photo[-1].file_id, True
    else:
        file_id, is_photo = m.document.file_id, False
    if not tid or not await db.submit_proof(tid, m.from_user.id, file_id):
        await state.clear()
        await m.answer("⌛ Bu to'lovning muddati tugagan yoki bekor qilingan. Qaytadan «Balans to'ldirish» ni bosing.")
        return
    topup = await db.get_topup(tid)
    await state.clear()
    await m.answer("✅ Chek qabul qilindi. Admin tekshirib, balansingizni to'ldiradi (odatda bir necha daqiqa).")

    uname = f"@{esc(m.from_user.username)}" if m.from_user.username else "—"
    caption = (
        f"💳 <b>Yangi to'lov #{tid}</b>\n\n"
        f"👤 {esc(m.from_user.full_name)} ({uname})\n"
        f"🆔 <code>{m.from_user.id}</code>\n"
        f"💰 Summa: <b>{money(topup['amount'])}</b>"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Pul tushdi", callback_data=f"tp:ok:{tid}")
    kb.button(text="❌ Rad etish", callback_data=f"tp:no:{tid}")
    kb.adjust(2)
    for aid in config.ADMIN_IDS:
        try:
            if is_photo:
                await bot.send_photo(aid, file_id, caption=caption, reply_markup=kb.as_markup())
            else:
                await bot.send_document(aid, file_id, caption=caption, reply_markup=kb.as_markup())
        except Exception as e:
            log.warning("Adminga chek yuborib bo'lmadi (%s): %s", aid, e)


@router.message(TopUp.proof)
async def proof_wrong(m: Message):
    await m.answer("📸 Iltimos, to'lov chekini rasm (skrinshot) sifatida yuboring yoki «Bekor qilish» ni bosing.")


@router.callback_query(F.data.startswith("tp:"))
async def cb_admin_topup(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("Ruxsat yo'q", show_alert=True)
        return
    _, action, tid = c.data.split(":")
    approve = action == "ok"
    row = await db.decide_topup(int(tid), c.from_user.id, approve)
    if row is None:
        await c.answer("Bu to'lov allaqachon ko'rib chiqilgan", show_alert=True)
        try:
            await c.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
        return
    await c.answer("Bajarildi")
    verdict = "✅ QABUL QILINDI" if approve else "❌ RAD ETILDI"
    try:
        await c.message.edit_caption(
            caption=f"{c.message.caption or ''}\n\n<b>{verdict}</b> — {esc(c.from_user.full_name)}",
            reply_markup=None,
        )
    except TelegramBadRequest:
        pass
    try:
        if approve:
            u = await db.get_user(row["user_id"])
            await bot.send_message(
                row["user_id"],
                f"✅ <b>To'lov tasdiqlandi!</b>\n\n+{money(row['amount'])}\n💰 Balansingiz: <b>{money(u['balance'])}</b>",
            )
        else:
            sup = f" @{esc(config.SUPPORT_USERNAME)}" if config.SUPPORT_USERNAME else ""
            await bot.send_message(
                row["user_id"],
                f"❌ <b>To'lov #{row['id']} rad etildi.</b>\nMuammo bo'lsa admin bilan bog'laning.{sup}",
            )
    except Exception as e:
        log.warning("Foydalanuvchiga xabar yuborilmadi: %s", e)


@router.callback_query(F.data == "tophist")
async def cb_topup_history(c: CallbackQuery):
    await c.answer()
    rows = await db.list_topups(c.from_user.id, 10)
    if not rows:
        await c.message.answer("📜 To'lovlar tarixi bo'sh.")
        return
    icons = {"approved": "✅", "rejected": "❌", "review": "⏳"}
    lines = [f"<b>#{r['id']}</b> {money(r['amount'])} {icons.get(r['status'], '')}" for r in rows]
    await c.message.answer("📜 <b>So'nggi to'lovlar</b>\n\n" + "\n".join(lines))


# ---------------------------------------------------------------- sotib olish
async def show_servers(target):
    b = InlineKeyboardBuilder()
    for key, s in SERVERS.items():
        b.button(text=s["title"], callback_data=f"srv:{key}")
    b.adjust(1)
    await render(target, "🌍 <b>Serverni tanlang:</b>", b.as_markup())


@router.message(F.text == BTN_BUY)
async def msg_buy(m: Message, state: FSMContext):
    await state.clear()
    await db.upsert_user(m.from_user.id, m.from_user.username, m.from_user.full_name)
    await show_servers(m)


@router.callback_query(F.data == "buy")
async def cb_buy(c: CallbackQuery):
    await c.answer()
    await show_servers(c)


@router.callback_query(F.data.startswith("srv:"))
async def cb_server(c: CallbackQuery):
    await c.answer()
    s = c.data.split(":")[1]
    if s not in SERVERS:
        return
    u = await db.upsert_user(c.from_user.id, c.from_user.username, c.from_user.full_name)
    b = InlineKeyboardBuilder()
    for ck, title in CATEGORIES.items():
        b.button(text=title, callback_data=f"cat:{s}:{ck}")
    b.button(text="⬅️ Orqaga", callback_data="buy")
    b.adjust(2, 1)
    await render(c, f"📂 <b>Kategoriyani tanlang</b>\n🌍 {SERVERS[s]['title']}\n💰 Balansingiz: <b>{money(u['balance'])}</b>", b.as_markup())


@router.callback_query(F.data.startswith("cat:"))
async def cb_category(c: CallbackQuery):
    await c.answer()
    _, s, cat = c.data.split(":")
    items = SERVERS.get(s, {}).get(cat)
    if not items:
        return
    b = InlineKeyboardBuilder()
    for it in items:
        b.button(text=f"{it.title} — {money(it.price)}", callback_data=f"it:{s}:{cat}:{it.key}")
    b.button(text="⬅️ Orqaga", callback_data=f"srv:{s}")
    b.adjust(1)
    await render(c, f"{CATEGORIES[cat]} — {SERVERS[s]['title']}\n\n🛒 Mahsulotni tanlang:", b.as_markup())


async def show_item(target, user_id: int, s: str, cat: str, key: str):
    item = get_item(s, cat, key)
    u = await db.get_user(user_id)
    if item is None or u is None:
        return
    if not u["nick"]:
        return False
    b = InlineKeyboardBuilder()
    text = (
        f"🛒 <b>{esc(item.title)}</b>\n"
        f"🌍 Server: {SERVERS[s]['title']}\n"
        f"💵 Narx: <b>{money(item.price)}</b>\n"
        f"🎮 Nik: <code>{esc(u['nick'])}</code>\n"
        f"💰 Balansingiz: <b>{money(u['balance'])}</b>"
    )
    if u["balance"] >= item.price:
        b.button(text="✅ Sotib olish", callback_data=f"ok:{s}:{cat}:{key}")
    else:
        text += f"\n\n❌ Balansingizda <b>{money(item.price - u['balance'])}</b> yetmaydi."
        b.button(text="➕ Balans to'ldirish", callback_data="topup")
    b.button(text="✏️ Nikni o'zgartirish", callback_data=f"nk:{s}:{cat}:{key}")
    b.button(text="⬅️ Orqaga", callback_data=f"cat:{s}:{cat}")
    b.adjust(1)
    await render(target, text, b.as_markup())
    return True


async def ask_nick(target, state: FSMContext, s: str, cat: str, key: str):
    await state.set_state(Buy.nick)
    await state.update_data(s=s, cat=cat, key=key)
    await render(
        target,
        "🎮 <b>O'yindagi nikingizni yozing.</b>\n\n"
        "Aynan o'yindagidek yozing (katta-kichik harf muhim). Nik serverga kamida bir marta kirgan bo'lishi kerak.",
    )


@router.callback_query(F.data.startswith("it:"))
async def cb_item(c: CallbackQuery, state: FSMContext):
    await c.answer()
    _, s, cat, key = c.data.split(":")
    await db.upsert_user(c.from_user.id, c.from_user.username, c.from_user.full_name)
    u = await db.get_user(c.from_user.id)
    if not u["nick"]:
        await ask_nick(c.message, state, s, cat, key)
        return
    await show_item(c, c.from_user.id, s, cat, key)


@router.callback_query(F.data.startswith("nk:"))
async def cb_change_nick(c: CallbackQuery, state: FSMContext):
    await c.answer()
    _, s, cat, key = c.data.split(":")
    await ask_nick(c.message, state, s, cat, key)


@router.message(Buy.nick, F.text)
async def got_nick(m: Message, state: FSMContext):
    nick = m.text.strip()
    if not NICK_RE.match(nick):
        await m.answer("❌ Nik noto'g'ri. 3–16 belgi: lotin harflari, raqam, <code>_</code> yoki <code>.</code> bo'lishi mumkin. Qaytadan yozing:")
        return
    data = await state.get_data()
    await state.clear()
    await db.upsert_user(m.from_user.id, m.from_user.username, m.from_user.full_name)
    await db.set_nick(m.from_user.id, nick)
    if data.get("s"):
        await show_item(m, m.from_user.id, data["s"], data["cat"], data["key"])
    else:
        await m.answer(f"✅ Nik saqlandi: <b>{esc(nick)}</b>")


@router.callback_query(F.data.startswith("ok:"))
async def cb_confirm_buy(c: CallbackQuery):
    _, s, cat, key = c.data.split(":")
    item = get_item(s, cat, key)
    u = await db.get_user(c.from_user.id)
    if item is None or u is None or not u["nick"]:
        await c.answer("Xatolik, qaytadan urinib ko'ring", show_alert=True)
        return
    pid = await db.create_purchase(c.from_user.id, u["nick"], s, cat, key, item.title, item.price)
    if pid is None:
        await c.answer("Balansingizda mablag' yetarli emas", show_alert=True)
        await show_item(c, c.from_user.id, s, cat, key)
        return
    await c.answer()
    await render(c, "⏳ Mahsulot serverga yuborilmoqda...")
    purchase = await db.get_purchase(pid)
    ok, info = await deliver(purchase)
    srv = SERVERS[s]["title"]
    if ok:
        await db.mark_delivered(pid)
        await render(
            c,
            f"✅ <b>Xarid muvaffaqiyatli!</b>\n\n"
            f"🛒 {esc(item.title)} — {srv}\n🎮 Nik: <code>{esc(u['nick'])}</code>\n"
            f"💵 {money(item.price)}\n\nServerga kirib tekshiring. Xaridingiz uchun rahmat! 🙌",
        )
        await notify_admins(
            f"🛍 <b>Xarid #{pid}</b> ✅\n{esc(c.from_user.full_name)} (<code>{c.from_user.id}</code>)\n"
            f"{srv} — {esc(item.title)} — {esc(u['nick'])} — {money(item.price)}"
        )
    else:
        await db.mark_failed(pid, info)
        await render(
            c,
            "⚠️ <b>Xaridingiz qabul qilindi, lekin serverga yuborishda muammo bo'ldi.</b>\n\n"
            "Admin tez orada hal qiladi yoki pulingiz balansga qaytariladi. «Xaridlarim» bo'limidan holatni ko'rishingiz mumkin.",
        )
        await notify_admins(
            f"⚠️ <b>Yetkazib berilmadi — xarid #{pid}</b>\n{esc(c.from_user.full_name)} (<code>{c.from_user.id}</code>)\n"
            f"{srv} — {esc(item.title)} — nik: <code>{esc(u['nick'])}</code> — {money(item.price)}\n\n"
            f"Sabab: <code>{esc(info)}</code>",
            admin_fail_kb(pid),
        )


@router.callback_query(F.data.startswith("pf:"))
async def cb_admin_purchase(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("Ruxsat yo'q", show_alert=True)
        return
    _, action, pid = c.data.split(":")
    pid = int(pid)
    if action == "retry":
        if not await db.claim_retry(pid):
            await c.answer("Bu xarid endi 'failed' holatda emas", show_alert=True)
            return
        purchase = await db.get_purchase(pid)
        ok, info = await deliver(purchase)
        if ok:
            await db.mark_delivered(pid)
            await c.answer("Yuborildi ✅")
            note = "✅ Qayta yuborildi"
            try:
                await bot.send_message(purchase["user_id"], f"✅ Xaridingiz #{pid} ({esc(purchase['title'])}) serverga yuborildi!")
            except Exception:
                pass
        else:
            await db.mark_failed(pid, info)
            await c.answer("Yana xato", show_alert=True)
            note = f"⚠️ Yana xato: {esc(info)}"
        try:
            await c.message.edit_text(f"{c.message.html_text}\n\n{note}", reply_markup=None if ok else admin_fail_kb(pid))
        except TelegramBadRequest:
            pass
    elif action == "refund":
        row = await db.refund_purchase(pid)
        if row is None:
            await c.answer("Bu xarid endi 'failed' holatda emas", show_alert=True)
            return
        await c.answer("Pul qaytarildi")
        try:
            await c.message.edit_text(f"{c.message.html_text}\n\n💰 Pul balansga qaytarildi", reply_markup=None)
        except TelegramBadRequest:
            pass
        try:
            await bot.send_message(row["user_id"], f"↩️ Xarid #{pid} bajarilmadi. <b>{money(row['price'])}</b> balansingizga qaytarildi.")
        except Exception:
            pass


# ---------------------------------------------------------------- admin buyruqlari
@router.message(Command("stats"))
async def cmd_stats(m: Message):
    if not is_admin(m.from_user.id):
        return
    s = await db.stats()
    await m.answer(
        "📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: {s['users']}\n"
        f"💳 Tasdiqlangan to'lovlar: {s['topups']['c']} ta — {money(s['topups']['s'])}\n"
        f"🛍 Yetkazilgan xaridlar: {s['sales']['c']} ta — {money(s['sales']['s'])}\n"
        f"⏳ Ko'rib chiqilmagan to'lovlar: {s['pending']}\n"
        f"⚠️ Yetkazilmagan xaridlar: {s['failed']}"
    )


@router.message(Command("user"))
async def cmd_user(m: Message):
    if not is_admin(m.from_user.id):
        return
    parts = m.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await m.answer("Foydalanish: <code>/user 123456789</code>")
        return
    u = await db.get_user(int(parts[1]))
    if not u:
        await m.answer("Topilmadi")
        return
    await m.answer(f"🆔 <code>{u['user_id']}</code> @{esc(u['username'])}\n👤 {esc(u['full_name'])}\n🎮 {esc(u['nick'])}\n💰 {money(u['balance'])}")


async def _adjust(m: Message, sign: int):
    if not is_admin(m.from_user.id):
        return
    parts = m.text.split()
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await m.answer("Foydalanish: <code>/qosh 123456789 5000</code> yoki <code>/ayir 123456789 5000</code>")
        return
    new = await db.adjust_balance(int(parts[1]), sign * int(parts[2]))
    if new is None:
        await m.answer("❌ Foydalanuvchi topilmadi yoki balans yetarli emas.")
        return
    await m.answer(f"✅ Yangi balans: <b>{money(new)}</b>")
    try:
        verb = "qo'shildi" if sign > 0 else "ayirildi"
        await bot.send_message(int(parts[1]), f"💰 Balansingizga <b>{money(int(parts[2]))}</b> {verb}. Yangi balans: <b>{money(new)}</b>")
    except Exception:
        pass


@router.message(Command("qosh"))
async def cmd_add(m: Message):
    await _adjust(m, +1)


@router.message(Command("ayir"))
async def cmd_sub(m: Message):
    await _adjust(m, -1)


@router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def fallback(m: Message):
    await m.answer("Menyudan kerakli bo'limni tanlang 👇", reply_markup=main_kb())


# ---------------------------------------------------------------- ishga tushirish
async def main():
    global db, bot
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN o'rnatilmagan (Railway Variables)")
    if not config.ADMIN_IDS:
        log.warning("ADMIN_IDS bo'sh — to'lovlarni hech kim tasdiqlay olmaydi!")
    if not config.CARD_NUMBER:
        log.warning("CARD_NUMBER bo'sh!")
    db = DB(config.DB_PATH)
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Bot ishga tushdi")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
