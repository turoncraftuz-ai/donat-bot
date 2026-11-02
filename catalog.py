"""Do'kon katalogi: serverlar, ranklar va tokenlar.

Narxlarni shu yerda o'zgartirasan (so'mda). `group` - LuckPerms'dagi guruh nomi.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    key: str
    title: str
    price: int
    kind: str          # "rank" yoki "token"
    value: str         # rank uchun guruh nomi, token uchun miqdor


def _ranks(rows):
    return [Item(g, g.capitalize(), p, "rank", g) for g, p in rows]


def _tokens(rows):
    return [Item(f"t{n}", f"{n:,}".replace(",", " ") + " Token", p, "token", str(n)) for n, p in rows]


SERVERS = {
    "anarxiya": {
        "title": "🏝 Anarxiya",
        "rcon_prefix": "ANARCHY",
        "ranks": _ranks([
            ("askar", 6000),
            ("qahramon", 10500),
            ("ritsar", 16000),
            ("alpomish", 22000),
            ("titan", 29000),
            ("elita", 32000),
            ("afsona", 48000),
            ("general", 68000),
            ("imperator", 86000),
        ]),
        # TODO: token narxlarini o'zingnikiga almashtir
        "tokens": _tokens([
            (1000, 1500),
            (5000, 7000),
            (10000, 14000),
            (20000, 25000),
            (100000, 140000),
        ]),
    },
    "boxpvp": {
        "title": "⚔️ BoxPvP",
        "rcon_prefix": "BOXPVP",
        # TODO: BoxPvP rank va token narxlarini o'zingnikiga almashtir
        "ranks": _ranks([
            ("vip", 10000),
            ("pro", 20000),
            ("mvp", 35000),
            ("elite", 50000),
            ("immortal", 80000),
        ]),
        "tokens": _tokens([
            (1000, 1500),
            (5000, 7000),
            (10000, 14000),
            (20000, 25000),
            (100000, 140000),
        ]),
    },
}

CATEGORIES = {"ranks": "🎖 Ranklar", "tokens": "🪙 Tokenlar"}


def get_item(server: str, category: str, key: str):
    for it in SERVERS.get(server, {}).get(category, []):
        if it.key == key:
            return it
    return None
