import os
import json
import time
import requests
from datetime import datetime, timezone
from deep_translator import GoogleTranslator

# =========================
# CONFIG
# =========================
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CHECK_INTERVAL = 1800          # 30 menit
MAX_AGE_MINUTES = 1440         # 24 jam
SEEN_FILE = "seen_news.json"

# =========================
# QUERY KHUSUS CRYPTO IMPACT
# =========================
NEWS_QUERY = (
    "("
    "bitcoin OR btc OR crypto OR cryptocurrency OR stablecoin OR etf OR sec OR binance OR cz "
    "OR trump OR white house OR fed OR powell OR inflation OR interest rate OR recession "
    "OR iran OR israel OR war OR attack OR missile OR hormuz OR oil OR opec "
    "OR sanctions OR tariff OR liquidity OR risk-off OR risk on"
    ")"
)

# =========================
# KEYWORD FILTER
# =========================
CRYPTO_IMPACT_KEYWORDS = [
    "bitcoin", "btc", "crypto", "cryptocurrency", "stablecoin", "etf", "sec",
    "binance", "cz",
    "trump", "white house",
    "fed", "powell", "interest rate", "inflation", "rate cut", "rate hike", "recession",
    "iran", "israel", "war", "attack", "missile", "conflict", "tensions",
    "hormuz", "oil", "opec", "sanction", "sanctions", "tariff",
    "liquidity", "risk-off", "risk on", "central bank"
]

SUPPORTING_MARKET_WORDS = [
    "market", "global", "economy", "economic", "macro",
    "price", "supply", "demand", "policy", "volatility"
]

BLACKLIST = [
    "sports", "football", "basketball", "baseball", "volleyball",
    "movie", "film", "music", "celebrity", "fashion", "recipe",
    "iphone", "android", "car review", "auto show",
    "game", "gaming", "lottery", "travel", "lifestyle",
    "wedding", "dating", "food", "restaurant"
]

# =========================
# FILTER KONTEXT OLAHRAGA
# =========================
SPORT_CONTEXT = [
    "nba", "nfl", "mlb", "nhl", "uefa", "fifa",
    "76ers", "celtics", "lakers", "warriors", "heat", "magic",
    "playoff", "playoffs", "regular season", "match", "matches",
    "team", "player", "players", "coach", "club", "league",
    "goal", "goals", "score", "scored", "points", "wins", "win", "lose", "lost",
    "quarterfinal", "semifinal", "final",
    "touchdown", "home run"
]

LOW_QUALITY_SOURCE_HINTS = [
    "blogspot",
    "wordpress",
    "forum",
    "reddit"
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
# TRANSLATE
# =========================
def translate_text(text):
    if not text:
        return ""
    try:
        return GoogleTranslator(source="auto", target="id").translate(text)
    except Exception:
        return text

# =========================
# FETCH NEWS
# =========================
def fetch_news():
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": NEWS_QUERY,
        "sortBy": "publishedAt",
        "language": "en",
        "apiKey": NEWS_API_KEY,
        "pageSize": 20,
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

def is_low_quality_source(source):
    s = (source or "").lower()
    return any(x in s for x in LOW_QUALITY_SOURCE_HINTS)

def has_sport_context(text):
    text = (text or "").lower()
    return any(x in text for x in SPORT_CONTEXT)

def is_relevant_for_crypto(title, desc):
    text = (title + " " + (desc or "")).lower()

    # buang total yang jelas sampah
    if any(x in text for x in BLACKLIST):
        return False

    # buang kalau konteks olahraga terdeteksi
    if has_sport_context(text):
        return False

    # harus ada pemicu yang mungkin berdampak ke crypto
    if any(x in text for x in CRYPTO_IMPACT_KEYWORDS):
        return True

    # fallback sengaja dimatikan agar tetap ketat:
    # market/global/economy saja tidak cukup
    return False

def get_priority(text):
    text = text.lower()

    if any(x in text for x in [
        "trump", "white house",
        "war", "iran", "israel", "attack", "missile", "conflict", "tensions",
        "oil", "opec", "hormuz", "blockade",
        "fed", "powell", "interest rate", "inflation", "rate hike", "rate cut",
        "sec", "etf", "binance", "cz", "stablecoin"
    ]):
        return "🔥 HIGH"

    if any(x in text for x in [
        "bitcoin", "btc", "crypto", "cryptocurrency",
        "recession", "economy", "liquidity", "market", "macro"
    ]):
        return "🟡 MEDIUM"

    return "ℹ️ INFO"

def get_bias(text):
    text = text.lower()

    if any(x in text for x in [
        "war", "attack", "missile", "sanction", "sanctions", "tariff",
        "inflation", "rate hike", "oil spike", "blockade", "risk-off",
        "recession", "conflict", "tensions"
    ]):
        return "SHORT BIAS / RISK-OFF"

    if any(x in text for x in [
        "ceasefire", "rate cut", "cooling inflation", "etf inflow",
        "risk on", "approval", "easing"
    ]):
        return "LONG BIAS / RISK-ON"

    return "PANTAU"

def get_kelayakan(age):
    if age <= 60:
        return "SANGAT LAYAK"
    elif age <= 180:
        return "LAYAK"
    elif age <= 360:
        return "HATI-HATI"
    elif age <= 720:
        return "TELAT RINGAN"
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

    title_id = translate_text(title)
    desc_id = translate_text(desc) if desc else ""

    msg = f"""🚨 *CRYPTO IMPACT NEWS*

📰 *{title_id}*

📌 {desc_id}

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
    print(f"Max umur berita: {MAX_AGE_MINUTES} menit")

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
            skipped_low_quality = 0

            for a in articles:
                title = a.get("title", "")
                desc = a.get("description", "")
                url = a.get("url", "")
                source = a.get("source", {}).get("name", "Unknown")
                published = a.get("publishedAt", "")

                if not title or not url or not published:
                    continue

                if is_low_quality_source(source):
                    skipped_low_quality += 1
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

                if not is_relevant_for_crypto(title, desc):
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

            print("----- STATUS -----")
            print(f"Bot aktif            : YA")
            print(f"Total dicek          : {len(articles)}")
            print(f"Terkirim             : {sent_count}")
            print(f"Skip seen            : {skipped_seen}")
            print(f"Skip terlalu lama    : {skipped_old}")
            print(f"Skip tidak relevan   : {skipped_irrelevant}")
            print(f"Skip source jelek    : {skipped_low_quality}")

        except Exception as e:
            print("ERROR MAIN:", e)

        print(f"Tunggu {CHECK_INTERVAL} detik...\n")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()