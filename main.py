import datetime
import textwrap
import requests
import os
import re
import math
import time
from PIL import Image, ImageDraw, ImageFont

# --- KONFIGURÁCIA ---
WIDTH = 800
HEIGHT = 480
MODE = '1' 
BACKGROUND_COLOR = 255 
TEXT_COLOR = 0         

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LAT = 48.0282
LON = 17.3097

def get_fonts():
    fonts = {}
    try:
        font_path_bold = os.path.join(BASE_DIR, "arialbd.ttf")
        font_path_reg = os.path.join(BASE_DIR, "arial.ttf")
        if not os.path.exists(font_path_bold):
            paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
            for p in paths:
                if os.path.exists(p):
                    font_path_bold, font_path_reg = p, p.replace("-Bold", "")
                    break
        fonts['large'] = ImageFont.truetype(font_path_bold, 35)
        fonts['medium'] = ImageFont.truetype(font_path_bold, 24)
        fonts['regular'] = ImageFont.truetype(font_path_reg, 18)
        fonts['small'] = ImageFont.truetype(font_path_reg, 15)
        fonts['tiny'] = ImageFont.truetype(font_path_reg, 13)
        fonts['bold_small'] = ImageFont.truetype(font_path_bold, 16) 
    except:
        d = ImageFont.load_default()
        fonts = {k: d for k in ['large', 'medium', 'regular', 'small', 'tiny', 'bold_small']}
    return fonts

def remove_html_tags(text):
    return re.sub(re.compile('<.*?>'), '', text).replace('&nbsp;', ' ').replace('\xa0', ' ').strip()

def shorten_weather_desc(text):
    if not text: return ""
    for w in ["Prevažne", "Miestami", "Ojedinele", "Čiastočne", "Prechodne"]: text = text.replace(w, "").replace(w.lower(), "")
    return re.sub(r'\s+', ' ', text).strip(" ,")[:34]

def get_moon_phase(date=None):
    if date is None: date = datetime.datetime.now()
    return (((date - datetime.datetime(2000, 1, 6, 18, 14)).days + (date.second/86400.0)) % 29.530588853) / 29.530588853

def draw_moon_phase(draw, cx, cy, r, color):
    p = get_moon_phase()
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=color, width=1)
    if 0.48 < p < 0.52: draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color); return
    wax = p < 0.5
    draw.chord([cx-r, cy-r, cx+r, cy+r], 270, 90, fill=color) if wax else draw.chord([cx-r, cy-r, cx+r, cy+r], 90, 270, fill=color)
    tw = abs(p - (0.25 if wax else 0.75)) * 4 * r
    if (wax and p > 0.25) or (not wax and p < 0.75): draw.ellipse([cx-tw, cy-r, cx+tw, cy+r], fill=color)
    else: draw.ellipse([cx-tw, cy-r, cx+tw, cy+r], fill=BACKGROUND_COLOR); draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=color, width=1)

def scrape_weather_detailed():
    weather, sunrise, sunset = [], "", ""
    try:
        r = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&daily=sunrise,sunset&timezone=auto", timeout=5).json()
        sunrise, sunset = r["daily"]["sunrise"][0].split("T")[1], r["daily"]["sunset"][0].split("T")[1]
        html = requests.get("https://www.pocasie.sk/slovensko/samorin/5.html", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).text
        for f in re.findall(r"<ul class='daily-forecast.*?</ul>", html, re.DOTALL)[:5]:
            d = remove_html_tags(re.sub(r"<br.*?>.*", "", re.search(r"<li class='date'>(.*?)</li>", f, re.DOTALL).group(1))).split('-')[0].strip()
            weather.append({"day": d, "desc": re.search(r"alt=['\"](.*?)['\"]", f).group(1), "max": re.search(r"<span class='day'>\s*(-?\d+)", f).group(1), "min": re.search(r"<span class='night'>\s*(-?\d+)", f).group(1)})
    except: pass
    return weather, sunrise, sunset

def scrape_etf_data():
    tickers = [
        {"isin": "IE00BKM4GZ66", "ticker": "IS3N.DE", "name": "Emerging Markets IMI"},
        {"isin": "IE00BF4RFH31", "ticker": "IUSN.DE", "name": "World Small Cap"},
        {"isin": "IE00B5BMR087", "ticker": "SXR8.DE", "name": "S&P 500 (Acc)"},
        {"isin": "IE0006WW1TQ4", "ticker": "EXX5.DE", "name": "World ex USA"}
    ]
    results = []
    for t in tickers:
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{t['ticker']}?interval=1d&range=5y"
        try:
            data = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).json()
            res = data['chart']['result'][0]
            meta = res['meta']
            curr_p = meta['regularMarketPrice']
            prev_close = meta['regularMarketPreviousClose'] # Toto je kľúč pre denné percentá
            
            ts, cls = res['timestamp'], res['indicators']['quote'][0]['close']
            valid = [(ts[i], cls[i]) for i in range(len(cls)) if cls[i] is not None]

            def get_perf_historical(days):
                target_ts = valid[-1][0] - (days * 86400)
                old_p = next((p for t_s, p in reversed(valid) if t_s <= target_ts), valid[0][1])
                return ((curr_p - old_p) / old_p) * 100

            perf = {
                "1D": ((curr_p - prev_close) / prev_close) * 100, # Výpočet od otvorenia trhu/včerajšieho close
                "1T": get_perf_historical(7),
                "1M": get_perf_historical(30),
                "1R": get_perf_historical(365),
                "3R": get_perf_historical(1095),
                "MAX": get_perf_historical(9999)
            }
            results.append({"name": t['name'], "price": curr_p, "perf": perf, "error": False})
        except: results.append({"name": t['name'], "error": True})
    return results

def create_dashboard():
    img = Image.new(MODE, (WIDTH, HEIGHT), BACKGROUND_COLOR)
    draw, fonts = ImageDraw.Draw(img), get_fonts()
    now = datetime.datetime.now()
    weather, sunrise, sunset = scrape_weather_detailed()
    etf_data = scrape_etf_data()
    
    draw.rectangle([(0, 0), (WIDTH, 64)], fill=TEXT_COLOR)
    draw.text((20, 15), f"{now.day}.{now.month}.{now.year}", font=fonts['large'], fill=BACKGROUND_COLOR)
    if sunrise:
        draw.text((WIDTH-130, 12), f"Východ: {sunrise}", font=fonts['tiny'], fill=BACKGROUND_COLOR)
        draw.text((WIDTH-130, 34), f"Západ: {sunset}", font=fonts['tiny'], fill=BACKGROUND_COLOR)
        draw_moon_phase(draw, WIDTH-160, 32, 16, BACKGROUND_COLOR)

    cy = 85
    draw.text((20, cy), "Počasie Šamorín", font=fonts['medium'], fill=TEXT_COLOR)
    cy += 40
    for d in weather:
        draw.text((20, cy), d['day'], font=fonts['bold_small'], fill=TEXT_COLOR)
        draw.text((75, cy), f"{d['max']}° / {d['min']}°", font=fonts['bold_small'], fill=TEXT_COLOR)
        draw.text((20, cy + 18), shorten_weather_desc(d['desc']), font=fonts['tiny'], fill=TEXT_COLOR)
        cy += 48

    draw.line([(340, 80), (340, 460)], fill=TEXT_COLOR, width=1)
    rx, ry = 360, 85
    draw.text((rx, ry), "Moje ETF portfólio", font=fonts['medium'], fill=TEXT_COLOR)
    ry += 40
    for etf in etf_data:
        if etf.get('error'): ry += 90; continue
        draw.text((rx, ry), etf['name'], font=fonts['bold_small'], fill=TEXT_COLOR)
        ps = f"{etf['price']:.2f} €"
        draw.text((WIDTH - draw.textlength(ps, font=fonts['bold_small']) - 20, ry), ps, font=fonts['bold_small'], fill=TEXT_COLOR)
        ry += 22
        pers = [("1D", "1T", "1M"), ("1R", "3R", "MAX")]
        for r_idx, row in enumerate(pers):
            for c_idx, p in enumerate(row):
                val = etf['perf'][p]
                draw.text((rx + c_idx*105, ry + r_idx*16), f"{p}: {'+' if val>0 else ''}{val:.1f}%", font=fonts['tiny'], fill=TEXT_COLOR)
        ry += 62
    draw.text((WIDTH - 130, HEIGHT - 22), f"Aktualizované: {now.strftime('%H:%M')}", font=fonts['tiny'], fill=TEXT_COLOR)
    return img

if __name__ == "__main__":
    create_dashboard().save("dashboard_output.bmp")