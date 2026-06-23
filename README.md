# Pump/Dip Alert Bot

Watches your CoinMarketCap "Invo" watchlist and pings your Telegram when a coin
moves **±5% in 1 hour** — your cue to look for a pullback / reversal.

## 1. Get your 3 keys

**CoinMarketCap API key**
1. Go to https://pro.coinmarketcap.com/signup → create a free account.
2. Dashboard → copy your **API Key**. (Free "Basic" plan is enough.)

**Telegram bot token**
1. In Telegram, message **@BotFather** → send `/newbot` → follow prompts.
2. It gives you a token like `123456:ABC-DEF...`. Copy it.

**Telegram chat ID** (where alerts get sent — your own account)
1. Start a chat with your new bot and send it any message (e.g. "hi").
2. Message **@userinfobot** in Telegram — it replies with your numeric **Id**.
   Use that as `TELEGRAM_CHAT_ID`.

## 2. Configure
1. Copy `.env.example` to `.env`.
2. Paste your 3 values in.

## 3. Run
```powershell
pip install -r requirements.txt
python bot.py
```
You should get a "✅ bot online" message in Telegram, then alerts as moves happen.

## Tweak it
Edit `.env`:
- `THRESHOLD_PCT` — alert size (try 7 or 10 for fewer, bigger moves)
- `POLL_SECONDS` — how often it checks (180 = every 3 min)
- `COOLDOWN_MINUTES` — silence per coin after an alert

Edit the `WATCHLIST_IDS` list in `bot.py` to add/remove coins (CoinMarketCap IDs).

## Notes
- Only your watchlist's real CMC coin IDs are included; the very long
  numeric entries in your export were custom list items, not coin IDs.
- Keep `.env` private — it holds your keys. Never commit/share it.
