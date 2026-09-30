# Spendwise 💰

Xarajatlarni hisoblab boruvchi Telegram bot. Interfeysi to'liq o'zbek tilida va istalgan odam foydalana oladi. Har bir foydalanuvchining ma'lumotlari alohida saqlanadi, o'z paroli bilan shifrlanadi va boshqalarga ko'rinmaydi.

## Foydalanish

Birinchi marta `/start` bosganda bot parol o'rnatishni so'raydi (pastdagi «Maxfiylik» bo'limiga qarang). Shundan keyin xarajatni oddiy xabar qilib yozing. Bot uni saqlaydi va xabaringizga 👍 qo'yadi:

```
50000 non
non 50000
taksi 25 000 so'm
30 ming tushlik
1.5 mln ijara
50k benzin
```

Pastda doimiy tugmalar turadi:

| Tugma | Nima qiladi |
|---|---|
| 📅 Bugun | Bugungi xarajatlar |
| 📆 Bu hafta | Haftalik hisobot + Excel fayl |
| 🗓 Bu oy | Oylik hisobot + Excel fayl |
| 📋 Ro'yxat | Shu oydagi barcha xarajatlar, raqamlari bilan |
| 📈 Statistika | Oxirgi 7 kun, oy jami, kunlik o'rtacha, eng katta xarajat |
| ↩️ Oxirgisini o'chirish | Oxirgi yozuvni tasdiqlab o'chirish |
| ❓ Yordam | Yordam |

Qo'shimcha buyruqlar:

| Buyruq | Nima qiladi |
|---|---|
| `/tahrir 3 45000 non` | 3-xarajatni o'zgartirish (raqam «Ro'yxat»dan olinadi) |
| `/ochirish 3` | 3-xarajatni o'chirish |
| `/qoshish 25.09 50000 non` | Boshqa kunga qo'shish (vaqti bilan: `/qoshish 25.09 14:30 50000 non`) |
| `/oy 08.2026` | Boshqa oy hisoboti |
| `/hisobot` | Avtomatik hisobotlarni yoqish/o'chirish |
| `/parol` | Parolni almashtirish |
| `/tozalash` | Barcha ma'lumotlarni o'chirish (parol unutilganda ham shu) |

### Avtomatik hisobotlar (Toshkent vaqti)
- **Haftalik:** har yakshanba soat 12:00 da (dushanba–yakshanba).
- **Oylik:** oyning oxirgi kuni soat 21:00 da.

Hisobotda jami summa, xarajatlar soni, kunlik o'rtacha va eng ko'p sarflangan yo'nalishlar bo'ladi. Unga Excel fayl ham qo'shiladi (`Sana | Vaqt | Summa | Izoh`, JAMI qatori va «Kunlik jami» varag'i). Xarajat yozilmagan davr uchun hisobot yuborilmaydi. Botga yangi qo'shilgan foydalanuvchiga u qo'shilishidan oldingi davr uchun hisobot kelmaydi.

### Saqlash muddati
Joriy oy va undan oldingi **12 oy** saqlanadi. Undan eskisi har kuni soat 03:00 da avtomatik o'chiriladi (shifrlangan fayllarni ochmasdan). Bitta foydalanuvchining bir yillik ma'lumoti odatda 1 MB dan kam joy oladi.

## Maxfiylik

Maqsad: har bir foydalanuvchining ma'lumotini faqat o'sha odamning o'zi ocha olishi, bot egasi (server administratori) ham ochib o'qiy olmasligi.

**Qanday ishlaydi**
- Har bir foydalanuvchi o'z **parolini** o'rnatadi. Xarajatlar Excel fayllari sifatida `Fernet` (AES-128-CBC + HMAC) bilan shifrlangan holda saqlanadi.
- Fayllarni shifrlaydigan kalit tasodifiy yaratiladi va parol (scrypt, `n=2^15`) yordamida o'ralgan holda `vault.json`da turadi. **Parol ham, ochiq kalit ham diskka yozilmaydi.**
- Ochilgan kalit faqat botning xotirasida turadi. Bot qayta ishga tushsa (masalan, yangilanganda), hamma foydalanuvchi **parolini qayta kiritishi kerak**. Shundan keyingina xarajat saqlanadi va hisobotlar keladi. Qulflangan paytda yuborilgan xarajat xotirada kutib turadi va ochilgandan keyin saqlanadi. Ochilishni kutgan hisobot ham shu paytda yuboriladi.
- Parol yozilgan xabarni bot chatdan o'chirishga harakat qiladi.
- 5 marta noto'g'ri urinishdan keyin 10 daqiqa kutish qo'yiladi.
- Boshqa foydalanuvchilar bir-birining ma'lumotini ko'ra olmaydi: har biri o'z papkasida (`data/users/<telegram_id>/`) va o'z kaliti bilan. Bot har so'rovda faqat yozgan odamning kalitini ishlatadi.
- Botda administrator buyrug'i yo'q. Xabar matnlari va parollar logga yozilmaydi. `users.json`da faqat Telegram ID va hisobot holati bor, ism, username yoki telefon yo'q.
- Bot faqat shaxsiy chatlarda ishlaydi.

**Muhim cheklovlar (halol ogohlantirish)**
- **Parol unutilsa, ma'lumotni tiklab bo'lmaydi** (`/tozalash` bilan hammasini o'chirib, boshidan boshlash mumkin). Bu ataylab shunday: tiklash yo'li bo'lsa, server egasi ham foydalana olardi.
- Telegram botlarida xabarlar end-to-end shifrlanmagan. Xabar Telegram serveri orqali o'tadi va bot kodi uni ochiq matn sifatida qayta ishlaydi. Server ustidan to'liq nazorati bor odam (root) botning kodini o'zgartirib yoki xotirasini o'qib, foydalanuvchi ochiq turgan paytda ma'lumotni ko'rishi **nazariy jihatdan mumkin**. Shifrlash quyidagilardan himoya qiladi: diskdagi fayllarni o'qish, zaxira nusxalar (`docker cp`), o'g'irlangan disk yoki server ma'lumoti sizib chiqishi. Shuning uchun bot egasiga ishonch baribir kerak.
- Hisobotdagi Excel fayl Telegram chatiga ochiq holda yuboriladi, chunki foydalanuvchi uni telefonida ochishi kerak. Ularni chatda saqlash foydalanuvchining o'z ixtiyorida.
- Diskda foydalanuvchining Telegram ID'si, fayl nomlari (oy) va fayl hajmi ko'rinib turadi.

## O'rnatish (Ubuntu + Docker)

1. @BotFather'da `/newbot` orqali bot yarating va tokenni oling.
2. Serverda:
   ```bash
   git clone https://github.com/Bunyod-Y/Spendwise.git /opt/spendwise
   cd /opt/spendwise
   cp .env.example .env
   nano .env          # BOT_TOKEN ni kiriting
   chmod 600 .env
   docker compose up -d --build
   docker compose logs -f     # "Spendwise started" chiqishi kerak
   ```

Token faqat serverdagi `.env` faylida turadi. `.env` `.gitignore`da, shuning uchun hech qachon gitga tushmaydi.

Oldingi (shifrlanmagan) versiya o'rnatilgan bo'lsa: yangilagandan keyin har bir foydalanuvchi parol o'rnatganda eski fayllari avtomatik shifrlanadi va ochiq nusxasi o'chiriladi.

## Boshqarish

```bash
git pull && docker compose up -d --build      # yangi versiyani o'rnatish (barcha foydalanuvchilar qulflanadi)
docker compose logs -f --tail 100             # loglar
docker compose restart                        # qayta ishga tushirish
docker compose down                           # to'xtatish (ma'lumotlar saqlanadi; -v qo'shmang, u ma'lumotlarni o'chiradi)
docker cp spendwise:/data ./backup-$(date +%F) # zaxira nusxa (shifrlangan, parolsiz ochilmaydi)
```

Ma'lumotlar `spendwise-data` Docker volume'ida turadi:
```
/data/users.json                          # foydalanuvchilar ro'yxati (faqat ID va hisobot holati)
/data/users/<telegram_id>/vault.json      # parol bilan o'ralgan kalit
/data/users/<telegram_id>/2026-09.enc     # shifrlangan oylik fayl
```
