"""Spendwise: multi-user Telegram spending tracker with an Uzbek UI.

Anyone can use the bot. Every user's spendings live in their own directory
(data/users/<telegram_id>/), and every handler resolves that directory from
the sender's own Telegram ID, so users can never see each other's data.

The files are encrypted with a key that only the user's password can unlock
(see vault.py). The unlocked key is kept in memory only, so after a restart
each user has to enter their password again. Data older than 12 months is
deleted automatically.

Group chats keep their own shared spendings (data/groups/<chat_id>/). A group
has no password; its key is wrapped with the personal key of each admin who
set it up (see GroupVault), so unlocking your own vault also opens your groups.
In groups the bot only reacts to commands and never reads ordinary messages.
"""
from __future__ import annotations

import asyncio
import calendar
import logging
import os
import re
import shutil
import zlib
from datetime import date, datetime, time, timedelta
from pathlib import Path
from time import monotonic
from zoneinfo import ZoneInfo

from telegram import (
    Bot,
    BotCommand,
    BotCommandScopeAllGroupChats,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from cryptography.fernet import Fernet
from telegram.constants import ChatMemberStatus, ChatType
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
from storage import GroupStorage, SpendingStorage, encrypt_legacy, member_totals, purge_old, shift_month
from users import UserRegistry
from vault import MAX_PASSWORD, MIN_PASSWORD, GroupVault, Vault

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
RETENTION_MONTHS = 12            # keep the current month plus this many earlier months
PURGE_AT = time(3, 0)            # daily cleanup of expired months
MAX_PASSWORD_FAILS = 5
LOCKOUT_SECONDS = 600
MAX_PENDING = 20         # messages held in memory while a user is locked
TG_LIMIT = 4000

users = UserRegistry(DATA_DIR / "users.json")
groups = UserRegistry(DATA_DIR / "groups.json")

# Unlocked data keys, in memory only. Never written to disk or logged.
CIPHERS: dict[int, Fernet] = {}
GROUP_KEYS: dict[int, bytes] = {}
# /x messages that arrived while their group was locked: chat id -> [(when, amount, reason, uid, name, msg)]
GROUP_PENDING: dict[int, list] = {}

# Personal commands work in private chats, group commands in groups; edits of old messages are ignored.
PRIVATE = filters.ChatType.PRIVATE & filters.UpdateType.MESSAGE
GROUP = filters.ChatType.GROUPS & filters.UpdateType.MESSAGE

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


def user_dir(uid: int) -> Path:
    return DATA_DIR / "users" / str(int(uid))


def store_for(uid: int) -> SpendingStorage | None:
    """The user's own storage, or None while they are locked (or have no vault yet)."""
    cipher = CIPHERS.get(int(uid))
    return SpendingStorage(user_dir(uid), cipher) if cipher else None


def register(uid: int) -> None:
    current = now()
    if users.register(
        uid,
        last_week=due_week_end(current).isoformat(),
        last_month=month_key(*due_month(current)),
    ):
        log.info("New user %s", uid)


async def gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> SpendingStorage | None:
    """The storage this chat works on, or None after saying why not.

    In a private chat that is the sender's own storage (asking for their password
    if locked); in a group chat it is the group's. Group members are never
    registered in users.json.
    """
    if update.effective_chat.type != ChatType.PRIVATE:
        return await ggate(update, context)
    register(update.effective_user.id)
    store = store_for(update.effective_user.id)
    if store is None:
        await prompt_password(update, context)
    return store


def group_dir(chat_id: int) -> Path:
    return DATA_DIR / "groups" / str(int(chat_id))


def group_store_for(chat_id: int) -> GroupStorage | None:
    """The group's storage, or None while it is locked (no key holder has unlocked it)."""
    key = GROUP_KEYS.get(int(chat_id))
    return GroupStorage(group_dir(chat_id), Fernet(key)) if key else None


async def ggate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> GroupStorage | None:
    """The group's unlocked storage, or None after telling the chat why not."""
    chat_id = update.effective_chat.id
    if not GroupVault(group_dir(chat_id)).exists():
        await update.effective_message.reply_text(t.GROUP_NOT_SET_UP)
        return None
    store = group_store_for(chat_id)
    if store is None:
        await update.effective_message.reply_text(t.GROUP_LOCKED)
    return store


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    except TelegramError:
        return False
    return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)


def author_of(update: Update) -> tuple[int, str]:
    user = update.effective_user
    return user.id, " ".join(user.full_name.split())[:40] or "Noma'lum"


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
    text = t.summary(title, start, end, today(), entries, show_days)
    if isinstance(store, GroupStorage):
        text += "\n\n" + t.member_breakdown(store.member_totals(start, end))
    await bot.send_message(chat_id, text)
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


async def send_reports(
    bot: Bot, registry: UserRegistry, chat_id: int, store: SpendingStorage | None
) -> bool:
    """Send a chat (a user or a group) the latest weekly/monthly report it has not received yet.

    Locked chats are skipped (their data cannot be read); they get the report
    as soon as they unlock. Returns True if a network problem means "retry later".
    """
    user = registry.get(chat_id)
    if user is None or store is None or not user.get("reports", True):
        return False
    current = now()
    week_end = due_week_end(current)
    week = week_end.isoformat()
    ym = due_month(current)
    month = month_key(*ym)
    try:
        if user.get("last_week", "") < week:
            start = week_end - timedelta(days=6)
            await send_period_report(
                bot, chat_id, store, "Haftalik hisobot", start, week_end,
                week_filename(start, week_end), show_days=True,
            )
            registry.update(chat_id, last_week=week)
        if user.get("last_month", "") < month:
            start, end = month_bounds(*ym)
            await send_period_report(
                bot, chat_id, store, f"Oylik hisobot: {t.month_name(*ym)}", start, end,
                month_filename(*ym), show_days=False,
            )
            registry.update(chat_id, last_month=month)
    except Forbidden:
        # The user blocked the bot; don't keep trying.
        log.info("Chat %s blocked the bot, skipping reports", chat_id)
        registry.update(chat_id, last_week=week, last_month=month)
    except NetworkError:
        log.warning("Network error sending report to %s, will retry", chat_id)
        return True
    except Exception:
        log.exception("Report for chat %s failed", chat_id)
        registry.update(chat_id, last_week=week, last_month=month)
    return False


async def send_user_reports(bot: Bot, uid: int) -> bool:
    return await send_reports(bot, users, uid, store_for(uid))


async def send_group_reports(bot: Bot, chat_id: int) -> bool:
    return await send_reports(bot, groups, chat_id, group_store_for(chat_id))


async def send_due_reports(bot: Bot) -> bool:
    """Send every unlocked user and group their due reports. True means "retry later"."""
    retry = False
    for uid in users.ids():
        retry |= await send_user_reports(bot, uid)
        await asyncio.sleep(0.1)  # stay well under Telegram's rate limits
    for chat_id in groups.ids():
        retry |= await send_group_reports(bot, chat_id)
        await asyncio.sleep(0.1)
    return retry


async def report_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    if await send_due_reports(context.bot):
        context.job_queue.run_once(report_job, when=300)


def schedule_reports(app: Application) -> None:
    # Both jobs run daily; send_due_reports decides whether anything is due
    # (Sunday for weekly, last day of month for monthly).
    app.job_queue.run_daily(report_job, time=WEEKLY_REPORT_AT.replace(tzinfo=TZ), name="weekly")
    app.job_queue.run_daily(report_job, time=MONTHLY_REPORT_AT.replace(tzinfo=TZ), name="monthly")
    app.job_queue.run_daily(purge_job, time=PURGE_AT.replace(tzinfo=TZ), name="purge")


# ---------- retention ----------

def purge_expired() -> int:
    """Delete month files older than RETENTION_MONTHS for every user and group (no keys needed)."""
    current = today()
    keep_from = shift_month(current.year, current.month, -RETENTION_MONTHS)
    deleted = sum(
        purge_old(d, keep_from)
        for root in (DATA_DIR / "users", DATA_DIR / "groups") if root.is_dir()
        for d in root.iterdir() if d.is_dir()
    )
    if deleted:
        log.info("Deleted %d expired month files", deleted)
    return deleted


async def purge_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await asyncio.to_thread(purge_expired)


# ---------- password flow ----------

FLOW_KEYS = ("state", "pw1", "old_pw")


def clear_flow(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in FLOW_KEYS:
        context.user_data.pop(key, None)


async def say(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs) -> None:
    # Not msg.reply_text: the user's message (a password) may already be deleted.
    await context.bot.send_message(update.effective_chat.id, text, **kwargs)


async def prompt_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask the sender to unlock (existing vault) or to set a password (new user)."""
    uid = update.effective_user.id
    if Vault(user_dir(uid)).exists():
        context.user_data["state"] = "unlock"
        text = t.LOCKED + (t.LOCKED_PENDING if context.user_data.get("pending") else "")
    else:
        context.user_data["state"] = "set1"
        text = t.PASSWORD_INTRO
    # The main keyboard is hidden so that a button tap is never mistaken for a password.
    await say(update, context, text, reply_markup=ReplyKeyboardRemove())


def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD:
        return t.PASSWORD_TOO_SHORT
    if len(password) > MAX_PASSWORD:
        return t.PASSWORD_TOO_LONG
    return None


def register_failure(context: ContextTypes.DEFAULT_TYPE) -> str:
    ud = context.user_data
    ud["fails"] = ud.get("fails", 0) + 1
    if ud["fails"] >= MAX_PASSWORD_FAILS:
        ud["fails"] = 0
        ud["locked_until"] = monotonic() + LOCKOUT_SECONDS
        return t.TOO_MANY_ATTEMPTS.format(minutes=LOCKOUT_SECONDS // 60)
    return t.WRONG_PASSWORD


async def flush_pending(update: Update, context: ContextTypes.DEFAULT_TYPE, store: SpendingStorage) -> None:
    """Save the messages that arrived while the user was locked."""
    saved = 0
    for when, amount, reason, msg in context.user_data.pop("pending", []):
        if len(store.entries(when.year, when.month)) >= MAX_ENTRIES_PER_MONTH:
            break
        store.append(when, amount, reason)
        saved += 1
        try:
            await msg.set_reaction("👍")
        except TelegramError:
            pass
    if saved:
        await say(update, context, t.PENDING_SAVED.format(n=saved))


def held_groups(uid: int) -> list[Path]:
    """Directories of the groups whose key `uid` holds."""
    root = DATA_DIR / "groups"
    if not root.is_dir():
        return []
    return [d for d in root.iterdir() if d.is_dir() and uid in GroupVault(d).holders()]


async def flush_group_pending(bot: Bot, chat_id: int) -> None:
    """Save the /x messages that arrived while the group was locked."""
    store = group_store_for(chat_id)
    saved = 0
    for when, amount, reason, uid, name, msg in GROUP_PENDING.pop(chat_id, []):
        if len(store.entries(when.year, when.month)) >= MAX_ENTRIES_PER_MONTH:
            break
        store.append(when, amount, reason, (uid, name))
        saved += 1
        try:
            await msg.set_reaction("👍")
        except TelegramError:
            pass
    if saved:
        await bot.send_message(chat_id, t.PENDING_SAVED.format(n=saved))


async def open_groups_of(bot: Bot, uid: int, cipher: Fernet) -> None:
    """A key holder just unlocked their vault: open the groups whose key they hold."""
    for d in await asyncio.to_thread(held_groups, uid):
        chat_id = int(d.name)
        if chat_id in GROUP_KEYS:
            continue
        key = GroupVault(d).unlock(uid, cipher)
        if key is None:  # the holder's vault was re-created since: this slot is dead
            continue
        GROUP_KEYS[chat_id] = key
        try:
            await flush_group_pending(bot, chat_id)
            await send_group_reports(bot, chat_id)  # reports that were due while locked
        except TelegramError:
            log.warning("Could not post to group %s after unlocking it", chat_id)


async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE, password: str) -> None:
    """One step of set / unlock / change-password. `password` is never logged or stored."""
    msg = update.effective_message
    ud = context.user_data
    uid = update.effective_user.id
    state = ud["state"]

    deleted = True
    try:
        await msg.delete()
    except TelegramError:
        deleted = False
    hint = "" if deleted else "\n\n" + t.PASSWORD_DELETE_HINT

    if state in ("unlock", "chg_old") and ud.get("locked_until", 0) > monotonic():
        minutes = max(1, round((ud["locked_until"] - monotonic()) / 60))
        await say(update, context, t.TOO_MANY_ATTEMPTS.format(minutes=minutes))
        return

    vault = Vault(user_dir(uid))
    if state == "unlock":
        cipher = await asyncio.to_thread(vault.unlock, password)
        if cipher is None:
            await say(update, context, register_failure(context))
            return
        ud.pop("fails", None)
        CIPHERS[uid] = cipher
        ud.pop("state", None)
        await say(update, context, t.UNLOCKED + hint, reply_markup=MAIN_KEYBOARD)
        await flush_pending(update, context, store_for(uid))
        await send_user_reports(context.bot, uid)  # reports that were due while locked
        await open_groups_of(context.bot, uid, cipher)

    elif state in ("set1", "chg1"):
        problem = password_problem(password)
        if problem:
            await say(update, context, problem)
            return
        ud["pw1"] = password
        ud["state"] = "set2" if state == "set1" else "chg2"
        await say(update, context, t.PASSWORD_AGAIN)

    elif state == "set2":
        first = ud.pop("pw1", None)
        if password != first:
            ud["state"] = "set1"
            await say(update, context, t.PASSWORD_MISMATCH)
            return
        cipher = await asyncio.to_thread(vault.create, password)
        CIPHERS[uid] = cipher
        converted = encrypt_legacy(user_dir(uid), cipher)
        ud.pop("state", None)
        await say(
            update, context,
            t.PASSWORD_SET + ("\n" + t.LEGACY_ENCRYPTED if converted else "") + hint,
            reply_markup=MAIN_KEYBOARD,
        )
        await flush_pending(update, context, store_for(uid))

    elif state == "chg_old":
        if await asyncio.to_thread(vault.unlock, password) is None:
            await say(update, context, register_failure(context))
            return
        ud.pop("fails", None)
        ud["old_pw"] = password
        ud["state"] = "chg1"
        await say(update, context, t.PASSWORD_CHANGE_ASK_NEW)

    elif state == "chg2":
        first, old = ud.pop("pw1", None), ud.pop("old_pw", None)
        if password != first or old is None:
            ud["state"] = "chg1"
            await say(update, context, t.PASSWORD_MISMATCH)
            return
        ud.pop("state", None)
        changed = await asyncio.to_thread(vault.change_password, old, password)
        await say(update, context, (t.PASSWORD_CHANGED if changed else t.ERROR) + hint,
                  reply_markup=MAIN_KEYBOARD)


# ---------- messages ----------

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    text = msg.text.strip()
    uid = update.effective_user.id
    register(uid)

    if handler := BUTTONS.get(text):
        clear_flow(context)  # a button tap always abandons a half-finished password step
        await handler(update, context)
        return
    if context.user_data.get("state"):
        await handle_password(update, context, msg.text)  # exact text: no stripping
        return

    store = store_for(uid)
    parsed = parse_spending(text)
    if store is None:
        # Locked: keep the spending in memory only, and save it after unlocking.
        pending = context.user_data.setdefault("pending", [])
        if parsed and len(pending) < MAX_PENDING:
            pending.append((local_minute(msg.date), *parsed, msg))
        await prompt_password(update, context)
        return
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
    uid = update.effective_user.id
    register(uid)
    if store_for(uid):
        await update.effective_message.reply_text(t.WELCOME, reply_markup=MAIN_KEYBOARD)
        return
    if not Vault(user_dir(uid)).exists():
        await update.effective_message.reply_text(t.WELCOME, reply_markup=ReplyKeyboardRemove())
    await prompt_password(update, context)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    register(update.effective_user.id)
    await update.effective_message.reply_text(t.HELP, reply_markup=MAIN_KEYBOARD)


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = await gate(update, context)
    if store is None:
        return
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
    store = await gate(update, context)
    if store is None:
        return
    end = today()
    start = end - timedelta(days=end.weekday())  # Monday
    if not await send_period_report(
        context.bot, update.effective_chat.id, store, "Bu hafta", start, end,
        week_filename(start, end), show_days=True,
    ):
        await update.effective_message.reply_text(t.NO_PERIOD)


async def cmd_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = await gate(update, context)
    if store is None:
        return
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
    store = await gate(update, context)
    if store is None:
        return
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


def last_7_days_lines(store: SpendingStorage, current: date) -> list[str]:
    days = [current - timedelta(days=offset) for offset in range(6, -1, -1)]
    recent = store.entries_between(days[0], current)
    totals = [sum(a for w, a, _ in recent if w.date() == d) for d in days]
    peak = max(totals) or 1
    lines = ["📈 Oxirgi 7 kun", ""]
    for day, total in zip(days, totals):
        lines.append(f"{t.weekday(day)} {day:%d.%m}  {t.num(total):>11}  {'▇' * round(total / peak * 10)}")
    return lines


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = await gate(update, context)
    if store is None:
        return
    current = today()
    lines = last_7_days_lines(store, current)

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
    store = await gate(update, context)
    if store is None:
        return
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
    author = author_of(update) if isinstance(store, GroupStorage) else None
    number = store.insert_sorted(when, *parsed, author=author)
    await update.effective_message.reply_text(
        t.ADDED.format(entry=t.entry_line(number, when, *parsed))
    )


async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = await gate(update, context)
    if store is None:
        return
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
    store = await gate(update, context)
    if store is None:
        return
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
    store = await gate(update, context)
    if store is None:
        return
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
    if (query.data or "").startswith("gdel:"):
        await on_group_delete(update, context)
        return
    await query.answer()
    uid = query.from_user.id  # every action below acts on the tapping user's own data only
    data = query.data or ""

    if data == "keep":
        await query.edit_message_text(t.KEPT)
    elif data == "wipe:no":
        await query.edit_message_text(t.WIPE_CANCELLED)
    elif data == "wipe:yes":
        CIPHERS.pop(uid, None)
        clear_flow(context)
        context.user_data.pop("pending", None)
        shutil.rmtree(user_dir(uid), ignore_errors=True)
        release_groups(uid)
        await query.edit_message_text(t.WIPE_DONE)
        await prompt_password(update, context)
    elif m := re.fullmatch(r"del:(\d{4}):(\d{1,2}):(\d+)", data):
        year, month, number = map(int, m.groups())
        store = store_for(uid)
        if store is None:  # the bot was restarted since the button was shown
            await query.edit_message_text(t.LOCKED)
            context.user_data["state"] = "unlock"
            return
        # Only delete if that entry is still the last one (nothing changed meanwhile).
        if len(store.entries(year, month)) != number:
            await query.edit_message_text(t.ALREADY_CHANGED)
            return
        removed = store.delete(year, month, number)
        if removed is None:
            await query.edit_message_text(t.ALREADY_CHANGED)
            return
        await query.edit_message_text(t.DELETED.format(entry=t.entry_short(removed[1], removed[2])))


async def cmd_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Change the password (needs the current one)."""
    store = await gate(update, context)
    if store is None:
        return
    context.user_data["state"] = "chg_old"
    await update.effective_message.reply_text(t.PASSWORD_CHANGE_ASK_OLD, reply_markup=ReplyKeyboardRemove())


def release_groups(uid: int) -> None:
    """The user's vault is gone, so their group key slots are dead: drop them.

    A group nobody else holds the key of can never be opened again, so it is deleted.
    """
    for d in held_groups(uid):
        if GroupVault(d).remove_holder(uid) == 0:
            chat_id = int(d.name)
            shutil.rmtree(d, ignore_errors=True)
            groups.remove(chat_id)
            GROUP_KEYS.pop(chat_id, None)
            GROUP_PENDING.pop(chat_id, None)
            log.info("Group %s deleted: its last key holder wiped their data", chat_id)


async def cmd_wipe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete all of the sender's data, also the way out when the password is forgotten."""
    uid = update.effective_user.id
    register(uid)
    sole = [d for d in held_groups(uid) if GroupVault(d).holders() == [uid]]
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(t.BTN_WIPE_YES, callback_data="wipe:yes"),
        InlineKeyboardButton(t.BTN_NO, callback_data="wipe:no"),
    ]])
    warning = t.WIPE_GROUPS_WARN.format(n=len(sole)) if sole else ""
    await update.effective_message.reply_text(t.WIPE_ASK + warning, reply_markup=keyboard)


async def clear_flow_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Any command abandons a half-finished password step (runs before the command itself)."""
    clear_flow(context)


def toggle_reports(registry: UserRegistry, chat_id: int) -> bool:
    """Flip automatic reports on/off for a user or group. Returns the new state."""
    enabled = not registry.get(chat_id).get("reports", True)
    fields = {"reports": enabled}
    if enabled:
        # Don't send reports for the period while they were switched off.
        current = now()
        fields.update(last_week=due_week_end(current).isoformat(), last_month=month_key(*due_month(current)))
    registry.update(chat_id, **fields)
    return enabled


async def cmd_reports(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    register(uid)
    enabled = toggle_reports(users, uid)
    await update.effective_message.reply_text(t.REPORTS_ON if enabled else t.REPORTS_OFF)


# ---------- group chats ----------
# /hafta /oy /qoshish also work in groups: gate() hands them the group's storage.

async def cmd_group_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/guruh in a private chat: how to use the bot in a family group."""
    register(update.effective_user.id)
    await update.effective_message.reply_text(t.GROUP_PRIVATE_INFO, reply_markup=MAIN_KEYBOARD)


async def g_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(t.GROUP_HELP)


async def g_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/guruh: set the group up (admin with an unlocked vault), or show its status."""
    msg = update.effective_message
    chat_id = update.effective_chat.id
    user = update.effective_user
    vault = GroupVault(group_dir(chat_id))
    if vault.exists():
        if args_of(context)[:1] == ["kalit"]:
            await add_key_holder(update, context, vault)
            return
        state = t.GROUP_STATE_OPEN if chat_id in GROUP_KEYS else t.GROUP_STATE_LOCKED
        await msg.reply_text(t.GROUP_STATUS.format(state=state, holders=len(vault.holders())))
        return
    if not await is_admin(update, context):
        await msg.reply_text(t.GROUP_NEED_ADMIN)
        return
    cipher = CIPHERS.get(user.id)
    if cipher is None:
        await msg.reply_text(t.GROUP_NEED_PERSONAL.format(link=f"https://t.me/{context.bot.username}"))
        return
    GROUP_KEYS[chat_id] = vault.create(user.id, cipher)
    current = now()
    groups.register(
        chat_id, last_week=due_week_end(current).isoformat(), last_month=month_key(*due_month(current))
    )
    log.info("New group %s", chat_id)
    await msg.reply_text(t.GROUP_READY)


async def add_key_holder(update: Update, context: ContextTypes.DEFAULT_TYPE, vault: GroupVault) -> None:
    """/guruh kalit: another admin also holds the key, so the group survives one person's loss."""
    msg = update.effective_message
    user = update.effective_user
    key = GROUP_KEYS.get(update.effective_chat.id)
    if key is None:
        await msg.reply_text(t.GROUP_KEY_NEED_OPEN)
    elif not await is_admin(update, context):
        await msg.reply_text(t.GROUP_NEED_ADMIN)
    elif user.id in vault.holders():
        await msg.reply_text(t.GROUP_KEY_ALREADY)
    elif (cipher := CIPHERS.get(user.id)) is None:
        await msg.reply_text(t.GROUP_NEED_PERSONAL.format(link=f"https://t.me/{context.bot.username}"))
    else:
        vault.add_holder(user.id, cipher, key)
        await msg.reply_text(t.GROUP_KEY_ADDED)


def entry_stamp(when: datetime, amount: float, reason: str) -> str:
    """Short fingerprint of an entry, so a stale button can never hit a different entry."""
    return f"{when:%Y%m%d%H%M}{zlib.crc32(f'{amount}|{reason}'.encode()) & 0xFFFFFF:06x}"


def group_numbered(store: GroupStorage, year: int, month: int) -> list[tuple]:
    """(number, when, amount, reason, author id, author name) for the month."""
    return [(i, *entry) for i, entry in enumerate(store.authored(year, month), 1)]


async def g_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/x 50000 non: record a group spending."""
    msg = update.effective_message
    chat_id = update.effective_chat.id
    args = split_args(update, 1)
    parsed = parse_spending(args[0]) if args else None
    if parsed is None:
        await msg.reply_text(t.USAGE_X)
        return
    if not GroupVault(group_dir(chat_id)).exists():
        await msg.reply_text(t.GROUP_NOT_SET_UP)
        return
    author = author_of(update)
    when = local_minute(msg.date)
    store = group_store_for(chat_id)
    if store is None:
        # Locked: keep the spending in memory only, and save it once the group is opened.
        pending = GROUP_PENDING.setdefault(chat_id, [])
        kept = len(pending) < MAX_PENDING
        if kept:
            pending.append((when, *parsed, *author, msg))
        await msg.reply_text(t.GROUP_LOCKED + (t.GROUP_LOCKED_PENDING if kept else ""))
        return
    if len(store.entries(when.year, when.month)) >= MAX_ENTRIES_PER_MONTH:
        await msg.reply_text(t.LIMIT_REACHED)
        return
    store.append(when, *parsed, author)
    try:
        await msg.set_reaction("👍")
    except TelegramError:
        await msg.reply_text(t.SAVED_FALLBACK)


async def g_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = await ggate(update, context)
    if store is None:
        return
    day = today()
    entries = [e for e in group_numbered(store, day.year, day.month) if e[1] and e[1].date() == day]
    if not entries:
        await update.effective_message.reply_text(t.NO_TODAY)
        return
    total = sum(e[2] for e in entries)
    lines = [f"📅 Bugun ({day:%d.%m}): {t.money(total)}", ""]
    lines += [
        t.group_entry_line(n, when, amount, reason, name, with_date=False)
        for n, when, amount, reason, _, name in entries
    ]
    await reply_long(update, "\n".join(lines))


async def g_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = await ggate(update, context)
    if store is None:
        return
    args = args_of(context)
    ym = parse_month(args[0]) if args else (today().year, today().month)
    if ym is None:
        await update.effective_message.reply_text(t.USAGE_MONTH)
        return
    entries = group_numbered(store, *ym)
    if not entries:
        await update.effective_message.reply_text(t.NO_PERIOD)
        return
    total = sum(e[2] for e in entries)
    lines = [f"📋 {t.month_name(*ym)}: {len(entries)} ta, jami {t.money(total)}", ""]
    lines += [t.group_entry_line(n, when, amount, reason, name) for n, when, amount, reason, _, name in entries]
    lines += ["", t.member_breakdown(member_totals([e[1:] for e in entries]))]
    lines += ["", "✏️ /tahrir 3 45000 non   🗑 /ochirish 3"]
    await reply_long(update, "\n".join(lines))


async def g_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = await ggate(update, context)
    if store is None:
        return
    current = today()
    lines = last_7_days_lines(store, current)
    month = store.authored(current.year, current.month)
    month_total = sum(e[1] for e in month)
    lines += [
        "",
        f"🗓 {t.month_name(current.year, current.month)}",
        f"💰 Jami: {t.money(month_total)} ({len(month)} ta)",
        f"📉 Kunlik o'rtacha: {t.money(round(month_total / current.day))}",
    ]
    if month:
        when, amount, reason, _, name = max(month, key=lambda e: e[1])
        lines.append(f"🔝 Eng katta: {t.entry_short(amount, reason)} ({name}, {when:%d.%m})")
        lines += ["", t.member_breakdown(member_totals(month))]
    prev = prev_month(current.year, current.month)
    if store.exists(*prev):
        prev_total = sum(a for _, a, _ in store.entries(*prev))
        lines += ["", f"⏮ {t.month_name(*prev)}: {t.money(prev_total)}"]
    await update.effective_message.reply_text("\n".join(lines))


async def may_change(
    update: Update, context: ContextTypes.DEFAULT_TYPE, store: GroupStorage, year: int, month: int, number: int
) -> bool:
    """Only an entry's author or a group admin may change it. Replies and returns False otherwise."""
    msg = update.effective_message
    entries = store.authored(year, month)
    if not 1 <= number <= len(entries):
        await msg.reply_text(t.NOT_FOUND.format(n=number))
        return False
    entry = entries[number - 1]
    if update.effective_user.id == entry[3]:
        return True
    if not await is_admin(update, context):
        await msg.reply_text(t.NOT_YOURS.format(name=entry[4]))
        return False
    # The admin check took a moment: make sure the numbering did not shift meanwhile.
    if store.authored(year, month)[number - 1:number] != [entry]:
        await msg.reply_text(t.ALREADY_CHANGED)
        return False
    return True


async def g_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = await ggate(update, context)
    if store is None:
        return
    args = split_args(update, 2)
    parsed = parse_spending(args[1]) if len(args) == 2 else None
    if not args or not args[0].isdigit() or parsed is None:
        await update.effective_message.reply_text(t.USAGE_EDIT)
        return
    current = today()
    number = int(args[0])
    if not await may_change(update, context, store, current.year, current.month, number):
        return
    old = store.update(current.year, current.month, number, *parsed)
    await update.effective_message.reply_text(
        t.EDITED.format(entry=t.entry_short(*parsed), old=t.entry_short(old[1], old[2]))
    )


async def g_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = await ggate(update, context)
    if store is None:
        return
    args = args_of(context)
    if not args or not args[0].isdigit():
        await update.effective_message.reply_text(t.USAGE_DELETE)
        return
    current = today()
    number = int(args[0])
    if not await may_change(update, context, store, current.year, current.month, number):
        return
    removed = store.delete(current.year, current.month, number)
    await update.effective_message.reply_text(
        t.DELETED.format(entry=t.entry_short(removed[1], removed[2]))
    )


async def g_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask for confirmation before deleting the sender's own latest spending of this month."""
    store = await ggate(update, context)
    if store is None:
        return
    current = today()
    mine = [e for e in group_numbered(store, current.year, current.month) if e[4] == update.effective_user.id]
    if not mine:
        await update.effective_message.reply_text(t.NOTHING_TO_UNDO)
        return
    number, when, amount, reason, _, name = mine[-1]
    # The fingerprint lets the callback notice that the numbering changed meanwhile.
    token = f"{current.year}:{current.month}:{number}:{entry_stamp(when, amount, reason)}"
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(t.BTN_YES_DELETE, callback_data=f"gdel:{token}"),
        InlineKeyboardButton(t.BTN_NO, callback_data="keep"),
    ]])
    await update.effective_message.reply_text(
        t.UNDO_CONFIRM.format(entry=t.entry_line(None, when, amount, reason)), reply_markup=keyboard,
    )


async def on_group_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    m = re.fullmatch(r"gdel:(\d{4}):(\d{1,2}):(\d+):(\d{12}[0-9a-f]{6})", query.data or "")
    chat = query.message.chat
    if not m or chat.type == ChatType.PRIVATE:
        await query.answer()
        return
    year, month, number = int(m[1]), int(m[2]), int(m[3])
    store = group_store_for(chat.id)
    if store is None:  # the bot was restarted since the button was shown
        await query.answer()
        await query.edit_message_text(t.GROUP_LOCKED)
        return
    entries = store.authored(year, month)
    entry = entries[number - 1] if 1 <= number <= len(entries) else None
    if entry is None or entry[0] is None or entry_stamp(entry[0], entry[1], entry[2]) != m[4]:
        await query.answer()
        await query.edit_message_text(t.ALREADY_CHANGED)
        return
    if entry[3] != query.from_user.id:  # someone else pressed the button
        await query.answer(t.NOT_YOUR_ENTRY, show_alert=True)
        return
    removed = store.delete(year, month, number)
    await query.answer()
    await query.edit_message_text(t.DELETED.format(entry=t.entry_short(removed[1], removed[2])))


async def g_reports(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if groups.get(chat_id) is None:
        await update.effective_message.reply_text(t.GROUP_NOT_SET_UP)
    elif not await is_admin(update, context):
        await update.effective_message.reply_text(t.GROUP_REPORTS_ADMIN)
    else:
        enabled = toggle_reports(groups, chat_id)
        await update.effective_message.reply_text(t.GROUP_REPORTS_ON if enabled else t.GROUP_REPORTS_OFF)


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
    await app.bot.set_my_commands(
        [BotCommand(c, d) for c, d in t.GROUP_COMMANDS], scope=BotCommandScopeAllGroupChats()
    )
    try:
        await app.bot.set_my_description(t.BOT_DESCRIPTION)
        await app.bot.set_my_short_description(t.BOT_SHORT_DESCRIPTION)
    except TelegramError:
        log.warning("Could not set bot description")
    schedule_reports(app)
    await asyncio.to_thread(purge_expired)
    log.info(
        "Spendwise started, %d users and %d groups (all locked until a key holder enters their password)",
        len(users.ids()), len(groups.ids()),
    )


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
        "parol": cmd_password,
        "tozalash": cmd_wipe,
        "guruh": cmd_group_info,
    }
    group_handlers = {
        "start": g_help,
        "yordam": g_help,
        "help": g_help,
        "guruh": g_setup,
        "x": g_add,
        "bugun": g_today,
        "hafta": cmd_week,
        "oy": cmd_month,
        "royxat": g_list,
        "statistika": g_stats,
        "qoshish": cmd_add,
        "tahrir": g_edit,
        "ochirish": g_delete,
        "bekor": g_undo,
        "hisobot": g_reports,
    }
    app.add_handler(MessageHandler(PRIVATE & filters.COMMAND, clear_flow_on_command), group=-1)
    for name, callback in handlers.items():
        app.add_handler(CommandHandler(name, callback, filters=PRIVATE))
    # In groups the bot only answers its own commands and never reads ordinary messages.
    for name, callback in group_handlers.items():
        app.add_handler(CommandHandler(name, callback, filters=GROUP))
    app.add_handler(MessageHandler(PRIVATE & filters.COMMAND, on_unknown_command))
    app.add_handler(MessageHandler(PRIVATE & filters.TEXT, on_text))
    app.add_handler(MessageHandler(PRIVATE & ~filters.TEXT, on_other))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_error_handler(on_error)

    app.run_polling(allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY])


if __name__ == "__main__":
    main()
