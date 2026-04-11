import time
import requests
from datetime import datetime, timezone
from deep_translator import GoogleTranslator


# =========================================================
# CONFIG
# =========================================================
NEWS_API_KEY = "d731f728bb10403799a7a14bea6ac0f6"
TELEGRAM_BOT_TOKEN = "8184173057:AAFxfvVPUpwovWHP3LPnZMlblqQy-E96sGA"
TELEGRAM_CHAT_ID = "7806614019"

# OPSIONAL
TRADING_ECONOMICS_API_KEY = ""
TRADING_ECONOMICS_COUNTRIES = ["United States"]

CHECK_INTERVAL = 1800              # 30 menit
PAGE_SIZE = 40

FRESH_NEWS_AGE_MINUTES = 240       # 4 jam
OK_NEWS_AGE_MINUTES = 720          # 12 jam
MAX_NEWS_AGE_MINUTES = 1440        # 24 jam

ENABLE_TELEGRAM = True
ENABLE_TRANSLATE = True
ENABLE_ECONOMIC_CALENDAR = True

# Query dibuat lebih longgar
QUERY = (
    '(trump OR fed OR fomc OR inflation OR cpi OR ppi OR pce OR recession OR '
    '"interest rates" OR tariff OR sanctions OR war OR conflict OR attack OR missile OR '
    'ceasefire OR truce OR de-escalation OR hormuz OR oil OR opec OR china OR '
    'russia OR ukraine OR israel OR iran OR treasury OR yields OR jobs OR payrolls OR '
    'bitcoin OR btc OR crypto OR etf OR "crypto regulation")'
)

STRONG_SOURCE_IDS = {
    "reuters",
    "bloomberg",
    "associated-press",
    "cnn",
    "cnbc",
    "financial-times",
    "the-wall-street-journal",
    "abc-news",
    "al-jazeera-english",
    "business-insider"
}

STRONG_SOURCE_NAMES = {
    "reuters",
    "bloomberg",
    "associated press",
    "cnn",
    "cnbc",
    "financial times",
    "the wall street journal",
    "abc news",
    "al jazeera english",
    "business insider",
    "coindesk",
    "cointelegraph",
    "the block",
    "marketwatch",
    "investing.com",
    "forbes",
    "yahoo finance",
    "barron's"
}

BLOCKED_SOURCE_NAMES = {
    "globenewswire"
}

NOISE_KEYWORDS = [
    "movie", "film", "gaming", "game", "celebrity", "fashion", "music",
    "tv show", "netflix", "iphone", "android phone", "gadget",
    "murder", "robbery", "helicopter"
]

TRUMP_KEYWORDS = [
    "trump", "donald trump", "white house", "president trump", "us election"
]

TRUMP_IMPACT_KEYWORDS = [
    "tariff", "china", "trade war", "sanctions", "iran", "israel",
    "ukraine", "russia", "war", "conflict", "attack", "missile",
    "oil", "opec", "fed", "inflation", "interest rate", "economy",
    "tax", "policy", "ceasefire", "truce", "de-escalation",
    "hormuz", "strait of hormuz"
]

DANGER_KEYWORDS = [
    "war", "missile", "attack", "airstrike", "invasion", "retaliation",
    "military", "nuclear", "blockade", "troops", "emergency",
    "martial law", "oil shock", "strait of hormuz", "shipping disruption"
]

DEESCALATION_KEYWORDS = [
    "ceasefire", "truce", "de-escalation", "peace talks",
    "suspend bombing", "shipping reopen", "reopen shipping",
    "hormuz reopen", "strait of hormuz reopen"
]

MACRO_KEYWORDS = [
    "fed", "fomc", "inflation", "cpi", "ppi", "interest rate",
    "rate hike", "rate cut", "payrolls", "jobs report", "recession",
    "gdp", "bond yield", "treasury", "central bank", "hawkish", "dovish",
    "pce", "unemployment", "jobless claims", "yield"
]

CRYPTO_KEYWORDS = [
    "bitcoin", "btc", "crypto", "etf", "sec", "crypto regulation",
    "stablecoin", "exchange", "liquidation"
]

IMPORTANT_KEYWORDS = [
    "tariff", "sanctions", "opec", "oil", "china", "russia",
    "ukraine", "israel", "iran", "bank crisis", "default",
    "treasury", "yield"
]

seen_titles = set()
sent_titles = set()
seen_calendar_events = set()
sent_calendar_events = set()


# =========================================================
# WARNA TERMINAL
# =========================================================
class C:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


# =========================================================
# UTIL
# =========================================================
def now():
    return datetime.now().strftime("%H:%M:%S")


def log(msg, color=C.WHITE):
    print(f"{color}[{now()}] {msg}{C.RESET}")


def bersih(text):
    if not text:
        return ""
    return " ".join(str(text).strip().split())


def translate(text):
    if not ENABLE_TRANSLATE:
        return text
    try:
        return GoogleTranslator(source="auto", target="id").translate(text)
    except Exception:
        return text


def kirim_telegram(pesan):
    if not ENABLE_TELEGRAM:
        return
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": pesan}
    try:
        requests.post(url, data=data, timeout=20)
    except Exception as e:
        print(C.RED + f"Gagal kirim telegram: {e}" + C.RESET)


def parse_published_at(published_at):
    if not published_at:
        return None
    try:
        return datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except Exception:
        return None


def local_time_str(dt_utc):
    if dt_utc is None:
        return "-"
    try:
        return dt_utc.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "-"


def age_minutes(dt_utc):
    if dt_utc is None:
        return 999999
    now_utc = datetime.now(timezone.utc)
    diff = now_utc - dt_utc.astimezone(timezone.utc)
    return int(diff.total_seconds() // 60)


def age_str(minutes_old):
    if minutes_old < 60:
        return f"{minutes_old} menit"
    jam = minutes_old // 60
    menit = minutes_old % 60
    return f"{jam}j {menit}m"


def source_strength(source_id, source_name):
    sid = (source_id or "").lower().strip()
    sname = (source_name or "").lower().strip()

    if sname in BLOCKED_SOURCE_NAMES:
        return -2
    if sid in STRONG_SOURCE_IDS or sname in STRONG_SOURCE_NAMES:
        return 2
    return 0


# =========================================================
# LOGIC NEWS
# =========================================================
def bukan_noise(text):
    t = text.lower()
    return not any(k in t for k in NOISE_KEYWORDS)


def score_berita(title, description="", source_id="", source_name=""):
    t = f"{title} {description}".lower()
    score = 0

    score += source_strength(source_id, source_name)

    if any(k in t for k in TRUMP_KEYWORDS):
        score += 4

    for k in DANGER_KEYWORDS:
        if k in t:
            score += 5

    for k in DEESCALATION_KEYWORDS:
        if k in t:
            score += 4

    for k in MACRO_KEYWORDS:
        if k in t:
            score += 3

    for k in CRYPTO_KEYWORDS:
        if k in t:
            score += 2

    for k in IMPORTANT_KEYWORDS:
        if k in t:
            score += 2

    return score


def kategori_berita(title, description="", source_id="", source_name=""):
    t = f"{title} {description}".lower()
    score = score_berita(title, description, source_id, source_name)

    if any(k in t for k in TRUMP_KEYWORDS):
        if any(k in t for k in TRUMP_IMPACT_KEYWORDS):
            return "TRUMP GLOBAL IMPACT", C.RED, max(score, 10)

    if any(k in t for k in DANGER_KEYWORDS):
        return "BAHAYA BESAR", C.RED, max(score, 7)

    if any(k in t for k in DEESCALATION_KEYWORDS):
        return "DE-ESCALATION", C.GREEN, max(score, 6)

    if any(k in t for k in MACRO_KEYWORDS) and score >= 4:
        return "PENTING MAKRO", C.YELLOW, score

    if any(k in t for k in CRYPTO_KEYWORDS) and score >= 3:
        return "PENTING CRYPTO", C.CYAN, score

    if score >= 2:
        return "PERHATIAN", C.BLUE, score

    return "INFO", C.WHITE, score


def dampak(text):
    t = text.lower()

    if any(k in t for k in TRUMP_KEYWORDS):
        if any(k in t for k in ["ceasefire", "truce", "de-escalation", "hormuz", "strait of hormuz"]):
            return "De-escalation: minyak bisa turun, risk sentiment bisa membaik, BTC bisa terbantu."
        if any(k in t for k in ["tariff", "trade war", "china", "sanctions"]):
            return "Trump + tarif/sanksi: risk-off, BTC bisa volatil atau tertekan."
        if any(k in t for k in ["war", "iran", "israel", "ukraine", "russia", "attack", "missile"]):
            return "Trump + geopolitik: market rawan liar. Pantau BTC, emas, minyak."

    if any(k in t for k in ["ceasefire", "truce", "de-escalation", "suspend bombing"]):
        return "Risk-on membaik. Minyak bisa melemah, BTC bisa lebih positif."

    if any(k in t for k in ["war", "attack", "missile", "airstrike", "retaliation", "strait of hormuz"]):
        return "Risk-off keras. Market liar, BTC volatil, minyak bisa naik."

    if any(k in t for k in ["inflation", "cpi", "ppi", "rate hike", "hawkish", "bond yield", "pce"]):
        return "Tekanan ke aset berisiko. BTC berpotensi tertekan."

    if any(k in t for k in ["rate cut", "cooling inflation", "stimulus", "dovish"]):
        return "Risk-on bisa menguat. BTC dan aset risiko bisa lebih positif."

    if any(k in t for k in ["oil", "opec"]):
        return "Pantau minyak, inflasi, dan sentimen risk-off."

    if any(k in t for k in ["bitcoin", "btc", "etf", "crypto regulation", "sec"]):
        return "Fokus ke BTC/crypto. Pantau follow-through candle dan volume."

    return "Pantau market. Jangan jadikan headline ini dasar entry tunggal."


def status_trading(text):
    t = text.lower()

    if any(k in t for k in TRUMP_KEYWORDS):
        if any(k in t for k in ["ceasefire", "truce", "de-escalation", "hormuz", "strait of hormuz"]):
            return "✅ PANTAU MOMENTUM RISK-ON"
        if any(k in t for k in ["tariff", "war", "china", "sanctions", "iran", "israel", "ukraine", "russia"]):
            return "⚠️ WAIT / JANGAN ENTRY BURU-BURU"
        return "👀 PANTAU REAKSI MARKET"

    if any(k in t for k in ["ceasefire", "truce", "de-escalation"]):
        return "✅ PANTAU MOMENTUM RISK-ON"

    if any(k in t for k in ["war", "attack", "missile", "airstrike", "inflation", "cpi", "ppi", "rate hike", "tariff", "pce"]):
        return "⚠️ WAIT / JANGAN ENTRY BURU-BURU"

    if any(k in t for k in ["rate cut", "stimulus", "cooling inflation", "dovish"]):
        return "✅ BOLEH PANTAU MOMENTUM"

    if any(k in t for k in ["bitcoin", "btc", "etf", "crypto regulation"]):
        return "👀 PANTAU REAKSI BTC"

    return "• HANYA INFO"


def freshness_info(minutes_old):
    if minutes_old <= FRESH_NEWS_AGE_MINUTES:
        return "FRESH <= 4 JAM", C.GREEN
    if minutes_old <= OK_NEWS_AGE_MINUTES:
        return "LAYAK <= 12 JAM", C.YELLOW
    return "LAMA <= 24 JAM", C.GRAY


# =========================================================
# ECONOMIC CALENDAR
# =========================================================
def fetch_economic_calendar():
    if not ENABLE_ECONOMIC_CALENDAR or not TRADING_ECONOMICS_API_KEY:
        return []

    try:
        url = "https://api.tradingeconomics.com/calendar"
        params = {"c": TRADING_ECONOMICS_API_KEY, "f": "json"}
        response = requests.get(url, params=params, timeout=20)
        data = response.json()

        if not isinstance(data, list):
            return []

        results = []
        for item in data:
            country = bersih(item.get("Country", ""))
            category = bersih(item.get("Category", ""))
            date_str = bersih(item.get("Date", ""))
            importance = item.get("Importance", 0)

            if TRADING_ECONOMICS_COUNTRIES and country not in TRADING_ECONOMICS_COUNTRIES:
                continue

            if int(importance or 0) < 3:
                continue

            dt_event = parse_te_datetime(date_str)
            if dt_event is None:
                continue

            diff_min = minutes_diff_from_now(dt_event)
            if abs(diff_min) > 720:
                continue

            event_id = f"{country}|{category}|{date_str}"
            results.append({
                "id": event_id,
                "country": country,
                "category": category,
                "date": dt_event,
                "importance": int(importance or 0),
                "actual": bersih(item.get("Actual", "")),
                "forecast": bersih(item.get("Forecast", "")),
                "previous": bersih(item.get("Previous", ""))
            })

        return results

    except Exception:
        return []


def parse_te_datetime(dt_str):
    if not dt_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(dt_str[:26], fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None


def minutes_diff_from_now(dt_utc):
    now_utc = datetime.now(timezone.utc)
    diff = dt_utc.astimezone(timezone.utc) - now_utc
    return int(diff.total_seconds() // 60)


def classify_calendar_effect(category, actual, forecast, previous):
    text = f"{category} {actual} {forecast} {previous}".lower()

    if any(k in text for k in ["cpi", "ppi", "pce", "inflation"]):
        return "PENTING KALENDER", C.YELLOW, "Data inflasi high impact. Pantau BTC, DXY, yield, dan reaksi candle."
    if any(k in text for k in ["interest rate", "fed", "fomc"]):
        return "PENTING KALENDER", C.RED, "Event suku bunga/Fed. Potensi volatilitas sangat besar."
    if any(k in text for k in ["payroll", "unemployment", "jobless claims", "employment"]):
        return "PENTING KALENDER", C.MAGENTA, "Data tenaga kerja high impact. Bisa gerakkan USD dan BTC."
    if any(k in text for k in ["gdp"]):
        return "PENTING KALENDER", C.CYAN, "GDP high impact. Pantau sentimen risk-on / risk-off."

    return "PENTING KALENDER", C.YELLOW, "Event ekonomi high impact. Tunggu reaksi market."


# =========================================================
# FETCH NEWS
# =========================================================
def fetch_top_headlines():
    url = "https://newsapi.org/v2/top-headlines"
    params = {
        "apiKey": NEWS_API_KEY,
        "language": "en",
        "category": "business",
        "pageSize": PAGE_SIZE
    }
    response = requests.get(url, params=params, timeout=20)
    data = response.json()
    if data.get("status") != "ok":
        return []
    return data.get("articles", [])


def fetch_everything():
    url = "https://newsapi.org/v2/everything"
    params = {
        "apiKey": NEWS_API_KEY,
        "q": QUERY,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": PAGE_SIZE
    }
    response = requests.get(url, params=params, timeout=20)
    data = response.json()
    if data.get("status") != "ok":
        return []
    return data.get("articles", [])


def ambil_berita():
    top = fetch_top_headlines()
    everything = fetch_everything()

    merged = []
    seen = set()

    for b in top + everything:
        title = bersih(b.get("title", ""))
        url = bersih(b.get("url", ""))
        key = f"{title}|{url}"
        if not title or key in seen:
            continue
        seen.add(key)
        merged.append(b)

    return merged


# =========================================================
# FORMAT
# =========================================================
def print_berita(kategori, warna, score, freshness_label, freshness_color, judul_indo, judul_asli, efek, status, source_name, published_local, umur_text):
    print(warna + C.BOLD + f"\n[{kategori}] SCORE={score}" + C.RESET)
    print(freshness_color + f"Fresh  : {freshness_label}" + C.RESET)
    print(warna + f"Sumber : {source_name}" + C.RESET)
    print(warna + f"Terbit : {published_local}" + C.RESET)
    print(warna + f"Umur   : {umur_text}" + C.RESET)
    print(warna + f"Judul  : {judul_indo}" + C.RESET)
    print(C.WHITE + f"Asli   : {judul_asli}" + C.RESET)
    print(C.MAGENTA + f"Dampak : {efek}" + C.RESET)
    print(C.YELLOW + f"Status : {status}" + C.RESET)


def print_calendar(event_type, color, event_name, country, event_time, actual, forecast, previous, note):
    print(color + C.BOLD + f"\n[{event_type}]" + C.RESET)
    print(color + f"Negara : {country}" + C.RESET)
    print(color + f"Jam    : {event_time}" + C.RESET)
    print(color + f"Event  : {event_name}" + C.RESET)
    print(color + f"Actual : {actual or '-'}" + C.RESET)
    print(color + f"Predik : {forecast or '-'}" + C.RESET)
    print(color + f"Sblm   : {previous or '-'}" + C.RESET)
    print(C.YELLOW + f"Catatan: {note}" + C.RESET)


def format_telegram_news(kategori, freshness_label, judul_indo, judul_asli, efek, status, source_name, url, published_local, umur_text):
    return (
        f"🚨 {kategori}\n\n"
        f"Status Waktu:\n{freshness_label}\n\n"
        f"Sumber:\n{source_name}\n\n"
        f"Terbit:\n{published_local}\n\n"
        f"Umur Berita:\n{umur_text}\n\n"
        f"Judul Indo:\n{judul_indo}\n\n"
        f"Judul Asli:\n{judul_asli}\n\n"
        f"Dampak:\n{efek}\n\n"
        f"Status:\n{status}\n\n"
        f"Link:\n{url}"
    )


def format_telegram_calendar(event_type, country, event_name, event_time, actual, forecast, previous, note):
    return (
        f"📅 {event_type}\n\n"
        f"Negara:\n{country}\n\n"
        f"Jam:\n{event_time}\n\n"
        f"Event:\n{event_name}\n\n"
        f"Actual:\n{actual or '-'}\n\n"
        f"Forecast:\n{forecast or '-'}\n\n"
        f"Previous:\n{previous or '-'}\n\n"
        f"Catatan:\n{note}"
    )


# =========================================================
# MAIN
# =========================================================
def main():
    print(C.GREEN + C.BOLD + "=== NEWS BOT START ===" + C.RESET)
    print(C.RED + "MERAH   = TRUMP GLOBAL IMPACT / BAHAYA BESAR" + C.RESET)
    print(C.GREEN + "HIJAU   = DE-ESCALATION / FRESH" + C.RESET)
    print(C.YELLOW + "KUNING  = MAKRO / LAYAK / KALENDER" + C.RESET)
    print(C.CYAN + "CYAN    = CRYPTO PENTING" + C.RESET)
    print(C.GRAY + "ABU     = BERITA LAMA TAPI MASIH KONTEKS" + C.RESET)
    print(C.BLUE + f"INTERVAL= {CHECK_INTERVAL // 60} menit" + C.RESET)
    print(C.BLUE + f"FRESH   = <= {FRESH_NEWS_AGE_MINUTES // 60} jam" + C.RESET)
    print(C.BLUE + f"LAYAK   = <= {OK_NEWS_AGE_MINUTES // 60} jam" + C.RESET)
    print(C.BLUE + f"MAX     = <= {MAX_NEWS_AGE_MINUTES // 60} jam" + C.RESET)

    while True:
        log("Cek berita...", C.BLUE)

        try:
            berita = ambil_berita()

            items = []
            skip_noise = 0
            skip_too_old = 0

            for b in berita:
                judul = bersih(b.get("title", ""))
                desc = bersih(b.get("description", ""))
                url = bersih(b.get("url", ""))
                source_id = bersih((b.get("source") or {}).get("id", "")).lower()
                source_name = bersih((b.get("source") or {}).get("name", "-"))
                published_at_raw = b.get("publishedAt", "")

                if not judul:
                    continue

                if judul in seen_titles:
                    continue

                if not bukan_noise(judul):
                    skip_noise += 1
                    continue

                dt_pub = parse_published_at(published_at_raw)
                menit_umur = age_minutes(dt_pub)

                if menit_umur > MAX_NEWS_AGE_MINUTES:
                    skip_too_old += 1
                    continue

                items.append({
                    "judul": judul,
                    "desc": desc,
                    "url": url,
                    "source_id": source_id,
                    "source_name": source_name,
                    "dt_pub": dt_pub,
                    "menit_umur": menit_umur
                })

            # urutkan paling baru dulu
            items.sort(key=lambda x: x["menit_umur"])

            tampil = 0
            kirim = 0
            fresh_count = 0
            ok_count = 0
            old_count = 0

            for item in items[:15]:
                judul = item["judul"]
                desc = item["desc"]
                url = item["url"]
                source_id = item["source_id"]
                source_name = item["source_name"]
                dt_pub = item["dt_pub"]
                menit_umur = item["menit_umur"]

                if judul in seen_titles:
                    continue
                seen_titles.add(judul)

                published_local = local_time_str(dt_pub)
                umur_text = age_str(menit_umur)
                freshness_label, freshness_color = freshness_info(menit_umur)

                if menit_umur <= FRESH_NEWS_AGE_MINUTES:
                    fresh_count += 1
                elif menit_umur <= OK_NEWS_AGE_MINUTES:
                    ok_count += 1
                else:
                    old_count += 1

                kategori, warna, score = kategori_berita(judul, desc, source_id, source_name)

                judul_indo = translate(judul)
                efek = dampak(f"{judul} {desc}")
                status = status_trading(f"{judul} {desc}")

                print_berita(
                    kategori=kategori,
                    warna=warna,
                    score=score,
                    freshness_label=freshness_label,
                    freshness_color=freshness_color,
                    judul_indo=judul_indo,
                    judul_asli=judul,
                    efek=efek,
                    status=status,
                    source_name=source_name,
                    published_local=published_local,
                    umur_text=umur_text
                )
                tampil += 1

                if kategori in [
                    "TRUMP GLOBAL IMPACT",
                    "BAHAYA BESAR",
                    "DE-ESCALATION",
                    "PENTING MAKRO",
                    "PENTING CRYPTO"
                ] and judul not in sent_titles:
                    pesan = format_telegram_news(
                        kategori=kategori,
                        freshness_label=freshness_label,
                        judul_indo=judul_indo,
                        judul_asli=judul,
                        efek=efek,
                        status=status,
                        source_name=source_name,
                        url=url,
                        published_local=published_local,
                        umur_text=umur_text
                    )
                    kirim_telegram(pesan)
                    sent_titles.add(judul)
                    kirim += 1

            if tampil == 0:
                print(C.YELLOW + "\n[INFO] Tidak ada berita relevan dalam 24 jam terakhir." + C.RESET)

            log(f"Berita tampil   : {tampil}", C.CYAN)
            log(f"Telegram kirim  : {kirim}", C.CYAN)
            log(f"Fresh <=4 jam   : {fresh_count}", C.GREEN)
            log(f"Layak <=12 jam  : {ok_count}", C.YELLOW)
            log(f"Lama <=24 jam   : {old_count}", C.GRAY)
            log(f"Skip noise      : {skip_noise}", C.BLUE)
            log(f"Skip >24 jam    : {skip_too_old}", C.BLUE)

        except Exception as e:
            print(C.RED + f"ERROR NEWS: {e}" + C.RESET)

        if ENABLE_ECONOMIC_CALENDAR:
            try:
                events = fetch_economic_calendar()
                tampil_cal = 0
                kirim_cal = 0

                for ev in events:
                    if ev["id"] in seen_calendar_events:
                        continue
                    seen_calendar_events.add(ev["id"])

                    event_type, color, note = classify_calendar_effect(
                        ev["category"], ev["actual"], ev["forecast"], ev["previous"]
                    )
                    event_time = local_time_str(ev["date"])

                    print_calendar(
                        event_type=event_type,
                        color=color,
                        event_name=ev["category"],
                        country=ev["country"],
                        event_time=event_time,
                        actual=ev["actual"],
                        forecast=ev["forecast"],
                        previous=ev["previous"],
                        note=note
                    )
                    tampil_cal += 1

                    if ev["id"] not in sent_calendar_events:
                        pesan = format_telegram_calendar(
                            event_type=event_type,
                            country=ev["country"],
                            event_name=ev["category"],
                            event_time=event_time,
                            actual=ev["actual"],
                            forecast=ev["forecast"],
                            previous=ev["previous"],
                            note=note
                        )
                        kirim_telegram(pesan)
                        sent_calendar_events.add(ev["id"])
                        kirim_cal += 1

                log(f"Kalender tampil: {tampil_cal}", C.MAGENTA)
                log(f"Kalender kirim : {kirim_cal}", C.MAGENTA)

            except Exception as e:
                print(C.RED + f"ERROR CALENDAR: {e}" + C.RESET)

        print(C.BLUE + f"\nTunggu {CHECK_INTERVAL} detik...\n" + C.RESET)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()