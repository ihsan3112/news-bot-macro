import os
import json
import time
import hashlib
from datetime import datetime, timezone

import requests
from deep_translator import GoogleTranslator

# ===============================
# CONFIG
# ===============================
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CHECK_INTERVAL = 180   # 3 menit
MAX_AGE_MINUTES = 360  # 6 jam
PAGE_SIZE = 30

SEEN_FILE = "seen_news.json"

ENABLE_TRANSLATE = True
DEBUG_MODE = True

# Query dibuat cukup luas, tapi masih fokus market mover
QUERY = (
    "crypto OR bitcoin OR btc OR fed OR inflation OR interest rate OR "
    "trump OR white house OR cz OR binance OR "
    "iran OR israel OR war OR missile OR attack OR oil OR etf OR whale OR liquidation"
)

# Source dibuat lebih longgar, tapi tetap relevan
ALLOWED_SOURCES = [
    "reuters",
    "bloomberg",
    "cnbc",
    "business insider",
    "coindesk",
    "cointelegraph",
    "decrypt",
    "yahoo",
    "marketwatch",
    "cnn",
    "forbes",
    "investing",
    "financial",
    "fortune",
    "axios",
    "crypto",
    "the block",
]

# ===============================
# LOAD / SAVE
# ===============================
def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False, indent=2)


# ===============================
# TELEGRAM
# ===============================
def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    try:
        requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg
            },
            timeout=10
        )
    except Exception:
        pass


# ===============================
# FETCH NEWS
# ===============================
def fetch_news():
    url = "https://newsapi.org/v2/everything"

    params = {
        "q": QUERY,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": PAGE_SIZE,
        "apiKey": NEWS_API_KEY
    }

    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    return data.get("articles", [])


# ===============================
# UTILS
# ===============================
def get_age_minutes(published_at):
    dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return (now - dt).total_seconds() / 60


def translate(text):
    if not ENABLE_TRANSLATE:
        return text

    try:
        return GoogleTranslator(source="auto", target="id").translate(text)
    except Exception:
        return text


def is_valid_source(source):
    s = source.lower()
    return any(x in s for x in ALLOWED_SOURCES)


def classify_priority(title):
    t = title.lower()

    if any(x in t for x in ["trump", "white house", "iran", "israel", "war", "attack", "missile"]):
        return "HIGH 🔴"

    if any(x in t for x in ["fed", "inflation", "interest rate", "powell"]):
        return "HIGH 🔴"

    if any(x in t for x in ["bitcoin", "btc", "crypto", "etf", "liquidation", "whale", "binance", "cz"]):
        return "MEDIUM 🟡"

    return "LOW ⚪"


def make_uid(title, source, url):
    # pakai title + source + url supaya anti-ulang lebih kuat
    raw = f"{title.strip().lower()}|{source.strip().lower()}|{url.strip().lower()}"
    return hashlib.md5(raw.encode()).hexdigest()


# ===============================
# MAIN
# ===============================
def main():
    seen = load_seen()

    print("🚀 NEWS BOT START (ANTI DUPLICATE MODE)")

    while True:
        print("\nCek berita...")

        if not NEWS_API_KEY:
            print("NEWS_API_KEY belum ada")
            time.sleep(30)
            continue

        try:
            articles = fetch_news()
        except Exception as e:
            print("Error ambil API:", e)
            time.sleep(30)
            continue

        raw_count = len(articles)
        sent = 0
        skip_seen = 0
        skip_age = 0
        skip_source = 0
        skip_short = 0

        print(f"Total dari API: {raw_count}")

        for a in articles:
            title = (a.get("title") or "").strip()
            url = (a.get("url") or "").strip()
            source = ((a.get("source") or {}).get("name") or "").strip()
            published = (a.get("publishedAt") or "").strip()

            if not title or not published or not url:
                continue

            # buang judul aneh/terlalu pendek
            if len(title) < 25:
                skip_short += 1
                continue

            age = get_age_minutes(published)
            if age > MAX_AGE_MINUTES:
                skip_age += 1
                continue

            if not is_valid_source(source):
                skip_source += 1
                continue

            uid = make_uid(title, source, url)
            if uid in seen:
                skip_seen += 1
                continue

            priority = classify_priority(title)
            indo = translate(title)

            msg = f"""🚨 MARKET NEWS 🚨

Priority:
{priority}

Sumber:
{source}

Umur:
{int(age)} menit

Judul:
{indo}

Link:
{url}
"""

            print("\n-------------------")
            print(msg)

            send_telegram(msg)

            seen.add(uid)
            sent += 1

        save_seen(seen)

        if DEBUG_MODE:
            print("\n===== DEBUG =====")
            print(f"Total API        : {raw_count}")
            print(f"Skip seen        : {skip_seen}")
            print(f"Skip age         : {skip_age}")
            print(f"Skip source      : {skip_source}")
            print(f"Skip short title : {skip_short}")

        print(f"Berita dikirim: {sent}")
        print("Tunggu 3 menit...")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()