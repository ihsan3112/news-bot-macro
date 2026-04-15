import os
import json
import time
import hashlib
import requests
from datetime import datetime, timezone
from deep_translator import GoogleTranslator

# ================= CONFIG =================
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CHECK_INTERVAL = 1800         # 3 menit
MAX_AGE_MINUTES = 720          # 12 jam
BYPASS_AGE_MINUTES = 1440      # 24 jam untuk keyword sangat penting
MAX_NEWS_ITEMS = 25

ENABLE_TELEGRAM = True
ENABLE_TRANSLATE = True
DEBUG_MODE = True

SEEN_FILE = "seen_news.json"
RECENT_FILE = "recent_titles.json"
RECENT_WINDOW_MINUTES = 45

# Query disederhanakan supaya NewsAPI tidak terlalu sempit
QUERY = "trump OR war OR iran OR israel OR fed OR powell OR bitcoin OR btc OR crypto OR oil OR opec OR binance OR cz"

PRIMARY_KEYWORDS = [
    "trump", "white house", "cz", "binance",
    "iran", "israel", "war", "missile", "attack", "retaliation",
    "ceasefire", "truce", "hormuz", "oil", "opec",
    "fed", "fomc", "powell", "inflation", "interest rate",
    "rate cut", "rate hike", "tariff", "sanction",
    "bitcoin", "btc", "crypto", "etf", "liquidation", "whale", "sec"
]

BYPASS_KEYWORDS = [
    "trump", "white house", "cz", "binance",
    "iran", "israel", "war", "missile", "attack",
    "fed", "powell", "inflation", "fomc", "interest rate",
    "hormuz", "oil", "opec"
]

BLACKLIST_KEYWORDS = [
    "sports", "football", "basketball", "baseball", "volleyball",
    "movie", "film", "music", "celebrity", "fashion", "recipe",
    "iphone", "android", "car review", "auto show", "pypi",
    "python package", "game", "gaming", "lottery", "travel"
]

LOW_QUALITY_SOURCE_HINTS = [
    "blogspot",
    "wordpress",
    "forum",
    "reddit"
]

# ================= STATE =================
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

def load_recent():
    try:
        with open(RECENT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_recent(data):
    try:
        with open(RECENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ================= TELEGRAM =================
def send_telegram(msg: str):
    if not ENABLE_TELEGRAM:
        return
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}

    try:
        requests.post(url, json=payload, timeout=15)
    except Exception:
        pass

# ================= UTILS =================
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def normalize_text(text: str) -> str:
    return " ".join((text or "").strip().split())

def make_uid(title: str, url: str) -> str:
    raw = f"{title}|{url}".lower().strip()
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

def local_time_str(dt):
    if dt is None:
        return "-"
    try:
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "-"

def age_text(minutes):
    if minutes < 60:
        return f"{minutes} menit"
    h = minutes // 60
    m = minutes % 60
    return f"{h} jam {m} menit"

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

def text_has_bypass_keyword(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in BYPASS_KEYWORDS)

def text_has_blacklist(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in BLACKLIST_KEYWORDS)

def is_low_quality_source(source_name: str) -> bool:
    s = (source_name or "").lower()
    return any(bad in s for bad in LOW_QUALITY_SOURCE_HINTS)

def is_recent_duplicate(title: str, recent_items: list) -> bool:
    t = normalize_text(title).lower()[:100]
    now_ts = time.time()
    for item in recent_items:
        if t == item.get("title", "") and (now_ts - item.get("time", 0)) < RECENT_WINDOW_MINUTES * 60:
            return True
    return False

def add_recent_title(title: str, recent_items: list):
    recent_items.append({
        "title": normalize_text(title).lower()[:100],
        "time": time.time()
    })

def cleanup_recent(recent_items: list):
    now_ts = time.time()
    return [x for x in recent_items if (now_ts - x.get("time", 0)) < RECENT_WINDOW_MINUTES * 60]

# ================= ANALYSIS =================
def classify_priority(text: str) -> str:
    t = (text or "").lower()

    high_hits = 0
    medium_hits = 0

    if any(x in t for x in ["trump", "white house", "cz", "binance"]):
        high_hits += 2
    if any(x in t for x in ["iran", "israel", "war", "missile", "attack", "retaliation", "hormuz", "oil", "opec"]):
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

def classify_kelayakan(priority: str, minutes: int, text: str) -> str:
    if minutes <= 60:
        return "SANGAT LAYAK"
    if minutes <= 180:
        return "LAYAK" if priority in ("HIGH", "MEDIUM") else "HATI-HATI"
    if minutes <= 360:
        return "HATI-HATI" if priority == "HIGH" else "KURANG IDEAL"
    if minutes <= 720:
        return "KURANG IDEAL" if priority == "HIGH" else "TELAT"
    if minutes <= 1440 and text_has_bypass_keyword(text):
        return "TELAT TAPI MASIH PENTING"
    return "TELAT"

# ================= FETCH NEWS =================
def fetch_newsapi():
    empty_stats = {
        "raw_total": 0,
        "kept": 0,
        "skip_source": 0,
        "skip_blacklist": 0,
        "skip_keyword": 0,
    }

    if not NEWS_API_KEY:
        print("DEBUG: NEWS_API_KEY kosong")
        return [], empty_stats

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": QUERY,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": MAX_NEWS_ITEMS,
        "apiKey": NEWS_API_KEY
    }

    try:
        r = requests.get(url, params=params, timeout=20)
        data = r.json()
    except Exception as e:
        print("DEBUG request error:", e)
        return [], empty_stats

    if DEBUG_MODE:
        print("DEBUG status       :", data.get("status"))
        print("DEBUG totalResults :", data.get("totalResults"))
        print("DEBUG message      :", data.get("message"))

    if data.get("status") != "ok":
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

        if is_low_quality_source(source):
            stats["skip_source"] += 1
            continue

        full_text = f"{title} {desc}"

        if text_has_blacklist(full_text):
            stats["skip_blacklist"] += 1
            continue

        ft = full_text.lower()
        if not text_has_primary_keyword(title) and not text_has_primary_keyword(full_text):
            if (
                "bitcoin" not in ft
                and "btc" not in ft
                and "crypto" not in ft
                and "oil" not in ft
                and "opec" not in ft
            ):
                stats["skip_keyword"] += 1
                continue

        articles.append({
            "title": title,
            "text": full_text,
            "url": url,
            "dt": dt,
            "source_name": source,
        })
        stats["kept"] += 1

    return articles, stats

# ================= MAIN FILTER =================
def collect_items():
    news_items, news_stats = fetch_newsapi()
    raw = sorted(news_items, key=lambda x: x["dt"], reverse=True)

    filtered = []
    seen_local = set()
    recent_items = load_recent()

    stats = {
        "newsapi_raw": news_stats["raw_total"],
        "newsapi_kept": news_stats["kept"],
        "newsapi_skip_source": news_stats["skip_source"],
        "newsapi_skip_blacklist": news_stats["skip_blacklist"],
        "newsapi_skip_keyword": news_stats["skip_keyword"],
        "skip_age": 0,
        "skip_duplicate": 0,
        "skip_recent": 0,
        "final_kept": 0,
    }

    for item in raw:
        minutes = age_minutes(item["dt"])
        text = item["text"]

        if minutes > MAX_AGE_MINUTES:
            if not (minutes <= BYPASS_AGE_MINUTES and text_has_bypass_keyword(text)):
                stats["skip_age"] += 1
                continue

        uid = make_uid(item["title"], item["url"])

        if uid in seen_local:
            stats["skip_duplicate"] += 1
            continue

        if is_recent_duplicate(item["title"], recent_items):
            stats["skip_recent"] += 1
            continue

        seen_local.add(uid)

        item["uid"] = uid
        item["age_minutes"] = minutes
        item["released_at"] = local_time_str(item["dt"])
        item["age_text"] = age_text(minutes)
        item["priority"] = classify_priority(text)
        item["bias"] = classify_bias(text)
        item["kelayakan"] = classify_kelayakan(item["priority"], minutes, text)

        filtered.append(item)
        add_recent_title(item["title"], recent_items)

    save_recent(cleanup_recent(recent_items))

    priority_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    filtered.sort(key=lambda x: (priority_rank.get(x["priority"], 9), x["age_minutes"]))

    stats["final_kept"] = len(filtered)
    return filtered, stats

# ================= FORMAT =================
def format_alert(item):
    return f"""🚨 IMPORTANT MARKET NEWS 🚨

Priority:
{item["priority"]}

Bias:
{item["bias"]}

Kelayakan Saat Ini:
{item["kelayakan"]}

Sumber:
{item["source_name"]}

Waktu Rilis:
{item["released_at"]}

Umur:
{item["age_text"]}

Judul:
{translate_text(item["title"])}

Asli:
{item["title"]}

Link:
{item["url"]}
"""

# ================= MAIN =================
def main():
    seen = load_seen()

    print("🚀 NEWS BOT START")
    print(f"Interval: {CHECK_INTERVAL} detik")
    print(f"Max umur normal: {MAX_AGE_MINUTES} menit")
    print(f"Bypass umur: {BYPASS_AGE_MINUTES} menit")

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
            print(f"Skip age               : {stats['skip_age']}")
            print(f"Skip duplicate local   : {stats['skip_duplicate']}")
            print(f"Skip recent            : {stats['skip_recent']}")

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