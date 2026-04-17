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
# QUERY
# Fokus ambil berita yang mungkin relevan ke crypto/macro
# =========================
NEWS_QUERY = (
    "("
    "bitcoin OR btc OR crypto OR cryptocurrency OR stablecoin OR etf OR sec OR binance OR cz "
    "OR trump OR fed OR powell OR inflation OR interest rate OR rate hike OR rate cut "
    "OR recession OR economy OR market OR oil OR opec OR hormuz OR iran OR israel "
    "OR tariff OR sanctions OR liquidity OR risk-off OR risk on OR regulation"
    ")"
)

# =========================
# GATE 1 - DIRECT CRYPTO
# =========================
DIRECT_CRYPTO_KEYWORDS = [
    "bitcoin", "btc", "crypto", "cryptocurrency", "stablecoin",
    "etf", "bitcoin etf", "spot etf", "sec",
    "binance", "cz", "exchange", "crypto exchange",
    "crypto regulation", "digital asset", "digital assets",
    "token", "tokens", "blockchain", "wallet",
    "ethereum", "eth", "solana", "xrp"
]

# =========================
# GATE 2 - TRUMP
# Trump tidak otomatis lolos.
# Harus ada konteks market/macro/risk
# =========================
TRUMP_KEYWORDS = [
    "trump", "donald trump", "white house", "us administration"
]

TRUMP_IMPACT_WORDS = [
    "tariff", "tariffs", "trade war", "china",
    "sanction", "sanctions", "fed", "powell",
    "inflation", "interest rate", "rate cut", "rate hike",
    "economy", "economic", "market", "markets",
    "stocks", "stock market", "bond", "bonds", "yield", "yields",
    "oil", "opec", "risk", "risk-off", "risk on",
    "liquidity", "volatility", "recession", "dollar", "treasury"
]

# =========================
# GATE 3 - MACRO / GEOPOLITIK
# Harus ada context impact ke market
# =========================
MACRO_GEO_KEYWORDS = [
    "fed", "powell", "interest rate", "rate cut", "rate hike",
    "inflation", "cpi", "ppi", "recession", "central bank",
    "oil", "opec", "hormuz", "iran", "israel",
    "war", "attack", "missile", "conflict", "tensions",
    "sanction", "sanctions", "tariff", "tariffs",
    "liquidity", "risk-off", "risk on"
]

MARKET_IMPACT_WORDS = [
    "market", "markets", "economy", "economic", "macro",
    "stocks", "equities", "bond", "bonds",
    "yield", "yields", "price", "prices",
    "investor", "investors", "trading",
    "selloff", "rally", "volatility",
    "risk asset", "risk appetite",
    "dollar", "treasury", "financial conditions",
    "global market", "global markets"
]

# =========================
# OPTIONAL NOISE FILTER RINGAN
# Bukan fokus utama, hanya pagar dasar
# =========================
NOISE_HINTS = [
    "sports", "football", "basketball", "baseball",
    "movie", "film", "music", "celebrity",
    "netflix", "streaming", "k-drama", "tv show",
    "recipe", "fashion", "dating", "wedding"
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
        "pageSize": 30,
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
def contains_any(text, keywords):
    return any(k in text for k in keywords)

def count_matches(text, keywords):
    return sum(1 for k in keywords if k in text)

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

# =========================
# CORE FILTER
# Fokus: yang masuk, bukan yang dibuang
# =========================
def classify_article(title, desc, source=""):
    text = f"{title} {desc or ''} {source or ''}".lower()

    # pagar dasar ringan
    if contains_any(text, NOISE_HINTS):
        return False, "noise_hint"

    # GATE 1: direct crypto
    direct_hits = count_matches(text, DIRECT_CRYPTO_KEYWORDS)
    if direct_hits >= 1:
        return True, "direct_crypto"

    # GATE 2: Trump + market impact
    trump_hits = count_matches(text, TRUMP_KEYWORDS)
    trump_impact_hits = count_matches(text, TRUMP_IMPACT_WORDS)

    if trump_hits >= 1 and trump_impact_hits >= 1:
        return True, "trump_market_impact"

    # GATE 3: macro/geopolitik + market impact
    macro_hits = count_matches(text, MACRO_GEO_KEYWORDS)
    market_hits = count_matches(text, MARKET_IMPACT_WORDS)

    if macro_hits >= 1 and market_hits >= 1:
        return True, "macro_market_impact"

    return False, "not_in_focus"

# =========================
# SCORING INFO
# =========================
def get_priority(text):
    text = text.lower()

    if contains_any(text, [
        "war", "iran", "israel", "attack", "missile", "conflict",
        "oil", "opec", "hormuz", "tariff", "sanctions",
        "fed", "powell", "interest rate", "inflation",
        "rate hike", "rate cut", "sec", "etf", "binance"
    ]):
        return "🔥 HIGH"

    if contains_any(text, [
        "bitcoin", "btc", "crypto", "recession",
        "economy", "market", "liquidity", "macro"
    ]):
        return "🟡 MEDIUM"

    return "ℹ️ INFO"

def get_bias(text):
    text = text.lower()

    if contains_any(text, [
        "war", "attack", "missile", "sanction", "sanctions",
        "tariff", "inflation", "rate hike", "risk-off",
        "recession", "selloff", "conflict", "oil spike"
    ]):
        return "SHORT BIAS / RISK-OFF"

    if contains_any(text, [
        "rate cut", "cooling inflation", "approval",
        "ceasefire", "risk on", "rally", "easing"
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
# FORMAT MESSAGE
# =========================
def format_news_message(title, desc, source, published, age, url, gate_reason):
    full_text = f"{title} {desc or ''}"
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
🧠 Filter: {gate_reason}

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
    print("Mode filter: direct crypto / trump impact / macro impact")

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
                    print(f"SKIP LOW QUALITY: {source} | {title}")
                    continue

                if url in seen:
                    skipped_seen += 1
                    continue

                try:
                    age = get_age_minutes(published)
                except Exception:
                    print(f"SKIP INVALID DATE: {title}")
                    continue

                if age > MAX_AGE_MINUTES:
                    skipped_old += 1
                    continue

                is_ok, reason = classify_article(title, desc, source)
                if not is_ok:
                    skipped_irrelevant += 1
                    print(f"SKIP {reason}: {title}")
                    continue

                msg = format_news_message(
                    title=title,
                    desc=desc,
                    source=source,
                    published=published,
                    age=age,
                    url=url,
                    gate_reason=reason
                )

                print(f"SEND [{reason}]: {title}")
                send_telegram(msg)

                seen.add(url)
                sent_count += 1

            save_seen(seen)

            print("----- STATUS -----")
            print(f"Bot aktif            : YA")
            print(f"Total dicek          : {len(articles)}")
            print(f"Terkirim             : {sent_count}")
            print(f"Skip seen            : {skipped_seen}")
            print(f"Skip terlalu lama    : {skipped_old}")
            print(f"Skip tidak fokus     : {skipped_irrelevant}")
            print(f"Skip source jelek    : {skipped_low_quality}")

        except Exception as e:
            print("ERROR MAIN:", e)

        print(f"Tunggu {CHECK_INTERVAL} detik...\n")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()