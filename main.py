```python
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
BACKGROUND_COLOR = 255 # Biela
TEXT_COLOR = 0         # Čierna

# Získame absolútnu cestu k priečinku pre hľadanie fontov
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LAT = 48.0282
LON = 17.3097

def get_fonts():
    fonts = {}
    try:
        # Skúsime nájsť lokálne fonty alebo systémové cesty
        font_path_bold = os.path.join(BASE_DIR, "arialbd.ttf")
        font_path_reg = os.path.join(BASE_DIR, "arial.ttf")
        
        if not os.path.exists(font_path_bold):
            # Cesty pre Raspberry Pi / Linux
            paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
            ]
            for p in paths:
                if os.path.exists(p):
                    font_path_bold = p
                    font_path_reg = p.replace("-Bold", "")
                    break

        fonts['large'] = ImageFont.truetype(font_path_bold, 35)
        fonts['medium'] = ImageFont.truetype(font_path_bold, 24)
        fonts['regular'] = ImageFont.truetype(font_path_reg, 18)
        fonts['small'] = ImageFont.truetype(font_path_reg, 15)
        fonts['tiny'] = ImageFont.truetype(font_path_reg, 13)
        fonts['bold_small'] = ImageFont.truetype(font_path_bold, 16) 
        fonts['value_20'] = ImageFont.truetype(font_path_bold, 20)
    except IOError:
        default = ImageFont.load_default()
        fonts = {k: default for k in ['large', 'medium', 'regular', 'small', 'tiny', 'bold_small', 'value_20']}
    return fonts

def remove_html_tags(text):
    clean = re.compile('<.*?>')
    text = re.sub(clean, '', text)
    text = text.replace('&nbsp;', ' ').replace('\xa0', ' ')
    return text.strip()

def shorten_weather_desc(text):
    if not text: return ""
    removes = ["Prevažne", "Miestami", "Ojedinele", "Čiastočne", "Prechodne"]
    for word in removes: 
        text = text.replace(word, "").replace(word.lower(), "")
    text = re.sub(r'\s+', ' ', text).strip(" ,") 
    if len(text) > 0: text = text[0].upper() + text[1:]
    return text[:34]

def get_moon_phase(date=None):
    if date is None: date = datetime.datetime.now()
    diff = date - datetime.datetime(2000, 1, 6, 18, 14)
    return ((diff.days + (diff.seconds / 86400.0)) % 29.530588853) / 29.530588853

def draw_moon_phase(draw, center_x, center_y, radius, color):
    phase = get_moon_phase()
    bbox = [center_x - radius, center_y - radius, center_x + radius, center_y + radius]
    draw.ellipse(bbox, outline=color, width=1)
    if 0.48 < phase < 0.52:
        draw.ellipse(bbox, fill=color)
        return
    is_waxing = phase < 0.5
    if is_waxing: draw.chord(bbox, start=270, end=90, fill=color)
    else: draw.chord(bbox, start=90, end=270, fill=color)
    terminator_width = abs(phase - (0.25 if is_waxing else 0.75)) * 4 * radius
    term_bbox = [center_x - terminator_width, center_y - radius, center_x + terminator_width, center_y + radius]
    if (is_waxing and phase > 0.25) or (not is_waxing and phase < 0.75):
        draw.ellipse(term_bbox, fill=color)
    else:
        draw.ellipse(term_bbox, fill=BACKGROUND_COLOR)
        draw.ellipse(bbox, outline=color, width=1)

def scrape_weather_detailed():
    weather_data, sunrise, sunset = [], "", ""
    try:
        # Open-Meteo pre astronómia dáta
        r = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&daily=sunrise,sunset&timezone=auto", timeout=5).json()
        sunrise = r["daily"]["sunrise"][0].split("T")[1]
        sunset = r["daily"]["sunset"][0].split("T")[1]
    except: pass
    
    # Počasie.sk pre textovú predpoveď
    url = "https://www.pocasie.sk/slovensko/samorin/5.html"
    try:
        html = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).text
        forecasts = re.findall(r"<ul class='daily-forecast.*?</ul>", html, re.DOTALL)[:5]
        for f in forecasts:
            day_match = re.search(r"<li class='date'>(.*?)</li>", f, re.DOTALL)
            if day_match:
                day = remove_html_tags(re.sub(r"<br.*?>.*", "", day_match.group(1))).split('-')[0].strip()
                desc = re.search(r"alt=['\"](.*?)['\"]", f).group(1)
                max_t = re.search(r"<span class='day'>\s*(-?\d+)", f).group(1)
                min_t = re.search(r"<span class='night'>\s*(-?\d+)", f).group(1)
                weather_data.append({"day": day, "desc": desc, "max": max_t, "min": min_t})
    except: pass
    return weather_data, sunrise, sunset

def scrape_etf_data():
    # Definovanie fondov: ISIN -> Ticker (XETRA) -> Zobrazený názov
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
            ts, cls = res['timestamp'], res['indicators']['quote'][0]['close']
            valid = [(ts[i], cls[i]) for i in range(len(cls)) if cls[i] is not None]
            
            curr_p = valid[-1][1]
            def get_perf(days):
                target_ts = valid[-1][0] - (days * 86400)
                # Nájdeme najbližšiu cenu k cieľovému dátumu
                old_p = next((p for t_s, p in reversed(valid) if t_s <= target_ts), valid[0][1])
                return ((curr_p - old_p) / old_p) * 100

            perf = {l: get_perf(d) for l, d in [
                ("1D", 1), ("1T", 7), ("1M", 30), ("1R", 365), ("3R", 1095), ("MAX", 9999)
            ]}
            results.append({"name": t['name'], "price": curr_p, "perf": perf, "error": False})
        except:
            results.append({"name": t['name'], "error": True})
    return results

def create_dashboard():
    # Inicializácia obrázka
    img = Image.new(MODE, (WIDTH, HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)
    fonts = get_fonts()
    now = datetime.datetime.now()
    
    # Zber dát
    weather, sunrise, sunset = scrape_weather_detailed()
    etf_data = scrape_etf_data()
    
    # 1. HLAVIČKA (Čierny pruh)
    draw.rectangle([(0, 0), (WIDTH, 64)], fill=TEXT_COLOR)
    date_str = f"{now.day}.{now.month}.{now.year}"
    draw.text((20, 15), date_str, font=fonts['large'], fill=BACKGROUND_COLOR)
    
    if sunrise:
        draw.text((WIDTH-130, 12), f"Východ: {sunrise}", font=fonts['tiny'], fill=BACKGROUND_COLOR)
        draw.text((WIDTH-130, 34), f"Západ: {sunset}", font=fonts['tiny'], fill=BACKGROUND_COLOR)
        draw_moon_phase(draw, WIDTH-160, 32, 16, BACKGROUND_COLOR)

    # 2. POČASIE (Ľavý stĺpec)
    cy = 85
    draw.text((20, cy), "Počasie Šamorín", font=fonts['medium'], fill=TEXT_COLOR)
    cy += 40
    for d in weather:
        # Riadok s dňom a teplotou
        draw.text((20, cy), d['day'], font=fonts['bold_small'], fill=TEXT_COLOR)
        temp_txt = f"{d['max']}° / {d['min']}°"
        draw.text((75, cy), temp_txt, font=fonts['bold_small'], fill=TEXT_COLOR)
        # Pod tým popis
        draw.text((20, cy + 18), shorten_weather_desc(d['desc']), font=fonts['tiny'], fill=TEXT_COLOR)
        cy += 48

    # 3. VERTIKÁLNA ODDELOVACIA ČIARA
    draw.line([(340, 80), (340, 460)], fill=TEXT_COLOR, width=1)

    # 4. ETF SEKCIA (Pravý stĺpec)
    rx = 360
    draw.text((rx, 85), "Moje ETF portfólio", font=fonts['medium'], fill=TEXT_COLOR)
    ry = 125
    
    for etf in etf_data:
        if etf.get('error'):
            draw.text((rx, ry), f"Chyba: {etf['name']}", font=fonts['tiny'], fill=TEXT_COLOR)
            ry += 30
            continue
            
        # Názov fondu a aktuálna cena
        draw.text((rx, ry), etf['name'], font=fonts['bold_small'], fill=TEXT_COLOR)
        price_txt = f"{etf['price']:.2f} €"
        draw.text((WIDTH - draw.textlength(price_txt, font=fonts['bold_small']) - 20, ry), price_txt, font=fonts['bold_small'], fill=TEXT_COLOR)
        ry += 22
        
        # Mriežka s výkonnosťou (2 riadky x 3 stĺpce)
        periods = [("1D", "1T", "1M"), ("1R", "3R", "MAX")]
        for row_idx, row in enumerate(periods):
            for col_idx, p in enumerate(row):
                val = etf['perf'][p]
                sign = "+" if val > 0 else ""
                txt = f"{p}: {sign}{val:.1f}%"
                draw.text((rx + col_idx*105, ry + row_idx*16), txt, font=fonts['tiny'], fill=TEXT_COLOR)
        ry += 62

    # Čas poslednej aktualizácie v pravom dolnom rohu
    update_txt = f"Aktualizované: {now.strftime('%H:%M')}"
    draw.text((WIDTH - 130, HEIGHT - 22), update_txt, font=fonts['tiny'], fill=TEXT_COLOR)
    
    return img

if __name__ == "__main__":
    # Spustenie a uloženie
    dashboard = create_dashboard()
    dashboard.save("dashboard_output.bmp")
    print("Dashboard bol úspešne uložený do súboru dashboard_output.bmp")

```
