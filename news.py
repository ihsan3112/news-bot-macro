import os
import time
import json
import hashlib
import requests
from datetime import datetime, timezone
from deep_translator import GoogleTranslator

# ================= CONFIG =================
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CHECK_INTERVAL = 180   # 3 menit
MAX_AGE_MINUTES = 720  # 12 jam

SEEN_FILE = "seen_news.json"

QUERY = "trump OR war OR iran OR israel OR fed OR bitcoin OR btc OR crypto OR oil"

# ================= UTIL =================
def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def hash_id(text):
    return hashlib.md5(text.encode()).hexdigest()

def load_seen():
    try:
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def translate(text):
    try:
        return GoogleTranslator(source='auto', target='id').translate(text)
    except:
        return text

def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

# ================= ANALISA =================
def classify_priority(text):
    text = text.lower()

    if any(x in text for x in ["trump", "war", "iran", "israel", "fed", "powell"]):
        return "HIGH"
    if any(x in text for x in ["bitcoin", "btc", "crypto", "oil"]):
        return "MEDIUM"
    return "LOW"

def classify_bias(text):
    text = text.lower()

    if any(x in text for x in ["war", "attack", "missile", "inflation", "rate hike"]):
        return "SHORT BIAS"

    if any(x in text for x in ["ceasefire", "rate cut", "etf inflow"]):
        return "LONG BIAS"

    return "PANTAU"

def kelayakan(age_min):
    if age_min <= 60:
        return "SANGAT LAYAK"
    elif age_min <= 180:
        return "LAYAK"
    elif age_min <= 360:
        return "HATI-HATI"
    else:
        return "TELAT"

def age_str(mins):
    if mins < 60:
        return f"{mins} menit"
    return f"{mins//60} jam {mins%60} menit"

# ================= FETCH =================
def fetch_news():
    url = "https://newsapi.org/v2/everything"

    params = {
        "q": QUERY,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 20,
        "apiKey": NEWS_API_KEY
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
    except:
        return []

    if data.get("status") != "ok":
        return []

    return data.get("articles", [])

# ================= MAIN =================
def main():
    seen = load_seen()

    print("=== NEWS BOT START ===")

    while True:
        print(f"[{now()}] cek berita...")

        articles = fetch_news()

        sent = 0

        for a in articles:
            title = a.get("title", "")
            url = a.get("url", "")
            published = a.get("publishedAt")

            if not title or not url or not published:
                continue

            uid = hash_id(title + url)

            if uid in seen:
                continue

            try:
                dt = datetime.fromisoformat(published.replace("Z","+00:00"))
            except:
                continue

            now_utc = datetime.now(timezone.utc)
            age_min = int((now_utc - dt).total_seconds() / 60)

            if age_min > MAX_AGE_MINUTES:
                continue

            text = title.lower()

            # filter sederhana biar gak noise
            if not any(k in text for k in ["trump","war","iran","fed","btc","crypto","oil"]):
                continue

            priority = classify_priority(text)
            bias = classify_bias(text)
            layak = kelayakan(age_min)

            msg = f"""🚨 IMPORTANT MARKET NEWS 🚨

Priority:
{priority}

Bias:
{bias}

Kelayakan:
{layak}

Waktu Rilis:
{dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")}

Umur:
{age_str(age_min)}

Judul:
{translate(title)}

Asli:
{title}

Link:
{url}
"""

            print(msg)

            send_telegram(msg)

            seen.add(uid)
            sent += 1

        save_seen(seen)

        print(f"kirim: {sent}")
        print(f"tunggu {CHECK_INTERVAL} detik...\n")

        time.sleep(CHECK_INTERVAL)

# ================= RUN =================
if __name__ == "__main__":
    main()