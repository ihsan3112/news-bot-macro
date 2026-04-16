import requests
import time
import json
import os
from datetime import datetime, timezone

# =========================
# CONFIG
# =========================
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CHECK_INTERVAL = 1800           # 30 menit
MAX_AGE_MINUTES = 360           # 6 jam
SEEN_FILE = "seen_news.json"

# =========================
# FILTER DASAR
# =========================
KEYWORDS = [
    "trump", "white house", "iran", "israel", "war", "attack", "missile",
    "oil", "opec", "hormuz", "blockade", "sanction", "tariff",
    "fed", "powell", "interest rate", "inflation", "rate cut", "rate hike",
    "economy", "economic", "recession", "slowdown", "central bank",
    "bitcoin", "btc", "crypto", "etf", "sec", "liquidity", "market"
]

BLACKLIST = [
    "sports", "football", "basketball", "baseball", "volleyball",
    "movie", "film", "music", "celebrity", "fashion", "recipe",
    "iphone", "android", "car review", "auto show", "pypi",
    "python package", "game", "gaming", "lottery", "travel"
]

FALLBACK_MARKET_WORDS = [
    "market", "global", "economy", "economic", "price",
    "supply", "demand", "inflation", "risk", "trade", "policy"
]

# =========================
# LOAD / SAVE
# =========================
def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen(seen):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen), f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": msg,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False
            },
            timeout=15
        )
    except Exception as e:
        print("ERROR TELEGRAM:", e)

# =========================
# FETCH NEWS
# =========================
def fetch_news():
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": "global OR economy OR market OR oil OR crypto OR fed OR inflation OR trump OR iran OR israel OR war",
        "sortBy": "publishedAt",
        "language": "en",
        "apiKey": NEWS_API_KEY,
        "pageSize": 20
    }

    try:
        res = requests.get(url, params=params, timeout=20)
        return res.json()
    except Exception as e:
        print("ERROR FETCH:", e)
        return {}

# =========================
# HELPERS
# =========================
def get_age_minutes(published):
    pub = datetime.fromisoformat(published.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return int((now - pub).total_seconds() / 60)

def age_text(age):
    if age < 60:
        return f"{age} menit"
    return f"{age // 60} jam {age % 60} menit"

def is_relevant(title, desc):
    text = (title + " " + (desc or "")).lower()

    # buang yang jelas sampah
    if any(x in text for x in BLACKLIST):
        return False

    # ada keyword penting → lolos
    if any(x in text for x in KEYWORDS):
        return True

    # fallback market/economy related → lolos
    if any(x in text for x in FALLBACK_MARKET_WORDS):
        return True

    return False

def get_priority(text):
    text = text.lower()

    if any(x in text for x in [
        "trump", "war", "iran", "israel", "attack", "missile",
        "oil", "opec", "hormuz", "blockade",
        "fed", "powell", "interest rate", "inflation"
    ]):
        return "🔥 HIGH"

    if any(x in text for x in [
        "economy", "economic", "recession", "slowdown",
        "bitcoin", "btc", "crypto", "etf", "sec", "market"
    ]):
        return "🟡 MEDIUM"

    return "ℹ️ INFO"

def get_bias(text):
    text = text.lower()

    if any(x in text for x in [
        "war", "attack", "missile", "sanction", "tariff",
        "inflation", "rate hike", "oil spike", "blockade", "risk-off"
    ]):
        return "SHORT BIAS"

    if any(x in text for x in [
        "ceasefire", "rate cut", "cooling inflation", "etf inflow", "risk on"
    ]):
        return "LONG BIAS"

    return "PANTAU"

def get_kelayakan(age):
    if age <= 60:
        return "SANGAT LAYAK"
    elif age <= 180:
        return "LAYAK"
    elif age <= 360:
        return "HATI-HATI"
    else:
        return "TELAT"

# =========================
# FORMAT
# =========================
def format_news_message(title, desc, source, published, age, url):
    full_text = (title + " " + (desc or ""))
    priority = get_priority(full_text)
    bias = get_bias(full_text)
    kelayakan = get_kelayakan(age)

    msg = f"""🚨 *MARKET NEWS*

📰 {title}

{priority}
📉 Bias: {bias}
⏱ Kelayakan: {kelayakan}

🕒 Umur: {age_text(age)}
📅 Rilis: {published}

🌍 Sumber: {source}

🔗 {url}
"""
    return msg

# =========================
# MAIN
# =========================
def main():
    seen = load_seen()

    print("=== NEWS BOT START ===")
    print(f"Interval: {CHECK_INTERVAL} detik")

    while True:
        try:
            data = fetch_news()

            if "articles" not in data:
                print("ERROR API:", data)
                time.sleep(CHECK_INTERVAL)
                continue

            articles = data["articles"]
            print(f"\n[{datetime.now()}] cek berita... total: {len(articles)}")

            sent_count = 0
            skipped_seen = 0
            skipped_old = 0
            skipped_irrelevant = 0

            for a in articles:
                title = a.get("title", "")
                desc = a.get("description", "")
                url = a.get("url", "")
                source = a.get("source", {}).get("name", "Unknown")
                published = a.get("publishedAt", "")

                if not title or not url or not published:
                    continue

                uid = url

                if uid in seen:
                    skipped_seen += 1
                    continue

                try:
                    age = get_age_minutes(published)
                except Exception:
                    continue

                if age > MAX_AGE_MINUTES:
                    skipped_old += 1
                    continue

                if not is_relevant(title, desc):
                    skipped_irrelevant += 1
                    continue

                msg = format_news_message(
                    title=title,
                    desc=desc,
                    source=source,
                    published=published,
                    age=age,
                    url=url
                )

                print(msg)
                send_telegram(msg)

                seen.add(uid)
                sent_count += 1

            save_seen(seen)

            # status hanya di log
            print("----- STATUS -----")
            print(f"Bot aktif          : YA")
            print(f"Total dicek        : {len(articles)}")
            print(f"Terkirim           : {sent_count}")
            print(f"Skip seen          : {skipped_seen}")
            print(f"Skip terlalu lama  : {skipped_old}")
            print(f"Skip tidak relevan : {skipped_irrelevant}")

        except Exception as e:
            print("ERROR MAIN:", e)

        print(f"Tunggu {CHECK_INTERVAL} detik...\n")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()