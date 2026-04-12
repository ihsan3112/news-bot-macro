import os
import re
import time
import html
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional

import requests
from deep_translator import GoogleTranslator


# =========================================================
# CONFIG
# =========================================================
NEWS_API_KEY = os.getenv("d731f728bb10403799a7a14bea6ac0f6")
TELEGRAM_BOT_TOKEN = os.getenv("8184173057:AAFxfvVPUpwovWHP3LPnZMlblqQy-E96sGA")
TELEGRAM_CHAT_ID = os.getenv("78066114019")

CHECK_INTERVAL = 1800  # 30 menit
PAGE_SIZE = 40

FRESH_NEWS_AGE_MINUTES = 360    # 6 jam
OK_NEWS_AGE_MINUTES = 1440      # 24 jam
MAX_NEWS_AGE_MINUTES = 2880     # 48 jam

ENABLE_TELEGRAM = True
ENABLE_TRANSLATE = True

QUERY = (
    '"donald trump" OR trump OR "white house" OR "jd vance" OR '
    'fed OR fomc OR powell OR inflation OR cpi OR ppi OR pce OR '
    '"interest rates" OR recession OR war OR conflict OR missile OR attack OR '
    'ceasefire OR truce OR iran OR israel OR ukraine OR russia OR '
    'oil OR opec OR hormuz OR bitcoin OR btc OR crypto OR etf OR liquidation OR whale'
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
    "business-insider",
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
    "marketwatch",
    "coindesk",
    "cointelegraph",
    "the block",
    "forbes",
    "yahoo finance",
    "barron's",
}

BLOCKED_SOURCE_NAMES = {
    "globenewswire",
}

NOISE_KEYWORDS = [
    "movie", "film", "gaming", "game", "celebrity", "fashion", "music",
    "tv show", "netflix", "iphone", "android phone", "gadget",
    "murder", "robbery", "helicopter", "badminton", "cricket"
]

TRUMP_KEYWORDS = [
    "trump", "donald trump", "white house", "president trump", "jd vance", "vance"
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


def source_strength(source_id: str, source_name: str) -> int:
    sid = (source_id or "").lower().strip()
    sname = (source_name or "").lower().strip()

    if sname in BLOCKED_SOURCE_NAMES:
        return -2
    if sid in STRONG_SOURCE_IDS or sname in STRONG_SOURCE_NAMES:
        return 2
    return 0


# =========================================================
# LOGIC
# =========================================================
def bukan_noise(text: str) -> bool:
    t = text.lower()
    return not any(k in t for k in NOISE_KEYWORDS)


def score_berita(title: str, description: str = "", source_id: str = "", source_name: str = "") -> int:
    t = f"{title} {description}".lower()
    score = 0

    score += source_strength(source_id, source_name)

    if any(k in t for k in TRUMP_KEYWORDS):
        score += 4
    if any(k in t for k in FED_KEYWORDS):
        score += 4
    if any(k in t for k in WAR_KEYWORDS):
        score += 4
    if any(k in t for k in CRYPTO_KEYWORDS):
        score += 2

    return score


def kategori_berita(title: str, description: str = "", source_id: str = "", source_name: str = ""):
    t = f"{title} {description}".lower()
    score = score_berita(title, description, source_id, source_name)

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
            "catatan": "Trump + perang = market cepat berubah. Tunggu konfirmasi candle.",
        }

    if any(k in t for k in TRUMP_KEYWORDS) and any(k in t for k in ["ceasefire", "truce", "de-escalation", "hormuz"]):
        return {
            "btc": "berpotensi terbantu",
            "wti": "bisa melemah",
            "emas": "bisa melemah / netral",
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
            "catatan": "Arus besar/whale hanya konfirmasi tambahan, bukan dasar entry tunggal.",
        }

    return {
        "btc": "pantau",
        "wti": "pantau",
        "emas": "pantau",
        "status": "• HANYA INFO",
        "catatan": "Belum cukup kuat untuk dijadikan dasar keputusan sendiri.",
    }


# =========================================================
# FETCH NEWS
# =========================================================
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
        if data.get("status") != "ok":
            return []
        return data.get("articles", [])
    except Exception:
        return []


def fetch_everything():
    if not NEWS_API_KEY:
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
        if data.get("status") != "ok":
            return []
        return data.get("articles", [])
    except Exception:
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

    return merged


# =========================================================
# FORMAT
# =========================================================
def print_berita(
    kategori: str,
    warna: str,
    score: int,
    freshness_label: str,
    freshness_color: str,
    judul_indo: str,
    judul_asli: str,
    source_name: str,
    published_local: str,
    umur_text: str,
    effect: dict,
) -> None:
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


def format_telegram_news(
    kategori: str,
    freshness_label: str,
    judul_indo: str,
    judul_asli: str,
    source_name: str,
    published_local: str,
    umur_text: str,
    url: str,
    effect: dict,
) -> str:
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
                effect = dampak_market(f"{judul} {desc}")

                print_berita(
                    kategori=kategori,
                    warna=warna,
                    score=score,
                    freshness_label=freshness_label,
                    freshness_color=freshness_color,
                    judul_indo=judul_indo,
                    judul_asli=judul,
                    source_name=source_name,
                    published_local=published_local,
                    umur_text=umur_text,
                    effect=effect,
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
                        kategori=kategori,
                        freshness_label=freshness_label,
                        judul_indo=judul_indo,
                        judul_asli=judul,
                        source_name=source_name,
                        published_local=published_local,
                        umur_text=umur_text,
                        url=url,
                        effect=effect,
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