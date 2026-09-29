"""Spendwise: private Telegram bot that saves every message as a spending.

"50000 lunch" → a row in this month's spreadsheet. At the end of each month
the bot sends the month's file.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram import BotCommand, Bot, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from settings import Settings
from storage import SpendingStorage

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("spendwise")

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))

spendings = SpendingStorage(DATA_DIR)
settings = Settings.load(
    DATA_DIR / "settings.json", default_timezone=os.environ.get("TIMEZONE", "Asia/Tashkent")
)

REPORT_JOB = "monthly_report"
MAX_CATCH_UP_MONTHS = 3
TG_LIMIT = 4000

# Only react to new messages from the owner; edits of old messages are ignored.
OWNER = filters.User(user_id=OWNER_ID) & filters.ChatType.PRIVATE & filters.UpdateType.MESSAGE

# Amount: 50000 / 50 000 / 50,000 / 12.5 / 12,5 / 50k (k = thousand)
AMOUNT = r"(?P<num>\d{1,3}(?:[ ,]\d{3})+|\d+)(?:[.,](?P<frac>\d{1,2}))?(?P<mult>[kKкК])?"
SPEND_AMOUNT_FIRST = re.compile(rf"^{AMOUNT}(?:\s+(?P<reason>.*))?$", re.S)
SPEND_AMOUNT_LAST = re.compile(rf"^(?P<reason>.*?)\s+{AMOUNT}$", re.S)
FORMAT_HINT = 'Send it like "50000 lunch", "taxi 25 000" or "50k groceries".'

COMMANDS = [
    ("month", "This month's spreadsheet: /month 08.2026"),
    ("list", "This month's spendings as text"),
    ("today", "Today's spendings"),
    ("stats", "Spending by day and month overview"),
    ("add", "Add for another day: /add 25.09 50000 lunch"),
    ("edit", "Edit spending: /edit 3 45000 lunch"),
    ("delete", "Delete spending: /delete 3"),
    ("undo", "Delete the last spending"),
    ("settings", "Show current settings"),
    ("settime", "Monthly report time: /settime 23:59"),
    ("settz", "Timezone: /settz Asia/Tashkent"),
    ("report", "Monthly report on/off: /report off"),
    ("help", "Show help"),
]

HELP_TEXT = """\
💰 Spendwise

Send every spending as a message, and I save it to this month's spreadsheet:
  50000 lunch
  taxi 25 000
  12.5 coffee
  50k groceries  (k = thousand)

On the last day of each month at {report_time} ({timezone}) I send you that month's file.

Files and lists
/month: this month's spreadsheet with TOTAL (/month 08.2026 for another month)
/list: this month's spendings, numbered, with total (/list 08.2026)
/today: today's spendings and total
/stats: totals per day for the last week and a month overview

Fixing entries (numbers come from /list)
/add 25.09 50000 lunch: add a spending for another day (optional time: /add 25.09 14:30 50000 lunch)
/edit 3 45000 lunch: change the amount and reason of spending 3
/delete 3: delete spending 3
/undo: delete the last spending

Settings
/settings: show the current settings
/settime 23:59: change the monthly report time
/settz Asia/Tashkent: change the timezone
/report on|off: turn the automatic monthly report on or off"""


# ---------- helpers ----------

def tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def now() -> datetime:
    return datetime.now(tz())


def today() -> date:
    return now().date()


def local_minute(dt: datetime) -> datetime:
    """Telegram UTC timestamp → naive local time, rounded down to the minute."""
    return dt.astimezone(tz()).replace(tzinfo=None, second=0, microsecond=0)


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
    """'50000 lunch' / 'taxi 25 000' / '50k food' → (amount, reason)."""
    text = text.strip()
    m = SPEND_AMOUNT_FIRST.match(text) or SPEND_AMOUNT_LAST.match(text)
    if not m:
        return None
    amount = float(re.sub(r"[ ,]", "", m["num"]) + "." + (m["frac"] or "0"))
    if m["mult"]:
        amount *= 1000
    if amount <= 0:
        return None
    if amount.is_integer():
        amount = int(amount)
    return amount, (m["reason"] or "").strip()


def fmt_amount(amount: float) -> str:
    text = f"{amount:,.0f}" if float(amount).is_integer() else f"{amount:,.2f}"
    return text.replace(",", " ")


def fmt_month(year: int, month: int) -> str:
    return f"{month:02d}.{year}"


def prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def is_last_day_of_month(day: date) -> bool:
    return (day + timedelta(days=1)).month != day.month


def split_args(update: Update, maxsplit: int) -> list[str]:
    """Split the raw command text, keeping newlines/spacing in the final part."""
    return (update.effective_message.text or "").split(maxsplit=maxsplit)[1:]


def month_arg(context: ContextTypes.DEFAULT_TYPE) -> tuple[int, int] | None:
    if not context.args:
        current = today()
        return current.year, current.month
    return parse_month(context.args[0])


def day_total(day: date) -> float:
    return sum(
        amount for when, amount, _ in spendings.entries(day.year, day.month)
        if when is not None and when.date() == day
    )


def month_total(year: int, month: int) -> float:
    return sum(amount for _, amount, _ in spendings.entries(year, month))


def saved_text(number: int, when: datetime, amount: float, reason: str) -> str:
    return (
        f"💰 #{number} saved: {fmt_amount(amount)}, {reason or 'no reason'}\n"
        f"{when:%d.%m}: {fmt_amount(day_total(when.date()))} · "
        f"{fmt_month(when.year, when.month)}: {fmt_amount(month_total(when.year, when.month))}"
    )


async def reply_long(update: Update, text: str) -> None:
    chunk = ""
    for line in text.splitlines():
        if len(chunk) + len(line) + 1 > TG_LIMIT:
            await update.effective_message.reply_text(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        await update.effective_message.reply_text(chunk)


async def send_month_file(bot: Bot, year: int, month: int, caption_prefix: str = "") -> None:
    data, count, total = spendings.export(year, month)
    await bot.send_document(
        chat_id=OWNER_ID,
        document=data,
        filename=f"spendings_{fmt_month(year, month)}.xlsx",
        caption=f"{caption_prefix}{fmt_month(year, month)}: {count} spendings, total {fmt_amount(total)}",
    )


# ---------- monthly report ----------

def due_report_month(on_schedule: bool = False) -> tuple[int, int]:
    """The most recent month whose report should already have been sent."""
    current = now()
    hour, minute = settings.report_hour_minute
    if is_last_day_of_month(current.date()) and (on_schedule or current.time() >= time(hour, minute)):
        return current.year, current.month
    return prev_month(current.year, current.month)


async def send_due_reports(bot: Bot, on_schedule: bool = False) -> None:
    """Send every monthly report that is due but not sent yet (e.g. after downtime)."""
    due = due_report_month(on_schedule)
    if settings.last_report_month is None:
        # First start: nothing is owed yet.
        settings.last_report_month = f"{due[0]:04d}-{due[1]:02d}"
        settings.save()
        return

    year, month = map(int, settings.last_report_month.split("-"))
    pending = []
    ym = next_month(year, month)
    while ym <= due:
        pending.append(ym)
        ym = next_month(*ym)

    for ym in pending[-MAX_CATCH_UP_MONTHS:]:
        prefix = "📊 Monthly spendings " if ym == due else "📊 Missed monthly spendings "
        await send_month_file(bot, *ym, caption_prefix=prefix)
        settings.last_report_month = f"{ym[0]:04d}-{ym[1]:02d}"
        settings.save()


async def report_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    # Runs every day at the report time; only sends on the last day of the month.
    try:
        await send_due_reports(context.bot, on_schedule=True)
    except Exception:
        log.exception("Monthly report failed, retrying in 5 minutes")
        context.job_queue.run_once(retry_job, when=300)


async def retry_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await send_due_reports(context.bot)
    except Exception:
        log.exception("Report retry failed, retrying in 5 minutes")
        context.job_queue.run_once(retry_job, when=300)


def schedule_report(app: Application) -> None:
    for job in app.job_queue.get_jobs_by_name(REPORT_JOB):
        job.schedule_removal()
    if settings.report_enabled:
        hour, minute = settings.report_hour_minute
        app.job_queue.run_daily(
            report_job, time=time(hour, minute, tzinfo=tz()), name=REPORT_JOB
        )
        log.info(
            "Monthly report scheduled at %s %s on the last day of each month",
            settings.report_time, settings.timezone,
        )


# ---------- messages ----------

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    parsed = parse_spending(msg.text)
    if parsed is None:
        await msg.reply_text(f"❗ No amount found. {FORMAT_HINT}")
        return
    when = local_minute(msg.date)
    number = spendings.append(when, *parsed)
    await msg.reply_text(saved_text(number, when, *parsed))


async def on_stranger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat and update.effective_chat.type == "private":
        await update.effective_message.reply_text(
            f"This is a private bot. Your Telegram ID is {update.effective_user.id}."
        )


# ---------- commands ----------

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        HELP_TEXT.format(report_time=settings.report_time, timezone=settings.timezone)
    )


async def cmd_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ym = month_arg(context)
    if ym is None:
        await update.effective_message.reply_text("Usage: /month or /month 08.2026")
        return
    if ym != (today().year, today().month) and not spendings.exists(*ym):
        await update.effective_message.reply_text(f"No spendings for {fmt_month(*ym)}.")
        return
    await send_month_file(context.bot, *ym)


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ym = month_arg(context)
    if ym is None:
        await update.effective_message.reply_text("Usage: /list or /list 08.2026")
        return
    entries = spendings.entries(*ym)
    if not entries:
        await update.effective_message.reply_text(f"No spendings for {fmt_month(*ym)}.")
        return
    total = sum(a for _, a, _ in entries)
    lines = [f"💰 {fmt_month(*ym)}: {len(entries)} spendings, total {fmt_amount(total)}", ""]
    for i, (when, amount, reason) in enumerate(entries, 1):
        stamp = when.strftime("%d.%m %H:%M") if when else "?"
        lines.append(f"{i}. {stamp}  {fmt_amount(amount)}  {reason[:200]}")
    await reply_long(update, "\n".join(lines))


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current = today()
    entries = [
        (i, when, amount, reason)
        for i, (when, amount, reason) in enumerate(spendings.entries(current.year, current.month), 1)
        if when is not None and when.date() == current
    ]
    if not entries:
        await update.effective_message.reply_text("No spendings today.")
        return
    total = sum(e[2] for e in entries)
    lines = [f"💰 Today ({current:%d.%m}): {fmt_amount(total)}", ""]
    for i, when, amount, reason in entries:
        lines.append(f"{i}. {when:%H:%M}  {fmt_amount(amount)}  {reason[:200]}")
    await reply_long(update, "\n".join(lines))


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current = today()
    days = [current - timedelta(days=offset) for offset in range(6, -1, -1)]
    totals = [day_total(d) for d in days]
    peak = max(totals) or 1
    lines = ["📈 Last 7 days", ""]
    for day, total in zip(days, totals):
        bar = "█" * round(total / peak * 12)
        lines.append(f"{day:%a %d.%m}  {fmt_amount(total):>12}  {bar}")

    entries = spendings.entries(current.year, current.month)
    total = sum(a for _, a, _ in entries)
    lines += ["", f"This month ({fmt_month(current.year, current.month)})"]
    lines.append(f"Total: {fmt_amount(total)} in {len(entries)} spendings")
    lines.append(f"Average per day: {fmt_amount(round(total / current.day))}")
    if entries:
        when, amount, reason = max(entries, key=lambda e: e[1])
        stamp = f" ({when:%d.%m})" if when else ""
        lines.append(f"Biggest: {fmt_amount(amount)}, {reason or 'no reason'}{stamp}")

    prev = prev_month(current.year, current.month)
    if spendings.exists(*prev):
        lines.append(f"Last month ({fmt_month(*prev)}): {fmt_amount(month_total(*prev))}")
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    usage = "Usage: /add 25.09 50000 lunch  or  /add 25.09 14:30 50000 lunch"
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
    if day is None and hm is None:
        await update.effective_message.reply_text(usage)
        return

    parsed = parse_spending(rest)
    if parsed is None:
        await update.effective_message.reply_text(usage)
        return
    when = datetime.combine(day or today(), time(*(hm or (12, 0))))
    number = spendings.insert_sorted(when, *parsed)
    await update.effective_message.reply_text(saved_text(number, when, *parsed))


async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = split_args(update, 2)
    parsed = parse_spending(args[1]) if len(args) == 2 else None
    if not args or not args[0].isdigit() or parsed is None:
        await update.effective_message.reply_text("Usage: /edit 3 45000 lunch  (numbers from /list)")
        return
    current = today()
    old = spendings.update(current.year, current.month, int(args[0]), *parsed)
    if old is None:
        await update.effective_message.reply_text(f"Spending {args[0]} not found this month.")
        return
    await update.effective_message.reply_text(
        f"✓ Spending {args[0]} updated: {fmt_amount(parsed[0])}, {parsed[1] or 'no reason'}\n"
        f"Was: {fmt_amount(old[1])}, {old[2] or 'no reason'}"
    )


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /delete 3  (numbers from /list)")
        return
    current = today()
    removed = spendings.delete(current.year, current.month, int(context.args[0]))
    if removed is None:
        await update.effective_message.reply_text(f"Spending {context.args[0]} not found this month.")
        return
    await update.effective_message.reply_text(
        f"🗑 Deleted: {fmt_amount(removed[1])}, {removed[2] or 'no reason'}"
    )


async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current = today()
    removed = spendings.delete(current.year, current.month)
    if removed is None:
        await update.effective_message.reply_text("Nothing to undo this month.")
        return
    await update.effective_message.reply_text(
        f"↩️ Removed: {fmt_amount(removed[1])}, {removed[2] or 'no reason'}"
    )


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "⚙️ Settings\n"
        f"Timezone: {settings.timezone}\n"
        f"Monthly report: {'on' if settings.report_enabled else 'off'}, "
        f"last day of month at {settings.report_time}\n"
        f"Last report sent for: {settings.last_report_month or 'none yet'}\n"
        f"Now: {now():%d.%m.%Y %H:%M}"
    )


async def cmd_settime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    hm = parse_hhmm(context.args[0]) if context.args else None
    if hm is None:
        await update.effective_message.reply_text("Usage: /settime 23:59")
        return
    settings.report_time = f"{hm[0]:02d}:{hm[1]:02d}"
    settings.save()
    schedule_report(context.application)
    await update.effective_message.reply_text(
        f"✓ Monthly report time set to {settings.report_time} ({settings.timezone})."
    )


async def cmd_settz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Usage: /settz Asia/Tashkent")
        return
    try:
        ZoneInfo(context.args[0])
    except (ZoneInfoNotFoundError, ValueError):
        await update.effective_message.reply_text(
            f"Unknown timezone '{context.args[0]}'. Example: Asia/Tashkent, Europe/Berlin."
        )
        return
    settings.timezone = context.args[0]
    settings.save()
    schedule_report(context.application)
    await update.effective_message.reply_text(
        f"✓ Timezone set to {settings.timezone}. Local time now: {now():%d.%m.%Y %H:%M}"
    )


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    arg = context.args[0].lower() if context.args else ""
    if arg not in ("on", "off"):
        await update.effective_message.reply_text("Usage: /report on  or  /report off")
        return
    settings.report_enabled = arg == "on"
    if settings.report_enabled:
        # Don't flood with backlog from the time the report was off.
        due = due_report_month()
        settings.last_report_month = f"{due[0]:04d}-{due[1]:02d}"
    settings.save()
    schedule_report(context.application)
    await update.effective_message.reply_text(
        f"✓ Monthly report {'enabled at ' + settings.report_time if settings.report_enabled else 'disabled'}."
    )


# ---------- app wiring ----------

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Error while handling update", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(f"⚠️ Error: {context.error}")
        except Exception:
            pass


async def post_init(app: Application) -> None:
    await app.bot.set_my_commands([BotCommand(c, d) for c, d in COMMANDS])
    schedule_report(app)
    if settings.report_enabled:
        try:
            await send_due_reports(app.bot)
        except Exception:
            log.exception("Catch-up of missed reports failed")
    log.info("Spendwise started for owner %s", OWNER_ID)


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    handlers = {
        "start": cmd_help,
        "help": cmd_help,
        "month": cmd_month,
        "list": cmd_list,
        "today": cmd_today,
        "stats": cmd_stats,
        "add": cmd_add,
        "edit": cmd_edit,
        "delete": cmd_delete,
        "undo": cmd_undo,
        "settings": cmd_settings,
        "settime": cmd_settime,
        "settz": cmd_settz,
        "report": cmd_report,
    }
    for name, callback in handlers.items():
        app.add_handler(CommandHandler(name, callback, filters=OWNER))
    app.add_handler(MessageHandler(OWNER & filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(
        MessageHandler(~filters.User(user_id=OWNER_ID) & filters.UpdateType.MESSAGE, on_stranger)
    )
    app.add_error_handler(on_error)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
