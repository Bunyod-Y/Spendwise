"""Spendwise: multi-user Telegram spending tracker with an Uzbek UI.

Anyone can use the bot. Every user's spendings live in their own directory
(data/users/<telegram_id>/), and every handler resolves that directory from
the sender's own Telegram ID, so users can never see each other's data.
"""
from __future__ import annotations

import asyncio
import calendar
import logging
import os
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import (
    Bot,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.error import Forbidden, NetworkError, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import texts as t
from storage import SpendingStorage
from users import UserRegistry

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("spendwise")

BOT_TOKEN = os.environ["BOT_TOKEN"]
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
TZ = ZoneInfo(os.environ.get("TIMEZONE", "Asia/Tashkent"))

WEEKLY_REPORT_AT = time(12, 0)   # every Sunday
MONTHLY_REPORT_AT = time(21, 0)  # last day of every month
MAX_ENTRIES_PER_MONTH = 3000     # per user; protects the server's disk
TG_LIMIT = 4000

users = UserRegistry(DATA_DIR / "users.json")

# Private chats only; edits of old messages are ignored.
PRIVATE = filters.ChatType.PRIVATE & filters.UpdateType.MESSAGE

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    t.KEYBOARD, resize_keyboard=True, is_persistent=True,
    input_field_placeholder=t.INPUT_PLACEHOLDER,
)

# Amount: 50000 / 50 000 / 50,000 / 12.5 / 12,5 / 50k / 30 ming / 1.5 mln
AMOUNT = (
    r"(?P<num>\d{1,3}(?:[ ,]\d{3})+|\d+)(?:[.,](?P<frac>\d{1,2}))?"
    r"(?:\s*(?P<mult>(?i:k|к|ming|mln|million|млн))(?![^\W\d_]))?"
)
MULTIPLIERS = {"k": 1e3, "к": 1e3, "ming": 1e3, "mln": 1e6, "million": 1e6, "млн": 1e6}
SPEND_AMOUNT_FIRST = re.compile(rf"^{AMOUNT}(?:\s+(?P<reason>.*))?$", re.S)
SPEND_AMOUNT_LAST = re.compile(rf"^(?P<reason>.*?)\s+{AMOUNT}$", re.S)
CURRENCY = r"(?i:so['ʻ’`‘]?m|sum|сум|сўм)"
CURRENCY_AT_END = re.compile(rf"(?:^|\s+){CURRENCY}[.!]?\s*$")
CURRENCY_AT_START = re.compile(rf"^{CURRENCY}(?![^\W\d_])[\s,.:-]*")


# ---------- helpers ----------

def now() -> datetime:
    return datetime.now(TZ)


def today() -> date:
    return now().date()


def local_minute(dt: datetime) -> datetime:
    """Telegram UTC timestamp → naive local time, rounded down to the minute."""
    return dt.astimezone(TZ).replace(tzinfo=None, second=0, microsecond=0)


def store_for(uid: int) -> SpendingStorage:
    return SpendingStorage(DATA_DIR / "users" / str(int(uid)))


def store_of(update: Update) -> SpendingStorage:
    """The sender's own storage. Registers the sender on first contact."""
    uid = update.effective_user.id
    current = now()
    if users.register(
        uid,
        last_week=due_week_end(current).isoformat(),
        last_month=month_key(*due_month(current)),
    ):
        log.info("New user %s", uid)
    return store_for(uid)


def args_of(context: ContextTypes.DEFAULT_TYPE) -> list[str]:
    return context.args or []


def split_args(update: Update, maxsplit: int) -> list[str]:
    """Split the raw command text, keeping newlines/spacing in the final part."""
    return (update.effective_message.text or "").split(maxsplit=maxsplit)[1:]


def parse_date(text: str) -> date | None:
    text = text.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    if re.fullmatch(r"\d{1,2}\.\d{1,2}", text):  # dd.mm → current year
        try:
            return datetime.strptime(f"{text}.{today().year}", "%d.%m.%Y").date()
        except ValueError:
            return None
    return None


def parse_hhmm(text: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", text.strip())
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def parse_month(text: str) -> tuple[int, int] | None:
    """'09.2026' / '9.2026' / '2026-09' / '09' (current year) → (year, month)."""
    text = text.strip()
    if m := re.fullmatch(r"(\d{1,2})[./](\d{4})", text):
        month, year = int(m[1]), int(m[2])
    elif m := re.fullmatch(r"(\d{4})-(\d{1,2})", text):
        year, month = int(m[1]), int(m[2])
    elif re.fullmatch(r"\d{1,2}", text):
        year, month = today().year, int(text)
    else:
        return None
    return (year, month) if 1 <= month <= 12 else None


def parse_spending(text: str) -> tuple[float, str] | None:
    """'50000 non' / 'taksi 25 000' / '30 ming tushlik' / '1.5 mln ijara' → (amount, reason)."""
    text = CURRENCY_AT_END.sub("", text.strip())
    m = SPEND_AMOUNT_FIRST.match(text) or SPEND_AMOUNT_LAST.match(text)
    if not m:
        return None
    amount = float(re.sub(r"[ ,]", "", m["num"]) + "." + (m["frac"] or "0"))
    if m["mult"]:
        amount *= MULTIPLIERS[m["mult"].lower()]
    amount = round(amount, 2)
    if not 0 < amount < 1e13:
        return None
    if amount.is_integer():
        amount = int(amount)
    reason = CURRENCY_AT_START.sub("", (m["reason"] or "").strip())
    return amount, reason.strip(" -–—:,")


def month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def numbered_month(store: SpendingStorage, year: int, month: int):
    return [(i, *entry) for i, entry in enumerate(store.entries(year, month), 1)]


async def reply_long(update: Update, text: str, **kwargs) -> None:
    chunk = ""
    for line in text.splitlines():
        if len(chunk) + len(line) + 1 > TG_LIMIT:
            await update.effective_message.reply_text(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        await update.effective_message.reply_text(chunk, **kwargs)


async def send_period_report(
    bot: Bot, chat_id: int, store: SpendingStorage,
    title: str, start: date, end: date, filename: str, show_days: bool,
) -> bool:
    """Send a summary message plus an Excel file. Returns False if the period is empty."""
    entries = store.entries_between(start, end)
    if not entries:
        return False
    await bot.send_message(chat_id, t.summary(title, start, end, today(), entries, show_days))
    data, _, _ = store.export_range(start, end, "Xarajatlar")
    await bot.send_document(chat_id, document=data, filename=filename)
    return True


def week_filename(start: date, end: date) -> str:
    return f"xarajatlar_{start:%d.%m}-{end:%d.%m.%Y}.xlsx"


def month_filename(year: int, month: int) -> str:
    return f"xarajatlar_{month:02d}.{year}.xlsx"


# ---------- automatic reports ----------

def due_week_end(current: datetime) -> date:
    """Sunday of the latest week whose report time has passed."""
    days_since_sunday = (current.weekday() + 1) % 7
    sunday = current.date() - timedelta(days=days_since_sunday)
    if days_since_sunday == 0 and current.time() < WEEKLY_REPORT_AT:
        sunday -= timedelta(days=7)
    return sunday


def due_month(current: datetime) -> tuple[int, int]:
    """The latest month whose report time has passed."""
    last_day = calendar.monthrange(current.year, current.month)[1]
    if current.day == last_day and current.time() >= MONTHLY_REPORT_AT:
        return current.year, current.month
    return prev_month(current.year, current.month)


async def send_due_reports(bot: Bot) -> bool:
    """Send each user the latest weekly/monthly report they have not received yet.

    Returns True if a network problem means it should be retried later.
    """
    current = now()
    week_end = due_week_end(current)
    week = week_end.isoformat()
    ym = due_month(current)
    month = month_key(*ym)
    retry = False

    for uid in users.ids():
        user = users.get(uid)
        if not user.get("reports", True):
            continue
        store = store_for(uid)
        try:
            if user.get("last_week", "") < week:
                start = week_end - timedelta(days=6)
                await send_period_report(
                    bot, uid, store, "Haftalik hisobot", start, week_end,
                    week_filename(start, week_end), show_days=True,
                )
                users.update(uid, last_week=week)
            if user.get("last_month", "") < month:
                start, end = month_bounds(*ym)
                await send_period_report(
                    bot, uid, store, f"Oylik hisobot: {t.month_name(*ym)}", start, end,
                    month_filename(*ym), show_days=False,
                )
                users.update(uid, last_month=month)
        except Forbidden:
            # The user blocked the bot; don't keep trying.
            log.info("User %s blocked the bot, skipping reports", uid)
            users.update(uid, last_week=week, last_month=month)
        except NetworkError:
            log.warning("Network error sending report to %s, will retry", uid)
            retry = True
        except Exception:
            log.exception("Report for user %s failed", uid)
            users.update(uid, last_week=week, last_month=month)
        await asyncio.sleep(0.1)  # stay well under Telegram's rate limits
    return retry


async def report_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    if await send_due_reports(context.bot):
        context.job_queue.run_once(report_job, when=300)


def schedule_reports(app: Application) -> None:
    # Both jobs run daily; send_due_reports decides whether anything is due
    # (Sunday for weekly, last day of month for monthly).
    app.job_queue.run_daily(report_job, time=WEEKLY_REPORT_AT.replace(tzinfo=TZ), name="weekly")
    app.job_queue.run_daily(report_job, time=MONTHLY_REPORT_AT.replace(tzinfo=TZ), name="monthly")


# ---------- messages ----------

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    text = msg.text.strip()
    if handler := BUTTONS.get(text):
        await handler(update, context)
        return

    store = store_of(update)
    parsed = parse_spending(text)
    if parsed is None:
        await msg.reply_text(t.NOT_UNDERSTOOD, reply_markup=MAIN_KEYBOARD)
        return
    when = local_minute(msg.date)
    if len(store.entries(when.year, when.month)) >= MAX_ENTRIES_PER_MONTH:
        await msg.reply_text(t.LIMIT_REACHED)
        return
    store.append(when, *parsed)
    try:
        await msg.set_reaction("👍")
    except TelegramError:
        await msg.reply_text(t.SAVED_FALLBACK)


async def on_other(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(t.ONLY_TEXT, reply_markup=MAIN_KEYBOARD)


async def on_unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(t.UNKNOWN_COMMAND, reply_markup=MAIN_KEYBOARD)


# ---------- commands ----------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store_of(update)
    await update.effective_message.reply_text(t.WELCOME, reply_markup=MAIN_KEYBOARD)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store_of(update)
    await update.effective_message.reply_text(t.HELP, reply_markup=MAIN_KEYBOARD)


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = store_of(update)
    day = today()
    entries = [e for e in numbered_month(store, day.year, day.month) if e[1] and e[1].date() == day]
    if not entries:
        await update.effective_message.reply_text(t.NO_TODAY)
        return
    total = sum(e[2] for e in entries)
    lines = [f"📅 Bugun ({day:%d.%m}): {t.money(total)}", ""]
    lines += [t.entry_line(n, when, amount, reason, with_date=False) for n, when, amount, reason in entries]
    await reply_long(update, "\n".join(lines))


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = store_of(update)
    end = today()
    start = end - timedelta(days=end.weekday())  # Monday
    if not await send_period_report(
        context.bot, update.effective_chat.id, store, "Bu hafta", start, end,
        week_filename(start, end), show_days=True,
    ):
        await update.effective_message.reply_text(t.NO_PERIOD)


async def cmd_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = store_of(update)
    args = args_of(context)
    ym = parse_month(args[0]) if args else (today().year, today().month)
    if ym is None:
        await update.effective_message.reply_text(t.USAGE_MONTH)
        return
    start, end = month_bounds(*ym)
    if not await send_period_report(
        context.bot, update.effective_chat.id, store, f"Oylik hisobot: {t.month_name(*ym)}",
        start, end, month_filename(*ym), show_days=False,
    ):
        await update.effective_message.reply_text(t.NO_PERIOD)


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = store_of(update)
    args = args_of(context)
    ym = parse_month(args[0]) if args else (today().year, today().month)
    if ym is None:
        await update.effective_message.reply_text(t.USAGE_MONTH)
        return
    entries = numbered_month(store, *ym)
    if not entries:
        await update.effective_message.reply_text(t.NO_PERIOD)
        return
    total = sum(e[2] for e in entries)
    lines = [f"📋 {t.month_name(*ym)}: {len(entries)} ta, jami {t.money(total)}", ""]
    lines += [t.entry_line(*e) for e in entries]
    lines += ["", "✏️ /tahrir 3 45000 non   🗑 /ochirish 3"]
    await reply_long(update, "\n".join(lines))


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = store_of(update)
    current = today()
    days = [current - timedelta(days=offset) for offset in range(6, -1, -1)]
    recent = store.entries_between(days[0], current)
    totals = [sum(a for w, a, _ in recent if w.date() == d) for d in days]
    peak = max(totals) or 1
    lines = ["📈 Oxirgi 7 kun", ""]
    for day, total in zip(days, totals):
        lines.append(f"{t.weekday(day)} {day:%d.%m}  {t.num(total):>11}  {'▇' * round(total / peak * 10)}")

    month_entries = store.entries(current.year, current.month)
    month_total = sum(a for _, a, _ in month_entries)
    lines += [
        "",
        f"🗓 {t.month_name(current.year, current.month)}",
        f"💰 Jami: {t.money(month_total)} ({len(month_entries)} ta)",
        f"📉 Kunlik o'rtacha: {t.money(round(month_total / current.day))}",
    ]
    if month_entries:
        when, amount, reason = max(month_entries, key=lambda e: e[1])
        lines.append(f"🔝 Eng katta: {t.entry_short(amount, reason)} ({when:%d.%m})")
    prev = prev_month(current.year, current.month)
    if store.exists(*prev):
        prev_total = sum(a for _, a, _ in store.entries(*prev))
        lines.append(f"⏮ {t.month_name(*prev)}: {t.money(prev_total)}")
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = store_of(update)
    args = split_args(update, 1)
    rest = args[0] if args else ""

    token, _, tail = rest.partition(" ")
    day = parse_date(token)
    if day is not None:
        rest = tail.strip()
        token, _, tail = rest.partition(" ")
    hm = parse_hhmm(token)
    if hm is not None:
        rest = tail.strip()
    parsed = parse_spending(rest) if (day or hm) else None
    if parsed is None:
        await update.effective_message.reply_text(t.USAGE_ADD)
        return
    when = datetime.combine(day or today(), time(*(hm or (12, 0))))
    if when.date() > today():
        await update.effective_message.reply_text(t.FUTURE_DATE)
        return
    if len(store.entries(when.year, when.month)) >= MAX_ENTRIES_PER_MONTH:
        await update.effective_message.reply_text(t.LIMIT_REACHED)
        return
    number = store.insert_sorted(when, *parsed)
    await update.effective_message.reply_text(
        t.ADDED.format(entry=t.entry_line(number, when, *parsed))
    )


async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = store_of(update)
    args = split_args(update, 2)
    parsed = parse_spending(args[1]) if len(args) == 2 else None
    if not args or not args[0].isdigit() or parsed is None:
        await update.effective_message.reply_text(t.USAGE_EDIT)
        return
    current = today()
    old = store.update(current.year, current.month, int(args[0]), *parsed)
    if old is None:
        await update.effective_message.reply_text(t.NOT_FOUND.format(n=args[0]))
        return
    await update.effective_message.reply_text(
        t.EDITED.format(entry=t.entry_short(*parsed), old=t.entry_short(old[1], old[2]))
    )


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = store_of(update)
    args = args_of(context)
    if not args or not args[0].isdigit():
        await update.effective_message.reply_text(t.USAGE_DELETE)
        return
    current = today()
    removed = store.delete(current.year, current.month, int(args[0]))
    if removed is None:
        await update.effective_message.reply_text(t.NOT_FOUND.format(n=args[0]))
        return
    await update.effective_message.reply_text(
        t.DELETED.format(entry=t.entry_short(removed[1], removed[2]))
    )


async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask for confirmation before deleting the most recent spending of this month."""
    store = store_of(update)
    current = today()
    entries = store.entries(current.year, current.month)
    if not entries:
        await update.effective_message.reply_text(t.NOTHING_TO_UNDO)
        return
    number = len(entries)
    when, amount, reason = entries[-1]
    token = f"{current.year}:{current.month}:{number}"
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(t.BTN_YES_DELETE, callback_data=f"del:{token}"),
        InlineKeyboardButton(t.BTN_NO, callback_data="keep"),
    ]])
    await update.effective_message.reply_text(
        t.UNDO_CONFIRM.format(entry=t.entry_line(None, when, amount, reason)),
        reply_markup=keyboard,
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == "keep":
        await query.edit_message_text(t.KEPT)
        return
    m = re.fullmatch(r"del:(\d{4}):(\d{1,2}):(\d+)", query.data or "")
    if not m:
        return
    year, month, number = map(int, m.groups())
    # Always the tapping user's own storage.
    store = store_for(query.from_user.id)
    # Only delete if that entry is still the last one (nothing changed meanwhile).
    if len(store.entries(year, month)) != number:
        await query.edit_message_text(t.ALREADY_CHANGED)
        return
    removed = store.delete(year, month, number)
    if removed is None:
        await query.edit_message_text(t.ALREADY_CHANGED)
        return
    await query.edit_message_text(t.DELETED.format(entry=t.entry_short(removed[1], removed[2])))


async def cmd_reports(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store_of(update)
    uid = update.effective_user.id
    enabled = not users.get(uid).get("reports", True)
    fields = {"reports": enabled}
    if enabled:
        # Don't send reports for the period while they were switched off.
        current = now()
        fields.update(last_week=due_week_end(current).isoformat(), last_month=month_key(*due_month(current)))
    users.update(uid, **fields)
    await update.effective_message.reply_text(t.REPORTS_ON if enabled else t.REPORTS_OFF)


BUTTONS = {
    t.BTN_TODAY: cmd_today,
    t.BTN_WEEK: cmd_week,
    t.BTN_MONTH: cmd_month,
    t.BTN_LIST: cmd_list,
    t.BTN_STATS: cmd_stats,
    t.BTN_UNDO: cmd_undo,
    t.BTN_HELP: cmd_help,
}


# ---------- app wiring ----------

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Error while handling update", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(t.ERROR)
        except TelegramError:
            pass


async def post_init(app: Application) -> None:
    await app.bot.set_my_commands([BotCommand(c, d) for c, d in t.COMMANDS])
    try:
        await app.bot.set_my_description(t.BOT_DESCRIPTION)
        await app.bot.set_my_short_description(t.BOT_SHORT_DESCRIPTION)
    except TelegramError:
        log.warning("Could not set bot description")
    schedule_reports(app)
    try:
        await send_due_reports(app.bot)
    except Exception:
        log.exception("Catch-up of missed reports failed")
    log.info("Spendwise started, %d users", len(users.ids()))


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    handlers = {
        "start": cmd_start,
        "yordam": cmd_help,
        "help": cmd_help,
        "bugun": cmd_today,
        "hafta": cmd_week,
        "oy": cmd_month,
        "royxat": cmd_list,
        "statistika": cmd_stats,
        "qoshish": cmd_add,
        "tahrir": cmd_edit,
        "ochirish": cmd_delete,
        "bekor": cmd_undo,
        "hisobot": cmd_reports,
    }
    for name, callback in handlers.items():
        app.add_handler(CommandHandler(name, callback, filters=PRIVATE))
    app.add_handler(MessageHandler(PRIVATE & filters.COMMAND, on_unknown_command))
    app.add_handler(MessageHandler(PRIVATE & filters.TEXT, on_text))
    app.add_handler(MessageHandler(PRIVATE & ~filters.TEXT, on_other))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_error_handler(on_error)

    app.run_polling(allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY])


if __name__ == "__main__":
    main()
