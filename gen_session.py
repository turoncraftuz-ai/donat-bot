"""Bir marta KOMPYUTERINGIZDA ishga tushiriladi (Railway'da emas).

    pip install telethon
    python gen_session.py

API ID va API HASH ni https://my.telegram.org -> API development tools dan oling.
Chiqqan uzun satrni Railway'da TG_SESSION o'zgaruvchisiga yozing. Uni hech kimga bermang —
u akkauntingizga to'liq kirish beradi.
"""
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = int(input("API ID: ").strip())
api_hash = input("API HASH: ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\nTG_SESSION =\n")
    print(client.session.save())
