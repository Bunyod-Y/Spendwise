# Spendwise 💰

Xarajatlarni hisoblab boruvchi Telegram bot. Interfeysi to'liq o'zbek tilida va istalgan odam foydalana oladi. Har bir foydalanuvchining ma'lumotlari alohida saqlanadi va boshqalarga ko'rinmaydi.

## Foydalanish

Xarajatni oddiy xabar qilib yozing. Bot uni saqlaydi va xabaringizga 👍 qo'yadi:

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

### Avtomatik hisobotlar (Toshkent vaqti)
- **Haftalik:** har yakshanba soat 12:00 da (dushanba–yakshanba).
- **Oylik:** oyning oxirgi kuni soat 21:00 da.

Hisobotda jami summa, xarajatlar soni, kunlik o'rtacha va eng ko'p sarflangan yo'nalishlar bo'ladi. Unga Excel fayl ham qo'shiladi (`Sana | Vaqt | Summa | Izoh`, JAMI qatori va «Kunlik jami» varag'i). Xarajat yozilmagan davr uchun hisobot yuborilmaydi. Botga yangi qo'shilgan foydalanuvchiga u qo'shilishidan oldingi davr uchun hisobot kelmaydi.

## Maxfiylik

- Har bir foydalanuvchining xarajatlari alohida papkada turadi: `data/users/<telegram_id>/`. Bot har bir so'rovda faqat yozgan odamning o'z papkasini ochadi. Boshqa foydalanuvchi ID'sini qabul qiladigan buyruq yo'q.
- `users.json` faqat Telegram ID va hisobot holatini saqlaydi. Ism, username yoki telefon raqami saqlanmaydi.
- Bot faqat shaxsiy chatlarda ishlaydi. Guruhga qo'shilsa, xabarlarga javob bermaydi.
- Xabar matnlari logga yozilmaydi.
- Fayllar serverda shifrlanmagan holda turadi, ya'ni server egasi ularni ko'ra oladi. Foydalanuvchilarga shuni aytib qo'ying.

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

## Boshqarish

```bash
git pull && docker compose up -d --build      # yangi versiyani o'rnatish
docker compose logs -f --tail 100             # loglar
docker compose restart                        # qayta ishga tushirish
docker compose down                           # to'xtatish (ma'lumotlar saqlanadi; -v qo'shmang, u ma'lumotlarni o'chiradi)
docker cp spendwise:/data ./backup-$(date +%F) # zaxira nusxa
```

Ma'lumotlar `spendwise-data` Docker volume'ida turadi:
```
/data/users.json                     # foydalanuvchilar ro'yxati (faqat ID)
/data/users/<telegram_id>/2026-09.xlsx   # har bir foydalanuvchi, har bir oy
```
