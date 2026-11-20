import datetime
import math
import os
import re
import time
import requests
from PIL import Image, ImageDraw, ImageFont

# --- KONFIGURÁCIA (zhodná s main.py pre reTerminal E1001) ---
WIDTH = 800
HEIGHT = 480
MODE = '1'
BACKGROUND_COLOR = 255  # Biela
TEXT_COLOR = 0          # Čierna

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
    fonts = {}
    try:
        font_bold = os.path.join(BASE_DIR, "arialbd.ttf")
        font_reg = os.path.join(BASE_DIR, "arial.ttf")

        if not os.path.exists(font_bold) and os.path.exists(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        ):
            font_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            font_reg = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

        fonts["header"] = ImageFont.truetype(font_bold, 19)
        fonts["header_mid_15"] = ImageFont.truetype(font_bold, 15)
        fonts["header_mid_13"] = ImageFont.truetype(font_bold, 13)
        fonts["header_mid_12"] = ImageFont.truetype(font_bold, 12)
        fonts["header_date"] = ImageFont.truetype(font_reg, 15)
        fonts["price"] = ImageFont.truetype(font_bold, 21)
        fonts["ticker"] = ImageFont.truetype(font_bold, 15)
        fonts["sec_title"] = ImageFont.truetype(font_bold, 13)
        fonts["bold_13"] = ImageFont.truetype(font_bold, 13)
        fonts["bold_12"] = ImageFont.truetype(font_bold, 12)
        fonts["bold_11"] = ImageFont.truetype(font_bold, 11)
        fonts["reg_13"] = ImageFont.truetype(font_reg, 13)
        fonts["reg_12"] = ImageFont.truetype(font_reg, 12)
        fonts["reg_11"] = ImageFont.truetype(font_reg, 11)
    except IOError:
        default = ImageFont.load_default()
        keys = [
            "header", "header_mid_15", "header_mid_13", "header_mid_12",
            "header_date", "price", "ticker", "sec_title", "bold_13",
            "bold_12", "bold_11", "reg_13", "reg_12", "reg_11",
        ]
        fonts = {k: default for k in keys}
    return fonts


def get_now_bratislava():
    try:
        os.environ["TZ"] = "Europe/Bratislava"
        time.tzset()
    except AttributeError:
        pass
    return datetime.datetime.now()


def remove_html_tags(text):
    clean = re.compile(r"<.*?>")
    text = re.sub(clean, "", text)
    text = text.replace("&nbsp;", " ").replace("&#160;", " ").replace("\xa0", " ")
    text = text.replace("&ndash;", "-").replace("&#8211;", "-").replace("–", "-")
    return re.sub(r"\s+", " ", text).strip()


# --- MENINY A SVIATKY (HLAVIČKA) ---

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
    """Stiahne dnešné meniny z kto-ma-meniny.sk so zálohou na zones.sk (ako v main.py)."""
    months = [
        "Január", "Február", "Marec", "Apríl", "Máj", "Jún",
        "Júl", "August", "September", "Október", "November", "December",
    ]
    date_str_today = f"{now.day}. {months[now.month - 1]}"

    # 1. Primárny zdroj: kto-ma-meniny.sk
    try:
        resp = requests.get("https://kto-ma-meniny.sk/", headers=HEADERS, timeout=8)
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
            "https://www.zones.sk/kalendar-udalosti/meniny/",
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


def get_header_nameday_or_holiday(now):
    """Vráti text pre stred hlavičky: aktuálne meniny, alebo sviatok ak meniny nikto nemá."""
    today_date = now.date()
    key = (today_date.month, today_date.day)

    # Dni, keď v slovenskom kalendári nemá meniny nikto -> rovno sviatok
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


# --- FORMÁTOVANIE A TEXT S OPRAVOU ZNAMIENKA MÍNUS ---

def fmt_eur(val, with_symbol=True):
    s = f"{val:.2f}".replace(".", ",") if abs(val) >= 100 else f"{val:.3f}".replace(".", ",")
    return f"{s} €" if with_symbol else s


def fmt_pct(val, show_plus=True, decimals=1):
    if val is None:
        return "—"
    sign = "+" if (show_plus and val > 0) else ""
    return f"{sign}{val:.{decimals}f}".replace(".", ",") + "%"


def measure_text_clean(draw, text, font, minus_gap=2):
    """Zmeria šírku textu s rovnakým odstupom znamienka mínus ako pri kreslení."""
    if "-" not in text:
        return draw.textlength(text, font=font)
    parts = text.split("-")
    w_minus = draw.textlength("-", font=font)
    total = 0.0
    for idx, part in enumerate(parts):
        if idx > 0:
            total += w_minus + minus_gap
        total += draw.textlength(part, font=font)
    return total


def draw_text_clean(draw, x, y, text, font, fill=TEXT_COLOR, align="left", minus_gap=2):
    """Vykreslí text s čistým 2 px odstupom za znamienkom mínus (pre ostrý 1-bit E-Ink)."""
    total_w = measure_text_clean(draw, text, font, minus_gap=minus_gap)
    if align == "right":
        cur_x = x - total_w
    elif align == "center":
        cur_x = x - total_w / 2.0
    else:
        cur_x = x

    if "-" not in text:
        draw.text((cur_x, y), text, font=font, fill=fill)
        return

    w_minus = draw.textlength("-", font=font)
    parts = text.split("-")
    for idx, part in enumerate(parts):
        if idx > 0:
            draw.text((cur_x, y), "-", font=font, fill=fill)
            cur_x += w_minus + minus_gap
        if part:
            draw.text((cur_x, y), part, font=font, fill=fill)
            cur_x += draw.textlength(part, font=font)


# --- SŤAHOVANIE ETF DÁT Z YAHOO FINANCE ---

def fetch_yahoo_chart(symbol, range_str, interval_str):
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
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

    # Ak história fondu nesiaha dostatočne ďaleko (tolerancia 14 dní)
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
    """Stiahne živú cenu, 1M/3M/6M/1R výkonnosť, 6M krivku, 52T rozpätie a ATH."""
    symbol = cfg["yahoo"]
    live = False

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
    series_6m = []

    try:
        # 1. Denné dáta za 2 roky (presné 1M, 3M, 6M, 1R, 52T min/max aj 6M sparkline)
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

            prev_close = meta.get("regularMarketPreviousClose")
            if prev_close is None and len(points) >= 2:
                prev_close = points[-2][1]
            if prev_close and float(prev_close) > 0:
                day_pct = ((price / float(prev_close)) - 1.0) * 100.0

            if points:
                latest_ts = points[-1][0]
                cutoff_6m = latest_ts - 183 * 86400
                cutoff_1y = latest_ts - 365 * 86400

                series_6m = [p[1] for p in points if p[0] >= cutoff_6m]

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

                # 52-týždňové minimum a maximum
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
                    dt = datetime.datetime.fromtimestamp(best_ts)
                    ath_date_str = dt.strftime("%m/%y")
    except Exception as e:
        print(f"Chyba sťahovania {symbol}: {e} (používam záložné dáta)")

    # Konzistencia hraníc
    if price > ath:
        ath = price
        ath_date_str = get_now_bratislava().strftime("%m/%y")
    low_52w = min(low_52w, price)
    high_52w = max(high_52w, price)

    if len(series_6m) < 5:
        series_6m = [
            ath * 0.92, ath * 0.95, ath * 0.93, ath * 0.97,
            ath, ath * 0.96, ath * 0.93, price,
        ]

    drawdown_pct = ((price / ath) - 1.0) * 100.0 if ath > 0 else 0.0
    needed_gain_pct = ((ath / price) - 1.0) * 100.0 if (0 < price < ath) else 0.0
    from_low_pct = ((price / low_52w) - 1.0) * 100.0 if low_52w > 0 else 0.0

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
        "from_low_pct": from_low_pct,
        "pos_52w": pos_52w,
        "series": series_6m,
        "live": live,
    }


# --- KRESLIACE POMOCNÉ FUNKCIE (1-BIT E-INK) ---

def draw_dashed_hline(draw, x0, x1, y, dash=3, gap=4, color=TEXT_COLOR):
    x = x0
    while x < x1:
        draw.line([(x, y), (min(x + dash, x1), y)], fill=color, width=1)
        x += dash + gap


def draw_dashed_vline(draw, x, y0, y1, dash=2, gap=3, color=TEXT_COLOR):
    y = y0
    while y < y1:
        draw.line([(x, y), (x, min(y + dash, y1))], fill=color, width=1)
        y += dash + gap


def draw_hatched_rect(draw, x0, y0, x1, y1, step=4, fill_solid=False):
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


def draw_sparkline_clean(draw, x0, y0, x1, y1, series, ath, fonts):
    """Vykreslí čistý 6M sparkline graf s prerušovanou čiarou ATH a štítkom 6M vpravo hore vedľa grafu."""
    draw.rectangle([x0, y0, x1, y1], outline=TEXT_COLOR, width=1)
    pad_x = 6
    pad_y = 7

    plot_x0 = x0 + pad_x
    plot_x1 = x1 - pad_x
    plot_y0 = y0 + pad_y
    plot_y1 = y1 - pad_y

    min_v = min(series)
    max_v = max(max(series), ath)
    span = max_v - min_v
    if span <= 0:
        span = 1.0

    # Prerušovaná vodorovná čiara historického maxima (ATH)
    ath_y = plot_y1 - int(((ath - min_v) / span) * (plot_y1 - plot_y0))
    draw_dashed_hline(draw, x0 + 2, x1 - 2, ath_y, dash=3, gap=3)

    # Krivka vývoja (2 px)
    pts = []
    n = len(series)
    for i, val in enumerate(series):
        px = plot_x0 + int((i / max(1, n - 1)) * (plot_x1 - plot_x0))
        py = plot_y1 - int(((val - min_v) / span) * (plot_y1 - plot_y0))
        pts.append((px, py))

    if len(pts) >= 2:
        draw.line(pts, fill=TEXT_COLOR, width=2)

    # Bodka na poslednej cene
    lx, ly = pts[-1]
    draw.ellipse([lx - 3, ly - 3, lx + 3, ly + 3], fill=TEXT_COLOR)

    # Štítok "6M" priradený zvonka vpravo hore vedľa grafu
    tag_x0 = x1
    tag_y0 = y0
    tag_x1 = x1 + 24
    tag_y1 = y0 + 16
    draw.rectangle([tag_x0, tag_y0, tag_x1, tag_y1], fill=BACKGROUND_COLOR, outline=TEXT_COLOR, width=1)
    w_6m = draw.textlength("6M", font=fonts["bold_11"])
    draw.text((tag_x0 + (tag_x1 - tag_x0 - w_6m) / 2.0, tag_y0 + 2), "6M", font=fonts["bold_11"], fill=TEXT_COLOR)


# --- HLAVNÉ VYKRESLENIE DASHBOARDU ---

def create_etf_dashboard():
    img = Image.new(MODE, (WIDTH, HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)
    fonts = get_fonts()
    now = get_now_bratislava()

    etfs = [fetch_etf_data(cfg) for cfg in ETF_CONFIG]
    any_live = any(e["live"] for e in etfs)
    header_mid_text = get_header_nameday_or_holiday(now)

    # ==========================================================
    # A. HLAVIČKA (y = 0..46): Názov | Meniny/Sviatok | Dátum
    # ==========================================================
    header_h = 46
    draw.rectangle([(0, 0), (WIDTH, header_h)], fill=TEXT_COLOR)

    title_left = "ETF PORTFÓLIO · XETRA"
    draw.text((14, 12), title_left, font=fonts["header"], fill=BACKGROUND_COLOR)
    left_end_x = 14 + draw.textlength(title_left, font=fonts["header"])

    days_short = ["Pon", "Uto", "Str", "Štv", "Pia", "So", "Ne"]
    date_right = f"{days_short[now.weekday()]} {now.strftime('%d.%m.%Y  %H:%M')}"
    w_date = draw.textlength(date_right, font=fonts["header_date"])
    right_start_x = WIDTH - w_date - 14
    draw.text((right_start_x, 14), date_right, font=fonts["header_date"], fill=BACKGROUND_COLOR)

    # Stred hlavičky: aktuálne meniny alebo sviatok (dynamické škálovanie bez prekrytia)
    if header_mid_text:
        avail_w = (right_start_x - 16) - (left_end_x + 16)
        mid_center_x = (left_end_x + right_start_x) / 2.0

        mid_candidates = [
            (fonts["header_mid_15"], 14),
            (fonts["header_mid_13"], 15),
            (fonts["header_mid_12"], 16),
        ]
        chosen_font, chosen_y = mid_candidates[-1]
        for fnt, fy in mid_candidates:
            if draw.textlength(header_mid_text, font=fnt) <= avail_w:
                chosen_font, chosen_y = fnt, fy
                break

        display_mid = header_mid_text
        while draw.textlength(display_mid, font=chosen_font) > avail_w and len(display_mid) > 6:
            display_mid = display_mid[:-2].rstrip() + "…"

        w_mid = draw.textlength(display_mid, font=chosen_font)
        draw.text(
            (mid_center_x - w_mid / 2.0, chosen_y),
            display_mid,
            font=chosen_font,
            fill=BACKGROUND_COLOR,
        )

    # ==========================================================
    # B. ĽAVÝ HLAVNÝ STĹPEC: 4 ETF FONDY (x = 0..504, y = 48..452)
    # ==========================================================
    row_h = 101
    start_y = 48

    for idx, e in enumerate(etfs):
        ry = start_y + idx * row_h

        # 1. Ticker badge + región + názov + ATH + 52T ukazovateľ (x = 12..184)
        badge_w = 58
        draw.rectangle([12, ry + 10, 12 + badge_w, ry + 32], fill=TEXT_COLOR)
        tw = draw.textlength(e["ticker"], font=fonts["ticker"])
        draw.text(
            (12 + (badge_w - tw) / 2.0, ry + 13),
            e["ticker"],
            font=fonts["ticker"],
            fill=BACKGROUND_COLOR,
        )
        draw.text((77, ry + 13), e["region"], font=fonts["bold_12"], fill=TEXT_COLOR)
        draw.text((12, ry + 37), e["name"], font=fonts["reg_13"], fill=TEXT_COLOR)

        ath_txt = f"ATH: {fmt_eur(e['ath'])} ({e['ath_date']})"
        draw.text((12, ry + 56), ath_txt, font=fonts["bold_12"], fill=TEXT_COLOR)

        # 52-týždňový rozsah (vizuálna pozícia v pásme)
        draw.text((12, ry + 77), "52T:", font=fonts["reg_11"], fill=TEXT_COLOR)
        bar_x0, bar_x1, bar_y = 40, 176, ry + 83
        draw.line([(bar_x0, bar_y), (bar_x1, bar_y)], fill=TEXT_COLOR, width=2)
        draw.line([(bar_x0, bar_y - 4), (bar_x0, bar_y + 4)], fill=TEXT_COLOR, width=1)
        draw.line([(bar_x1, bar_y - 4), (bar_x1, bar_y + 4)], fill=TEXT_COLOR, width=1)
        marker_x = bar_x0 + int(e["pos_52w"] * (bar_x1 - bar_x0))
        draw.rectangle([marker_x - 3, bar_y - 5, marker_x + 3, bar_y + 5], fill=TEXT_COLOR)

        # 2. Čistý 6M Sparkline graf s prerušovanou čiarou ATH a štítkom 6M vpravo hore (x = 188..356, štítok 356..380)
        draw_sparkline_clean(draw, 188, ry + 11, 356, ry + 89, e["series"], e["ath"], fonts)

        # 3. Cena, Dnes a štítok "Na ATH" (x = 372..500)
        right_anchor = 500
        price_str = fmt_eur(e["price"])
        draw_text_clean(draw, right_anchor, ry + 9, price_str, fonts["price"], align="right")

        day_str = f"Dnes: {fmt_pct(e['day_pct'], decimals=2)}"
        draw_text_clean(draw, right_anchor, ry + 38, day_str, fonts["bold_13"], align="right")

        # Štítok "Na ATH" (koľko % rastu treba na návrat na historické maximum)
        box_x0, box_y0, box_x1, box_y1 = 372, ry + 62, right_anchor, ry + 88
        is_deep = e["needed_gain_pct"] >= 15.0
        if e["needed_gain_pct"] < 0.05:
            na_ath_lbl = "NA MAXIME"
        else:
            na_ath_lbl = f"Na ATH {fmt_pct(e['needed_gain_pct'], show_plus=True, decimals=1)}"

        if is_deep:
            draw.rectangle([box_x0, box_y0, box_x1, box_y1], fill=TEXT_COLOR)
            txt_fill = BACKGROUND_COLOR
        else:
            draw.rectangle([box_x0, box_y0, box_x1, box_y1], outline=TEXT_COLOR, width=1)
            txt_fill = TEXT_COLOR

        draw_text_clean(
            draw,
            (box_x0 + box_x1) / 2.0,
            box_y0 + 6,
            na_ath_lbl,
            fonts["bold_12"],
            fill=txt_fill,
            align="center",
        )

        if idx < len(etfs) - 1:
            draw.line([(12, ry + row_h), (500, ry + row_h)], fill=TEXT_COLOR, width=1)

    # ==========================================================
    # C. VERTIKÁLNA ODDEĽOVACIA ČIARA
    # ==========================================================
    draw.line([(509, header_h + 8), (509, HEIGHT - 32)], fill=TEXT_COLOR, width=3)

    # ==========================================================
    # D. PRAVÝ ŠTATISTICKÝ PANEL (x = 519..788) — BEZ DUPLICÍT
    # ==========================================================
    rx = 519
    rx_end = 788

    # --- Sekcia 1: POKLES OD ATH (s priemerom v hlavičke) ---
    avg_dd = sum(e["drawdown_pct"] for e in etfs) / len(etfs)
    draw.text((rx, 52), "POKLES OD ATH", font=fonts["sec_title"], fill=TEXT_COLOR)
    avg_txt = f"Ø {fmt_pct(avg_dd, show_plus=False, decimals=1)}"
    draw_text_clean(draw, rx_end, 53, avg_txt, fonts["bold_12"], align="right")
    draw.line([(rx, 70), (rx_end, 70)], fill=TEXT_COLOR, width=1)

    max_dd_abs = max([abs(e["drawdown_pct"]) for e in etfs] + [20.0])
    scale_max = max(25.0, math.ceil(max_dd_abs / 5.0) * 5.0)
    bar_left = 566
    bar_right = 728
    bar_max_w = bar_right - bar_left

    for ref_pct in (10.0, 20.0):
        if ref_pct <= scale_max:
            ref_x = bar_left + int((ref_pct / scale_max) * bar_max_w)
            draw_dashed_vline(draw, ref_x, 73, 162, dash=2, gap=3)
            draw_text_clean(draw, ref_x, 164, f"-{int(ref_pct)}%", fonts["reg_11"], align="center")
    draw.text((bar_left - 4, 164), "0%", font=fonts["reg_11"], fill=TEXT_COLOR)

    for idx, e in enumerate(etfs):
        by = 76 + idx * 22
        draw.text((rx, by + 1), e["ticker"], font=fonts["bold_12"], fill=TEXT_COLOR)
        dd_abs = abs(e["drawdown_pct"])
        bw = max(2, int((dd_abs / scale_max) * bar_max_w))
        draw_hatched_rect(
            draw,
            bar_left,
            by + 1,
            bar_left + bw,
            by + 15,
            step=4,
            fill_solid=(dd_abs >= 20.0),
        )
        val_txt = fmt_pct(e["drawdown_pct"], show_plus=False, decimals=1)
        draw_text_clean(draw, rx_end, by + 1, val_txt, fonts["bold_12"], align="right")

    # --- Sekcia 2: VÝKONNOSŤ (1M · 3M · 6M · 1R) ---
    s2_y = 186
    draw.text((rx, s2_y), "VÝKONNOSŤ", font=fonts["sec_title"], fill=TEXT_COLOR)
    draw.line([(rx, s2_y + 18), (rx_end, s2_y + 18)], fill=TEXT_COLOR, width=1)

    th_y = s2_y + 22
    col_1m_r = 620
    col_3m_r = 676
    col_6m_r = 732
    col_1y_r = rx_end

    draw.text((rx, th_y), "Fond", font=fonts["bold_11"], fill=TEXT_COLOR)
    for title, anchor in [("1M", col_1m_r), ("3M", col_3m_r), ("6M", col_6m_r), ("1R", col_1y_r)]:
        draw_text_clean(draw, anchor, th_y, title, fonts["bold_11"], align="right")
    draw.line([(rx, th_y + 16), (rx_end, th_y + 16)], fill=TEXT_COLOR, width=1)

    for idx, e in enumerate(etfs):
        ty = th_y + 21 + idx * 20
        draw.text((rx, ty), e["ticker"], font=fonts["bold_12"], fill=TEXT_COLOR)
        draw_text_clean(draw, col_1m_r, ty + 1, fmt_pct(e["perf_1m"]), fonts["reg_11"], align="right")
        draw_text_clean(draw, col_3m_r, ty + 1, fmt_pct(e["perf_3m"]), fonts["reg_11"], align="right")
        draw_text_clean(draw, col_6m_r, ty + 1, fmt_pct(e["perf_6m"]), fonts["reg_11"], align="right")
        draw_text_clean(draw, col_1y_r, ty + 1, fmt_pct(e["perf_1y"]), fonts["bold_11"], align="right")

    # --- Sekcia 3: ROČNÉ ROZPÄTIE (52T) ---
    s3_y = 320
    draw.text((rx, s3_y), "ROČNÉ ROZPÄTIE (52T)", font=fonts["sec_title"], fill=TEXT_COLOR)
    draw_text_clean(draw, rx_end, s3_y + 2, "(EUR)", fonts["reg_11"], align="right")
    draw.line([(rx, s3_y + 18), (rx_end, s3_y + 18)], fill=TEXT_COLOR, width=1)

    r3_h_y = s3_y + 22
    col_min_r = 642
    col_max_r = 716
    col_dna_r = rx_end

    draw.text((rx, r3_h_y), "Fond", font=fonts["bold_11"], fill=TEXT_COLOR)
    for title, anchor in [("Min", col_min_r), ("Max", col_max_r), ("Od dna", col_dna_r)]:
        draw_text_clean(draw, anchor, r3_h_y, title, fonts["bold_11"], align="right")
    draw.line([(rx, r3_h_y + 16), (rx_end, r3_h_y + 16)], fill=TEXT_COLOR, width=1)

    for idx, e in enumerate(etfs):
        ty = r3_h_y + 21 + idx * 20
        draw.text((rx, ty), e["ticker"], font=fonts["bold_12"], fill=TEXT_COLOR)
        draw_text_clean(
            draw, col_min_r, ty + 1, fmt_eur(e["low_52w"], with_symbol=False), fonts["reg_11"], align="right"
        )
        draw_text_clean(
            draw, col_max_r, ty + 1, fmt_eur(e["high_52w"], with_symbol=False), fonts["reg_11"], align="right"
        )
        draw_text_clean(
            draw, col_dna_r, ty + 1, fmt_pct(e["from_low_pct"], show_plus=True), fonts["bold_11"], align="right"
        )

    # ==========================================================
    # E. PÄTIČKA (y = 452..480) — pravá strana zámerne prázdna
    # ==========================================================
    draw.line([(0, 452), (WIDTH, 452)], fill=TEXT_COLOR, width=1)
    status_txt = "LIVE · Yahoo Finance (Xetra)" if any_live else "ZÁLOŽNÉ DÁTA · API nedostupné"
    draw.text((14, 459), status_txt, font=fonts["reg_12"], fill=TEXT_COLOR)

    return img


def main():
    print("Sťahujem ETF dáta a generujem etf_output.bmp...")
    image = create_etf_dashboard()
    image.save(OUTPUT_FILE)
    print(f"Hotovo. Uložené do: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()