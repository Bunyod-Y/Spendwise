"""All user-facing texts (Uzbek) and formatting helpers."""
from __future__ import annotations

from datetime import date, datetime, timedelta

CURRENCY = "so'm"
WEEKDAYS = ("Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya")
MONTHS = (
    "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
    "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
)

# Reply-keyboard buttons (always visible under the input field).
BTN_TODAY = "📅 Bugun"
BTN_WEEK = "📆 Bu hafta"
BTN_MONTH = "🗓 Bu oy"
BTN_LIST = "📋 Ro'yxat"
BTN_STATS = "📈 Statistika"
BTN_UNDO = "↩️ Oxirgisini o'chirish"
BTN_HELP = "❓ Yordam"
KEYBOARD = [
    [BTN_TODAY, BTN_WEEK],
    [BTN_MONTH, BTN_LIST],
    [BTN_STATS, BTN_UNDO],
    [BTN_HELP],
]
INPUT_PLACEHOLDER = "Masalan: 50000 non"

BOT_SHORT_DESCRIPTION = "Xarajatlaringizni oson hisoblab boruvchi yordamchi 💰"
BOT_DESCRIPTION = (
    "💰 Spendwise: shaxsiy xarajatlar daftari.\n\n"
    "Xarajatni oddiy xabar qilib yozing (masalan: 50000 non), "
    "men uni saqlab boraman va har hafta, har oy hisobot yuboraman.\n\n"
    "Boshlash uchun «Start» tugmasini bosing."
)

COMMANDS = [
    ("bugun", "Bugungi xarajatlar"),
    ("hafta", "Shu haftalik hisobot"),
    ("oy", "Oylik hisobot va Excel fayl"),
    ("royxat", "Shu oydagi xarajatlar ro'yxati"),
    ("statistika", "Statistika"),
    ("qoshish", "Boshqa kunga xarajat qo'shish"),
    ("tahrir", "Xarajatni tahrirlash"),
    ("ochirish", "Xarajatni o'chirish"),
    ("bekor", "Oxirgi xarajatni o'chirish"),
    ("hisobot", "Avtomatik hisobotlarni yoqish/o'chirish"),
    ("parol", "Parolni almashtirish"),
    ("tozalash", "Barcha ma'lumotlarimni o'chirish"),
    ("yordam", "Yordam"),
]

WELCOME = """\
Assalomu alaykum! 👋

Men xarajatlaringizni hisoblab boraman.

✍️ Har bir xarajatni oddiy xabar qilib yozing:
   50000 non
   taksi 25 000
   30 ming tushlik
   1.5 mln ijara

Saqlaganimni 👍 belgisi bilan bildiraman.

📊 Har yakshanba soat 12:00 da haftalik, oyning oxirgi kuni soat 21:00 da oylik hisobot yuboraman.

🔒 Ma'lumotlaringiz parol bilan shifrlanadi: ularni faqat siz ocha olasiz, boshqa foydalanuvchilar ham, bot egasi ham ko'ra olmaydi.

🗓 Oxirgi 12 oylik ma'lumot saqlanadi, undan eskisi avtomatik o'chiriladi.

Pastdagi tugmalardan foydalaning 👇"""

HELP = """\
❓ Yordam

✍️ Xarajat yozish: summa va izohni yuboring (tartibi muhim emas):
   50000 non
   non 50000
   taksi 25 000 so'm
   30 ming tushlik
   1.5 mln ijara

Tugmalar:
📅 Bugun: bugungi xarajatlar
📆 Bu hafta: haftalik hisobot + Excel
🗓 Bu oy: oylik hisobot + Excel
📋 Ro'yxat: shu oydagi barcha xarajatlar (raqamlari bilan)
📈 Statistika: oxirgi 7 kun va oy bo'yicha
↩️ Oxirgisini o'chirish: oxirgi yozuvni o'chirish

Xatoni tuzatish (raqamni «📋 Ro'yxat»dan oling):
/tahrir 3 45000 non: 3-xarajatni o'zgartirish
/ochirish 3: 3-xarajatni o'chirish
/qoshish 25.09 50000 non: boshqa kunga qo'shish
/qoshish 25.09 14:30 50000 non: vaqti bilan

Boshqa:
/oy 08.2026: boshqa oy hisoboti
/hisobot: avtomatik hisobotlarni yoqish/o'chirish

📊 Hisobotlar: har yakshanba 12:00 da haftalik, oyning oxirgi kuni 21:00 da oylik.

🔒 Xavfsizlik:
/parol: parolni almashtirish
/tozalash: barcha ma'lumotlaringizni o'chirish (parol unutilganda ham shu)
Ma'lumotlar parolingiz bilan shifrlangan, parolni bot egasi ham bilmaydi. Parol unutilsa, uni tiklab bo'lmaydi.
🗓 Faqat oxirgi 12 oy saqlanadi, eskisi avtomatik o'chiriladi."""

NOT_UNDERSTOOD = (
    "🤔 Summani topa olmadim.\n\n"
    "Xarajatni shunday yozing:\n"
    "   50000 non\n"
    "   taksi 25 000\n"
    "   30 ming tushlik"
)
ONLY_TEXT = "✍️ Iltimos, xarajatni matn qilib yozing. Masalan: 50000 non"
UNKNOWN_COMMAND = "Bunday buyruq yo'q. Yordam uchun /yordam ni bosing."
SAVED_FALLBACK = "✅ Saqlandi"
LIMIT_REACHED = "⚠️ Bu oy uchun yozuvlar soni juda ko'p. Yangi yozuv saqlanmadi."
ERROR = "⚠️ Kechirasiz, xatolik yuz berdi. Birozdan keyin qayta urinib ko'ring."

NO_TODAY = "📅 Bugun hali xarajat yozilmagan."
NO_PERIOD = "📭 Bu davrda xarajat yozilmagan."
NOTHING_TO_UNDO = "Bu oyda o'chiradigan xarajat yo'q."
NOT_FOUND = "❗ {n}-raqamli xarajat bu oyda topilmadi. Raqamlarni «📋 Ro'yxat»dan ko'ring."

USAGE_EDIT = "Masalan: /tahrir 3 45000 non\n(raqamni «📋 Ro'yxat»dan oling)"
USAGE_DELETE = "Masalan: /ochirish 3\n(raqamni «📋 Ro'yxat»dan oling)"
USAGE_ADD = "Masalan:\n/qoshish 25.09 50000 non\n/qoshish 25.09 14:30 50000 non"
USAGE_MONTH = "Masalan: /oy yoki /oy 08.2026"
FUTURE_DATE = "❗ Kelajakdagi sanaga xarajat qo'shib bo'lmaydi."

UNDO_CONFIRM = "Shu xarajat o'chirilsinmi?\n\n{entry}"
BTN_YES_DELETE = "🗑 Ha, o'chirish"
BTN_NO = "❌ Yo'q"
DELETED = "🗑 O'chirildi: {entry}"
KEPT = "👌 O'chirilmadi."
ALREADY_CHANGED = "Bu yozuv allaqachon o'zgargan. «📋 Ro'yxat»ni qayta oching."

ADDED = "✅ Qo'shildi: {entry}"
EDITED = "✏️ O'zgartirildi: {entry}\nOldin: {old}"

REPORTS_ON = "🔔 Avtomatik hisobotlar yoqildi (yakshanba 12:00 da haftalik, oy oxirida oylik)."
REPORTS_OFF = "🔕 Avtomatik hisobotlar o'chirildi. Qayta yoqish uchun /hisobot ni bosing."


# ---------- formatting ----------

def num(amount: float) -> str:
    text = f"{amount:,.0f}" if float(amount).is_integer() else f"{amount:,.2f}"
    return text.replace(",", " ")


def money(amount: float) -> str:
    return f"{num(amount)} {CURRENCY}"


def month_name(year: int, month: int) -> str:
    return f"{MONTHS[month - 1]} {year}"


def weekday(day: date) -> str:
    return WEEKDAYS[day.weekday()]


def period(start: date, end: date) -> str:
    if start == end:
        return f"{start:%d.%m.%Y}"
    if start.year == end.year:
        return f"{start:%d.%m} – {end:%d.%m.%Y}"
    return f"{start:%d.%m.%Y} – {end:%d.%m.%Y}"


def entry_line(number: int | None, when: datetime | None, amount: float, reason: str, with_date: bool = True) -> str:
    prefix = f"{number}. " if number is not None else ""
    stamp = ""
    if when is not None:
        stamp = f"{when:%d.%m %H:%M}  " if with_date else f"{when:%H:%M}  "
    return f"{prefix}{stamp}{num(amount)}  {reason or 'izohsiz'}"


def entry_short(amount: float, reason: str) -> str:
    return f"{money(amount)}, {reason or 'izohsiz'}"


def top_reasons(entries, limit: int = 5) -> list[tuple[str, float]]:
    """Group spendings by reason (case-insensitive) and return the biggest groups."""
    groups: dict[str, list] = {}
    for _, amount, reason in entries:
        key = (reason or "izohsiz").strip().lower()
        label, total = groups.get(key, [reason or "izohsiz", 0])
        groups[key] = [label, total + amount]
    return sorted((tuple(v) for v in groups.values()), key=lambda g: -g[1])[:limit]


def summary(title: str, start: date, end: date, today: date, entries, show_days: bool) -> str:
    total = sum(amount for _, amount, _ in entries)
    days_counted = (min(end, today) - start).days + 1
    lines = [
        f"📊 {title}",
        f"📅 {period(start, end)}",
        "",
        f"💰 Jami: {money(total)}",
        f"🧾 Xarajatlar soni: {len(entries)} ta",
        f"📉 Kunlik o'rtacha: {money(round(total / max(days_counted, 1)))}",
    ]
    if show_days:
        per_day: dict[date, float] = {}
        for when, amount, _ in entries:
            per_day[when.date()] = per_day.get(when.date(), 0) + amount
        lines += ["", "Kunlar bo'yicha:"]
        day = start
        while day <= min(end, today):
            lines.append(f"{weekday(day)} {day:%d.%m}: {num(per_day.get(day, 0))}")
            day += timedelta(days=1)
    top = top_reasons(entries)
    if top:
        lines += ["", "🔝 Eng ko'p sarflangan:"]
        lines += [f"{i}. {label}: {money(amount)}" for i, (label, amount) in enumerate(top, 1)]
    return "\n".join(lines)


# ---------- password / security ----------

PASSWORD_INTRO = """🔐 Avval parol o'rnatamiz.

Ma'lumotlaringiz shu parol bilan shifrlanadi, shuning uchun uni faqat siz ocha olasiz: bot egasi ham, boshqa foydalanuvchilar ham ko'ra olmaydi.

⚠️ Parolni unutsangiz, ma'lumotlarni tiklab bo'lmaydi.
⚠️ Bot qayta ishga tushganda (masalan, yangilanganda) parolni qayta kiritishingiz kerak bo'ladi.

Kamida 6 belgidan iborat parolni yozing 👇
(Parol yozilgan xabarni bot avtomatik o'chirishga harakat qiladi.)"""
PASSWORD_AGAIN = "Yaxshi. Xatosiz bo'lishi uchun parolni yana bir marta yozing 👇"
PASSWORD_TOO_SHORT = "❗ Parol kamida 6 belgidan iborat bo'lishi kerak. Qayta yozing 👇"
PASSWORD_TOO_LONG = "❗ Parol juda uzun (ko'pi bilan 128 belgi). Qayta yozing 👇"
PASSWORD_MISMATCH = "❗ Parollar bir xil emas. Boshidan boshlaymiz, parolni yozing 👇"
PASSWORD_SET = "✅ Parol o'rnatildi. Endi xarajatlarni yozishingiz mumkin!"
PASSWORD_CHANGED = "✅ Parol almashtirildi."
LEGACY_ENCRYPTED = "🔐 Oldingi ma'lumotlaringiz ham shifrlandi."
PASSWORD_CHANGE_ASK_OLD = "🔑 Hozirgi parolingizni yozing 👇"
PASSWORD_CHANGE_ASK_NEW = "Yangi parolni yozing (kamida 6 belgi) 👇"
PASSWORD_DELETE_HINT = "🧹 Parol yozilgan xabarni chatdan o'chirib qo'ying."

LOCKED = """🔒 Ma'lumotlaringiz qulflangan.

Ochish uchun parolingizni yozing 👇
(Parolni unutgan bo'lsangiz: /tozalash, lekin bu barcha ma'lumotlarni o'chiradi.)"""
LOCKED_PENDING = "\n\n✍️ Yuborgan xarajatingiz parol kiritilgach saqlanadi."
UNLOCKED = "🔓 Ochildi. Xush kelibsiz!"
WRONG_PASSWORD = "❌ Parol noto'g'ri. Qayta urinib ko'ring 👇"
TOO_MANY_ATTEMPTS = "⏳ Juda ko'p noto'g'ri urinish. {minutes} daqiqadan keyin qayta urinib ko'ring."
PENDING_SAVED = "✅ Kutib turgan {n} ta xarajat saqlandi."

WIPE_ASK = """⚠️ Barcha xarajatlaringiz butunlay o'chiriladi va tiklab bo'lmaydi. Parol ham bekor bo'ladi.

Davom etamizmi?"""
BTN_WIPE_YES = "🗑 Ha, hammasini o'chir"
WIPE_DONE = "🗑 Barcha ma'lumotlaringiz o'chirildi."
WIPE_CANCELLED = "👌 Hech narsa o'chirilmadi."
