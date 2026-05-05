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

# Získame absolútnu cestu k priečinku
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Fixné pozície pre sekcie (aby neskákali)
WEATHER_FIXED_Y = 255

# Súradnice Šamorín
LAT = 48.0282
LON = 17.3097

def get_fonts():
    fonts = {}
    try:
        font_path_bold = os.path.join(BASE_DIR, "arialbd.ttf")
        font_path_reg = os.path.join(BASE_DIR, "arial.ttf")

        if not os.path.exists(font_path_bold) and os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
            font_path_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            font_path_reg = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

        fonts['huge'] = ImageFont.truetype(font_path_bold, 60)
        fonts['large'] = ImageFont.truetype(font_path_bold, 35)
        fonts['medium'] = ImageFont.truetype(font_path_bold, 24)
        fonts['regular'] = ImageFont.truetype(font_path_reg, 18)
        fonts['small'] = ImageFont.truetype(font_path_reg, 15)
        fonts['tiny'] = ImageFont.truetype(font_path_reg, 13)
        fonts['bold_small'] = ImageFont.truetype(font_path_bold, 16) 
        fonts['bold_tiny'] = ImageFont.truetype(font_path_bold, 13)

        fonts['value_22'] = ImageFont.truetype(font_path_bold, 22)
        fonts['value_20'] = ImageFont.truetype(font_path_bold, 20)
        fonts['value_18'] = ImageFont.truetype(font_path_bold, 18)
        fonts['value_16'] = ImageFont.truetype(font_path_bold, 16)
        fonts['value_14'] = ImageFont.truetype(font_path_bold, 14)

        fonts['label'] = ImageFont.truetype(font_path_reg, 14)
        fonts['value'] = ImageFont.truetype(font_path_bold, 22)
        fonts['value_reg'] = ImageFont.truetype(font_path_reg, 22)

    except IOError:
        print("POZOR: Systémové fonty sa nenašli, používam predvolený.")
        default = ImageFont.load_default()
        fonts = {k: default for k in ['huge', 'large', 'medium', 'regular', 'small', 'tiny', 'bold_small', 'bold_tiny', 'label', 'value', 'value_reg', 'value_22', 'value_20', 'value_18', 'value_16', 'value_14']}

    return fonts

def remove_html_tags(text):
    clean = re.compile('<.*?>')
    text = re.sub(clean, '', text)
    text = text.replace('&nbsp;', ' ').replace('&#160;', ' ').replace('\xa0', ' ')
    text = text.replace('&ndash;', '-').replace('&#8211;', '-').replace('–', '-')
    text = text.replace('…', '...').replace('...', '') 
    text = re.sub(r'\[\d+\]', '', text)
    text = text.replace('\\\'', '\'') 
    return text.strip()

def shorten_weather_desc(text):
    if not text: return ""
    removes = [
        "Prevažne", "prevažne", "Miestami", "miestami", "Ojedinele", "ojedinele", 
        "Čiastočne", "čiastočne", "Prechodne", "prechodne", "Neskôr", "neskôr",
        "Ráno", "ráno", "Lokálne", "lokálne"
    ]
    for word in removes: text = text.replace(word, "")
    text = text.replace(" a ", ", ").replace(" s ", ", ").replace(" so ", ", ").replace(" až ", "/")

    replacements_phrases = {
        "slabým snežením": "slabé sneženie", "miernym snežením": "mierne sneženie",
        "hustým snežením": "husté sneženie", "občasným snežením": "občasné sneženie",
        "trvalým snežením": "trvalé sneženie", "slabým dažďom": "slabý dážď",
        "miernym dažďom": "mierny dážď", "silným dažďom": "silný dážď",
        "prudkým dažďom": "prudký dážď", "občasným dažďom": "občasný dážď",
        "trvalým dažďom": "trvalý dážď", "slabým mrholením": "slabé mrholenie",
        "miernym mrholením": "mierne mrholenie", "silným vetrom": "silný vietor",
        "prudkým vetrom": "prudký vietor", "nárazovým vetrom": "nárazový vietor",
        "ojedinelými búrkami": "ojedinelé búrky", "miestnymi búrkami": "miestne búrky",
        "silnými búrkami": "silné búrky", "ojedinelými prehánkami": "ojedinelé prehánky",
        "miestnymi prehánkami": "miestne prehánky", "občasnými prehánkami": "občasné prehánky",
        "snehovými prehánkami": "snehové prehánky"
    }
    for old, new in replacements_phrases.items(): text = text.replace(old, new)

    replacements_words = {
        "prehánkami": "prehánky", "mrholením": "mrholenie", "dažďom": "dážď",
        "snežením": "sneženie", "búrkami": "búrky", "vetrom": "vietor", "hmlou": "hmla"
    }
    for old, new in replacements_words.items(): text = text.replace(old, new)

    text = re.sub(r'\s+', ' ', text).strip(" ,") 
    text = re.sub(r',\s*,', ',', text) 
    if len(text) > 0: text = text[0].upper() + text[1:]
    if len(text) > 34: text = text[:32] + ".."
    return text

def get_moon_phase(date=None):
    if date is None: date = datetime.datetime.now()
    ref_date = datetime.datetime(2000, 1, 6, 18, 14)
    diff = date - ref_date
    days = diff.days + (diff.seconds / 86400.0)
    lunation = 29.530588853
    return (days % lunation) / lunation

def draw_moon_phase(draw, center_x, center_y, radius, color):
    phase = get_moon_phase()
    bbox = [center_x - radius, center_y - radius, center_x + radius, center_y + radius]
    draw.ellipse(bbox, outline=color, width=1)

    if phase < 0.02 or phase > 0.98: return
    if 0.48 < phase < 0.52:
        draw.ellipse(bbox, fill=color)
        return

    is_waxing = phase < 0.5
    if is_waxing: draw.chord(bbox, start=270, end=90, fill=color)
    else: draw.chord(bbox, start=90, end=270, fill=color)

    offset = phase - 0.25 if is_waxing else phase - 0.75
    terminator_width = abs(offset) * 4 * radius
    term_bbox = [center_x - terminator_width, center_y - radius, center_x + terminator_width, center_y + radius]
    is_gibbous = (is_waxing and phase > 0.25) or (not is_waxing and phase < 0.75)

    if is_gibbous: draw.ellipse(term_bbox, fill=color)
    else:
        draw.ellipse(term_bbox, fill=BACKGROUND_COLOR)
        draw.ellipse(bbox, outline=color, width=1)

# --- IKONY ---

def draw_icon_sun_rays(draw, cx, cy, size, color, stroke_width=1):
    r_core = size * 0.28
    draw.ellipse([cx - r_core, cy - r_core, cx + r_core, cy + r_core], outline=color, width=stroke_width)
    r_inner = r_core + size * 0.12
    r_outer = size * 0.5
    for i in range(0, 360, 45):
        rad = math.radians(i)
        sx, sy = cx + math.cos(rad) * r_inner, cy + math.sin(rad) * r_inner
        ex, ey = cx + math.cos(rad) * r_outer, cy + math.sin(rad) * r_outer
        draw.line([sx, sy, ex, ey], fill=color, width=stroke_width)

def draw_icon_cloud_contour(draw, cx, cy, size, color, bg_color, filled_bg=False):
    circles = [(-0.25, 0.1, 0.25), (0.25, 0.05, 0.22), (-0.05, -0.15, 0.3)]
    base_w, base_h = size * 0.8, size * 0.25
    base_x, base_y = cx - base_w / 2, cy + size * 0.15
    def draw_shape(fill_col, expansion=0):
        bx, by, bw, bh = base_x - expansion, base_y - expansion, base_w + 2*expansion, base_h + 2*expansion
        r_corner = bh / 2
        draw.ellipse([bx, by, bx + 2*r_corner, by + 2*r_corner], fill=fill_col) 
        draw.ellipse([bx + bw - 2*r_corner, by, bx + bw, by + 2*r_corner], fill=fill_col) 
        draw.rectangle([bx + r_corner, by, bx + bw - r_corner, by + bh], fill=fill_col) 
        for ox, oy, r_base in circles:
            r = (size * r_base) + expansion
            x, y = cx + size * ox, cy + size * oy
            draw.ellipse([x - r, y - r, x + r, y + r], fill=fill_col)
    if filled_bg: draw_shape(bg_color, expansion=3)
    stroke = 1
    draw_shape(color, expansion=stroke/2) 
    draw_shape(bg_color, expansion=-stroke/2) 

def draw_icon_rain(draw, cx, cy, size, color):
    y_start, length = cy + size * 0.35, size * 0.25
    for offset in [-0.2, 0, 0.2]:
        x = cx + size * offset
        draw.line([x, y_start, x, y_start + length], fill=color, width=1)

def draw_icon_lightning(draw, cx, cy, size, color):
    y_top = cy + size * 0.1
    pts = [(cx + 2, y_top), (cx - 4, y_top + size*0.25), (cx - 1, y_top + size*0.25),
           (cx - 3, y_top + size*0.55), (cx + 4, y_top + size*0.20), (cx + 1, y_top + size*0.20)]
    draw.polygon(pts, fill=color) 

def draw_icon_snow(draw, cx, cy, size, color):
    y = cy + size * 0.45
    font = ImageFont.load_default()
    draw.text((cx - size*0.25, y - 5), "*", font=font, fill=color)
    draw.text((cx + size*0.1, y - 5), "*", font=font, fill=color)

def draw_icon_fog(draw, cx, cy, size, color):
    y, w = cy + size * 0.1, size * 0.6
    for i in range(3):
        y_line = y + i * 5
        draw.line([cx - w/2, y_line, cx + w/2, y_line], fill=color, width=1)

def draw_weather_icon(draw, x, y, size, condition_text):
    cond = condition_text.lower()
    color, bg_color = TEXT_COLOR, BACKGROUND_COLOR
    cx, cy = x + size // 2, y + size // 2
    if "jasno" in cond or "slneč" in cond:
        draw_icon_sun_rays(draw, cx, cy, size, color)
    elif "polo" in cond or "malá oblač" in cond:
        draw_icon_sun_rays(draw, cx + 4, cy - 4, size*0.8, color)
        draw_icon_cloud_contour(draw, cx - 3, cy + 3, size*0.85, color, bg_color, filled_bg=True)
    elif "dážď" in cond or "prš" in cond or "prehánk" in cond or "mrhol" in cond:
        if "prehánk" in cond: draw_icon_sun_rays(draw, cx + 5, cy - 5, size*0.7, color)
        draw_icon_rain(draw, cx, cy, size, color)
        draw_icon_cloud_contour(draw, cx, cy, size*0.9, color, bg_color, filled_bg=True)
    elif "búrk" in cond:
        draw_icon_lightning(draw, cx, cy, size, color)
        draw_icon_cloud_contour(draw, cx, cy, size*0.9, color, bg_color, filled_bg=True)
    elif "sneh" in cond or "snež" in cond:
        draw_icon_snow(draw, cx, cy, size, color)
        draw_icon_cloud_contour(draw, cx, cy, size*0.9, color, bg_color, filled_bg=True)
    elif "oblač" in cond or "zamrač" in cond:
        if "zamrač" in cond:
             draw_icon_cloud_contour(draw, cx + 5, cy - 3, size*0.75, color, bg_color)
             draw_icon_cloud_contour(draw, cx - 2, cy + 3, size*0.85, color, bg_color, filled_bg=True)
        else:
             draw_icon_cloud_contour(draw, cx, cy, size*0.9, color, bg_color)
    elif "hmla" in cond:
        draw_icon_fog(draw, cx, cy, size, color)
    else:
        font = ImageFont.load_default()
        draw.text((cx-3, cy-8), "?", font=font, fill=color)

# --- SCRAPING ZÁKLADU ---

def scrape_weather_detailed():
    weather_data, sunrise, sunset = [], "", ""
    try:
        url_sun = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&daily=sunrise,sunset&timezone=auto"
        response_sun = requests.get(url_sun, timeout=5).json()
        if response_sun.get("daily", {}).get("sunrise") and response_sun.get("daily", {}).get("sunset"):
            sunrise = response_sun["daily"]["sunrise"][0].split("T")[1]
            sunset = response_sun["daily"]["sunset"][0].split("T")[1]
    except Exception as e: print(f"Chyba Open-Meteo (Slnko): {e}")

    url = "https://www.pocasie.sk/slovensko/samorin/5.html"
    headers = {'User-Agent': 'Mozilla/5.0'}
    short_days_map = {"Pondelok": "Pon", "Utorok": "Uto", "Streda": "Str", "Štvrtok": "Štv", "Piatok": "Pia", "Sobota": "So", "Nedeľa": "Ne"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding if response.encoding == 'ISO-8859-1' else response.encoding
        html = response.text
        if not sunrise or not sunset:
            match_sun = re.search(r'Východ.*?>(\d{1,2}:\d{2})<.*?Západ.*?>(\d{1,2}:\d{2})<', html, re.IGNORECASE | re.DOTALL)
            if match_sun: sunrise, sunset = match_sun.group(1), match_sun.group(2)

        forecast_blocks = re.findall(r"<ul class='daily-forecast.*?</ul>", html, re.DOTALL)
        for block in forecast_blocks:
            day_match = re.search(r"<li class='date'>(.*?)</li>", block, re.DOTALL)
            day_name = "Neznáme"
            if day_match:
                raw_day_html = day_match.group(1)
                special_day = re.search(r"<i>(Dnes|Zajtra)</i>", raw_day_html, re.IGNORECASE)
                if special_day: day_name = special_day.group(1)
                else:
                    clean_text = re.sub(r"<br.*?>.*", "", raw_day_html, flags=re.DOTALL) 
                    clean_text = remove_html_tags(clean_text).strip()
                    day_name = clean_text.split('-')[0].strip()
                    if day_name in short_days_map: day_name = short_days_map[day_name]

            desc_match = re.search(r"<li class='weather'>.*?alt=['\"](.*?)['\"]", block, re.DOTALL)
            desc = desc_match.group(1).strip() if desc_match else "Neznáme"

            max_t_match = re.search(r"<span class='day'>\s*(-?\d+)\s*°C</span>", block)
            max_t = max_t_match.group(1) if max_t_match else "?"
            min_t_match = re.search(r"<span class='night'>\s*(-?\d+)\s*°C</span>", block)
            min_t = min_t_match.group(1) if min_t_match else "?"

            wind_match = re.search(r"title=['\"][^'\"]*vietor['\"][^>]*>.*?&nbsp;\s*(\d+\s*km/h)", block, re.IGNORECASE | re.DOTALL)
            wind = wind_match.group(1) if wind_match else ""
            prob_match = re.search(r"title=['\"]pravdepodobnosť zrážok['\"][^>]*>.*?&nbsp;\s*(\d+%)", block, re.IGNORECASE | re.DOTALL)
            precip_prob = prob_match.group(1) if prob_match else ""

            if day_name != "Neznáme":
                weather_data.append({"day": day_name, "desc": desc, "max": max_t, "min": min_t, "wind": wind, "prob": precip_prob})
    except Exception as e: print(f"Chyba pocasie.sk: {e}")
    return weather_data, sunrise, sunset

def get_meniny_combined():
    headers = {'User-Agent': 'Mozilla/5.0'}
    # Kto má meniny
    try:
        response = requests.get("https://kto-ma-meniny.sk/", headers=headers, timeout=10)
        response.encoding = 'utf-8'
        html = response.text
        now, tomorrow = datetime.datetime.now(), datetime.datetime.now() + datetime.timedelta(days=1)
        months = ["Január", "Február", "Marec", "Apríl", "Máj", "Jún", "Júl", "August", "September", "Október", "November", "December"]
        
        def get_names_for_date(date_str):
            pattern = fr">\s*{re.escape(date_str)}\s*</div>\s*<div[^>]*>.*?</div>\s*<div[^>]*>(.*?)</div>"
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            return remove_html_tags(match.group(1)).strip().strip(" ,") if match else "Neznáme"

        name_today = get_names_for_date(f"{now.day}. {months[now.month-1]}")
        name_tomorrow = get_names_for_date(f"{tomorrow.day}. {months[tomorrow.month-1]}")
        if name_today != "Neznáme": return name_today, name_tomorrow
    except: pass

    # Fallback Zones
    try:
        response = requests.get("https://www.zones.sk/kalendar-udalosti/meniny/", headers=headers, timeout=10)
        response.encoding = 'utf-8'
        match = re.search(r"meniny</a> má.*?<strong>(.*?)</strong>.*?zajtra.*?<strong>(.*?)</strong>", response.text, re.DOTALL | re.IGNORECASE)
        if match: return remove_html_tags(match.group(1)).strip(), remove_html_tags(match.group(2)).strip()
    except: pass

    return None, None

def get_combined_international_days(day, month):
    headers = {'User-Agent': 'Mozilla/5.0'}
    days = []
    try:
        html = requests.get("https://www.zones.sk/kalendar-udalosti/medzinarodne-dni/", headers=headers, timeout=10).text
        matches = re.findall(r"title=['\"]Medzinárodný deň Dnes['\"][^>]*>\s*<h2>(.*?)</h2>", html, re.IGNORECASE | re.DOTALL)
        for raw_text in matches:
            clean = re.sub(r'\s+\d{4}$', '', remove_html_tags(raw_text).strip())
            if clean: days.append(clean)
    except: pass
    return ", ".join(days[:3]) if days else ""

def get_next_season_info():
    now = datetime.datetime.now()
    events = [
        (datetime.datetime(now.year, 3, 20), "Prvý jarný deň", "rovnodennosť"),
        (datetime.datetime(now.year, 6, 21), "Prvý letný deň", "slnovrat"),
        (datetime.datetime(now.year, 9, 23), "Prvý jesenný deň", "rovnodennosť"),
        (datetime.datetime(now.year, 12, 21), "Prvý zimný deň", "slnovrat")
    ]
    next_event = next((e for e in events if e[0].date() > now.date()), (datetime.datetime(now.year + 1, 3, 20), "Prvý jarný deň", "rovnodennosť"))
    days_left = (next_event[0].date() - now.date()).days
    days_str = "deň" if days_left == 1 else "dni" if 2 <= days_left <= 4 else "dní"
    return next_event[1], f"({next_event[2]})", f"o {days_left} {days_str}"

# === SŤAHOVANIE ETF DÁT (YAHOO FINANCE) ===

def scrape_etf_data():
    # Využívame mapovanie z ISIN na XETRA (.DE) tickery pre získanie hodnoty v EUR
    tickers = [
        {"isin": "IE00BKM4GZ66", "ticker": "IS3N.DE", "name": "MSCI Emerg. Markets"},
        {"isin": "IE00BF4RFH31", "ticker": "EUNL.DE", "name": "MSCI World"},
        {"isin": "IE00B5BMR087", "ticker": "SXR8.DE", "name": "S&P 500"},
        {"isin": "IE0006WW1TQ4", "ticker": "FWRG.DE", "name": "FTSE All-World"}
    ]
    results = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0'}
    
    for t in tickers:
        # Interval 1 deň, rozsah: celé dostupné obdobie (max)
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{t['ticker']}?interval=1d&range=max"
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            if not data.get('chart', {}).get('result'):
                raise ValueError("Žiadne dáta v odpovedi")
                
            result = data['chart']['result'][0]
            timestamps = result['timestamp']
            closes = result['indicators']['quote'][0]['close']
            
            # Odstránime neplatné dáta (sviatky atď., kde nebola cena)
            valid_data = [(ts, c) for ts, c in zip(timestamps, closes) if c is not None]
            if not valid_data:
                raise ValueError("Žiadne platné ceny")
                
            current_ts, current_price = valid_data[-1]
            
            def get_price_at(days_ago):
                if days_ago == 'max':
                    return valid_data[0][1]
                target_ts = current_ts - (days_ago * 86400)
                # Hľadáme najbližší predchádzajúci dostupný záznam z burzy
                for ts, c in reversed(valid_data):
                    if ts <= target_ts:
                        return c
                return valid_data[0][1] # Fallback na najstarší ak je obdobie príliš dlhé
                
            # 1D je posledný zatvárací deň
            p_1d = valid_data[-2][1] if len(valid_data) > 1 else current_price
            p_1w = get_price_at(7)
            p_1m = get_price_at(30)
            p_1y = get_price_at(365)
            p_3y = get_price_at(365 * 3)
            p_max = valid_data[0][1]
            
            perf = {}
            for label, p_past in [("1D", p_1d), ("1T", p_1w), ("1M", p_1m), ("1R", p_1y), ("3R", p_3y), ("MAX", p_max)]:
                diff_eur = current_price - p_past
                diff_pct = (diff_eur / p_past) * 100 if p_past else 0
                perf[label] = {"eur": diff_eur, "pct": diff_pct}
                
            results.append({
                "name": t['name'],
                "isin": t['isin'],
                "price": current_price,
                "perf": perf,
                "error": False
            })
            
        except Exception as e:
            print(f"Chyba pri sťahovaní ETF {t['isin']}: {e}")
            results.append({
                "name": t['name'],
                "isin": t['isin'],
                "error": True
            })
            
    return results

def get_slovak_date():
    try:
        os.environ['TZ'] = 'Europe/Bratislava'
        time.tzset()
    except AttributeError: pass
    now = datetime.datetime.now()
    days = ["Pondelok", "Utorok", "Streda", "Štvrtok", "Piatok", "Sobota", "Nedeľa"]
    months = ["Január", "Február", "Marec", "Apríl", "Máj", "Jún", "Júl", "August", "September", "Október", "November", "December"]
    return now, f"{days[now.weekday()]}, {now.day}. {months[now.month-1]} {now.year}"

# === HLAVNÝ VYKRESLOVACÍ CYKLUS ===

def create_dashboard():
    img = Image.new(MODE, (WIDTH, HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)
    fonts = get_fonts()
    now, date_str = get_slovak_date()

    meniny_today, meniny_tomorrow = get_meniny_combined()
    intl_day_text = get_combined_international_days(now.day, now.month)
    weather_list, sunrise, sunset = scrape_weather_detailed()
    
    # NOVÉ: Načítanie dát pre ETF
    etf_data = scrape_etf_data()
    
    last_updated = now.strftime("%H:%M")

    # A. HLAVIČKA
    header_height = 64
    draw.rectangle([(0, 0), (WIDTH, header_height)], fill=TEXT_COLOR)
    draw.text((20, 15), date_str, font=fonts['large'], fill=BACKGROUND_COLOR)

    if sunrise and sunset:
        text_rise, text_set = f"Východ: {sunrise}", f"Západ: {sunset}"
        w_rise = draw.textlength(text_rise, font=fonts['small'])
        w_set = draw.textlength(text_set, font=fonts['small'])
        draw.text((WIDTH - w_rise - 20, 12), text_rise, font=fonts['small'], fill=BACKGROUND_COLOR)
        draw.text((WIDTH - w_set - 20, 34), text_set, font=fonts['small'], fill=BACKGROUND_COLOR)
        draw_moon_phase(draw, WIDTH - max(w_rise, w_set) - 38, header_height // 2, 18, BACKGROUND_COLOR)

    # B. ĽAVÝ STĹPEC
    left_col_x = 20
    col_y_start = header_height + 15
    draw.text((left_col_x, col_y_start), "Meniny má ", font=fonts['regular'], fill=TEXT_COLOR)
    y_names = col_y_start 

    if meniny_today and meniny_tomorrow:
        name_text = meniny_today + ","
        current_x = left_col_x + draw.textlength("Meniny má ", font=fonts['regular']) + 3
        available_w = 315 - current_x
        selected_font, selected_offset = fonts['value_14'], 4
        for font, offset in [(fonts['value_22'], -3), (fonts['value_20'], -1), (fonts['value_18'], 0), (fonts['value_16'], 2), (fonts['value_14'], 4)]:
            if draw.textlength(name_text, font=font) <= available_w:
                selected_font, selected_offset = font, offset
                break
        draw.text((current_x, y_names + selected_offset), name_text, font=selected_font, fill=TEXT_COLOR)
        
        y_tomorrow = y_names + 25
        draw.text((left_col_x, y_tomorrow), "zajtra ", font=fonts['small'], fill=TEXT_COLOR)
        draw.text((left_col_x + draw.textlength("zajtra ", font=fonts['small']) + 3, y_tomorrow), meniny_tomorrow, font=fonts['small'], fill=TEXT_COLOR)
    else:
        draw.text((left_col_x, y_names + 25), "Dáta nedostupné", font=fonts['value'], fill=TEXT_COLOR)

    center_x_left_col = 160
    info_area_top, info_area_bottom = 135, WEATHER_FIXED_Y
    
    if intl_day_text:
        is_long = len(intl_day_text) > 40
        selected_font = fonts['small'] if is_long else fonts['regular']
        wrapped_info = textwrap.wrap(intl_day_text, width=35 if is_long else 30)
        current_y_info = info_area_top + (info_area_bottom - info_area_top - len(wrapped_info) * (18 if is_long else 22)) // 2
        for line in wrapped_info:
            draw.text((center_x_left_col - draw.textlength(line, font=selected_font)/2, current_y_info), line, font=selected_font, fill=TEXT_COLOR)
            current_y_info += 18 if is_long else 22
    else:
        line1, line2, line3 = get_next_season_info()
        current_y_season = info_area_top + (info_area_bottom - info_area_top - 66) // 2
        draw.text((center_x_left_col - draw.textlength(line1, font=fonts['regular'])/2, current_y_season), line1, font=fonts['regular'], fill=TEXT_COLOR)
        draw.text((center_x_left_col - draw.textlength(line2, font=fonts['small'])/2, current_y_season + 22), line2, font=fonts['small'], fill=TEXT_COLOR)
        draw.text((center_x_left_col - draw.textlength(line3, font=fonts['regular'])/2, current_y_season + 42), line3, font=fonts['regular'], fill=TEXT_COLOR)

    # POČASIE
    current_y = WEATHER_FIXED_Y
    draw.text((left_col_x, current_y), "Predpoveď počasia", font=fonts['regular'], fill=TEXT_COLOR)
    current_y += 30

    if weather_list:
        has_minus_night = any('-' in str(d['min']) for d in weather_list)
        max_night_width = max([fonts['bold_small'].getlength(str(d['min'])) for d in weather_list] + [0])

        for day_data in weather_list:
            if current_y > HEIGHT - 30: break
            draw_weather_icon(draw, left_col_x, current_y, 24, day_data['desc'])
            text_x = left_col_x + 35
            draw.text((text_x, current_y), day_data['day'], font=fonts['bold_small'], fill=TEXT_COLOR)
            draw.text((text_x, current_y + 19), shorten_weather_desc(day_data['desc']), font=fonts['tiny'], fill=TEXT_COLOR)

            sep_x_center, gap = text_x + 95, 12
            max_t_str, min_t_str = str(day_data['max']), str(day_data['min'])
            w_max, w_min = draw.textlength(max_t_str, font=fonts['bold_small']), draw.textlength(min_t_str, font=fonts['bold_small'])

            max_anchor_x = sep_x_center - gap
            if max_t_str.startswith('-'):
                draw.text((max_anchor_x - w_max - 3, current_y), '-', font=fonts['bold_small'], fill=TEXT_COLOR)
                draw.text((max_anchor_x - w_max + draw.textlength('-', font=fonts['bold_small']), current_y), max_t_str[1:], font=fonts['bold_small'], fill=TEXT_COLOR)
            else: draw.text((max_anchor_x - w_max, current_y), max_t_str, font=fonts['bold_small'], fill=TEXT_COLOR)

            min_start_x = sep_x_center + gap
            if not has_minus_night: draw.text((min_start_x, current_y), min_t_str, font=fonts['bold_small'], fill=TEXT_COLOR)
            else:
                orig_x = min_start_x + max_night_width - w_min
                if min_t_str.startswith('-'):
                    draw.text((orig_x - 3, current_y), '-', font=fonts['bold_small'], fill=TEXT_COLOR)
                    draw.text((orig_x + draw.textlength('-', font=fonts['bold_small']), current_y), min_t_str[1:], font=fonts['bold_small'], fill=TEXT_COLOR)
                else: draw.text((orig_x, current_y), min_t_str, font=fonts['bold_small'], fill=TEXT_COLOR)

            if day_data['wind']: draw.text((text_x + 195 - fonts['tiny'].getlength(day_data['wind']), current_y + 2), day_data['wind'], font=fonts['tiny'], fill=TEXT_COLOR)
            if day_data['prob'] and day_data['prob'] != "0%": draw.text((text_x + 245 - fonts['tiny'].getlength(day_data['prob']), current_y + 2), day_data['prob'], font=fonts['tiny'], fill=TEXT_COLOR)
            current_y += 35
    else: draw.text((left_col_x, current_y), "Dáta počasia nedostupné", font=fonts['small'], fill=TEXT_COLOR)

    # C. ODDELOVACIA ČIARA
    draw.line([(330, header_height + 20), (330, HEIGHT - 20)], fill=TEXT_COLOR, width=3)

    # D. PRAVÝ STĹPEC - ETF FONDY
    right_col_x = 350
    draw.text((right_col_x, col_y_start), "Vývoj ETF fondov", font=fonts['medium'], fill=TEXT_COLOR)
    right_y = col_y_start + 35

    for etf in etf_data:
        if right_y > HEIGHT - 50: break
            
        if etf.get('error'):
            draw.text((right_col_x, right_y), f"{etf['name']} - Chyba pri sťahovaní", font=fonts['small'], fill=TEXT_COLOR)
            right_y += 30
            continue

        # Názov fondu naľavo, Cena napravo
        draw.text((right_col_x, right_y), etf['name'], font=fonts['bold_small'], fill=TEXT_COLOR)
        
        price_str = f"{etf['price']:.2f} €"
        w_price = fonts['bold_small'].getlength(price_str)
        draw.text((WIDTH - w_price - 20, right_y), price_str, font=fonts['bold_small'], fill=TEXT_COLOR)
        
        right_y += 20

        # Tabuľka (grid) s vývojom: 3 stĺpce, 2 riadky
        labels = ["1D", "1T", "1M", "1R", "3R", "MAX"]
        col_offsets = [0, 150, 290]

        for i, label in enumerate(labels):
            data = etf['perf'][label]
            sign = "+" if data['pct'] > 0 else ""
            val_str = f"{label}: {sign}{data['pct']:.1f}% ({sign}{data['eur']:.1f}€)"
            
            row = i // 3
            col = i % 3
            x_pos = right_col_x + col_offsets[col]
            y_pos = right_y + (row * 18)

            draw.text((x_pos, y_pos), val_str, font=fonts['small'], fill=TEXT_COLOR)

        right_y += 45 # Odstup pre ďalší fond

    # E. PÄTIČKA
    update_text = f"Aktualizované: {last_updated}"
    w_update = draw.textlength(update_text, font=fonts['small'])
    draw.text((WIDTH - w_update - 20, HEIGHT - 30), update_text, font=fonts['small'], fill=TEXT_COLOR)

    return img

def main():
    print("Sťahujem dáta a generujem dashboard s ETF...")
    image = create_dashboard()
    image.save("dashboard_output.bmp")
    print("Hotovo. Obrázok bol uložený.")
    # Ak spúšťaš na PC pre testovanie:
    # image.show()

if __name__ == "__main__":
    main()

```
