"""SQLite baza (standart kutubxona). Barcha yozuvlar bitta lock ostida bajariladi."""
import asyncio
import os
import random
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    nick TEXT,
    balance INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS topups(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    status TEXT NOT NULL,            -- waiting, review, approved, rejected, cancelled
    proof_file_id TEXT,
    pay_amount INTEGER,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    decided_by INTEGER,
    decided_at INTEGER
);
CREATE TABLE IF NOT EXISTS purchases(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    nick TEXT NOT NULL,
    server TEXT NOT NULL,
    category TEXT NOT NULL,
    item_key TEXT NOT NULL,
    title TEXT NOT NULL,
    price INTEGER NOT NULL,
    status TEXT NOT NULL,            -- processing, delivered, failed, refunded
    error TEXT,
    created_at INTEGER NOT NULL,
    delivered_at INTEGER
);
CREATE TABLE IF NOT EXISTS processed_payments(
    chat_id INTEGER NOT NULL,
    msg_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY(chat_id, msg_id)
);
"""


class DB:
    def __init__(self, path: str):
        self.path = path
        self.lock = asyncio.Lock()
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        cols = [r["name"] for r in self.conn.execute("PRAGMA table_info(topups)").fetchall()]
        if "pay_amount" not in cols:  # eski bazani yangilash
            self.conn.execute("ALTER TABLE topups ADD COLUMN pay_amount INTEGER")

    # --- ichki yordamchilar -------------------------------------------------
    def _one(self, sql, args=()):
        return self.conn.execute(sql, args).fetchone()

    def _all(self, sql, args=()):
        return self.conn.execute(sql, args).fetchall()

    async def _run(self, fn, *a):
        async with self.lock:
            return await asyncio.to_thread(fn, *a)

    def _tx(self, fn):
        """fn(conn) ni bitta tranzaksiyada bajaradi."""
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            res = fn(self.conn)
            self.conn.execute("COMMIT")
            return res
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    # --- foydalanuvchilar ---------------------------------------------------
    async def upsert_user(self, user_id, username, full_name):
        def f():
            self.conn.execute(
                "INSERT INTO users(user_id, username, full_name, created_at) VALUES(?,?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, full_name=excluded.full_name",
                (user_id, username, full_name, int(time.time())),
            )
            return self._one("SELECT * FROM users WHERE user_id=?", (user_id,))
        return await self._run(f)

    async def get_user(self, user_id):
        return await self._run(lambda: self._one("SELECT * FROM users WHERE user_id=?", (user_id,)))

    async def set_nick(self, user_id, nick):
        await self._run(lambda: self.conn.execute("UPDATE users SET nick=? WHERE user_id=?", (nick, user_id)))

    async def adjust_balance(self, user_id, delta):
        """Balansni o'zgartiradi. Manfiy bo'lib qolsa None qaytaradi."""
        def f():
            def tx(c):
                row = c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
                if row is None or row["balance"] + delta < 0:
                    return None
                c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (delta, user_id))
                return row["balance"] + delta
            return self._tx(tx)
        return await self._run(f)

    # --- balans to'ldirish --------------------------------------------------
    async def create_topup(self, user_id, amount, ttl_min, grace_min=15, max_offset=99):
        """To'lov so'rovi yaratadi. Qaytaradi: (id, pay_amount). pay_amount - noyob (amount + 1..99 so'm)."""
        def f():
            def tx(c):
                c.execute("UPDATE topups SET status='cancelled' WHERE user_id=? AND status='waiting'", (user_id,))
                now = int(time.time())
                rows = c.execute(
                    "SELECT pay_amount FROM topups WHERE pay_amount IS NOT NULL AND "
                    "(status='review' OR (status='waiting' AND expires_at>=?))", (now - grace_min * 60,)).fetchall()
                used = {r["pay_amount"] for r in rows}
                offsets = list(range(1, max_offset + 1))
                random.shuffle(offsets)
                offsets += list(range(max_offset + 1, 1000))
                pay = amount if max_offset <= 0 else next((amount + o for o in offsets if amount + o not in used), amount)
                cur = c.execute(
                    "INSERT INTO topups(user_id, amount, status, pay_amount, created_at, expires_at) VALUES(?,?,?,?,?,?)",
                    (user_id, amount, "waiting", pay, now, now + ttl_min * 60),
                )
                return cur.lastrowid, pay
            return self._tx(tx)
        return await self._run(f)

    async def get_topup(self, topup_id):
        return await self._run(lambda: self._one("SELECT * FROM topups WHERE id=?", (topup_id,)))

    async def submit_proof(self, topup_id, user_id, file_id):
        def f():
            cur = self.conn.execute(
                "UPDATE topups SET status='review', proof_file_id=? "
                "WHERE id=? AND user_id=? AND status='waiting' AND expires_at>=?",
                (file_id, topup_id, user_id, int(time.time())),
            )
            return cur.rowcount == 1
        return await self._run(f)

    async def cancel_topup(self, topup_id, user_id):
        def f():
            cur = self.conn.execute(
                "UPDATE topups SET status='cancelled' WHERE id=? AND user_id=? AND status='waiting'",
                (topup_id, user_id),
            )
            return cur.rowcount == 1
        return await self._run(f)

    async def decide_topup(self, topup_id, admin_id, approve: bool):
        """Faqat 'review' holatidagi to'lovni qabul/rad etadi. Qaytaradi: topup qatori yoki None."""
        def f():
            def tx(c):
                cur = c.execute(
                    "UPDATE topups SET status=?, decided_by=?, decided_at=? WHERE id=? AND status='review'",
                    ("approved" if approve else "rejected", admin_id, int(time.time()), topup_id),
                )
                if cur.rowcount != 1:
                    return None
                row = c.execute("SELECT * FROM topups WHERE id=?", (topup_id,)).fetchone()
                if approve:
                    c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (row["amount"], row["user_id"]))
                return row
            return self._tx(tx)
        return await self._run(f)

    async def register_payment(self, chat_id, msg_id, amount):
        """Bank xabarini bir marta qayta ishlash uchun. Yangi bo'lsa True."""
        def f():
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO processed_payments(chat_id, msg_id, amount, created_at) VALUES(?,?,?,?)",
                (chat_id, msg_id, amount, int(time.time())))
            return cur.rowcount == 1
        return await self._run(f)

    async def auto_approve(self, pay_amount, grace_min=15):
        """Kelgan summaga mos so'rovni topib tasdiqlaydi va balansni to'ldiradi. Topilmasa None."""
        def f():
            def tx(c):
                row = c.execute(
                    "SELECT * FROM topups WHERE pay_amount=? AND "
                    "(status='review' OR (status='waiting' AND expires_at>=?)) ORDER BY id DESC LIMIT 1",
                    (pay_amount, int(time.time()) - grace_min * 60)).fetchone()
                if row is None:
                    return None
                c.execute("UPDATE topups SET status='approved', decided_by=0, decided_at=? WHERE id=?",
                          (int(time.time()), row["id"]))
                c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (row["amount"], row["user_id"]))
                return row
            return self._tx(tx)
        return await self._run(f)

    async def list_topups(self, user_id, limit=10):
        return await self._run(lambda: self._all(
            "SELECT * FROM topups WHERE user_id=? AND status IN ('approved','rejected','review') "
            "ORDER BY id DESC LIMIT ?", (user_id, limit)))

    # --- xaridlar -----------------------------------------------------------
    async def create_purchase(self, user_id, nick, server, category, item_key, title, price):
        """Balansdan pulni yechadi va 'processing' xarid yaratadi. Pul yetmasa None."""
        def f():
            def tx(c):
                cur = c.execute(
                    "UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?", (price, user_id, price))
                if cur.rowcount != 1:
                    return None
                cur = c.execute(
                    "INSERT INTO purchases(user_id, nick, server, category, item_key, title, price, status, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (user_id, nick, server, category, item_key, title, price, "processing", int(time.time())),
                )
                return cur.lastrowid
            return self._tx(tx)
        return await self._run(f)

    async def get_purchase(self, pid):
        return await self._run(lambda: self._one("SELECT * FROM purchases WHERE id=?", (pid,)))

    async def mark_delivered(self, pid):
        await self._run(lambda: self.conn.execute(
            "UPDATE purchases SET status='delivered', error=NULL, delivered_at=? WHERE id=?", (int(time.time()), pid)))

    async def mark_failed(self, pid, error):
        await self._run(lambda: self.conn.execute(
            "UPDATE purchases SET status='failed', error=? WHERE id=?", (error[:500], pid)))

    async def claim_retry(self, pid):
        def f():
            cur = self.conn.execute("UPDATE purchases SET status='processing' WHERE id=? AND status='failed'", (pid,))
            return cur.rowcount == 1
        return await self._run(f)

    async def refund_purchase(self, pid):
        """'failed' xaridni qaytaradi (pul balansga). Qaytaradi: xarid qatori yoki None."""
        def f():
            def tx(c):
                cur = c.execute("UPDATE purchases SET status='refunded' WHERE id=? AND status='failed'", (pid,))
                if cur.rowcount != 1:
                    return None
                row = c.execute("SELECT * FROM purchases WHERE id=?", (pid,)).fetchone()
                c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (row["price"], row["user_id"]))
                return row
            return self._tx(tx)
        return await self._run(f)

    async def list_purchases(self, user_id, limit=10):
        return await self._run(lambda: self._all(
            "SELECT * FROM purchases WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)))

    async def stats(self):
        def f():
            return {
                "users": self._one("SELECT COUNT(*) c FROM users")["c"],
                "topups": self._one("SELECT COALESCE(SUM(amount),0) s, COUNT(*) c FROM topups WHERE status='approved'"),
                "sales": self._one("SELECT COALESCE(SUM(price),0) s, COUNT(*) c FROM purchases WHERE status='delivered'"),
                "pending": self._one("SELECT COUNT(*) c FROM topups WHERE status='review'")["c"],
                "failed": self._one("SELECT COUNT(*) c FROM purchases WHERE status='failed'")["c"],
            }
        return await self._run(f)
