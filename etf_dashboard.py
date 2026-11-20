import datetime
import math
import os
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

# Voliteľné: zadaj počet kusov (podielov) pre výpočet hodnoty portfólia v €.
# Ak necháš všetky na 0, zobrazí sa súhrn košíka (1 ks z každého fondu).
PORTFOLIO_SHARES = {
    "SXR8": 0.0,
    "EXUS": 0.0,
    "IS3N": 0.0,
    "IUSN": 0.0,
}

# Definícia 4 ETF fondov (Xetra, EUR) + záložné dáta pri výpadku API
ETF_CONFIG = [
    {
        "ticker": "SXR8",
        "yahoo": "SXR8.DE",
        "name": "Core S&P 500",
        "region": "USA",
        "fallback_price": 690.14,
        "fallback_day_pct": -2.23,
        "fallback_ath": 755.30,
        "fallback_ath_date": "10/26",
    },
    {
        "ticker": "EXUS",
        "yahoo": "EXUS.DE",
        "name": "MSCI World ex USA",
        "region": "EX-US",
        "fallback_price": 38.245,
        "fallback_day_pct": -1.02,
        "fallback_ath": 41.180,
        "fallback_ath_date": "11/26",
    },
    {
        "ticker": "IS3N",
        "yahoo": "IS3N.DE",
        "name": "Core MSCI EM IMI",
        "region": "EM",
        "fallback_price": 40.606,
        "fallback_day_pct": -4.20,
        "fallback_ath": 51.006,
        "fallback_ath_date": "06/26",
    },
    {
        "ticker": "IUSN",
        "yahoo": "IUSN.DE",
        "name": "MSCI World Small Cap",
        "region": "SMALL",
        "fallback_price": 8.701,
        "fallback_day_pct": -0.32,
        "fallback_ath": 9.362,
        "fallback_ath_date": "08/26",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
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

        fonts["header"] = ImageFont.truetype(font_bold, 22)
        fonts["price"] = ImageFont.truetype(font_bold, 21)
        fonts["ticker"] = ImageFont.truetype(font_bold, 15)
        fonts["sec_title"] = ImageFont.truetype(font_bold, 14)
        fonts["bold_14"] = ImageFont.truetype(font_bold, 14)
        fonts["bold_13"] = ImageFont.truetype(font_bold, 13)
        fonts["bold_12"] = ImageFont.truetype(font_bold, 12)
        fonts["reg_15"] = ImageFont.truetype(font_reg, 15)
        fonts["reg_13"] = ImageFont.truetype(font_reg, 13)
        fonts["reg_12"] = ImageFont.truetype(font_reg, 12)
        fonts["reg_11"] = ImageFont.truetype(font_reg, 11)
    except IOError:
        default = ImageFont.load_default()
        keys = [
            "header", "price", "ticker", "sec_title", "bold_14",
            "bold_13", "bold_12", "reg_15", "reg_13", "reg_12", "reg_11",
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


def fmt_eur(val, compact=False):
    if compact:
        return f"{val:,.0f}".replace(",", " ") + " €"
    if abs(val) >= 100:
        return f"{val:.2f}".replace(".", ",") + " €"
    return f"{val:.3f}".replace(".", ",") + " €"


def fmt_pct(val, show_plus=True, decimals=1):
    sign = "+" if (show_plus and val > 0) else ""
    return f"{sign}{val:.{decimals}f}".replace(".", ",") + "%"


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


def fetch_etf_data(cfg):
    """Stiahne aktuálnu cenu, 6M históriu a historické maximum (ATH) z Yahoo Finance."""
    symbol = cfg["yahoo"]
    live = False

    price = cfg["fallback_price"]
    day_pct = cfg["fallback_day_pct"]
    ath = cfg["fallback_ath"]
    ath_date_str = cfg["fallback_ath_date"]
    closes_6m = []
    low_52w = None
    high_52w = None

    try:
        # 1. Denné dáta za 6 mesiacov (sparkline, volatilita, 6M vývoj, 52W rozsah)
        chart_6m = fetch_yahoo_chart(symbol, "6mo", "1d")
        if chart_6m:
            meta = chart_6m.get("meta", {})
            quote = chart_6m.get("indicators", {}).get("quote", [{}])[0]
            raw_closes = quote.get("close", [])
            closes_6m = [float(c) for c in raw_closes if c is not None]

            reg_price = meta.get("regularMarketPrice")
            if reg_price is not None:
                price = float(reg_price)
                live = True
            elif closes_6m:
                price = closes_6m[-1]
                live = True

            # Denná zmena voči predchádzajúcemu obchodnému dňu
            prev_close = meta.get("regularMarketPreviousClose")
            if prev_close is None and len(closes_6m) >= 2:
                prev_close = closes_6m[-2]
            if prev_close and prev_close > 0:
                day_pct = ((price / float(prev_close)) - 1.0) * 100.0

            if meta.get("fiftyTwoWeekLow"):
                low_52w = float(meta["fiftyTwoWeekLow"])
            if meta.get("fiftyTwoWeekHigh"):
                high_52w = float(meta["fiftyTwoWeekHigh"])

        # 2. Týždenné dáta za celú históriu (presné ATH a dátum maxima)
        chart_max = fetch_yahoo_chart(symbol, "max", "1wk")
        if chart_max:
            timestamps = chart_max.get("timestamp", [])
            quote_max = chart_max.get("indicators", {}).get("quote", [{}])[0]
            highs = quote_max.get("high", [])
            closes_max = quote_max.get("close", [])

            best_val = 0.0
            best_ts = None
            for idx in range(len(timestamps)):
                h_val = highs[idx] if idx < len(highs) else None
                c_val = closes_max[idx] if idx < len(closes_max) else None
                cand = h_val if h_val is not None else c_val
                if cand is not None and float(cand) > best_val:
                    best_val = float(cand)
                    best_ts = timestamps[idx]

            if best_val > 0:
                ath = max(best_val, price, high_52w or 0.0)
                if best_ts:
                    dt = datetime.datetime.fromtimestamp(best_ts)
                    ath_date_str = dt.strftime("%m/%y")
    except Exception as e:
        print(f"Chyba sťahovania {symbol}: {e} (používam záložné dáta)")

    # Ošetrenie ATH, aby nebolo nižšie než aktuálna cena
    if price > ath:
        ath = price
        ath_date_str = get_now_bratislava().strftime("%m/%y")

    # Záložná krivka ak API nevrátilo históriu
    if len(closes_6m) < 5:
        closes_6m = [
            ath * 0.94, ath * 0.97, ath * 0.95, ath,
            ath * 0.96, ath * 0.92, price,
        ]

    if low_52w is None:
        low_52w = min(min(closes_6m), price)
    if high_52w is None:
        high_52w = max(max(closes_6m), ath)

    # Výpočty štatistík
    drawdown_pct = ((price / ath) - 1.0) * 100.0 if ath > 0 else 0.0
    needed_gain_pct = ((ath / price) - 1.0) * 100.0 if (0 < price < ath) else 0.0
    perf_6m_pct = (
        ((price / closes_6m[0]) - 1.0) * 100.0 if closes_6m[0] > 0 else 0.0
    )

    # Anualizovaná volatilita z denných výnosov (6M okno)
    vol_pct = 0.0
    if len(closes_6m) >= 10:
        returns = [
            (closes_6m[i] - closes_6m[i - 1]) / closes_6m[i - 1]
            for i in range(1, len(closes_6m))
            if closes_6m[i - 1] > 0
        ]
        if len(returns) >= 5:
            mean_r = sum(returns) / len(returns)
            var_r = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
            vol_pct = math.sqrt(var_r) * math.sqrt(252) * 100.0

    # Relatívna pozícia ceny v 52-týždňovom pásme (0.0 až 1.0)
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
        "perf_6m_pct": perf_6m_pct,
        "vol_pct": vol_pct,
        "low_52w": low_52w,
        "high_52w": high_52w,
        "pos_52w": pos_52w,
        "series": closes_6m,
        "live": live,
    }


# --- POMOCNÉ KRESLIACE FUNKCIE PRE 1-BIT E-INK ---

def draw_dashed_hline(draw, x0, x1, y, dash=4, gap=3, color=TEXT_COLOR):
    x = x0
    while x < x1:
        draw.line([(x, y), (min(x + dash, x1), y)], fill=color, width=1)
        x += dash + gap


def draw_dashed_vline(draw, x, y0, y1, dash=3, gap=3, color=TEXT_COLOR):
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


def draw_sparkline(draw, x0, y0, x1, y1, series, ath, fonts):
    """Vykreslí 6M sparkline graf s prerušovanou hornou hranicou ATH."""
    draw.rectangle([x0, y0, x1, y1], outline=TEXT_COLOR, width=1)
    pad_x = 5
    pad_top = 8
    pad_bot = 6

    plot_x0 = x0 + pad_x
    plot_x1 = x1 - pad_x
    plot_y0 = y0 + pad_top
    plot_y1 = y1 - pad_bot

    min_v = min(series)
    max_v = max(max(series), ath)
    span = max_v - min_v
    if span <= 0:
        span = 1.0

    # Prerušovaná čiara ATH
    ath_y = plot_y1 - int(((ath - min_v) / span) * (plot_y1 - plot_y0))
    draw_dashed_hline(draw, x0 + 2, x1 - 2, ath_y, dash=3, gap=3)
    draw.text((x0 + 4, ath_y + 1), "ATH", font=fonts["reg_11"], fill=TEXT_COLOR)

    # Kreslenie krivky vývoja
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


def get_dca_status(dd_pct):
    if dd_pct <= -20.0:
        return "SILNA ZLAVA (>20%)"
    if dd_pct <= -10.0:
        return "KOREKCIA (>10%)"
    if dd_pct <= -5.0:
        return "MIERNA ZLAVA"
    return "BLIZKO MAXIMA"


# --- HLAVNÉ VYKRESLENIE DASHBOARDU ---

def create_etf_dashboard():
    img = Image.new(MODE, (WIDTH, HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)
    fonts = get_fonts()
    now = get_now_bratislava()

    etfs = [fetch_etf_data(cfg) for cfg in ETF_CONFIG]
    any_live = any(e["live"] for e in etfs)

    # A. HLAVIČKA (y = 0..46)
    header_h = 46
    draw.rectangle([(0, 0), (WIDTH, header_h)], fill=TEXT_COLOR)
    draw.text((14, 10), "ETF PORTFÓLIO · XETRA (EUR)", font=fonts["header"], fill=BACKGROUND_COLOR)

    days_short = ["Pon", "Uto", "Str", "Štv", "Pia", "So", "Ne"]
    date_right = f"{days_short[now.weekday()]} {now.strftime('%d.%m.%Y  %H:%M')}"
    w_date = draw.textlength(date_right, font=fonts["reg_15"])
    draw.text((WIDTH - w_date - 14, 14), date_right, font=fonts["reg_15"], fill=BACKGROUND_COLOR)

    # B. ĽAVÝ HLAVNÝ STĹPEC: 4 ETF FONDY (x = 0..514, y = 48..452)
    row_h = 101
    start_y = 48

    for idx, e in enumerate(etfs):
        ry = start_y + idx * row_h

        # 1. Ticker badge + región + názov + ATH + 52T rozsah (x = 12..186)
        badge_w = 58
        draw.rectangle([12, ry + 8, 12 + badge_w, ry + 30], fill=TEXT_COLOR)
        tw = draw.textlength(e["ticker"], font=fonts["ticker"])
        draw.text(
            (12 + (badge_w - tw) / 2, ry + 11),
            e["ticker"],
            font=fonts["ticker"],
            fill=BACKGROUND_COLOR,
        )
        draw.text((76, ry + 11), e["region"], font=fonts["bold_12"], fill=TEXT_COLOR)
        draw.text((12, ry + 34), e["name"], font=fonts["reg_13"], fill=TEXT_COLOR)

        ath_txt = f"ATH: {fmt_eur(e['ath'])} ({e['ath_date']})"
        draw.text((12, ry + 53), ath_txt, font=fonts["bold_12"], fill=TEXT_COLOR)

        # 52-týždňový rozsah (min -> max)
        draw.text((12, ry + 75), "52T:", font=fonts["reg_11"], fill=TEXT_COLOR)
        bar_x0, bar_x1, bar_y = 40, 178, ry + 82
        draw.line([(bar_x0, bar_y), (bar_x1, bar_y)], fill=TEXT_COLOR, width=2)
        draw.line([(bar_x0, bar_y - 4), (bar_x0, bar_y + 4)], fill=TEXT_COLOR, width=1)
        draw.line([(bar_x1, bar_y - 4), (bar_x1, bar_y + 4)], fill=TEXT_COLOR, width=1)
        marker_x = bar_x0 + int(e["pos_52w"] * (bar_x1 - bar_x0))
        draw.rectangle([marker_x - 3, bar_y - 5, marker_x + 3, bar_y + 5], fill=TEXT_COLOR)

        # 2. 6M Sparkline graf (x = 192..366)
        draw_sparkline(draw, 192, ry + 10, 366, ry + 74, e["series"], e["ath"], fonts)
        sub_spark = f"6M: {fmt_pct(e['perf_6m_pct'])}  |  Vol: {e['vol_pct']:.0f}%"
        draw.text((193, ry + 78), sub_spark, font=fonts["reg_11"], fill=TEXT_COLOR)

        # 3. Cena, denná zmena, štítok poklesu od ATH (x = 374..508)
        right_anchor = 508
        price_str = fmt_eur(e["price"])
        w_price = draw.textlength(price_str, font=fonts["price"])
        draw.text((right_anchor - w_price, ry + 7), price_str, font=fonts["price"], fill=TEXT_COLOR)

        day_str = f"Dnes: {fmt_pct(e['day_pct'], decimals=2)}"
        w_day = draw.textlength(day_str, font=fonts["bold_13"])
        draw.text((right_anchor - w_day, ry + 36), day_str, font=fonts["bold_13"], fill=TEXT_COLOR)

        # Štítok vzdialenosti od ATH (inverzný čierny ak pokles >= 10 %)
        box_x0, box_y0, box_x1, box_y1 = 382, ry + 61, right_anchor, ry + 86
        is_discount = e["drawdown_pct"] <= -10.0
        dd_label = (
            f"ZĽAVA {fmt_pct(e['drawdown_pct'], show_plus=False)}"
            if is_discount
            else f"ATH {fmt_pct(e['drawdown_pct'], show_plus=False)}"
        )
        if is_discount:
            draw.rectangle([box_x0, box_y0, box_x1, box_y1], fill=TEXT_COLOR)
            txt_fill = BACKGROUND_COLOR
        else:
            draw.rectangle([box_x0, box_y0, box_x1, box_y1], outline=TEXT_COLOR, width=1)
            txt_fill = TEXT_COLOR

        w_dd = draw.textlength(dd_label, font=fonts["bold_13"])
        draw.text(
            (box_x0 + (box_x1 - box_x0 - w_dd) / 2, box_y0 + 5),
            dd_label,
            font=fonts["bold_13"],
            fill=txt_fill,
        )

        # Oddeľovač medzi riadkami
        if idx < len(etfs) - 1:
            draw.line([(12, ry + row_h), (508, ry + row_h)], fill=TEXT_COLOR, width=1)

    # C. VERTIKÁLNA ODDEĽOVACIA ČIARA (rovnaká hrúbka ako v main.py)
    draw.line([(518, header_h + 8), (518, HEIGHT - 32)], fill=TEXT_COLOR, width=3)

    # D. PRAVÝ ŠTATISTICKÝ PANEL (x = 530..788)
    rx = 530
    rx_end = 788

    # --- Sekcia 1: Pokles od maxima (ATH) ---
    draw.text((rx, 54), "POKLES OD MAXIMA (ATH)", font=fonts["sec_title"], fill=TEXT_COLOR)
    draw.line([(rx, 73), (rx_end, 73)], fill=TEXT_COLOR, width=1)

    max_dd_abs = max([abs(e["drawdown_pct"]) for e in etfs] + [20.0])
    scale_max = max(25.0, math.ceil(max_dd_abs / 5.0) * 5.0)
    bar_left = 576
    bar_right = 736
    bar_max_w = bar_right - bar_left

    # Zvislé referenčné hranice -10 % a -20 %
    for ref_pct in (10.0, 20.0):
        if ref_pct <= scale_max:
            ref_x = bar_left + int((ref_pct / scale_max) * bar_max_w)
            draw_dashed_vline(draw, ref_x, 78, 174, dash=2, gap=3)
            lbl = f"-{int(ref_pct)}%"
            w_l = draw.textlength(lbl, font=fonts["reg_11"])
            draw.text((ref_x - w_l / 2, 176), lbl, font=fonts["reg_11"], fill=TEXT_COLOR)
    draw.text((bar_left - 4, 176), "0%", font=fonts["reg_11"], fill=TEXT_COLOR)

    for idx, e in enumerate(etfs):
        by = 82 + idx * 23
        draw.text((rx, by + 1), e["ticker"], font=fonts["bold_13"], fill=TEXT_COLOR)
        dd_abs = abs(e["drawdown_pct"])
        bw = max(2, int((dd_abs / scale_max) * bar_max_w))
        draw_hatched_rect(
            draw,
            bar_left,
            by + 1,
            bar_left + bw,
            by + 16,
            step=4,
            fill_solid=(dd_abs >= 20.0),
        )
        val_txt = fmt_pct(e["drawdown_pct"], show_plus=False)
        w_v = draw.textlength(val_txt, font=fonts["bold_12"])
        draw.text((rx_end - w_v, by + 2), val_txt, font=fonts["bold_12"], fill=TEXT_COLOR)

    # --- Sekcia 2: Asymetria strát & Volatilita ---
    s2_y = 198
    draw.text((rx, s2_y), "NÁVRAT NA ATH & 6M VÝVOJ", font=fonts["sec_title"], fill=TEXT_COLOR)
    draw.line([(rx, s2_y + 19), (rx_end, s2_y + 19)], fill=TEXT_COLOR, width=1)

    th_y = s2_y + 24
    col_gain_r = 668
    col_6m_r = 734
    col_vol_r = rx_end

    draw.text((rx, th_y), "Fond", font=fonts["bold_12"], fill=TEXT_COLOR)
    for title, anchor in [("Na ATH", col_gain_r), ("6M", col_6m_r), ("Vol.", col_vol_r)]:
        wt = draw.textlength(title, font=fonts["bold_12"])
        draw.text((anchor - wt, th_y), title, font=fonts["bold_12"], fill=TEXT_COLOR)
    draw.line([(rx, th_y + 16), (rx_end, th_y + 16)], fill=TEXT_COLOR, width=1)

    for idx, e in enumerate(etfs):
        ty = th_y + 20 + idx * 20
        draw.text((rx, ty), e["ticker"], font=fonts["bold_13"], fill=TEXT_COLOR)

        gain_s = fmt_pct(e["needed_gain_pct"], show_plus=True)
        w_g = draw.textlength(gain_s, font=fonts["bold_13"])
        draw.text((col_gain_r - w_g, ty), gain_s, font=fonts["bold_13"], fill=TEXT_COLOR)

        p6_s = fmt_pct(e["perf_6m_pct"], show_plus=True)
        w_6 = draw.textlength(p6_s, font=fonts["reg_13"])
        draw.text((col_6m_r - w_6, ty), p6_s, font=fonts["reg_13"], fill=TEXT_COLOR)

        vol_s = f"{e['vol_pct']:.0f}%"
        w_vo = draw.textlength(vol_s, font=fonts["reg_13"])
        draw.text((col_vol_r - w_vo, ty), vol_s, font=fonts["reg_13"], fill=TEXT_COLOR)

    # --- Sekcia 3: DCA Signál & Portfólio / Košík ---
    box_top = 332
    box_bot = 444
    draw.rectangle([rx, box_top, rx_end, box_bot], outline=TEXT_COLOR, width=2)
    draw.rectangle([rx, box_top, rx_end, box_top + 24], fill=TEXT_COLOR)

    avg_dd = sum(e["drawdown_pct"] for e in etfs) / len(etfs)
    draw.text((rx + 8, box_top + 5), "DCA SIGNÁL", font=fonts["bold_13"], fill=BACKGROUND_COLOR)
    avg_txt = f"PRIEMER {fmt_pct(avg_dd, show_plus=False)}"
    w_avg = draw.textlength(avg_txt, font=fonts["bold_12"])
    draw.text((rx_end - w_avg - 8, box_top + 5), avg_txt, font=fonts["bold_12"], fill=BACKGROUND_COLOR)

    best_disc = min(etfs, key=lambda item: item["drawdown_pct"])
    draw.text(
        (rx + 8, box_top + 31),
        f"Najväčšia zľava: {best_disc['ticker']} ({fmt_pct(best_disc['drawdown_pct'], show_plus=False)})",
        font=fonts["bold_13"],
        fill=TEXT_COLOR,
    )
    draw.text(
        (rx + 8, box_top + 51),
        f"Signál: {get_dca_status(best_disc['drawdown_pct'])}",
        font=fonts["reg_13"],
        fill=TEXT_COLOR,
    )

    draw.line([(rx + 8, box_top + 73), (rx_end - 8, box_top + 73)], fill=TEXT_COLOR, width=1)

    # Ak máš zadané počty kusov v PORTFOLIO_SHARES, vypočíta hodnotu portfólia
    total_shares = sum(PORTFOLIO_SHARES.values())
    if total_shares > 0:
        total_val = sum(e["price"] * PORTFOLIO_SHARES.get(e["ticker"], 0.0) for e in etfs)
        day_eur = 0.0
        for e in etfs:
            sh = PORTFOLIO_SHARES.get(e["ticker"], 0.0)
            if sh > 0 and (1.0 + e["day_pct"] / 100.0) > 0:
                prev_p = e["price"] / (1.0 + e["day_pct"] / 100.0)
                day_eur += (e["price"] - prev_p) * sh
        day_sign = "+" if day_eur > 0 else ""
        draw.text(
            (rx + 8, box_top + 79),
            f"Portfólio: {fmt_eur(total_val, compact=True)}",
            font=fonts["bold_13"],
            fill=TEXT_COLOR,
        )
        draw.text(
            (rx + 8, box_top + 95),
            f"Dnes: {day_sign}{day_eur:.2f}".replace(".", ",") + " €",
            font=fonts["reg_12"],
            fill=TEXT_COLOR,
        )
    else:
        basket_sum = sum(e["price"] for e in etfs)
        best_6m = max(etfs, key=lambda item: item["perf_6m_pct"])
        draw.text(
            (rx + 8, box_top + 79),
            f"Košík (1× každý): {fmt_eur(basket_sum)}",
            font=fonts["bold_12"],
            fill=TEXT_COLOR,
        )
        draw.text(
            (rx + 8, box_top + 95),
            f"Líder 6M: {best_6m['ticker']} ({fmt_pct(best_6m['perf_6m_pct'])})",
            font=fonts["reg_12"],
            fill=TEXT_COLOR,
        )

    # E. PÄTIČKA (y = 452..480)
    draw.line([(0, 452), (WIDTH, 452)], fill=TEXT_COLOR, width=1)
    status_txt = "LIVE · Yahoo Finance (Xetra)" if any_live else "ZÁLOŽNÉ DÁTA · API nedostupné"
    draw.text((14, 459), status_txt, font=fonts["reg_12"], fill=TEXT_COLOR)

    footer_r = f"Aktualizované: {now.strftime('%H:%M')} · E1001"
    w_fr = draw.textlength(footer_r, font=fonts["reg_12"])
    draw.text((WIDTH - w_fr - 14, 459), footer_r, font=fonts["reg_12"], fill=TEXT_COLOR)

    return img


def main():
    print("Sťahujem ETF dáta a generujem etf_output.bmp...")
    image = create_etf_dashboard()
    image.save(OUTPUT_FILE)
    print(f"Hotovo. Uložené do: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
