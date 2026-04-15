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

CHECK_INTERVAL = 1800  # 30 menit
MAX_AGE_MINUTES = 360  # 6 jam
SEEN_FILE = "seen_news.json"

# =========================
# KEYWORD (GEO + MACRO)
# =========================
KEYWORDS = [
    "trump", "war", "iran", "oil",
    "fed", "interest rate", "inflation",
    "economy", "geopolitics"
]

# =========================
# LOAD SEEN
# =========================
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    if not TELEGRAM_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    })

# =========================
# FETCH NEWS
# =========================
def fetch_news():
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": "trump OR war OR iran OR oil OR fed OR inflation OR economy",
        "sortBy": "publishedAt",
        "language": "en",
        "apiKey": NEWS_API_KEY,
        "pageSize": 20
    }
    res = requests.get(url, params=params)
    return res.json()

# =========================
# FILTER
# =========================
def is_relevant(title, desc):
    text = (title + " " + (desc or "")).lower()
    return any(k in text for k in KEYWORDS)

def get_age_minutes(published):
    pub = datetime.fromisoformat(published.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return int((now - pub).total_seconds() / 60)

# =========================
# PRIORITY LOGIC
# =========================
def get_priority(text):
    text = text.lower()

    if any(k in text for k in ["trump", "war", "iran", "oil"]):
        return "🔥 HIGH"

    if any(k in text for k in ["fed", "interest rate", "inflation"]):
        return "⚠️ MEDIUM"

    return "ℹ️ LOW"

# =========================
# MAIN
# =========================
def main():
    seen = load_seen()

    print("=== NEWS BOT START ===")
    print(f"Interval: {CHECK_INTERVAL} detik\n")

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

            for a in articles:
                title = a["title"]
                desc = a["description"]
                url = a["url"]
                source = a["source"]["name"]
                published = a["publishedAt"]

                uid = url

                # skip duplicate
                if uid in seen:
                    continue

                # skip tidak relevan
                if not is_relevant(title, desc):
                    continue

                # skip terlalu lama
                age = get_age_minutes(published)
                if age > MAX_AGE_MINUTES:
                    continue

                priority = get_priority(title + " " + (desc or ""))

                msg = f"""
🚨 *MARKET NEWS*

📰 {title}

{priority}

🕒 Umur: {age} menit
📅 Rilis: {published}

🌍 Sumber: {source}

🔗 {url}
"""

                print(msg)
                send_telegram(msg)

                seen.add(uid)
                sent_count += 1

            save_seen(seen)

            # =========================
            # STATUS (ANTI DIAM)
            # =========================
            if sent_count == 0:
                status_msg = f"""
📡 *STATUS NEWS BOT*

⏱ {datetime.now().strftime('%H:%M:%S')}

✅ Bot aktif
📊 Total dicek: {len(articles)}
❌ Tidak ada berita penting

(filter: geopolitik & ekonomi)
"""
                print(status_msg)
                send_telegram(status_msg)

        except Exception as e:
            print("ERROR:", e)

        print(f"Tunggu {CHECK_INTERVAL} detik...\n")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()