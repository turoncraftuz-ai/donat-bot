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
