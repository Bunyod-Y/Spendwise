# Spendwise

A private Telegram bot for tracking spending. Send each spending as a message and the bot saves it to this month's Excel file:

| Date       | Time  | Amount | Reason |
|------------|-------|--------|--------|
| 28.09.2026 | 13:05 | 50 000 | lunch  |

The amount can come first or last: `50000 lunch`, `taxi 25 000`, `1,250,000 rent`, `12.5 coffee`, `50k groceries` (`k` means ×1000). Each saved spending is confirmed with the day's and the month's running totals.

On the **last day of each month at 23:59 (Asia/Tashkent)**, the bot sends that month's file. The file has a TOTAL row and a *Summary* sheet with the total for each day. Only your Telegram account (`OWNER_ID`) can use the bot. Anyone else only gets a "private bot" reply.

## Commands

| Command | What it does |
|---|---|
| `/month` | This month's spreadsheet (`/month 08.2026` for another month) |
| `/list` | This month's spendings, numbered, with total (`/list 08.2026`) |
| `/today` | Today's spendings and total |
| `/stats` | Totals per day for the last 7 days, month total, daily average, biggest spending, last month's total |
| `/add 25.09 50000 lunch` | Add a spending for another day. Time is optional (`/add 25.09 14:30 50000 lunch`); without it, 12:00 is used |
| `/edit 3 45000 lunch` | Change the amount and reason of spending #3 this month |
| `/delete 3` | Delete spending #3 this month |
| `/undo` | Delete the last spending |
| `/settings` | Show the current settings |
| `/settime 23:59` | Change the monthly report time |
| `/settz Asia/Tashkent` | Change the timezone |
| `/report on` / `/report off` | Turn the automatic monthly report on or off |
| `/help` | Show help |

Spending numbers for `/edit` and `/delete` come from `/list`.

## Setup

### 1. Create the bot
In Telegram, open **@BotFather**, send `/newbot`, and copy the token. Use a **new** bot: each running bot needs its own token.

### 2. Deploy on the server
Docker must already be installed. This repo is public, so it can be cloned over HTTPS without a key:
```bash
ssh root@YOUR_SERVER_IP
git clone https://github.com/Bunyod-Y/Spendwise.git /opt/spendwise
cd /opt/spendwise
cp .env.example .env
nano .env            # set BOT_TOKEN and OWNER_ID
chmod 600 .env
docker compose up -d --build
docker compose logs -f   # should show "Spendwise started for owner ..."
```
Send `/start` to the bot in Telegram.

If you don't know your Telegram ID, set `OWNER_ID=1` first. Message the bot; it replies with your ID. Put that in `.env` and run `docker compose up -d`.

This bot can run on the same server as other bots. It uses its own container (`spendwise`) and its own data volume (`spendwise-data`).

## Operations

Run these inside `/opt/spendwise`:

```bash
git pull && docker compose up -d --build   # deploy new code
docker compose logs -f --tail 100          # view logs
docker compose restart                     # restart
docker compose down                        # stop (data is kept; never add -v, it deletes the data)
docker cp spendwise:/data ./backup-$(date +%F)   # back up all spending files
```

### Where the data lives
```
/data/spendings/2026-09.xlsx   # one file per month
/data/settings.json            # timezone, report time, etc.
```
The data is only on the server, not in git. `.env` (the bot token) is in `.gitignore`, so it is never pushed.

## How the monthly report works

- The report job runs every day at the report time. It sends a file only on the last day of the month.
- If the server was down at that moment, missed monthly reports (up to 3 months) are sent the next time the bot starts.
- If sending fails, the bot retries every 5 minutes.
- Each spending gets the time you sent the message in Telegram. Messages queued while the bot was offline keep their real time.
- Date, Time and Amount are real Excel values, so you can sort, filter, sum and build pivot tables on them.
