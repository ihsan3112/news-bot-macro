import requests
import time
import json
import os
from datetime import datetime, timezone

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CHECK_INTERVAL = 1800
MAX_AGE_MINUTES = 360
SEEN_FILE = "seen_news.json"

KEYWORDS = [
    "trump", "war", "iran", "israel", "attack", "missile",
    "oil", "opec", "fed", "powell", "interest rate", "inflation",
    "sanction", "tariff", "hormuz", "blockade", "central bank",
    "recession", "liquidity", "conflict", "tensions",
    "economy", "economic", "crypto", "bitcoin", "btc", "etf", "sec"
]

BLACKLIST = [
    "sports", "football", "basketball", "movie", "music",
    "celebrity", "recipe", "game", "gaming", "travel"
]

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

def fetch_news():
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": "trump OR war OR iran OR israel OR oil OR fed OR inflation OR economy OR bitcoin OR crypto OR etf OR sanctions OR conflict",
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
    if any(x in text for x in BLACKLIST):
        return False
    return any(x in text for x in KEYWORDS)

def get_priority(text):
    text = text.lower()
    if any(x in text for x in ["trump", "war", "iran", "israel", "attack", "missile", "oil", "fed", "powell"]):
        return "🔥 HIGH"
    if any(x in text for x in ["inflation", "interest rate", "economy", "crypto", "bitcoin", "btc", "etf"]):
        return "🟡 MEDIUM"
    return "ℹ️ INFO"

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
            print(f"[{datetime.now()}] cek berita... total: {len(articles)}")

            sent = 0

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
                    continue

                if not is_relevant(title, desc):
                    continue

                try:
                    age = get_age_minutes(published)
                except Exception:
                    continue

                if age > MAX_AGE_MINUTES:
                    continue

                priority = get_priority(title + " " + (desc or ""))

                msg = f"""🚨 *MARKET NEWS*

📰 {title}

{priority}

🕒 Umur: {age_text(age)}
📅 Rilis: {published}

🌍 Sumber: {source}

🔗 {url}
"""
                print(msg)
                send_telegram(msg)
                seen.add(uid)
                sent += 1

            save_seen(seen)
            print(f"Terkirim: {sent}")

        except Exception as e:
            print("ERROR MAIN:", e)

        print(f"Tunggu {CHECK_INTERVAL} detik...\n")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()