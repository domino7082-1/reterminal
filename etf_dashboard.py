import datetime
import math
import os
import re
import time
import requests
from PIL import Image, ImageDraw, ImageFont

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

# --- KONFIGURÁCIA (reTerminal E1001 · 800x480 1-bit BMP) ---
WIDTH = 800
HEIGHT = 480
RENDER_MODE = 'L'
THRESHOLD_ON_WHITE = 155  # Plnšie čierne ťahy (znamenká +, − a číslice) na bielom pozadí
THRESHOLD_ON_BLACK = 110  # Plnšie biele ťahy v čiernych hlavičkách a štítkoch
BACKGROUND_COLOR = 255    # Biela
TEXT_COLOR = 0            # Čierna
MINUS_SIGN = "\u2212"     # Skutočné matematické mínus (−), rovnaká šírka aj hrúbka ako +
ATH_INVERT_THRESHOLD = -10.0  # Hranica poklesu od ATH pre inverzný čierny štítok

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "etf_output.bmp")

# Definícia 4 ETF fondov (Xetra, EUR) + záložné dáta pri výpadku API
ETF_CONFIG = [
    {
        "ticker": "SXR8",
        "yahoo": "SXR8.DE",
        "name": "Core S&P 500",
        "region": "USA",
        "fallback_price": 694.06,
        "fallback_day_pct": -3.51,
        "fallback_ath": 755.30,
        "fallback_ath_date": "10/26",
        "fallback_min_52w": 562.40,
        "fallback_max_52w": 755.30,
        "fallback_perf": {"1m": -4.2, "3m": -2.8, "6m": 1.1, "1y": 14.6},
    },
    {
        "ticker": "EXUS",
        "yahoo": "EXUS.DE",
        "name": "MSCI World ex USA",
        "region": "EX-US",
        "fallback_price": 38.500,
        "fallback_day_pct": -2.37,
        "fallback_ath": 41.180,
        "fallback_ath_date": "11/26",
        "fallback_min_52w": 33.420,
        "fallback_max_52w": 41.180,
        "fallback_perf": {"1m": -3.1, "3m": -1.4, "6m": 1.2, "1y": 11.4},
    },
    {
        "ticker": "IS3N",
        "yahoo": "IS3N.DE",
        "name": "Core MSCI EM IMI",
        "region": "EM",
        "fallback_price": 40.955,
        "fallback_day_pct": -4.93,
        "fallback_ath": 51.006,
        "fallback_ath_date": "06/26",
        "fallback_min_52w": 38.120,
        "fallback_max_52w": 51.006,
        "fallback_perf": {"1m": -6.8, "3m": -9.2, "6m": -10.7, "1y": 4.8},
    },
    {
        "ticker": "IUSN",
        "yahoo": "IUSN.DE",
        "name": "MSCI World Small Cap",
        "region": "SMALL",
        "fallback_price": 8.728,
        "fallback_day_pct": -2.50,
        "fallback_ath": 9.362,
        "fallback_ath_date": "08/26",
        "fallback_min_52w": 7.410,
        "fallback_max_52w": 9.362,
        "fallback_perf": {"1m": -3.4, "3m": -2.1, "6m": 1.2, "1y": 12.1},
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Dni v slovenskom kalendári, keď nemá nikto meniny
NO_NAMEDAY_HOLIDAYS = {
    (1, 1): "Nový rok",
    (5, 1): "Sviatok práce",
    (11, 1): "Sviatok všetkých svätých",
    (12, 25): "1. sviatok vianočný",
}

# Pevné slovenské sviatky (záložné zobrazenie, ak zlyhá načítanie menín)
FIXED_HOLIDAYS_SK = {
    (1, 1): "Nový rok",
    (1, 6): "Zjavenie Pána (Traja králi)",
    (5, 1): "Sviatok práce",
    (5, 8): "Deň víťazstva nad fašizmom",
    (7, 5): "Sviatok sv. Cyrila a Metoda",
    (8, 29): "Výročie SNP",
    (9, 15): "Sedembolestná Panna Mária",
    (11, 1): "Sviatok všetkých svätých",
    (11, 17): "Deň boja za slobodu a demokraciu",
    (12, 24): "Štedrý deň",
    (12, 25): "1. sviatok vianočný",
    (12, 26): "2. sviatok vianočný",
}


def get_fonts():
    """Uprednostní DejaVu Sans Bold pre maximálnu čitateľnosť z diaľky na 1-bit E-Ink."""
    fonts = {}
    font_candidates = [
        (
            os.path.join(BASE_DIR, "DejaVuSans-Bold.ttf"),
            os.path.join(BASE_DIR, "DejaVuSans.ttf"),
        ),
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ),
        (
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
        ),
        (
            os.path.join(BASE_DIR, "arialbd.ttf"),
            os.path.join(BASE_DIR, "arial.ttf"),
        ),
    ]

    font_bold = None
    font_reg = None
    for cand_b, cand_r in font_candidates:
        if os.path.exists(cand_b) and os.path.exists(cand_r):
            font_bold, font_reg = cand_b, cand_r
            break

    try:
        if not font_bold or not font_reg:
            raise IOError("Fonty nenájdené")

        fonts["header"] = ImageFont.truetype(font_bold, 18)
        fonts["header_date"] = ImageFont.truetype(font_bold, 14)
        fonts["price_lg"] = ImageFont.truetype(font_bold, 26)
        fonts["ticker"] = ImageFont.truetype(font_bold, 16)
        fonts["bold_14"] = ImageFont.truetype(font_bold, 14)
        fonts["bold_13"] = ImageFont.truetype(font_bold, 13)
        fonts["bold_12"] = ImageFont.truetype(font_bold, 12)
        fonts["bold_11"] = ImageFont.truetype(font_bold, 11)
        fonts["reg_13"] = ImageFont.truetype(font_reg, 13)
    except IOError:
        default = ImageFont.load_default()
        keys = [
            "header", "header_date", "price_lg", "ticker",
            "bold_14", "bold_13", "bold_12", "bold_11", "reg_13",
        ]
        fonts = {k: default for k in keys}
    return fonts


def get_now_bratislava():
    if ZoneInfo is not None:
        try:
            return datetime.datetime.now(ZoneInfo("Europe/Bratislava"))
        except Exception:
            pass
    try:
        os.environ["TZ"] = "Europe/Bratislava"
        time.tzset()
    except AttributeError:
        pass
    return datetime.datetime.now()


def ts_to_bratislava(ts):
    """Prevedie Unix timestamp (z Yahoo Finance) na lokálny bratislavský čas."""
    if ZoneInfo is not None:
        try:
            return datetime.datetime.fromtimestamp(ts, tz=ZoneInfo("Europe/Bratislava"))
        except Exception:
            pass
    return datetime.datetime.fromtimestamp(ts)


def remove_html_tags(text):
    clean = re.compile(r"<.*?>")
    text = re.sub(clean, "", text)
    text = text.replace("&nbsp;", " ").replace("&#160;", " ").replace("\xa0", " ")
    text = text.replace("&ndash;", "-").replace("&#8211;", "-").replace("–", "-")
    return re.sub(r"\s+", " ", text).strip()


# --- MENINY A SVIATKY (DOLNÁ LIŠTA) ---

def get_easter_sunday(year):
    """Meeus/Jones/Butcher algoritmus pre výpočet Veľkonočnej nedele."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)


def get_slovak_holiday(date_obj):
    key = (date_obj.month, date_obj.day)
    if key in FIXED_HOLIDAYS_SK:
        return FIXED_HOLIDAYS_SK[key]
    easter = get_easter_sunday(date_obj.year)
    if date_obj == easter - datetime.timedelta(days=2):
        return "Veľký piatok"
    if date_obj == easter:
        return "Veľkonočná nedeľa"
    if date_obj == easter + datetime.timedelta(days=1):
        return "Veľkonočný pondelok"
    return None


def scrape_meniny_today(now):
    """Stiahne dnešné meniny z kto-ma-meniny.sk so zálohou na zones.sk."""
    months = [
        "Január", "Február", "Marec", "Apríl", "Máj", "Jún",
        "Júl", "August", "September", "Október", "November", "December",
    ]
    date_str_today = f"{now.day}. {months[now.month - 1]}"

    # 1. Primárny zdroj: kto-ma-meniny.sk
    try:
        resp = requests.get("[https://kto-ma-meniny.sk/](https://kto-ma-meniny.sk/)", headers=HEADERS, timeout=8)
        resp.encoding = "utf-8"
        pattern = (
            fr">\s*{re.escape(date_str_today)}\s*</div>"
            r"\s*<div[^>]*>.*?</div>\s*<div[^>]*>(.*?)</div>"
        )
        match = re.search(pattern, resp.text, re.DOTALL | re.IGNORECASE)
        if match:
            names = remove_html_tags(match.group(1)).strip(" ,-")
            if names and names.lower() not in ("neznáme", "nikto"):
                return names
    except Exception as e:
        print(f"Chyba menín (kto-ma-meniny.sk): {e}")

    # 2. Záložný zdroj: zones.sk
    try:
        resp = requests.get(
            "[https://www.zones.sk/kalendar-udalosti/meniny/](https://www.zones.sk/kalendar-udalosti/meniny/)",
            headers=HEADERS,
            timeout=8,
        )
        resp.encoding = "utf-8"
        match = re.search(
            r"meniny</a> má.*?<strong>(.*?)</strong>",
            resp.text,
            re.DOTALL | re.IGNORECASE,
        )
        if match:
            names = remove_html_tags(match.group(1)).strip(" ,-")
            if names and names.lower() not in ("neznáme", "nikto"):
                return names
    except Exception as e:
        print(f"Chyba menín (zones.sk): {e}")

    return None


def get_nameday_or_holiday(now):
    """Vráti text pre dolnú lištu: aktuálne meniny, alebo sviatok ak meniny nikto nemá."""
    today_date = now.date()
    key = (today_date.month, today_date.day)

    if key in NO_NAMEDAY_HOLIDAYS:
        return f"Sviatok: {NO_NAMEDAY_HOLIDAYS[key]}"

    meniny = scrape_meniny_today(now)
    holiday = get_slovak_holiday(today_date)

    if meniny:
        low = meniny.lower()
        holiday_keywords = ("nový rok", "sviatok", "vianočný", "pamiatka", "deň vzniku")
        if any(kw in low for kw in holiday_keywords):
            return f"Sviatok: {holiday or meniny}"
        return f"Meniny: {meniny}"

    if holiday:
        return f"Sviatok: {holiday}"

    return ""


# --- FORMÁTOVANIE ČÍSEL S ČITATEĽNÝM ZNAMIENKOM MÍNUS (−) ---

def fmt_eur(val, with_symbol=True):
    s = f"{val:.2f}".replace(".", ",") if abs(val) >= 100 else f"{val:.3f}".replace(".", ",")
    return f"{s} €" if with_symbol else s


def fmt_pct(val, show_plus=True, decimals=1, with_percent=True):
    """Naformátuje percento so skutočným matematickým mínus (−), ktoré má rovnakú šírku ako +."""
    if val is None:
        return "—"
    if val < 0:
        sign = MINUS_SIGN
        num_val = abs(val)
    elif show_plus and val > 0:
        sign = "+"
        num_val = val
    else:
        sign = ""
        num_val = abs(val)
    num_str = f"{num_val:.{decimals}f}".replace(".", ",")
    suffix = "%" if with_percent else ""
    return f"{sign}{num_str}{suffix}"


def draw_text_aligned(draw, x, y, text, font, fill=TEXT_COLOR, align="left"):
    w = draw.textlength(text, font=font)
    if align == "right":
        cur_x = x - w
    elif align == "center":
        cur_x = x - w / 2.0
    else:
        cur_x = x
    draw.text((cur_x, y), text, font=font, fill=fill)


def draw_text_centered_in_box(draw, x0, y0, x1, y1, text, font, fill=TEXT_COLOR):
    """Presne vycentruje text horizontálne aj vertikálne v zadanom obdĺžniku."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = x0 + ((x1 - x0) - tw) / 2.0 - bbox[0]
    ty = y0 + ((y1 - y0) - th) / 2.0 - bbox[1]
    draw.text((tx, ty), text, font=font, fill=fill)


def paste_inverted_block(img_1bit, x0, y0, x1, y1, draw_fn):
    """Vykreslí čierny blok s bielym textom s vlastným prahom, aby biele písmo ostalo plné."""
    w = int(x1 - x0)
    h = int(y1 - y0)
    if w <= 0 or h <= 0:
        return
    sub_gray = Image.new(RENDER_MODE, (w, h), TEXT_COLOR)
    sub_draw = ImageDraw.Draw(sub_gray)
    draw_fn(sub_draw, w, h)
    sub_1bit = sub_gray.point(
        lambda p: BACKGROUND_COLOR if p >= THRESHOLD_ON_BLACK else TEXT_COLOR,
        mode='1',
    )
    img_1bit.paste(sub_1bit, (int(x0), int(y0)))


# --- SŤAHOVANIE ETF DÁT Z YAHOO FINANCE ---

def fetch_yahoo_chart(symbol, range_str, interval_str):
    url = (
        f"[https://query1.finance.yahoo.com/v8/finance/chart/](https://query1.finance.yahoo.com/v8/finance/chart/){symbol}"
        f"?range={range_str}&interval={interval_str}"
    )
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    result = data.get("chart", {}).get("result")
    if not result:
        return None
    return result[0]


def get_return_over_days(points, latest_price, days_back):
    """Vypočíta % výkonnosť oproti najbližšiemu obchodnému dňu spred `days_back` dní."""
    if not points or latest_price <= 0:
        return None
    latest_ts = points[-1][0]
    target_ts = latest_ts - days_back * 86400

    if points[0][0] > target_ts + 14 * 86400:
        return None

    best_price = None
    best_diff = float("inf")
    for ts, close_val in points:
        diff = abs(ts - target_ts)
        if diff < best_diff:
            best_diff = diff
            best_price = close_val

    if best_price and best_price > 0:
        return ((latest_price / best_price) - 1.0) * 100.0
    return None


def fetch_etf_data(cfg):
    """Stiahne živú cenu, čas posledného kurzu, 1M/3M/6M/1R výkonnosť, 52T rozpätie a ATH."""
    symbol = cfg["yahoo"]
    live = False
    market_ts = None

    price = cfg["fallback_price"]
    day_pct = cfg["fallback_day_pct"]
    ath = cfg["fallback_ath"]
    ath_date_str = cfg["fallback_ath_date"]
    low_52w = cfg["fallback_min_52w"]
    high_52w = cfg["fallback_max_52w"]
    perf_1m = cfg["fallback_perf"]["1m"]
    perf_3m = cfg["fallback_perf"]["3m"]
    perf_6m = cfg["fallback_perf"]["6m"]
    perf_1y = cfg["fallback_perf"]["1y"]

    try:
        # 1. Denné dáta za 2 roky (presné 1M, 3M, 6M, 1R a 52T min/max)
        chart_2y = fetch_yahoo_chart(symbol, "2y", "1d")
        if chart_2y:
            meta = chart_2y.get("meta", {})
            timestamps = chart_2y.get("timestamp", [])
            quote = chart_2y.get("indicators", {}).get("quote", [{}])[0]
            raw_closes = quote.get("close", [])
            raw_lows = quote.get("low", [])
            raw_highs = quote.get("high", [])

            points = []
            for idx in range(min(len(timestamps), len(raw_closes))):
                c_val = raw_closes[idx]
                if c_val is not None:
                    points.append((int(timestamps[idx]), float(c_val)))

            reg_price = meta.get("regularMarketPrice")
            if reg_price is not None:
                price = float(reg_price)
                live = True
            elif points:
                price = points[-1][1]
                live = True

            reg_time = meta.get("regularMarketTime")
            if reg_time:
                market_ts = int(reg_time)
            elif points:
                market_ts = points[-1][0]

            prev_close = meta.get("regularMarketPreviousClose")
            if prev_close is None and len(points) >= 2:
                prev_close = points[-2][1]
            if prev_close and float(prev_close) > 0:
                day_pct = ((price / float(prev_close)) - 1.0) * 100.0

            if points:
                latest_ts = points[-1][0]
                cutoff_1y = latest_ts - 365 * 86400

                r1m = get_return_over_days(points, price, 30)
                r3m = get_return_over_days(points, price, 91)
                r6m = get_return_over_days(points, price, 183)
                r1y = get_return_over_days(points, price, 365)

                if r1m is not None:
                    perf_1m = r1m
                if r3m is not None:
                    perf_3m = r3m
                if r6m is not None:
                    perf_6m = r6m
                if r1y is not None:
                    perf_1y = r1y

                lows_1y = [
                    float(raw_lows[i])
                    for i in range(min(len(timestamps), len(raw_lows)))
                    if timestamps[i] >= cutoff_1y and raw_lows[i] is not None
                ]
                highs_1y = [
                    float(raw_highs[i])
                    for i in range(min(len(timestamps), len(raw_highs)))
                    if timestamps[i] >= cutoff_1y and raw_highs[i] is not None
                ]

                meta_low = meta.get("fiftyTwoWeekLow")
                meta_high = meta.get("fiftyTwoWeekHigh")
                if meta_low:
                    low_52w = float(meta_low)
                elif lows_1y:
                    low_52w = min(lows_1y)

                if meta_high:
                    high_52w = float(meta_high)
                elif highs_1y:
                    high_52w = max(highs_1y)

        # 2. Týždenné dáta za celú históriu (presné ATH a mesiac/rok maxima)
        chart_max = fetch_yahoo_chart(symbol, "max", "1wk")
        if chart_max:
            timestamps_m = chart_max.get("timestamp", [])
            quote_m = chart_max.get("indicators", {}).get("quote", [{}])[0]
            highs_m = quote_m.get("high", [])
            closes_m = quote_m.get("close", [])

            best_val = 0.0
            best_ts = None
            for idx in range(len(timestamps_m)):
                h_val = highs_m[idx] if idx < len(highs_m) else None
                c_val = closes_m[idx] if idx < len(closes_m) else None
                cand = h_val if h_val is not None else c_val
                if cand is not None and float(cand) > best_val:
                    best_val = float(cand)
                    best_ts = timestamps_m[idx]

            if best_val > 0:
                ath = max(best_val, price, high_52w)
                if best_ts:
                    dt = ts_to_bratislava(best_ts)
                    ath_date_str = dt.strftime("%m/%y")
    except Exception as e:
        print(f"Chyba sťahovania {symbol}: {e} (používam záložné dáta)")

    if price > ath:
        ath = price
        ath_date_str = get_now_bratislava().strftime("%m/%y")
    low_52w = min(low_52w, price)
    high_52w = max(high_52w, price)

    drawdown_pct = ((price / ath) - 1.0) * 100.0 if ath > 0 else 0.0
    needed_gain_pct = ((ath / price) - 1.0) * 100.0 if (0 < price < ath) else 0.0

    span_52w = high_52w - low_52w
    pos_52w = (price - low_52w) / span_52w if span_52w > 0 else 0.5
    pos_52w = max(0.0, min(1.0, pos_52w))

    return {
        "ticker": cfg["ticker"],
        "name": cfg["name"],
        "region": cfg["region"],
        "price": price,
        "day_pct": day_pct,
        "ath": ath,
        "ath_date": ath_date_str,
        "drawdown_pct": drawdown_pct,
        "needed_gain_pct": needed_gain_pct,
        "perf_1m": perf_1m,
        "perf_3m": perf_3m,
        "perf_6m": perf_6m,
        "perf_1y": perf_1y,
        "low_52w": low_52w,
        "high_52w": high_52w,
        "pos_52w": pos_52w,
        "live": live,
        "market_ts": market_ts,
    }


# --- KRESLIACE POMOCNÉ FUNKCIE (E-INK) ---

def draw_dashed_vline(draw, x, y0, y1, dash=2, gap=2, color=TEXT_COLOR):
    y = y0
    while y < y1:
        draw.line([(x, y), (x, min(y + dash, y1))], fill=color, width=1)
        y += dash + gap


def draw_hatched_rect(draw, x0, y0, x1, y1, step=4, fill_solid=False):
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    if x1 <= x0 or y1 <= y0:
        return
    if fill_solid:
        draw.rectangle([x0, y0, x1, y1], fill=TEXT_COLOR, outline=TEXT_COLOR)
        return
    draw.rectangle([x0, y0, x1, y1], fill=BACKGROUND_COLOR, outline=TEXT_COLOR, width=1)
    w = x1 - x0
    h = y1 - y0
    for k in range(step, w + h, step):
        sx = x0 + max(0, k - h)
        sy = y0 + min(h, k)
        ex = x0 + min(w, k)
        ey = y0 + max(0, k - w)
        draw.line([(sx, sy), (ex, ey)], fill=TEXT_COLOR, width=1)


def draw_ath_drawdown_meter(draw, x0, y0, x1, drawdown_pct, fonts):
    """Vykreslí popis 'Pokles od ATH' v rovnakom riadku ako lištu poklesu (0% až -25%) so stupnicou."""
    label = "Pokles od ATH"
    label_font = fonts["bold_12"]
    scale_font = fonts["bold_11"]

    bar_h = 20
    bar_y0 = y0
    bar_y1 = y0 + bar_h

    # Popis zarovnaný vľavo a vertikálne vycentrovaný k lište grafu
    lbl_bbox = draw.textbbox((0, 0), label, font=label_font)
    lbl_w = lbl_bbox[2] - lbl_bbox[0]
    lbl_h = lbl_bbox[3] - lbl_bbox[1]
    lbl_y = bar_y0 + (bar_h - lbl_h) / 2.0 - lbl_bbox[1]
    draw.text((x0, lbl_y), label, font=label_font, fill=TEXT_COLOR)

    bar_x0 = int(x0 + lbl_w + 10)
    bar_x1 = int(x1)
    bar_w = bar_x1 - bar_x0
    if bar_w <= 20:
        return

    dd_abs = abs(min(0.0, drawdown_pct))
    scale_max = max(25.0, float(math.ceil(dd_abs / 5.0) * 5))
    step_pct = 5.0 if scale_max <= 25.0 else 10.0

    # Vonkajší rámik lišty
    draw.rectangle([bar_x0, bar_y0, bar_x1, bar_y1], fill=BACKGROUND_COLOR, outline=TEXT_COLOR, width=2)

    # Výplň aktuálneho poklesu (od -10% plná čierna, pod 10% šrafovaná)
    if dd_abs > 0.05:
        fill_w = max(2, int((min(dd_abs, scale_max) / scale_max) * (bar_w - 2)))
        draw_hatched_rect(
            draw,
            bar_x0 + 1,
            bar_y0 + 1,
            bar_x0 + 1 + fill_w,
            bar_y1 - 1,
            step=4,
            fill_solid=(drawdown_pct <= ATH_INVERT_THRESHOLD),
        )

    # Zvislé deliace rysky a popisky stupnice priamo pod lištou
    tick_vals = []
    cur = 0.0
    while cur < scale_max:
        tick_vals.append(cur)
        cur += step_pct
    tick_vals.append(scale_max)

    tick_lbl_y = bar_y1 + 5
    for val in tick_vals:
        tx = bar_x0 + int((val / scale_max) * bar_w)
        if 0 < val < scale_max:
            draw_dashed_vline(draw, tx, bar_y0 + 2, bar_y1 - 2, dash=2, gap=2)
            draw.line([(tx, bar_y1), (tx, bar_y1 + 3)], fill=TEXT_COLOR, width=1)
        else:
            draw.line([(tx, bar_y1), (tx, bar_y1 + 3)], fill=TEXT_COLOR, width=1)

        lbl_txt = "0%" if val == 0 else f"{MINUS_SIGN}{int(val)}%"
        if val == 0:
            draw_text_aligned(draw, tx, tick_lbl_y, lbl_txt, scale_font, align="left")
        elif val == scale_max:
            draw_text_aligned(draw, tx, tick_lbl_y, lbl_txt, scale_font, align="right")
        else:
            draw_text_aligned(draw, tx, tick_lbl_y, lbl_txt, scale_font, align="center")


# --- HLAVNÉ VYKRESLENIE DASHBOARDU (KARTY 2×2 · NÁVRH 2) ---

def create_etf_dashboard():
    # Krok 1: Všetky čierne prvky na bielom pozadí kreslíme do odtieňov sivej ('L')
    img_gray = Image.new(RENDER_MODE, (WIDTH, HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img_gray)
    fonts = get_fonts()
    now = get_now_bratislava()

    etfs = [fetch_etf_data(cfg) for cfg in ETF_CONFIG]
    any_live = any(e["live"] for e in etfs)
    market_times = [e["market_ts"] for e in etfs if e.get("market_ts")]
    latest_market_dt = ts_to_bratislava(max(market_times)) if market_times else now
    footer_nameday_text = get_nameday_or_holiday(now)

    header_h = 46
    inverted_tasks = []  # Čierne bloky s bielym textom (vykreslia sa s vlastným prahom)

    # ==========================================================
    # A. HLAVIČKA (y = 0..46): Názov | Dátum a čas
    # ==========================================================
    def draw_header(hd, hw, hh):
        title_left = "ETF PORTFÓLIO · XETRA"
        hd.text((12, 13), title_left, font=fonts["header"], fill=BACKGROUND_COLOR)

        days_short = ["Pon", "Uto", "Str", "Štv", "Pia", "So", "Ne"]
        date_right = f"{days_short[now.weekday()]} {now.strftime('%d.%m.%Y  %H:%M')}"
        w_date = hd.textlength(date_right, font=fonts["header_date"])
        right_start_x = hw - w_date - 12
        hd.text((right_start_x, 15), date_right, font=fonts["header_date"], fill=BACKGROUND_COLOR)

    inverted_tasks.append((0, 0, WIDTH, header_h, draw_header))

    # ==========================================================
    # B. MRIEŽKA 2×2 ETF KARIET (x = 8..792, y = 50..448)
    # ==========================================================
    margin_x = 8
    gap_x = 8
    card_w = (WIDTH - 2 * margin_x - gap_x) // 2  # 388 px

    start_y = 50
    gap_y = 8
    card_h = 195  # 50 + 195 + 8 + 195 = 448 px (4 px odstup od pätičky y = 452)

    def make_centered_inverted_drawer(label_text, font_obj):
        def _draw(sd, sw, sh):
            draw_text_centered_in_box(sd, 0, 0, sw, sh, label_text, font_obj, fill=BACKGROUND_COLOR)
        return _draw

    for idx, e in enumerate(etfs[:4]):
        col = idx % 2
        row = idx // 2
        cx = margin_x + col * (card_w + gap_x)
        cy = start_y + row * (card_h + gap_y)
        inner_l = cx + 10
        inner_r = cx + card_w - 10

        # Vonkajší rámik karty (2 px)
        draw.rectangle([cx, cy, cx + card_w, cy + card_h], outline=TEXT_COLOR, width=2)

        # 1. Horný riadok karty: Ticker štítok + Región | ATH štítok (inverzný pri <= -10%)
        inverted_tasks.append((
            inner_l,
            cy + 9,
            inner_l + 64,
            cy + 34,
            make_centered_inverted_drawer(e["ticker"], fonts["ticker"]),
        ))
        draw.text((inner_l + 72, cy + 13), e["region"], font=fonts["bold_13"], fill=TEXT_COLOR)

        if abs(e["drawdown_pct"]) < 0.05:
            ath_badge_txt = "NA MAXIME"
        else:
            ath_badge_txt = f"ATH {fmt_pct(e['drawdown_pct'], show_plus=False, decimals=1)}"

        badge_x0 = inner_r - 126
        badge_y0 = cy + 9
        badge_x1 = inner_r
        badge_y1 = cy + 35

        if e["drawdown_pct"] <= ATH_INVERT_THRESHOLD:
            inverted_tasks.append((
                badge_x0,
                badge_y0,
                badge_x1,
                badge_y1,
                make_centered_inverted_drawer(ath_badge_txt, fonts["bold_14"]),
            ))
        else:
            draw.rectangle([badge_x0, badge_y0, badge_x1, badge_y1], outline=TEXT_COLOR, width=2)
            draw_text_centered_in_box(
                draw, badge_x0, badge_y0, badge_x1, badge_y1, ath_badge_txt, fonts["bold_14"], fill=TEXT_COLOR
            )

        # 2. Názov fondu, veľká cena (vľavo) + Dnes, ATH a Na ATH (vpravo)
        draw.text((inner_l, cy + 39), e["name"], font=fonts["reg_13"], fill=TEXT_COLOR)
        draw.text((inner_l, cy + 56), fmt_eur(e["price"]), font=fonts["price_lg"], fill=TEXT_COLOR)

        day_str = f"Dnes: {fmt_pct(e['day_pct'], decimals=2)}"
        draw_text_aligned(draw, inner_r, cy + 40, day_str, fonts["bold_14"], align="right")

        ath_info = f"ATH: {fmt_eur(e['ath'])} ({e['ath_date']})"
        draw_text_aligned(draw, inner_r, cy + 60, ath_info, fonts["bold_12"], align="right")

        na_ath_str = (
            "Na ATH: 0,0%"
            if e["needed_gain_pct"] < 0.05
            else f"Na ATH: {fmt_pct(e['needed_gain_pct'], show_plus=True, decimals=1)}"
        )
        draw_text_aligned(draw, inner_r, cy + 76, na_ath_str, fonts["bold_12"], align="right")

        # 3. Jednoriadkový merač poklesu od ATH ("Pokles od ATH" + lišta + stupnica)
        draw_ath_drawdown_meter(draw, inner_l, cy + 101, inner_r, e["drawdown_pct"], fonts)

        # 4. 52-týždňový rozsah (52T + 18 px medzera + Min | posuvník | Max)
        row_52w_y = cy + 148
        lbl_52t = "52T"
        low_txt = fmt_eur(e["low_52w"], with_symbol=False)
        high_txt = fmt_eur(e["high_52w"], with_symbol=False)

        draw.text((inner_l, row_52w_y), lbl_52t, font=fonts["bold_12"], fill=TEXT_COLOR)
        lbl_52t_w = draw.textlength(lbl_52t, font=fonts["bold_12"])

        low_x = int(inner_l + lbl_52t_w + 18)  # Zväčšená medzera za "52T"
        draw.text((low_x, row_52w_y), low_txt, font=fonts["bold_12"], fill=TEXT_COLOR)
        draw_text_aligned(draw, inner_r, row_52w_y, high_txt, fonts["bold_12"], align="right")

        low_w = draw.textlength(low_txt, font=fonts["bold_12"])
        high_w = draw.textlength(high_txt, font=fonts["bold_12"])
        bar_x0 = int(low_x + low_w + 10)
        bar_x1 = int(inner_r - high_w - 10)
        bar_y = row_52w_y + 7
        if bar_x1 > bar_x0 + 16:
            draw.line([(bar_x0, bar_y), (bar_x1, bar_y)], fill=TEXT_COLOR, width=2)
            draw.line([(bar_x0, bar_y - 4), (bar_x0, bar_y + 4)], fill=TEXT_COLOR, width=1)
            draw.line([(bar_x1, bar_y - 4), (bar_x1, bar_y + 4)], fill=TEXT_COLOR, width=1)
            marker_x = bar_x0 + int(e["pos_52w"] * (bar_x1 - bar_x0))
            draw.rectangle([marker_x - 3, bar_y - 5, marker_x + 3, bar_y + 5], fill=TEXT_COLOR)

        # 5. Výkonnostný riadok (1M · 3M · 6M · 1R)
        draw.line([(inner_l, cy + 168), (inner_r, cy + 168)], fill=TEXT_COLOR, width=1)
        perf_y = cy + 173
        draw_text_aligned(
            draw, inner_l, perf_y, f"1M {fmt_pct(e['perf_1m'], decimals=1)}", fonts["bold_12"], align="left"
        )
        draw_text_aligned(
            draw, cx + 148, perf_y, f"3M {fmt_pct(e['perf_3m'], decimals=1)}", fonts["bold_12"], align="center"
        )
        draw_text_aligned(
            draw, cx + 242, perf_y, f"6M {fmt_pct(e['perf_6m'], decimals=1)}", fonts["bold_12"], align="center"
        )
        draw_text_aligned(
            draw, inner_r, perf_y, f"1R {fmt_pct(e['perf_1y'], decimals=1)}", fonts["bold_12"], align="right"
        )

    # ==========================================================
    # C. PÄTIČKA (y = 452..480) — zdroj + čas dát + meniny/sviatok
    # ==========================================================
    draw.line([(0, 452), (WIDTH, 452)], fill=TEXT_COLOR, width=1)
    if any_live:
        data_time_str = latest_market_dt.strftime("%d.%m.%Y %H:%M")
        status_txt = f"Yahoo Finance · Dáta: {data_time_str}"
    else:
        status_txt = f"ZÁLOŽNÉ DÁTA · API nedostupné · {now.strftime('%d.%m.%Y %H:%M')}"

    if footer_nameday_text:
        status_txt = f"{status_txt} · {footer_nameday_text}"

    max_footer_w = WIDTH - 24
    while draw.textlength(status_txt, font=fonts["bold_12"]) > max_footer_w and len(status_txt) > 6:
        status_txt = status_txt[:-2].rstrip() + "…"

    draw.text((12, 459), status_txt, font=fonts["bold_12"], fill=TEXT_COLOR)

    # Krok 2: Ostrý 1-bit prevod s optimalizovaným prahom pre biele pozadie
    img_1bit = img_gray.point(
        lambda p: BACKGROUND_COLOR if p >= THRESHOLD_ON_WHITE else TEXT_COLOR,
        mode='1',
    )

    # Krok 3: Vloženie čiernych blokov s vlastným prahom pre plný biely text
    for x0, y0, x1, y1, fn in inverted_tasks:
        paste_inverted_block(img_1bit, x0, y0, x1, y1, fn)

    return img_1bit


def main():
    print("Sťahujem ETF dáta a generujem etf_output.bmp...")
    image = create_etf_dashboard()
    image.save(OUTPUT_FILE)
    print(f"Hotovo. Uložené do: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
