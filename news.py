import os
import json
import time
import hashlib
import requests
from datetime import datetime, timezone
from deep_translator import GoogleTranslator

# =========================================================
# CONFIG
# =========================================================
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CHECK_INTERVAL = 180          # 3 menit
MAX_AGE_MINUTES = 360         # 6 jam
MAX_NEWS_ITEMS = 30
ENABLE_TELEGRAM = True
ENABLE_TRANSLATE = True
DEBUG_MODE = True

SEEN_FILE = "seen_hybrid_news.json"

# Fokus market mover, tapi dibuat lebih longgar
NEWS_QUERY = (
    '("trump" OR "white house" OR "cz" OR "binance" OR '
    '"iran" OR "israel" OR "war" OR "missile" OR "attack" OR '
    '"fed" OR "powell" OR "inflation" OR "interest rate" OR '
    '"bitcoin" OR "btc" OR "crypto" OR "etf" OR "liquidation" OR "whale" OR "sec")'
)

# Fokus NewsAPI dulu. Twitter dimatikan sementara.
TWITTER_ELITE_USERS = []

# Sumber media yang dianggap layak, dibuat lebih longgar
ALLOWED_NEWS_SOURCES = {
    "reuters",
    "bloomberg",
    "cnbc",
    "financial times",
    "the wall street journal",
    "wall street journal",
    "wsj",
    "business insider",
    "marketwatch",
    "coindesk",
    "cointelegraph",
    "decrypt",
    "the block",
    "yahoo finance",
    "barron's",
    "axios",
    "cnn",
    "abc news",
    "forbes",
    "fortune",
    "investing.com",
    "slashdot.org",
    "cna",
    "financial post",
    "investopedia",
    "the street",
    "newsweek",
}

PRIMARY_KEYWORDS = [
    "trump", "white house", "cz", "binance",
    "iran", "israel", "war", "missile", "attack", "retaliation",
    "ceasefire", "truce", "hormuz", "oil", "opec",
    "fed", "fomc", "powell", "inflation", "interest rate",
    "rate cut", "rate hike", "tariff", "sanction",
    "bitcoin", "btc", "crypto", "etf", "liquidation", "whale", "sec"
]

BLACKLIST_KEYWORDS = [
    "sports", "football", "basketball", "baseball", "volleyball",
    "movie", "film", "music", "celebrity", "fashion", "recipe",
    "iphone", "android", "car review", "auto show", "pypi",
    "python package", "game", "gaming", "lottery", "travel"
]


# =========================================================
# STATE
# =========================================================
def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen), f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# =========================================================
# TELEGRAM
# =========================================================
def send_telegram(msg: str):
    if not ENABLE_TELEGRAM:
        return
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
    }

    try:
        requests.post(url, json=payload, timeout=15)
    except Exception:
        pass


# =========================================================
# UTILS
# =========================================================
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_text(text: str) -> str:
    return " ".join((text or "").strip().split())


def make_uid(source_type: str, source_name: str, title: str, url: str) -> str:
    raw = f"{source_type}|{source_name}|{title}|{url}".lower().strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_newsapi_time(ts: str):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def age_minutes(dt):
    if dt is None:
        return 999999
    now = datetime.now(timezone.utc)
    return int((now - dt.astimezone(timezone.utc)).total_seconds() // 60)


def translate_text(text: str) -> str:
    if not ENABLE_TRANSLATE:
        return text
    try:
        return GoogleTranslator(source="auto", target="id").translate(text)
    except Exception:
        return text


def text_has_primary_keyword(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in PRIMARY_KEYWORDS)


def text_has_blacklist(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in BLACKLIST_KEYWORDS)


def classify_priority(text: str) -> str:
    t = (text or "").lower()

    high_hits = 0
    medium_hits = 0

    if any(x in t for x in ["trump", "white house", "cz", "binance"]):
        high_hits += 2
    if any(x in t for x in ["iran", "israel", "war", "missile", "attack", "retaliation"]):
        high_hits += 2
    if any(x in t for x in ["fed", "powell", "inflation", "interest rate", "fomc"]):
        high_hits += 2
    if any(x in t for x in ["bitcoin", "btc", "crypto", "etf", "liquidation", "whale", "sec"]):
        medium_hits += 1

    if high_hits >= 2:
        return "HIGH"
    if high_hits >= 1 or medium_hits >= 1:
        return "MEDIUM"
    return "LOW"


def classify_bias(text: str) -> str:
    t = (text or "").lower()

    short_hits = 0
    long_hits = 0

    if any(x in t for x in ["war", "attack", "missile", "retaliation", "sanction", "tariff"]):
        short_hits += 3
    if any(x in t for x in ["iran", "israel", "hormuz", "oil spike", "opec cut"]):
        short_hits += 2
    if any(x in t for x in ["inflation hotter", "rate hike", "hawkish", "powell warns"]):
        short_hits += 3
    if any(x in t for x in ["liquidation", "sec sues", "exchange outflow pressure"]):
        short_hits += 2

    if any(x in t for x in ["ceasefire", "truce", "de-escalation"]):
        long_hits += 3
    if any(x in t for x in ["rate cut", "dovish", "cooling inflation"]):
        long_hits += 3
    if any(x in t for x in ["etf inflow", "etf approval", "institutional buying"]):
        long_hits += 3
    if any(x in t for x in ["whale accumulation", "exchange outflow", "buyback"]):
        long_hits += 2

    if short_hits >= long_hits + 2 and short_hits >= 3:
        return "SHORT BIAS"
    if long_hits >= short_hits + 2 and long_hits >= 3:
        return "LONG BIAS"
    return "WARNING / PANTAU"


# =========================================================
# NEWSAPI FETCH
# =========================================================
def fetch_newsapi():
    empty_stats = {
        "raw_total": 0,
        "kept": 0,
        "skip_source": 0,
        "skip_blacklist": 0,
        "skip_keyword": 0,
    }

    if not NEWS_API_KEY:
        return [], empty_stats

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": NEWS_QUERY,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": MAX_NEWS_ITEMS,
        "apiKey": NEWS_API_KEY,
    }

    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return [], empty_stats

    stats = dict(empty_stats)
    stats["raw_total"] = len(data.get("articles", []))

    articles = []
    for a in data.get("articles", []):
        title = normalize_text(a.get("title", ""))
        desc = normalize_text(a.get("description", ""))
        url = normalize_text(a.get("url", ""))
        source = normalize_text((a.get("source") or {}).get("name", ""))
        dt = parse_newsapi_time(a.get("publishedAt", ""))

        if not title or not url or not source or dt is None:
            continue

        if source.lower() not in ALLOWED_NEWS_SOURCES:
            stats["skip_source"] += 1
            continue

        full_text = f"{title} {desc}"

        if text_has_blacklist(full_text):
            stats["skip_blacklist"] += 1
            continue

        # Longgarkan keyword: kalau title ATAU full text ada keyword, lolos
        # Dan kalau ada bitcoin/crypto di full text, juga lolos
        ft = full_text.lower()
        if not text_has_primary_keyword(title) and not text_has_primary_keyword(full_text):
            if "bitcoin" not in ft and "btc" not in ft and "crypto" not in ft:
                stats["skip_keyword"] += 1
                continue

        articles.append({
            "source_type": "news",
            "source_name": source,
            "title": title,
            "text": full_text,
            "url": url,
            "dt": dt,
        })
        stats["kept"] += 1

    return articles, stats


# =========================================================
# TWITTER (DIMATIKAN SEMENTARA)
# =========================================================
def fetch_twitter_whitelist():
    return [], {}


# =========================================================
# MERGE + FILTER
# =========================================================
def collect_items():
    news_items, news_stats = fetch_newsapi()
    twitter_items, twitter_stats = fetch_twitter_whitelist()

    raw = news_items + twitter_items
    raw.sort(key=lambda x: x["dt"], reverse=True)

    filtered = []
    seen_local = set()

    stats = {
        "newsapi_raw": news_stats["raw_total"],
        "newsapi_kept": news_stats["kept"],
        "newsapi_skip_source": news_stats["skip_source"],
        "newsapi_skip_blacklist": news_stats["skip_blacklist"],
        "newsapi_skip_keyword": news_stats["skip_keyword"],
        "twitter_kept": len(twitter_items),
        "twitter_per_user": twitter_stats,
        "skip_age": 0,
        "skip_duplicate": 0,
        "final_kept": 0,
    }

    for item in raw:
        title = item["title"]
        url = item["url"]
        source_type = item["source_type"]
        source_name = item["source_name"]
        minutes = age_minutes(item["dt"])

        if minutes > MAX_AGE_MINUTES:
            stats["skip_age"] += 1
            continue

        uid = make_uid(source_type, source_name, title, url)
        if uid in seen_local:
            stats["skip_duplicate"] += 1
            continue

        seen_local.add(uid)
        item["uid"] = uid
        item["age_minutes"] = minutes
        item["priority"] = classify_priority(item["text"])
        filtered.append(item)

    filtered.sort(key=lambda x: (x["priority"] != "HIGH", x["age_minutes"]))
    stats["final_kept"] = len(filtered)

    return filtered, stats


# =========================================================
# FORMAT
# =========================================================
def format_alert(item):
    title_id = translate_text(item["title"])
    bias = classify_bias(item["text"])
    source_label = "TWITTER ELITE" if item["source_type"] == "twitter" else "NEWS MEDIA"

    return f"""🚨 IMPORTANT MARKET NEWS 🚨

Priority:
{item["priority"]}

Bias:
{bias}

Sumber Tipe:
{source_label}

Sumber:
{item["source_name"]}

Umur:
{item["age_minutes"]} menit

Judul:
{title_id}

Asli:
{item["title"]}

Link:
{item["url"]}
"""


# =========================================================
# MAIN
# =========================================================
def main():
    seen = load_seen()

    print("🚀 HYBRID NEWS BOT START")
    print("Mode: NewsAPI focus")
    print(f"Interval: {CHECK_INTERVAL} detik")
    print(f"Max umur: {MAX_AGE_MINUTES} menit")

    while True:
        print(f"\n[{now_str()}] Cek berita penting...")

        items, stats = collect_items()
        sent = 0
        skipped_seen = 0

        if DEBUG_MODE:
            print("----- DEBUG -----")
            print(f"NewsAPI raw            : {stats['newsapi_raw']}")
            print(f"NewsAPI kept           : {stats['newsapi_kept']}")
            print(f"Skip source            : {stats['newsapi_skip_source']}")
            print(f"Skip blacklist         : {stats['newsapi_skip_blacklist']}")
            print(f"Skip keyword           : {stats['newsapi_skip_keyword']}")
            print(f"Twitter kept           : {stats['twitter_kept']}")
            print(f"Twitter per user       : {stats['twitter_per_user']}")
            print(f"Skip age               : {stats['skip_age']}")
            print(f"Skip duplicate local   : {stats['skip_duplicate']}")

        for item in items:
            if item["uid"] in seen:
                skipped_seen += 1
                continue

            msg = format_alert(item)
            print("\n==============================")
            print(msg)

            send_telegram(msg)
            seen.add(item["uid"])
            sent += 1

        save_seen(seen)

        print(f"Item lolos filter : {len(items)}")
        print(f"Sudah pernah kirim: {skipped_seen}")
        print(f"Telegram terkirim : {sent}")
        print(f"Tunggu {CHECK_INTERVAL} detik...")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()