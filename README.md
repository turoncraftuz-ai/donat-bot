# TuronCraft donat boti

## Fayllar
- `bot.py` — asosiy bot (menyu, balans, to'ldirish, sotib olish, admin tugmalari)
- `catalog.py` — **narxlar va mahsulotlar** (Anarxiya va BoxPvP alohida)
- `config.py` — Railway Variables'ni o'qiydi
- `db.py` — SQLite baza
- `rcon.py` — serverga buyruq yuboruvchi (RCON)

## Railway'da ishga tushirish
1. Fayllarni GitHub repoga yuklang va Railway'da shu repodan deploy qiling.
2. **Volume** qo'shing va Mount path: `/data` (aks holda har deployda balanslar o'chib ketadi).
3. Variables bo'limiga `.env.example` dagi o'zgaruvchilarni kiriting.
4. Start command: `python bot.py` (Procfile bor, o'zi topadi).

## Serverlarda RCON yoqish (ikkala server uchun)
`server.properties`:
```
enable-rcon=true
rcon.port=XXXXX
rcon.password=KUCHLI_PAROL
```
Serverni qayta ishga tushiring. RCON portini hosting panelida tashqaridan ochiq qiling.
Shu port va parolni Railway Variables'dagi `*_RCON_PORT` va `*_RCON_PASSWORD` ga yozing.

## Mahsulot berish buyruqlari
- Rank: `lp user {nick} parent add {group}`
- Token: `points give {nick} {amount}`

## Admin buyruqlari
- `/stats` — statistika
- `/user ID` — foydalanuvchi ma'lumoti
- `/qosh ID SUMMA` — balans qo'shish
- `/ayir ID SUMMA` — balansdan ayirish

Yetkazib berish xato bersa, adminga **«Qayta yuborish»** va **«Pulni qaytarish»** tugmalari keladi.

## Avto-to'lov (pul tushganini bot o'zi aniqlaydi)
1. https://my.telegram.org → **API development tools** → `api_id` va `api_hash` oling.
2. Kompyuteringizda: `pip install telethon`, so'ng `python gen_session.py` — telefon raqam va kodni kiriting.
   Chiqqan uzun satr = `TG_SESSION`. Uni hech kimga bermang.
3. Railway Variables: `TG_API_ID`, `TG_API_HASH`, `TG_SESSION`, `PAYMENT_BOT` (standart `HUMOcardbot`).
4. Birinchi kunlarda `PAY_DEBUG=1` qo'ying: bank xabari qanday ko'rinishda kelishini adminga yuboradi.
   Summa noto'g'ri o'qilsa `PAY_AMOUNT_REGEX` bilan sozlanadi. Hammasi to'g'ri ishlasa, `PAY_DEBUG` ni 0 qiling.

Ishlash tartibi: bot o'yinchiga noyob summa beradi (masalan 10 000 so'm uchun 10 037), bank botidan kirim xabari
kelganda shu summaga mos so'rovni topib balansni o'zi to'ldiradi. Mos so'rov topilmasa adminga xabar boradi.
