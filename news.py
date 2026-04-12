import os
import time
from datetime import datetime, timezone

import requests
from deep_translator import GoogleTranslator


# =========================================================
# CONFIG
# =========================================================
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CHECK_INTERVAL = 1800 # test dulu 60 detik. nanti kalau sudah oke ubah ke 1800
PAGE_SIZE = 20

FRESH_NEWS_AGE_MINUTES = 360    # 6 jam
OK_NEWS_AGE_MINUTES = 1440      # 24 jam
MAX_NEWS_AGE_MINUTES = 2880     # 48 jam

ENABLE_TELEGRAM = True
ENABLE_TRANSLATE = True
DEBUG_MODE = True

QUERY = "trump OR iran OR bitcoin OR fed"


# =========================================================
# KEYWORDS
# =========================================================
TRUMP_KEYWORDS = [
    "trump", "donald trump", "white house", "jd vance", "vance"
]

FED_KEYWORDS = [
    "fed", "fomc", "powell", "federal reserve",
    "interest rate", "rate hike", "rate cut",
    "cpi", "ppi", "pce", "inflation", "hawkish", "dovish",
]

WAR_KEYWORDS = [
    "war", "conflict", "attack", "missile", "airstrike", "retaliation",
    "ceasefire", "truce", "de-escalation", "iran", "israel",
    "ukraine", "russia", "hormuz", "strait of hormuz", "oil", "opec",
]

CRYPTO_KEYWORDS = [
    "bitcoin", "btc", "crypto", "etf", "liquidation",
    "exchange", "stablecoin", "whale",
]

NOISE_KEYWORDS = [
    "movie", "film", "gaming", "game", "celebrity", "fashion", "music",
    "tv show", "netflix", "iphone", "android phone", "gadget",
    "murder", "robbery", "helicopter", "badminton", "cricket"
]


seen_titles = set()
sent_titles = set()


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
def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def log(msg: str, color: str = C.WHITE) -> None:
    print(f"{color}[{now()}] {msg}{C.RESET}")


def bersih(text: str) -> str:
    if not text:
        return ""
    return " ".join(str(text).strip().split())


def translate(text: str) -> str:
    if not ENABLE_TRANSLATE or not text:
        return text
    try:
        return GoogleTranslator(source="auto", target="id").translate(text)
    except Exception:
        return text


def kirim_telegram(pesan: str) -> None:
    if not ENABLE_TELEGRAM:
        return
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": pesan,
    }

    try:
        requests.post(url, data=data, timeout=20)
    except Exception as e:
        print(C.RED + f"Gagal kirim telegram: {e}" + C.RESET)


def parse_published_at(published_at: str):
    if not published_at:
        return None
    try:
        return datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except Exception:
        return None


def local_time_str(dt_utc) -> str:
    if dt_utc is None:
        return "-"
    try:
        return dt_utc.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "-"


def age_minutes(dt_utc) -> int:
    if dt_utc is None:
        return 999999
    now_utc = datetime.now(timezone.utc)
    diff = now_utc - dt_utc.astimezone(timezone.utc)
    return int(diff.total_seconds() // 60)


def age_str(minutes_old: int) -> str:
    if minutes_old < 60:
        return f"{minutes_old} menit"
    jam = minutes_old // 60
    menit = minutes_old % 60
    return f"{jam}j {menit}m"


def freshness_info(minutes_old: int):
    if minutes_old <= FRESH_NEWS_AGE_MINUTES:
        return "FRESH <= 6 JAM", C.GREEN
    if minutes_old <= OK_NEWS_AGE_MINUTES:
        return "LAYAK <= 24 JAM", C.YELLOW
    return "LAMA <= 48 JAM", C.GRAY


# =========================================================
# LOGIC
# =========================================================
def bukan_noise(text: str) -> bool:
    t = text.lower()
    return not any(k in t for k in NOISE_KEYWORDS)


def score_berita(title: str, description: str = "") -> int:
    t = f"{title} {description}".lower()
    score = 0

    if any(k in t for k in TRUMP_KEYWORDS):
        score += 4
    if any(k in t for k in FED_KEYWORDS):
        score += 4
    if any(k in t for k in WAR_KEYWORDS):
        score += 4
    if any(k in t for k in CRYPTO_KEYWORDS):
        score += 2

    return score


def kategori_berita(title: str, description: str = ""):
    t = f"{title} {description}".lower()
    score = score_berita(title, description)

    if any(k in t for k in TRUMP_KEYWORDS) and any(k in t for k in WAR_KEYWORDS):
        return "TRUMP + PERANG", C.RED, max(score, 9)

    if any(k in t for k in TRUMP_KEYWORDS) and any(k in t for k in FED_KEYWORDS):
        return "TRUMP + EKONOMI", C.RED, max(score, 9)

    if any(k in t for k in FED_KEYWORDS):
        return "FED / MAKRO", C.YELLOW, max(score, 7)

    if any(k in t for k in WAR_KEYWORDS):
        if any(k in t for k in ["ceasefire", "truce", "de-escalation"]):
            return "DE-ESCALATION", C.GREEN, max(score, 7)
        return "PERANG / GEOPOLITIK", C.MAGENTA, max(score, 7)

    if any(k in t for k in CRYPTO_KEYWORDS):
        return "CRYPTO MARKET", C.CYAN, max(score, 5)

    if score >= 2:
        return "PERHATIAN", C.BLUE, score

    return "INFO", C.WHITE, score


def dampak_market(text: str):
    t = text.lower()

    if any(k in t for k in TRUMP_KEYWORDS) and any(k in t for k in ["war", "attack", "missile", "iran", "israel", "ukraine", "russia"]):
        return {
            "btc": "rawan volatil / bisa tertekan",
            "wti": "cenderung naik",
            "emas": "cenderung naik",
            "status": "⚠️ WAIT / JANGAN ENTRY BURU-BURU",
            "catatan": "Trump + perang = market cepat berubah.",
        }

    if any(k in t for k in TRUMP_KEYWORDS) and any(k in t for k in ["ceasefire", "truce", "de-escalation", "hormuz"]):
        return {
            "btc": "berpotensi terbantu",
            "wti": "bisa melemah",
            "emas": "bisa netral / melemah",
            "status": "✅ PANTAU MOMENTUM RISK-ON",
            "catatan": "De-escalation biasanya meredakan fear market.",
        }

    if any(k in t for k in ["inflation", "cpi", "ppi", "pce", "hawkish", "rate hike"]):
        return {
            "btc": "berpotensi tertekan",
            "wti": "netral / tergantung konteks",
            "emas": "campuran",
            "status": "⚠️ VOLATILE / TUNGGU REAKSI DATA",
            "catatan": "Data makro panas biasanya menekan aset berisiko.",
        }

    if any(k in t for k in ["rate cut", "dovish", "cooling inflation"]):
        return {
            "btc": "berpotensi positif",
            "wti": "netral",
            "emas": "bisa positif",
            "status": "✅ BOLEH PANTAU MOMENTUM",
            "catatan": "Sentimen risk-on bisa membaik.",
        }

    if any(k in t for k in ["war", "attack", "missile", "airstrike", "retaliation"]):
        return {
            "btc": "volatil / rawan fake move",
            "wti": "cenderung naik",
            "emas": "cenderung naik",
            "status": "⚠️ HIGH RISK MARKET",
            "catatan": "Perang = market tidak stabil.",
        }

    if any(k in t for k in ["ceasefire", "truce", "de-escalation"]):
        return {
            "btc": "bisa lebih positif",
            "wti": "bisa turun",
            "emas": "bisa melemah",
            "status": "✅ RISK-ON BISA MEMBAIK",
            "catatan": "Market biasanya lebih tenang kalau konflik mereda.",
        }

    if any(k in t for k in ["liquidation", "whale", "exchange", "stablecoin"]):
        return {
            "btc": "pantau reaksi harga langsung",
            "wti": "tidak relevan",
            "emas": "tidak relevan",
            "status": "👀 PANTAU REAKSI BTC",
            "catatan": "Whale hanya konfirmasi tambahan, bukan dasar entry tunggal.",
        }

    return {
        "btc": "pantau",
        "wti": "pantau",
        "emas": "pantau",
        "status": "• HANYA INFO",
        "catatan": "Belum cukup kuat untuk dasar keputusan sendiri.",
    }


# =========================================================
# FETCH
# =========================================================
def fetch_everything():
    if not NEWS_API_KEY:
        print("DEBUG: NEWS_API_KEY kosong")
        return []

    url = "https://newsapi.org/v2/everything"
    params = {
        "apiKey": NEWS_API_KEY,
        "q": QUERY,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": PAGE_SIZE,
    }

    try:
        response = requests.get(url, params=params, timeout=20)
        data = response.json()

        if DEBUG_MODE:
            print("DEBUG EVERYTHING STATUS:", data.get("status"))
            print("DEBUG EVERYTHING TOTAL:", data.get("totalResults"))
            if data.get("status") != "ok":
                print("DEBUG EVERYTHING FULL:", data)

        if data.get("status") != "ok":
            return []

        return data.get("articles", [])
    except Exception as e:
        print("DEBUG EVERYTHING ERROR:", e)
        return []


def fetch_top_headlines():
    if not NEWS_API_KEY:
        return []

    url = "https://newsapi.org/v2/top-headlines"
    params = {
        "apiKey": NEWS_API_KEY,
        "language": "en",
        "category": "business",
        "pageSize": PAGE_SIZE,
    }

    try:
        response = requests.get(url, params=params, timeout=20)
        data = response.json()

        if DEBUG_MODE:
            print("DEBUG TOP STATUS:", data.get("status"))
            print("DEBUG TOP TOTAL:", data.get("totalResults"))
            if data.get("status") != "ok":
                print("DEBUG TOP FULL:", data)

        if data.get("status") != "ok":
            return []

        return data.get("articles", [])
    except Exception as e:
        print("DEBUG TOP ERROR:", e)
        return []


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

    if DEBUG_MODE:
        print("DEBUG MERGED COUNT:", len(merged))

    return merged


# =========================================================
# FORMAT
# =========================================================
def print_berita(kategori, warna, score, freshness_label, freshness_color, judul_indo, judul_asli, source_name, published_local, umur_text, effect):
    print(warna + C.BOLD + f"\n[{kategori}] SCORE={score}" + C.RESET)
    print(freshness_color + f"Fresh  : {freshness_label}" + C.RESET)
    print(warna + f"Sumber : {source_name}" + C.RESET)
    print(warna + f"Terbit : {published_local}" + C.RESET)
    print(warna + f"Umur   : {umur_text}" + C.RESET)
    print(warna + f"Judul  : {judul_indo}" + C.RESET)
    print(C.WHITE + f"Asli   : {judul_asli}" + C.RESET)
    print(C.CYAN + f"BTC    : {effect['btc']}" + C.RESET)
    print(C.YELLOW + f"WTI    : {effect['wti']}" + C.RESET)
    print(C.WHITE + f"EMAS   : {effect['emas']}" + C.RESET)
    print(C.MAGENTA + f"Status : {effect['status']}" + C.RESET)
    print(C.BLUE + f"Catatan: {effect['catatan']}" + C.RESET)


def format_telegram_news(kategori, freshness_label, judul_indo, judul_asli, source_name, published_local, umur_text, url, effect):
    return (
        f"🚨 {kategori}\n\n"
        f"Status Waktu:\n{freshness_label}\n\n"
        f"Sumber:\n{source_name}\n\n"
        f"Terbit:\n{published_local}\n\n"
        f"Umur Berita:\n{umur_text}\n\n"
        f"Judul Indo:\n{judul_indo}\n\n"
        f"Judul Asli:\n{judul_asli}\n\n"
        f"Dampak:\n"
        f"- BTC  : {effect['btc']}\n"
        f"- WTI  : {effect['wti']}\n"
        f"- EMAS : {effect['emas']}\n\n"
        f"Status:\n{effect['status']}\n\n"
        f"Catatan:\n{effect['catatan']}\n\n"
        f"Link:\n{url}"
    )


# =========================================================
# MAIN
# =========================================================
def main():
    print(C.GREEN + C.BOLD + "=== NEWS BOT START ===" + C.RESET)
    print(C.RED + "MERAH   = TRUMP + PERANG / TRUMP + EKONOMI" + C.RESET)
    print(C.MAGENTA + "MAGENTA = PERANG / GEOPOLITIK" + C.RESET)
    print(C.YELLOW + "KUNING  = FED / MAKRO" + C.RESET)
    print(C.GREEN + "HIJAU   = DE-ESCALATION / FRESH" + C.RESET)
    print(C.CYAN + "CYAN    = CRYPTO MARKET" + C.RESET)
    print(C.GRAY + "ABU     = BERITA LAMA TAPI MASIH LAYAK" + C.RESET)
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
                    "source_name": source_name,
                    "dt_pub": dt_pub,
                    "menit_umur": menit_umur,
                })

            items.sort(key=lambda x: x["menit_umur"])

            tampil = 0
            kirim = 0
            fresh_count = 0
            ok_count = 0
            old_count = 0

            for item in items[:12]:
                judul = item["judul"]
                desc = item["desc"]
                url = item["url"]
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

                kategori, warna, score = kategori_berita(judul, desc)
                judul_indo = translate(judul)
                effect = dampak_market(f"{judul} {desc}")

                print_berita(
                    kategori,
                    warna,
                    score,
                    freshness_label,
                    freshness_color,
                    judul_indo,
                    judul,
                    source_name,
                    published_local,
                    umur_text,
                    effect,
                )
                tampil += 1

                if kategori in [
                    "TRUMP + PERANG",
                    "TRUMP + EKONOMI",
                    "FED / MAKRO",
                    "PERANG / GEOPOLITIK",
                    "DE-ESCALATION",
                    "CRYPTO MARKET",
                    "PERHATIAN",
                ] and judul not in sent_titles:
                    pesan = format_telegram_news(
                        kategori,
                        freshness_label,
                        judul_indo,
                        judul,
                        source_name,
                        published_local,
                        umur_text,
                        url,
                        effect,
                    )
                    kirim_telegram(pesan)
                    sent_titles.add(judul)
                    kirim += 1

            if tampil == 0:
                print(C.YELLOW + "\n[INFO] Tidak ada berita relevan dalam 48 jam terakhir." + C.RESET)

            log(f"Berita tampil   : {tampil}", C.CYAN)
            log(f"Telegram kirim  : {kirim}", C.CYAN)
            log(f"Fresh <=6 jam   : {fresh_count}", C.GREEN)
            log(f"Layak <=24 jam  : {ok_count}", C.YELLOW)
            log(f"Lama <=48 jam   : {old_count}", C.GRAY)
            log(f"Skip noise      : {skip_noise}", C.BLUE)
            log(f"Skip >48 jam    : {skip_too_old}", C.BLUE)

        except Exception as e:
            print(C.RED + f"ERROR NEWS: {e}" + C.RESET)

        print(C.BLUE + f"\nTunggu {CHECK_INTERVAL} detik...\n" + C.RESET)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()