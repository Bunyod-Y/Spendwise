# Spendwise 💰

Xarajatlarni hisoblab boruvchi Telegram bot. Interfeysi to'liq o'zbek tilida va istalgan odam foydalana oladi. Har bir foydalanuvchining ma'lumotlari alohida saqlanadi, o'z paroli bilan shifrlanadi va boshqalarga ko'rinmaydi. Botni oilaviy guruhga qo'shib, umumiy xarajatni ham birga yuritish mumkin.

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

## Guruh (oilaviy xarajat)

Botni guruhga qo'shsangiz, a'zolar umumiy xarajatni birga yozadi va bot kim qancha sarflaganini hisoblab beradi. Shaxsiy xarajatlar guruhdan alohida qoladi va guruhga ko'rinmaydi.

**Sozlash (bir marta)**
1. Botni guruhga qo'shing. Botda guruh xabarlarini o'qish huquqi kerak emas: bot faqat buyruqlarga javob beradi va oddiy suhbatni o'qimaydi.
2. Guruh admini botga shaxsiy chatda `/start` bosib parol o'rnatadi va kiritadi.
3. Guruhda o'sha admin `/guruh` ni bosadi. Guruh admini bo'lmagan odam sozlay olmaydi.

**Ishlatish (hamma a'zo)**

| Buyruq | Nima qiladi |
|---|---|
| `/x 50000 non` | Xarajat yozish (kim yozgani saqlanadi) |
| `/bugun` | Guruhning bugungi xarajatlari |
| `/hafta`, `/oy`, `/oy 08.2026` | Hisobot: jami, **kim qancha sarflagani** va Excel (`Xarajatlar`, `Kunlik jami`, `Kim bo'yicha` varaqlari) |
| `/royxat` | Shu oydagi xarajatlar raqamlari va ismlari bilan |
| `/statistika` | Oxirgi 7 kun, oy jami, har kimning ulushi |
| `/tahrir 3 45000 non`, `/ochirish 3`, `/bekor` | O'z yozuvini o'zgartirish/o'chirish. Birovning yozuviga faqat guruh admini tegadi |
| `/qoshish 25.09 50000 non` | Boshqa kunga qo'shish |
| `/hisobot` | Avtomatik hisobotlarni yoqish/o'chirish (faqat admin) |
| `/guruh` | Guruh holati. `/guruh kalit`: boshqa admin ham kalit egasi bo'ladi |

Avtomatik hisobotlar (yakshanba 12:00, oy oxirida 21:00) guruhning o'ziga yuboriladi. Guruh a'zolari botda ro'yxatdan o'tishi yoki parol qo'yishi shart emas.

**Shifrlash.** Guruhda parol yozib bo'lmaydi (hamma ko'radi), shuning uchun guruh kaliti guruhni sozlagan adminning **shaxsiy kaliti** bilan o'raladi. Bot qayta ishga tushganda guruh qulflanadi va kalit egasi botga shaxsiy chatda parolini kiritishi bilan ochiladi. Shu paytgacha guruhda yozilgan `/x` (20 tagacha) xotirada turadi va guruh ochilgach saqlanadi. `/guruh kalit` bilan ikkinchi admin ham kalit egasi bo'lsa, guruh bitta odamga bog'liq bo'lib qolmaydi.

**Esda tuting**
- Kalit egasi `/tozalash` qilsa va u guruhning **yagona** kalit egasi bo'lsa, guruh ma'lumotlari ham o'chadi (bot avval ogohlantiradi).
- Guruh a'zolarining ismlari (Telegram'dagi ko'rinadigan ismi) va ID'si shifrlangan faylning ichida turadi, `users.json`/`groups.json`da emas.
- Oddiy guruh superguruhga aylansa, Telegram chat ID'sini o'zgartiradi: `/guruh` ni qayta bosib, yangidan boshlash kerak bo'ladi.

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
- Shaxsiy xarajatlar faqat shaxsiy chatda ko'rinadi. Guruhda bot faqat o'z buyruqlariga javob beradi va oddiy xabarlarni o'qimaydi. Guruh ma'lumoti alohida (`data/groups/<chat_id>/`) va guruh kaliti bilan shifrlangan (yuqoridagi «Guruh» bo'limiga qarang).

**Muhim cheklovlar (halol ogohlantirish)**
- **Parol unutilsa, ma'lumotni tiklab bo'lmaydi** (`/tozalash` bilan hammasini o'chirib, boshidan boshlash mumkin). Bu ataylab shunday: tiklash yo'li bo'lsa, server egasi ham foydalana olardi.
- Telegram botlarida xabarlar end-to-end shifrlanmagan. Xabar Telegram serveri orqali o'tadi va bot kodi uni ochiq matn sifatida qayta ishlaydi. Server ustidan to'liq nazorati bor odam (root) botning kodini o'zgartirib yoki xotirasini o'qib, foydalanuvchi ochiq turgan paytda ma'lumotni ko'rishi **nazariy jihatdan mumkin**. Shifrlash quyidagilardan himoya qiladi: diskdagi fayllarni o'qish, zaxira nusxalar (`docker cp`), o'g'irlangan disk yoki server ma'lumoti sizib chiqishi. Shuning uchun bot egasiga ishonch baribir kerak.
- Hisobotdagi Excel fayl Telegram chatiga ochiq holda yuboriladi, chunki foydalanuvchi uni telefonida ochishi kerak. Ularni chatda saqlash foydalanuvchining o'z ixtiyorida.
- Diskda foydalanuvchining Telegram ID'si, fayl nomlari (oy) va fayl hajmi ko'rinib turadi. Guruhlarda qo'shimcha ravishda kalit egalarining Telegram ID'si `vault.json`da ochiq turadi.

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
/data/groups.json                         # guruhlar ro'yxati (faqat chat ID va hisobot holati)
/data/groups/<chat_id>/vault.json         # guruh kaliti, har bir kalit egasining kaliti bilan o'ralgan
/data/groups/<chat_id>/2026-09.enc        # shifrlangan guruh xarajatlari (kim yozgani bilan)
```
