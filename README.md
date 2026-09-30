# Spendwise 💰

A Telegram bot that keeps track of your spending. Write an expense as a normal message, and the bot saves it, sends weekly and monthly reports with an Excel file, and can also track shared spending in a family group.

- **Personal tracking:** every user has a private ledger that only they can open.
- **Group tracking:** add the bot to a family group and it totals who spent how much.
- **Encrypted at rest:** data is encrypted with a key that only the user's password (or, for groups, a group admin's password) can unlock. Even the server owner cannot read the files on disk.
- **Reports:** automatic weekly and monthly summaries plus on-demand reports, each with an Excel file.

> The bot's interface (messages, buttons, command names) is in **Uzbek**. This README is in English. Command names are listed below so you know what to type.

## Contents

1. [Quick start](#quick-start)
2. [Recording expenses](#recording-expenses)
3. [Commands](#commands)
4. [Group mode](#group-mode)
5. [Reports](#reports)
6. [Privacy and security](#privacy-and-security)
7. [Deployment](#deployment)
8. [Operations](#operations)
9. [Project layout](#project-layout)
10. [Limits and known limitations](#limits-and-known-limitations)

---

## Quick start

1. Open the bot and press **Start**.
2. Choose a password (at least 6 characters) and repeat it to confirm. The bot tries to delete the messages containing your password.
3. Send an expense, for example `50000 non`. The bot reacts with 👍 when it is saved.

Use the buttons under the input field to see what you spent:

| Button | What it does |
|---|---|
| 📅 Bugun (Today) | Today's expenses |
| 📆 Bu hafta (This week) | Weekly report + Excel file |
| 🗓 Bu oy (This month) | Monthly report + Excel file |
| 📋 Ro'yxat (List) | All expenses this month, with numbers |
| 📈 Statistika (Statistics) | Last 7 days, month total, daily average, biggest expense |
| ↩️ Oxirgisini o'chirish (Delete last) | Delete the most recent entry (asks for confirmation) |
| ❓ Yordam (Help) | Help text |

## Recording expenses

Just write a message with an amount and an optional note, in either order:

```
50000 non
non 50000
taksi 25 000 so'm
30 ming tushlik
1.5 mln ijara
50k benzin
```

Understood amount formats: `50000`, `50 000`, `50,000`, `12.5`, `50k`, `30 ming` (thousand), `1.5 mln` (million). A trailing `so'm` is ignored. The time of the entry is the time you sent the message.

## Commands

### Personal chat

| Command | What it does |
|---|---|
| `/bugun` | Today's expenses |
| `/hafta` | This week's report + Excel |
| `/oy` or `/oy 08.2026` | Monthly report + Excel (current or given month) |
| `/royxat` | This month's expenses with numbers (`/royxat 08.2026` for another month) |
| `/statistika` | Statistics |
| `/tahrir 3 45000 non` | Change expense number 3 (numbers come from `/royxat`, current month only) |
| `/ochirish 3` | Delete expense number 3 (current month only) |
| `/bekor` | Delete the last expense (with confirmation) |
| `/qoshish 25.09 50000 non` | Add an expense on another day (`/qoshish 25.09 14:30 50000 non` with a time). Future dates are rejected |
| `/hisobot` | Turn automatic weekly/monthly reports on or off |
| `/parol` | Change your password |
| `/tozalash` | Delete **all** your data (also the way out if you forgot your password) |
| `/guruh` | Explains how to use the bot in a group |
| `/yordam` | Help |

### Group chat

See [Group mode](#group-mode).

## Group mode

Add the bot to a family group and members record shared spending together. The bot tells you how much each person spent and what the group spent in total. Your personal expenses stay separate and are never visible to the group.

### Setting a group up (once)

1. Add the bot to the group. It does not need permission to read messages: in groups it only reacts to commands and never reads ordinary conversation.
2. A group **admin** opens the bot in a private chat, presses **Start**, and sets and enters a password. This is the admin's personal key (see [Group encryption](#group-encryption)).
3. In the group, that same admin sends `/guruh`. Only a group admin can set a group up.

Group members do **not** need to register, open the bot privately, or set a password.

### Using it (every member)

| Command | What it does |
|---|---|
| `/x 50000 non` | Record an expense. The bot remembers who wrote it |
| `/bugun` | Today's group expenses, with names |
| `/hafta` | Weekly report: total, **who spent how much**, Excel file |
| `/oy` or `/oy 08.2026` | Monthly report, same content |
| `/royxat` | This month's expenses with numbers, names, and each person's share |
| `/statistika` | Last 7 days, month total, daily average, biggest expense, each person's share |
| `/tahrir 3 45000 non` | Change your own expense number 3 |
| `/ochirish 3` | Delete your own expense number 3 |
| `/bekor` | Delete your own last expense (with confirmation; only you can press the button) |
| `/qoshish 25.09 50000 non` | Add an expense on another day |
| `/hisobot` | Turn the group's automatic reports on or off (**admin only**) |
| `/guruh` | Show the group's status (open/locked, number of key holders) |
| `/guruh kalit` | Become an extra key holder (**admin only**, see below) |

Who can change what: everyone can edit or delete **only their own** entries. Group admins can change any entry.

The group Excel report has three sheets: `Xarajatlar` (every expense with the author's name), `Kunlik jami` (daily totals), and `Kim bo'yicha` (per-person count and total).

### Group encryption

A group has no password, because anything typed in a group chat is visible to everyone. Instead:

- The group gets its own random key.
- That key is stored only in **wrapped** form: encrypted separately with the personal data key of each **key holder** (the admin who set the group up, plus any admin who later runs `/guruh kalit`).
- When the bot restarts, all groups are **locked**. As soon as a key holder unlocks their own vault by entering their password in the private chat, their groups open automatically.
- While a group is locked, `/x` messages (up to 20 per group) are held in memory and saved once the group opens. Other commands answer that the group is locked.

**Tip:** have a second admin run `/guruh kalit`, so the group can still be opened if one person is away or forgets their password.

### Group notes

- If the **only** key holder of a group wipes their data with `/tozalash`, the group's data is deleted too, because it could never be opened again. The bot warns them first.
- If a normal group is upgraded to a supergroup, Telegram changes its chat ID. Run `/guruh` again to start fresh.
- Members' display names and Telegram IDs are stored inside the encrypted monthly files, not in `users.json` or `groups.json`.
- The same 12-month retention applies to groups.

## Reports

All times are Tashkent time (configurable, see [Configuration](#configuration)).

| Report | When |
|---|---|
| **Weekly** | Every Sunday at **12:00 noon**, covering Monday to Sunday |
| **Monthly** | On the last day of each month at **21:00** |

- Personal reports go to the user; group reports go to the group.
- There is **at most one** weekly and one monthly report per period. The bot never posts a daily report.
- You can ask for a report at any time with `/hafta` or `/oy`. This never affects the automatic schedule.
- A report contains the total, number of expenses, daily average, the biggest spending categories, and an Excel file. The Excel file has the columns `Sana | Vaqt | Summa | Izoh` (date, time, amount, note), a `JAMI` (total) row, and a `Kunlik jami` (daily totals) sheet.
- No report is sent for a period with no expenses.
- A new user (or a user who turns reports back on with `/hisobot`) does not receive reports for periods before that moment.
- If a user (or group) is locked when a report is due, it is sent as soon as they unlock. Only the latest due period is sent, not every period that was missed.
- Use `/hisobot` to turn automatic reports off. In groups, only an admin can.

## Privacy and security

**Goal:** only you can open your data. The bot owner (the server administrator) cannot read the files on disk.

### How it works

- Every user has their own directory, `data/users/<telegram_id>/`. Each request opens only the sender's own directory, and there is no command that accepts another user's ID.
- When you set a password, the bot creates a random **data key** for you. All your monthly Excel files are encrypted with it using Fernet (AES-128-CBC + HMAC-SHA256).
- The data key is stored only **wrapped** (encrypted) with a key derived from your password using scrypt (`n=2^15, r=8, p=1`) in `vault.json`. **Neither your password nor the unwrapped key is ever written to disk.**
- After you unlock, the data key lives in the bot's memory only. So after every bot restart (including a redeploy) **every user has to enter their password again**.
- Changing your password only re-wraps the data key, so your files do not have to be rewritten.
- After 5 wrong attempts you must wait 10 minutes.
- The bot only works in private chats for personal data. In groups it answers only its own commands.
- Message texts and passwords are never logged.
- `users.json` stores only Telegram IDs and report state: no names, usernames, or phone numbers.
- There is no administrator command in the bot.

### Important limitations (please read)

- **If you forget your password, your data cannot be recovered.** This is on purpose: a recovery path would also let the server owner in. `/tozalash` deletes everything so you can start over.
- **Telegram bots are not end-to-end encrypted.** Messages pass through Telegram's servers and the bot processes them as plain text. Someone with full control of the server (root) could modify the bot or read its memory while a user is unlocked. Encryption protects against: reading files on disk, backups (`docker cp`), a stolen disk, and leaked server data. You still have to trust the bot owner.
- **Report Excel files are sent unencrypted to the Telegram chat**, because users need to open them on their phones. What you keep in the chat is up to you.
- The disk reveals the Telegram IDs, which months exist, and file sizes. For groups it also reveals the IDs of key holders in `vault.json`.

## Deployment

Requirements: a server with Docker and Docker Compose (Ubuntu recommended) and a bot token from [@BotFather](https://t.me/BotFather) (`/newbot`).

```bash
git clone https://github.com/Bunyod-Y/Spendwise.git /opt/spendwise
cd /opt/spendwise
cp .env.example .env
nano .env                 # put your BOT_TOKEN in
chmod 600 .env
docker compose up -d --build
docker compose logs -f    # wait for "Spendwise started"
```

The token lives only in `.env` on the server. `.env` is in `.gitignore`, so it is never committed.

### Configuration

Set these in `.env`:

| Variable | Default | Meaning |
|---|---|---|
| `BOT_TOKEN` | (required) | Token from @BotFather |
| `TIMEZONE` | `Asia/Tashkent` | Timezone for timestamps and report times |
| `DATA_DIR` | `/data` | Where data is stored (already set in the Docker image) |

### Upgrading from the old unencrypted version

After you upgrade, each user sets a password the first time they open the bot. Their old plain `.xlsx` files are then encrypted automatically and the plain copies are deleted.

## Operations

```bash
git pull && docker compose up -d --build      # install a new version (locks all users and groups)
docker compose logs -f --tail 100             # logs
docker compose restart                        # restart (locks all users and groups)
docker compose down                           # stop (data is kept; do NOT add -v, it deletes the data)
docker cp spendwise:/data ./backup-$(date +%F) # backup (encrypted, unreadable without passwords)
```

Remember that every restart locks everyone until they enter their password again: users in their private chat, and groups through a key holder. Reports for locked users and groups wait until they unlock.

### Data layout

Data lives in the `spendwise-data` Docker volume:

```
/data/users.json                          # user list (IDs and report state only)
/data/users/<telegram_id>/vault.json      # password-wrapped data key
/data/users/<telegram_id>/2026-09.enc     # encrypted monthly file
/data/groups.json                         # group list (chat IDs and report state only)
/data/groups/<chat_id>/vault.json         # group key, wrapped once per key holder
/data/groups/<chat_id>/2026-09.enc        # encrypted group expenses (with authors)
```

### Retention

The current month and the previous **12 months** are kept. Older month files are deleted automatically every day at 03:00 (without decrypting them), for users and groups alike. One user's yearly data is usually under 1 MB.

## Project layout

```
bot/
  main.py      Telegram handlers, parsing, report scheduling, password and group flows
  storage.py   Encrypted Excel storage (SpendingStorage per user, GroupStorage per group)
  vault.py     Key management: password-wrapped user keys (Vault), per-holder group keys (GroupVault)
  users.py     Registry of user/group IDs and report state (JSON)
  texts.py     All user-facing Uzbek texts and formatting helpers
Dockerfile, docker-compose.yml, requirements.txt, .env.example
```

Built with Python 3.12, [python-telegram-bot](https://python-telegram-bot.org/), openpyxl, and cryptography.

## Limits and known limitations

- At most **3000 entries per month** for each user and each group.
- Passwords are 6 to 128 characters long.
- Editing and deleting by number works only in the **current month**.
- In a locked group, at most 20 `/x` messages are held in memory. Anything beyond that is refused. Held messages are lost if the bot restarts before a key holder unlocks the group.
- A member who writes as an **anonymous admin** cannot set up a group or act as an admin, because Telegram hides who they are.
- There are no automated tests in the repository yet.
