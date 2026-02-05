import datetime
import textwrap
import requests
import json
import os
import re
import random
import math
import time
from PIL import Image, ImageDraw, ImageFont

# --- KONFIGURÁCIA ---
WIDTH = 800
HEIGHT = 480
MODE = '1' 
BACKGROUND_COLOR = 255 # Biela
TEXT_COLOR = 0         # Čierna

# --- OPRAVA CIEST K SÚBOROM ---
# Získame absolútnu cestu k priečinku, v ktorom sa nachádza tento skript (main.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Súbory budeme hľadať relatívne k tomuto priečinku
STATE_FILE = os.path.join(BASE_DIR, "dashboard_state.json") 
FACTS_FILE = os.path.join(BASE_DIR, "facts.json")

# Fixné pozície pre sekcie (aby neskákali)
WEATHER_FIXED_Y = 255
TV_PROGRAM_FIXED_Y = 320

# Súradnice Šamorín
LAT = 48.0282
LON = 17.3097

def get_fonts():
    fonts = {}
    try:
        # Aj fonty budeme hľadať v priečinku skriptu, ak ide o lokálne súbory
        font_path_bold = os.path.join(BASE_DIR, "arialbd.ttf")
        font_path_reg = os.path.join(BASE_DIR, "arial.ttf")
        
        # Ak lokálne fonty nie sú, skúsime systémové cesty (Linux/Raspberry Pi)
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
        
        # Nové veľkosti pre dynamické škálovanie mien
        fonts['value_22'] = ImageFont.truetype(font_path_bold, 22) # Alias pre value
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
    """Odstráni HTML značky a entity z textu."""
    clean = re.compile('<.*?>')
    text = re.sub(clean, '', text)
    text = text.replace('&nbsp;', ' ').replace('&#160;', ' ').replace('\xa0', ' ')
    text = text.replace('&ndash;', '-').replace('&#8211;', '-').replace('–', '-')
    text = text.replace('…', '...').replace('...', '') 
    text = re.sub(r'\[\d+\]', '', text)
    text = text.replace('\\\'', '\'') 
    return text.strip()

def shorten_weather_desc(text):
    """Skráti popis počasia pre zobrazenie v ľavom stĺpci."""
    if not text:
        return ""
        
    removes = [
        "Prevažne", "prevažne", "Miestami", "miestami", "Ojedinele", "ojedinele", 
        "Čiastočne", "čiastočne", "Prechodne", "prechodne", "Neskôr", "neskôr",
        "Ráno", "ráno", "Lokálne", "lokálne"
    ]
    
    for word in removes:
        text = text.replace(word, "")
        
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
    
    for old, new in replacements_phrases.items():
        text = text.replace(old, new)

    replacements_words = {
        "prehánkami": "prehánky", "mrholením": "mrholenie", "dažďom": "dážď",
        "snežením": "sneženie", "búrkami": "búrky", "vetrom": "vietor", "hmlou": "hmla"
    }
    for old, new in replacements_words.items():
        text = text.replace(old, new)
    
    text = re.sub(r'\s+', ' ', text).strip(" ,") 
    text = re.sub(r',\s*,', ',', text) 
    
    if len(text) > 0:
        text = text[0].upper() + text[1:]

    if len(text) > 34:
        text = text[:32] + ".."
        
    return text

def get_moon_phase(date=None):
    if date is None:
        date = datetime.datetime.now()
    ref_date = datetime.datetime(2000, 1, 6, 18, 14)
    diff = date - ref_date
    days = diff.days + (diff.seconds / 86400.0)
    lunation = 29.530588853
    phase = (days % lunation) / lunation
    return phase

def draw_moon_phase(draw, center_x, center_y, radius, color):
    phase = get_moon_phase()
    bbox = [center_x - radius, center_y - radius, center_x + radius, center_y + radius]
    draw.ellipse(bbox, outline=color, width=1)
    
    if phase < 0.02 or phase > 0.98: return
    if 0.48 < phase < 0.52:
        draw.ellipse(bbox, fill=color)
        return

    is_waxing = phase < 0.5
    if is_waxing:
        draw.chord(bbox, start=270, end=90, fill=color)
    else:
        draw.chord(bbox, start=90, end=270, fill=color)

    if is_waxing:
        offset = phase - 0.25
    else:
        offset = phase - 0.75
        
    terminator_width = abs(offset) * 4 * radius
    term_bbox = [center_x - terminator_width, center_y - radius, 
                 center_x + terminator_width, center_y + radius]
    
    is_gibbous = (is_waxing and phase > 0.25) or (not is_waxing and phase < 0.75)
    
    if is_gibbous:
        draw.ellipse(term_bbox, fill=color)
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
        sx = cx + math.cos(rad) * r_inner
        sy = cy + math.sin(rad) * r_inner
        ex = cx + math.cos(rad) * r_outer
        ey = cy + math.sin(rad) * r_outer
        draw.line([sx, sy, ex, ey], fill=color, width=stroke_width)

def draw_icon_cloud_contour(draw, cx, cy, size, color, bg_color, filled_bg=False):
    circles = [(-0.25, 0.1, 0.25), (0.25, 0.05, 0.22), (-0.05, -0.15, 0.3)]
    base_w = size * 0.8
    base_h = size * 0.25
    base_x = cx - base_w / 2
    base_y = cy + size * 0.15
    def draw_shape(fill_col, outline_col=None, width=0, expansion=0):
        bx, by, bw, bh = base_x - expansion, base_y - expansion, base_w + 2*expansion, base_h + 2*expansion
        r_corner = bh / 2
        draw.ellipse([bx, by, bx + 2*r_corner, by + 2*r_corner], fill=fill_col) 
        draw.ellipse([bx + bw - 2*r_corner, by, bx + bw, by + 2*r_corner], fill=fill_col) 
        draw.rectangle([bx + r_corner, by, bx + bw - r_corner, by + bh], fill=fill_col) 
        for ox, oy, r_base in circles:
            r = (size * r_base) + expansion
            x = cx + size * ox
            y = cy + size * oy
            draw.ellipse([x - r, y - r, x + r, y + r], fill=fill_col)
    if filled_bg:
        draw_shape(bg_color, expansion=3)
    stroke = 1
    draw_shape(color, expansion=stroke/2) 
    draw_shape(bg_color, expansion=-stroke/2) 

def draw_icon_rain(draw, cx, cy, size, color):
    y_start = cy + size * 0.35
    length = size * 0.25
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
    y = cy + size * 0.1
    w = size * 0.6
    for i in range(3):
        y_line = y + i * 5
        draw.line([cx - w/2, y_line, cx + w/2, y_line], fill=color, width=1)

def draw_weather_icon(draw, x, y, size, condition_text):
    cond = condition_text.lower()
    color = TEXT_COLOR
    bg_color = BACKGROUND_COLOR
    cx = x + size // 2
    cy = y + size // 2
    if "jasno" in cond or "slneč" in cond:
        draw_icon_sun_rays(draw, cx, cy, size, color)
    elif "polo" in cond or "malá oblač" in cond:
        draw_icon_sun_rays(draw, cx + 4, cy - 4, size*0.8, color)
        draw_icon_cloud_contour(draw, cx - 3, cy + 3, size*0.85, color, bg_color, filled_bg=True)
    elif "dážď" in cond or "prš" in cond or "prehánk" in cond or "mrhol" in cond:
        if "prehánk" in cond:
             draw_icon_sun_rays(draw, cx + 5, cy - 5, size*0.7, color)
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

# --- SCRAPING ---

def scrape_weather_detailed():
    weather_data = []
    sunrise = ""
    sunset = ""
    try:
        url_sun = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&daily=sunrise,sunset&timezone=auto"
        response_sun = requests.get(url_sun, timeout=5)
        data_sun = response_sun.json()
        daily = data_sun.get("daily", {})
        sunrises = daily.get("sunrise", [])
        sunsets = daily.get("sunset", [])
        if sunrises and sunsets:
            sunrise = sunrises[0].split("T")[1]
            sunset = sunsets[0].split("T")[1]
    except Exception as e:
        print(f"Chyba Open-Meteo (Slnko): {e}")

    url = "https://www.pocasie.sk/slovensko/samorin/5.html"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    short_days_map = {"Pondelok": "Pon", "Utorok": "Uto", "Streda": "Str", "Štvrtok": "Štv", "Piatok": "Pia", "Sobota": "So", "Nedeľa": "Ne"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding if response.encoding == 'ISO-8859-1' else response.encoding
        html = response.text
        if not sunrise or not sunset:
            match_sun = re.search(r'Východ.*?>(\d{1,2}:\d{2})<.*?Západ.*?>(\d{1,2}:\d{2})<', html, re.IGNORECASE | re.DOTALL)
            if match_sun:
                sunrise, sunset = match_sun.group(1), match_sun.group(2)
        
        forecast_blocks = re.findall(r"<ul class='daily-forecast.*?</ul>", html, re.DOTALL)
        for block in forecast_blocks:
            day_match = re.search(r"<li class='date'>(.*?)</li>", block, re.DOTALL)
            day_name = "Neznáme"
            if day_match:
                raw_day_html = day_match.group(1)
                special_day = re.search(r"<i>(Dnes|Zajtra)</i>", raw_day_html, re.IGNORECASE)
                if special_day:
                    day_name = special_day.group(1)
                else:
                    clean_text = re.sub(r"<br.*?>.*", "", raw_day_html, flags=re.DOTALL) 
                    clean_text = remove_html_tags(clean_text).strip()
                    day_name = clean_text.split('-')[0].strip()
                    if day_name in short_days_map: day_name = short_days_map[day_name]

            desc = "Neznáme"
            desc_match = re.search(r"<li class='weather'>.*?alt=['\"](.*?)['\"]", block, re.DOTALL)
            if desc_match: desc = desc_match.group(1).strip()
            
            max_t = "?"
            min_t = "?"
            max_t_match = re.search(r"<span class='day'>\s*(-?\d+)\s*°C</span>", block)
            if max_t_match: max_t = max_t_match.group(1)
            min_t_match = re.search(r"<span class='night'>\s*(-?\d+)\s*°C</span>", block)
            if min_t_match: min_t = min_t_match.group(1)
                
            wind = ""
            precip_prob = ""
            wind_match = re.search(r"title=['\"][^'\"]*vietor['\"][^>]*>.*?&nbsp;\s*(\d+\s*km/h)", block, re.IGNORECASE | re.DOTALL)
            if wind_match: wind = wind_match.group(1)
            prob_match = re.search(r"title=['\"]pravdepodobnosť zrážok['\"][^>]*>.*?&nbsp;\s*(\d+%)", block, re.IGNORECASE | re.DOTALL)
            if prob_match: precip_prob = prob_match.group(1)
            
            if day_name != "Neznáme":
                weather_data.append({"day": day_name, "desc": desc, "max": max_t, "min": min_t, "wind": wind, "prob": precip_prob})
    except Exception as e:
        print(f"Chyba pri sťahovaní z pocasie.sk: {e}")
    return weather_data, sunrise, sunset

def scrape_tv_program_fallback():
    """Záložný scraper využívajúci alternatívny zdroj (tv-program.sk alebo všeobecnejší parser pre program.sk), keďže pôvodný zlyhával."""
    print("Skúšam záložný zdroj (tv-program.sk / alternative)...")
    
    # Použijeme tv-program.sk, ktorý má často jednoduchšiu štruktúru pre parsing (čistý text)
    url = "https://tv-program.sk/"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    targets = [
        {"search_name": "Jednotka", "display_name": "Jednotka", "target_time": 20*60 + 30},
        {"search_name": "Markíza", "display_name": "Markíza", "target_time": 20*60 + 30},
        {"search_name": "JOJ", "display_name": "JOJ", "target_time": 20*60 + 40},
        {"search_name": "Plus", "display_name": "JOJ Plus", "target_time": 20*60 + 30},
        {"search_name": "Dajto", "display_name": "Dajto", "target_time": 20*60 + 30}
    ]
    results = []
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        # Nastavíme encoding, ak je potrebný (tv-program.sk zvyčajne utf-8 alebo windows-1250)
        response.encoding = 'utf-8' 
        html = response.text
        
        # Keďže štruktúra môže byť zložitá, použijeme robustné vyhľadávanie v texte.
        # Hľadáme názov stanice a potom najbližší čas k cieľovému času.
        
        # Odstránime nadbytočné biele znaky pre jednoduchšie regexy
        # Ale zachováme poradie
        
        for target in targets:
            s_name = target["search_name"]
            t_time = target["target_time"]
            
            # 1. Nájdeme index výskytu stanice v texte
            # Hľadáme napr. "Jednotka" nasledované nejakým programom
            # Pozor na "JOJ" vs "JOJ Plus". Ak hľadáme "JOJ", nesmie za tým byť "Plus".
            
            station_regex = re.escape(s_name)
            if s_name == "JOJ":
                station_regex = r"JOJ(?!\s*Plus)"
            elif s_name == "Plus":
                station_regex = r"(JOJ\s*Plus|Plus)"
            
            # Hľadáme stanicu
            # Zvyčajne je to nadpis alebo v zozname. Zoberieme prvý výskyt, ktorý vyzerá ako hlavička
            # alebo proste prvý výskyt a budeme skenovať text za ním.
            
            matches = list(re.finditer(station_regex, html, re.IGNORECASE))
            
            best_prog = None
            min_diff = 9999
            
            # Prejdeme nájdené výskyty názvu stanice (môže ich byť viac, napr. v menu)
            # Skúsime každý, či za ním nasledujú časy programov.
            found_valid_block = False
            
            for match in matches:
                if found_valid_block: break # Ak sme už našli program pre túto stanicu, končíme
                
                start_pos = match.end()
                # Pozrieme sa na nasledujúcich cca 5000 znakov
                chunk = html[start_pos:start_pos+5000]
                
                # Hľadáme patterny času: HH:MM Názov
                # Regex: Čas (HH:MM), potom nejaké znaky (medzery, tagy), potom Názov
                # Názov končí ďalším časom alebo tagom.
                
                prog_matches = re.findall(r"(\d{1,2}:\d{2})\s*(?:<[^>]*>|\s|&nbsp;|-)*\s*([^<]+)", chunk)
                
                # Ak sme našli aspoň 3 programy s časmi, považujeme to za správny blok
                if len(prog_matches) > 2:
                    found_valid_block = True
                    for time_str, title_raw in prog_matches:
                        try:
                            hh, mm = map(int, time_str.split(':'))
                            minutes = hh * 60 + mm
                            diff = abs(minutes - t_time)
                            
                            # Ak je rozdiel menší ako 60 minút a je to lepší match
                            if diff < min_diff and diff < 60:
                                clean_title = remove_html_tags(title_raw).strip()
                                # Filter na nezmysly (príliš krátke alebo len čísla)
                                if len(clean_title) > 2:
                                    min_diff = diff
                                    best_prog = {
                                        "time": f"{hh:02d}:{mm:02d}",
                                        "title": clean_title
                                    }
                        except ValueError: continue

            if best_prog:
                results.append({"station": target['display_name'], "time": best_prog['time'], "title": best_prog['title']})
            else:
                results.append({"station": target['display_name'], "time": "--:--", "title": "Nedostupné"})

    except Exception as e:
        print(f"Chyba záložného zdroja: {e}")
        return []
        
    return results

def scrape_tv_program():
    """Hlavná funkcia pre TV program s fallbackom."""
    # 1. Primárny zdroj
    url = "https://tv-program.aktuality.sk/dnes/"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    targets = [
        {"search_name": "Jednotka", "display_name": "Jednotka", "target_time": 20*60 + 30},
        {"search_name": "Markíza", "display_name": "Markíza", "target_time": 20*60 + 30},
        {"search_name": "JOJ", "display_name": "JOJ", "target_time": 20*60 + 40},
        {"search_name": "Plus", "display_name": "JOJ Plus", "target_time": 20*60 + 30},
        {"search_name": "Dajto", "display_name": "Dajto", "target_time": 20*60 + 30}
    ]
    results = []
    
    success_primary = False
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        html_content = response.text
        pattern = r"program_desc\[\d+\]\s*=\s*\{(.*?)\}"
        matches = re.findall(pattern, html_content, re.DOTALL)
        
        if matches:
            all_programs = []
            for match in matches:
                title_m = re.search(r"title:'(.*?)'", match)
                time_m = re.search(r"time:'(.*?)'", match)
                channel_m = re.search(r"channel_title:'(.*?)'", match)
                if title_m and time_m and channel_m:
                    title = remove_html_tags(title_m.group(1))
                    time_str = time_m.group(1) 
                    channel = remove_html_tags(channel_m.group(1))
                    start_time_str = time_str.split('-')[0].strip()
                    try:
                        hh, mm = map(int, start_time_str.split(':'))
                        minutes = hh * 60 + mm
                        all_programs.append({"channel": channel, "time_str": start_time_str, "minutes": minutes, "title": title})
                    except ValueError: continue

            # Ak sme našli nejaké programy, spracujeme ich
            if all_programs:
                success_count = 0
                for target in targets:
                    best_match = None
                    min_diff = 9999
                    channel_programs = [p for p in all_programs if target["search_name"].lower() in p["channel"].lower()]
                    if target["search_name"] == "JOJ":
                        channel_programs = [p for p in channel_programs if "plus" not in p["channel"].lower()]
                    for prog in channel_programs:
                        diff = abs(prog["minutes"] - target["target_time"])
                        if diff < min_diff and diff < 45: 
                            min_diff = diff
                            best_match = prog
                    if best_match:
                        results.append({"station": target['display_name'], "time": best_match['time_str'], "title": best_match['title']})
                        success_count += 1
                    else:
                        results.append({"station": target['display_name'], "time": "--:--", "title": "Dáta nedostupné"})
                
                if success_count >= 2: # Považujeme za úspech ak máme aspoň 2 stanice
                    success_primary = True

    except Exception as e:
        print(f"Chyba pri sťahovaní TV programu (aktuality): {e}")

    # 2. Fallback ak primárny zlyhal
    if not success_primary:
        fallback_results = scrape_tv_program_fallback()
        if fallback_results:
            # Skontrolujeme, či fallback vrátil použiteľné dáta (nie samé chyby)
            valid_count = sum(1 for r in fallback_results if r['time'] != "--:--")
            if valid_count > 0:
                return fallback_results
            
    # Ak primárny zdroj vrátil aspoň niečo (aj keď s chybami), vrátime to, inak prázdne
    if results:
        return results
        
    return []

def scrape_wikipedia_events():
    """Stiahne iba udalosti z Hlavnej stránky Wikipédie. Zaujímavosti odstránené."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    events = []

    try:
        url_main = "https://sk.wikipedia.org/wiki/Hlavn%C3%A1_str%C3%A1nka"
        response = requests.get(url_main, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        html_main = response.text
        
        matches_events = re.findall(r'<li><a[^>]*title="\d+"[^>]*>(\d+)</a>\s*[–-]\s*(.*?)</li>', html_main)
        for year, content in matches_events:
            events.append(f"{year}: {remove_html_tags(content)}")
    except Exception as e:
        print(f"Chyba Wiki (Hlavná stránka - udalosti): {e}")
        events = ["Chyba dát."]

    if not events: events = ["Dáta nedostupné."]
    
    return events

# === FAKTY Z FACTS.JSON ===

def get_random_fact_cyclic():
    """
    Načíta fakty z facts.json, vyberie náhodný fakt, ktorý ešte nebol zobrazený.
    Používa dashboard_state.json na sledovanie zobrazených ID.
    Ak sa minú všetky fakty, reštartuje cyklus.
    """
    if not os.path.exists(FACTS_FILE):
        return None, "Súbor s faktami nenájdený."

    try:
        with open(FACTS_FILE, 'r', encoding='utf-8') as f:
            facts = json.load(f)
    except Exception as e:
        return None, f"Chyba načítania faktov: {e}"

    if not facts:
        return None, "Žiadne fakty v databáze."

    # Načítanie stavu
    state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
        except Exception as e:
            print(f"Chyba načítania stavu: {e}")

    shown_ids = set(state.get('shown_fact_ids', []))
    
    # Filtrovanie dostupných faktov
    available_facts = [f for f in facts if f['id'] not in shown_ids]

    # Ak sú všetky fakty zobrazené, reštartujeme cyklus
    if not available_facts:
        print("Všetky fakty boli zobrazené, začínam odznova.")
        shown_ids = set()
        available_facts = facts

    # Náhodný výber
    selected_fact = random.choice(available_facts)
    
    # Aktualizácia stavu
    shown_ids.add(selected_fact['id'])
    state['shown_fact_ids'] = list(shown_ids)
    
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Chyba ukladania stavu: {e}")

    return selected_fact['kategoria'], selected_fact['text']

# === MENINY ===

def scrape_meniny_kto_ma_meniny():
    url = "https://kto-ma-meniny.sk/"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        html = response.text
        now = datetime.datetime.now()
        tomorrow = now + datetime.timedelta(days=1)
        months = ["Január", "Február", "Marec", "Apríl", "Máj", "Jún", "Júl", "August", "September", "Október", "November", "December"]
        date_str_today = f"{now.day}. {months[now.month-1]}"
        date_str_tomorrow = f"{tomorrow.day}. {months[tomorrow.month-1]}"
        def get_names_for_date(date_str):
            pattern = fr">\s*{re.escape(date_str)}\s*</div>\s*<div[^>]*>.*?</div>\s*<div[^>]*>(.*?)</div>"
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match:
                names_html = match.group(1)
                names = remove_html_tags(names_html).strip()
                names = names.strip(" ,")
                return names
            return "Neznáme"
        name_today = get_names_for_date(date_str_today)
        name_tomorrow = get_names_for_date(date_str_tomorrow)
        if name_today != "Neznáme":
            return name_today, name_tomorrow
    except Exception as e:
        print(f"Chyba pri sťahovaní menín (kto-ma-meniny): {e}")
    return None, None

def scrape_meniny_zones():
    """Fallback funkcia pre stiahnutie menín zo zones.sk"""
    url = "https://www.zones.sk/kalendar-udalosti/meniny/"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        print("Skúšam sťahovať meniny zo zones.sk...")
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        html = response.text
        match = re.search(r"meniny</a> má.*?<strong>(.*?)</strong>.*?zajtra.*?<strong>(.*?)</strong>", html, re.DOTALL | re.IGNORECASE)
        
        if match:
            name_today = remove_html_tags(match.group(1)).strip()
            name_tomorrow = remove_html_tags(match.group(2)).strip()
            return name_today, name_tomorrow
        else:
            print("Regex na zones.sk nenašiel mená.")
            
    except Exception as e:
        print(f"Chyba pri sťahovaní menín (zones.sk): {e}")
    return None, None

def get_meniny_combined():
    """Hlavná funkcia na získanie menín s fallbackom."""
    today, tomorrow = scrape_meniny_kto_ma_meniny()
    if today and tomorrow and today != "Neznáme":
        return today, tomorrow
    
    today, tomorrow = scrape_meniny_zones()
    if today and tomorrow:
        return today, tomorrow
        
    return None, None

# === MEDZINÁRODNÉ DNI (Wiki + Zones) ===

def scrape_wiki_international_days(day, month):
    """Vráti dnešný medzinárodný deň z Hlavnej stránky Wikipédie (časť 'Dnes je' po meninách)."""
    url = "https://sk.wikipedia.org/wiki/Hlavn%C3%A1_str%C3%A1nka"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        html = response.text
        
        # 1. Nájdeme sekciu "Meniny má", a zoberieme celý kontext (napr. po koniec odseku)
        # Použijeme širší regex, aby sme zachytili celý odstavec
        match_block = re.search(r"(Meniny má.*?</p>)", html, re.IGNORECASE | re.DOTALL)
        
        search_text = ""
        if match_block:
            search_text = match_block.group(1)
        else:
            # Fallback: ak nenájdeme </p>, skúsime nájsť aspoň "Meniny má" a kus textu za tým
            match_start = re.search(r"Meniny má", html, re.IGNORECASE)
            if match_start:
                search_text = html[match_start.start():match_start.start()+1000]

        if search_text:
            # 2. Odstránime HTML tagy PRED hľadaním bodky. 
            # Tým zmiznú URL adresy v href="", ktoré obsahujú bodky a mýlili predchádzajúci regex.
            clean_block = remove_html_tags(search_text)
            
            # 3. Hľadáme vetu "Dnes je..." v očistenom texte
            # Hľadáme po prvú bodku alebo koniec riadku
            match_sentence = re.search(r"Dnes je\s+(.*?)(?:\.|$)", clean_block, re.IGNORECASE)
            
            if match_sentence:
                raw_day = match_sentence.group(1).strip()
                
                # Filter: Ak text začína dňom v týždni, je to dátum, nie sviatok
                days_sk = ["Pondelok", "Utorok", "Streda", "Štvrtok", "Piatok", "Sobota", "Nedeľa"]
                first_word = raw_day.split()[0].replace(',', '') if raw_day else ""
                
                if first_word.capitalize() in days_sk:
                    return []
                
                if raw_day:
                    # Niekedy je tam viac sviatkov oddelených čiarkou, to je OK
                    return [raw_day]

    except Exception as e:
        print(f"Chyba Wiki Int. days (Hlavná stránka): {e}")
        
    return []

def scrape_zones_international_days(day, month):
    """Vráti 'Medzinárodný deň Dnes' z boxu na zones.sk."""
    url = "https://www.zones.sk/kalendar-udalosti/medzinarodne-dni/"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        html = response.text
        
        # Hľadáme špeciálny box pre dnešný deň: <div id='mdni_box'> ... <h2>Názov dňa</h2>
        match = re.search(r"<div id='mdni_box'>.*?<h2>(.*?)</h2>", html, re.DOTALL | re.IGNORECASE)
        
        if match:
            content = match.group(1)
            clean_text = remove_html_tags(content).strip()
            
            # Odstránime rok (napr. " 2026") z konca textu
            clean_text = re.sub(r'\s+\d{4}$', '', clean_text)
            
            if clean_text:
                return [clean_text]
                
    except Exception as e:
        print(f"Chyba Zones Int. days (Box): {e}")
        
    return []

def get_combined_international_days(day, month):
    """Kombinuje a deduplikuje dni z Wiki a Zones. Vráti string."""
    wiki_days = scrape_wiki_international_days(day, month)
    zones_days = scrape_zones_international_days(day, month)
    
    final_list = []
    seen_normalized = set()
    
    # Pomocná funkcia na pridanie dňa ak nie je duplikát
    def add_day(d_text):
        norm = d_text.lower().strip()
        # Odstránime "medzinárodný" pre porovnanie, aby sme odhalili "Deň Zeme" vs "Medzinárodný deň Zeme"
        norm_short = norm.replace("medzinárodný ", "").replace("svetový ", "")
        
        # Skontrolujeme či sme už niečo veľmi podobné nepridali
        is_duplicate = False
        for seen in seen_normalized:
            if norm_short in seen or seen in norm_short:
                is_duplicate = True
                break
        
        if not is_duplicate:
            final_list.append(d_text)
            seen_normalized.add(norm_short)

    # Pridáme najprv Zones (priorita pre dnešný box)
    for d in zones_days:
        add_day(d)

    # Pridáme Wiki (doplnenie)
    for d in wiki_days:
        add_day(d)
        
    # Limit na 3 dni
    if len(final_list) > 3:
        final_list = final_list[:3]
        
    return ", ".join(final_list)

def get_next_season_info():
    now = datetime.datetime.now()
    year = now.year
    
    # Definícia udalostí (orientačné dátumy)
    # Jar: 20.3., Leto: 21.6., Jeseň: 23.9., Zima: 21.12.
    events = [
        (datetime.datetime(year, 3, 20), "Prvý jarný deň", "rovnodennosť"),
        (datetime.datetime(year, 6, 21), "Prvý letný deň", "slnovrat"),
        (datetime.datetime(year, 9, 23), "Prvý jesenný deň", "rovnodennosť"),
        (datetime.datetime(year, 12, 21), "Prvý zimný deň", "slnovrat")
    ]
    
    next_event = None
    for date_obj, name, type_name in events:
        # Porovnanie iba dátumov
        if date_obj.date() > now.date():
            next_event = (date_obj, name, type_name)
            break
            
    # Ak už prešli všetky tento rok, zoberieme jar budúceho roka
    if next_event is None:
        next_event = (datetime.datetime(year + 1, 3, 20), "Prvý jarný deň", "rovnodennosť")
        
    evt_date, evt_name, evt_type = next_event
    days_left = (evt_date.date() - now.date()).days
    
    # Skloňovanie slova "deň"
    if days_left == 1:
        days_str = "deň"
    elif 2 <= days_left <= 4:
        days_str = "dni"
    else:
        days_str = "dní"
        
    # Vrátime rozdelené hodnoty pre 3-riadkový výpis
    return evt_name, f"({evt_type})", f"o {days_left} {days_str}"

def get_next_event_cyclic(events, key_suffix="otd"):
    if not events: return "Žiadne dáta."
    today_str = datetime.date.today().isoformat()
    current_index = 0
    state = {}
    index_key = f"index_{key_suffix}"
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                if state.get('date') == today_str:
                    current_index = state.get(index_key, 0)
                else:
                    state['date'] = today_str
                    state['index_otd'] = 0
                    current_index = 0
        except Exception as e: pass
    
    safe_index = current_index % len(events)
    selected_event = events[safe_index]
    
    state['date'] = today_str
    state[index_key] = current_index + 1
    try:
        with open(STATE_FILE, 'w') as f: json.dump(state, f)
    except: pass
    return selected_event

def get_slovak_date():
    try:
        os.environ['TZ'] = 'Europe/Bratislava'
        time.tzset()
    except AttributeError:
        pass

    now = datetime.datetime.now()
    days = ["Pondelok", "Utorok", "Streda", "Štvrtok", "Piatok", "Sobota", "Nedeľa"]
    months = ["Január", "Február", "Marec", "Apríl", "Máj", "Jún", "Júl", "August", "September", "Október", "November", "December"]
    date_str = f"{days[now.weekday()]}, {now.day}. {months[now.month-1]} {now.year}"
    return now, date_str

def draw_text_mixed(draw, x_start, y_start, max_width, year_text, body_text, fonts, simulate=False):
    x = x_start
    y = y_start
    line_height = 20
    year_font = fonts['bold_small']
    body_font = fonts['small']
    if year_text:
        if not simulate:
            draw.text((x, y), year_text, font=year_font, fill=TEXT_COLOR)
        year_width = fonts['bold_small'].getlength(year_text) # Using getlength for simulate/draw
        x += year_width + 6
    words = body_text.split()
    space_width = fonts['small'].getlength(" ")
    for word in words:
        word_width = fonts['small'].getlength(word)
        if x + word_width > x_start + max_width:
            x = x_start
            y += line_height
            if y > HEIGHT - 50: return y 
        if not simulate:
            draw.text((x, y), word, font=body_font, fill=TEXT_COLOR)
        x += word_width + space_width
    return y + line_height 

def create_dashboard():
    img = Image.new(MODE, (WIDTH, HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)
    fonts = get_fonts()
    now, date_str = get_slovak_date()
    
    meniny_today, meniny_tomorrow = get_meniny_combined()
    
    # Wiki (iba events)
    all_events = scrape_wikipedia_events()
    todays_event = get_next_event_cyclic(all_events, key_suffix="otd")
    
    # FAKTY z facts.json
    fact_category, fact_text = get_random_fact_cyclic()
    
    # KOMBINOVANÉ MEDZINÁRODNÉ DNI (Wiki + Zones)
    intl_day_text = get_combined_international_days(now.day, now.month)
    
    weather_list, sunrise, sunset = scrape_weather_detailed()
    tv_program_list = scrape_tv_program()
    
    last_updated = now.strftime("%H:%M")

    # A. HLAVIČKA
    header_height = 64
    draw.rectangle([(0, 0), (WIDTH, header_height)], fill=TEXT_COLOR)
    draw.text((20, 15), date_str, font=fonts['large'], fill=BACKGROUND_COLOR)
    
    if sunrise and sunset:
        font_sun = fonts['small']
        text_rise = f"Východ: {sunrise}"
        text_set = f"Západ: {sunset}"
        w_rise = draw.textlength(text_rise, font=font_sun)
        w_set = draw.textlength(text_set, font=font_sun)
        text_x_start = WIDTH - max(w_rise, w_set) - 20
        draw.text((WIDTH - w_rise - 20, 12), text_rise, font=font_sun, fill=BACKGROUND_COLOR)
        draw.text((WIDTH - w_set - 20, 34), text_set, font=font_sun, fill=BACKGROUND_COLOR)
        moon_radius = 18
        moon_center_x = text_x_start - moon_radius - 20 
        moon_center_y = header_height // 2
        draw_moon_phase(draw, moon_center_x, moon_center_y, moon_radius, BACKGROUND_COLOR)

    # B. ĽAVÝ STĹPEC (Meniny + Sviatky + Počasie)
    left_col_x = 20
    col_y_start = header_height + 15
    
    label_meniny = "Meniny má "
    draw.text((left_col_x, col_y_start), label_meniny, font=fonts['regular'], fill=TEXT_COLOR)
    w_label = draw.textlength(label_meniny, font=fonts['regular'])
    
    y_names = col_y_start 
    
    if meniny_today and meniny_tomorrow:
        name_text = meniny_today + ","
        max_name_x = 315
        # POSUN: Mená posunuté o 3px doprava
        current_x = left_col_x + w_label + 3
        available_w = max_name_x - current_x
        
        font_candidates = [
            (fonts['value_22'], -3),     
            (fonts['value_20'], -1),     
            (fonts['value_18'], 0),      
            (fonts['value_16'], 2),      
            (fonts['value_14'], 4)       
        ]
        
        selected_font = font_candidates[-1][0]
        selected_offset = font_candidates[-1][1]
        
        for font, offset in font_candidates:
            w_text = draw.textlength(name_text, font=font)
            if w_text <= available_w:
                selected_font = font
                selected_offset = offset
                break

        draw.text((current_x, y_names + selected_offset), name_text, font=selected_font, fill=TEXT_COLOR)
        
        y_tomorrow = y_names + 25
        label_tomorrow = "zajtra "
        draw.text((left_col_x, y_tomorrow), label_tomorrow, font=fonts['small'], fill=TEXT_COLOR)
        
        w_label_tom = draw.textlength(label_tomorrow, font=fonts['small'])
        # POSUN: Meno zajtra posunuté o 3px doprava od slova "zajtra"
        draw.text((left_col_x + w_label_tom + 3, y_tomorrow), meniny_tomorrow, font=fonts['small'], fill=TEXT_COLOR)
        
    else:
        draw.text((left_col_x, y_names + 25), "Dáta nedostupné", font=fonts['value'], fill=TEXT_COLOR)
    
    # SVIATKY / SEZÓNY
    
    left_padding = 20
    right_limit_x = 320 - left_padding # 300
    center_x_left_col = (left_padding + right_limit_x) // 2 # 160
    
    # Približné hranice priestoru pre info
    info_area_top = 135
    info_area_bottom = WEATHER_FIXED_Y
    info_area_height = info_area_bottom - info_area_top
    
    # Ak máme medzinárodný deň (alebo viac dní), zobrazíme ich
    if intl_day_text:
        # CENTROVANÉ ZOBRAZENIE MEDZINÁRODNÉHO DŇA (alebo viacerých dní)
        text_info = intl_day_text
        
        # Ak je text dlhý, použijeme menšie písmo, inak regular
        is_long = len(text_info) > 40
        selected_font = fonts['small'] if is_long else fonts['regular']
        line_spacing = 18 if is_long else 22
        
        # Znížená šírka pre zalamovanie
        max_width_chars = 35 if is_long else 30 
        
        wrapped_info = textwrap.wrap(text_info, width=max_width_chars)
        
        # Vypočítame celkovú výšku textového bloku
        total_text_height = len(wrapped_info) * line_spacing
        
        # Vypočítame štartovaciu Y pozíciu pre vertikálne centrovanie
        start_y_centered = info_area_top + (info_area_height - total_text_height) // 2
        
        current_y_info = start_y_centered
        for line in wrapped_info:
            w_line = draw.textlength(line, font=selected_font)
            draw.text((center_x_left_col - w_line/2, current_y_info), line, font=selected_font, fill=TEXT_COLOR)
            current_y_info += line_spacing

    else:
        # FALLBACK: Ak nie je žiaden medzinárodný deň, zobrazíme sezónu (jar/leto...)
        line1, line2, line3 = get_next_season_info()
        
        block_height = 66
        start_y_season = info_area_top + (info_area_height - block_height) // 2
        
        current_y_season = start_y_season
        
        # Riadok 1
        w1 = draw.textlength(line1, font=fonts['regular'])
        draw.text((center_x_left_col - w1/2, current_y_season), line1, font=fonts['regular'], fill=TEXT_COLOR)
        current_y_season += 22
        
        # Riadok 2
        w2 = draw.textlength(line2, font=fonts['small'])
        draw.text((center_x_left_col - w2/2, current_y_season), line2, font=fonts['small'], fill=TEXT_COLOR)
        current_y_season += 20
        
        # Riadok 3
        w3 = draw.textlength(line3, font=fonts['regular'])
        draw.text((center_x_left_col - w3/2, current_y_season), line3, font=fonts['regular'], fill=TEXT_COLOR)

    # POČASIE - FIXNÁ POZÍCIA
    current_y = WEATHER_FIXED_Y
    draw.text((left_col_x, current_y), "Predpoveď počasia", font=fonts['regular'], fill=TEXT_COLOR)
    current_y += 30
    
    if weather_list:
        row_height = 35
        
        # --- ZISTENIE STAVU PRE ZAROVNANIE ---
        # Zistíme, či sa v noci vyskytuje mínusová teplota
        has_minus_night = False
        max_night_width = 0
        for d in weather_list:
            if '-' in str(d['min']):
                has_minus_night = True
            # Vypočítame maximálnu šírku textu pre min teploty (potrebné pre zarovnanie doprava)
            w = fonts['bold_small'].getlength(str(d['min']))
            if w > max_night_width:
                max_night_width = w
                
        for day_data in weather_list:
            if current_y > HEIGHT - 30: break
            draw_weather_icon(draw, left_col_x, current_y, 24, day_data['desc'])
            text_x = left_col_x + 35
            draw.text((text_x, current_y), day_data['day'], font=fonts['bold_small'], fill=TEXT_COLOR)
            
            cleaned_desc = shorten_weather_desc(day_data['desc'])
            draw.text((text_x, current_y + 19), cleaned_desc, font=fonts['tiny'], fill=TEXT_COLOR)
            
            # --- ÚPRAVA ZAROVNANIA TEPLÔT ---
            # Definovanie stredovej osi pre zarovnanie
            sep_x_center = text_x + 95
            
            gap = 12 
            
            max_t_str = str(day_data['max'])
            min_t_str = str(day_data['min'])
            
            w_max = draw.textlength(max_t_str, font=fonts['bold_small'])
            w_min = draw.textlength(min_t_str, font=fonts['bold_small'])
            
            # 1. Max teplota: Vždy zarovnaná DOPRAVA k virtuálnemu stredu
            max_anchor_x = sep_x_center - gap
            draw.text((max_anchor_x - w_max, current_y), max_t_str, font=fonts['bold_small'], fill=TEXT_COLOR)
            
            # 3. Min teplota: DYNAMICKÉ ZAROVNANIE
            min_start_x = sep_x_center + gap
            
            if not has_minus_night:
                # PRÍPAD A: Všetky teploty sú kladné
                draw.text((min_start_x, current_y), min_t_str, font=fonts['bold_small'], fill=TEXT_COLOR)
            else:
                # PRÍPAD B: Existuje mínusová teplota
                min_anchor_right = min_start_x + max_night_width
                draw.text((min_anchor_right - w_min, current_y), min_t_str, font=fonts['bold_small'], fill=TEXT_COLOR)

            if day_data['wind']:
                 draw.text((text_x + 145, current_y + 2), day_data['wind'], font=fonts['tiny'], fill=TEXT_COLOR)
            if day_data['prob'] and day_data['prob'] != "0%":
                 draw.text((text_x + 210, current_y + 2), day_data['prob'], font=fonts['tiny'], fill=TEXT_COLOR)
            current_y += row_height
    else:
        draw.text((left_col_x, current_y), "Dáta počasia nedostupné", font=fonts['small'], fill=TEXT_COLOR)

    # C. ODDELOVACIA ČIARA
    draw.line([(320, header_height + 20), (320, HEIGHT - 20)], fill=TEXT_COLOR, width=3)

    # D. PRAVÝ STĹPEC
    right_col_x = 350
    max_text_width = WIDTH - right_col_x - 20 
    
    draw.text((right_col_x, col_y_start), "V tento deň...", font=fonts['regular'], fill=TEXT_COLOR)
    right_y = col_y_start + 25
    
    parts = todays_event.split(':', 1)
    if len(parts) == 2:
        year_str = parts[0] + ":"
        text_str = parts[1].strip()
        right_y = draw_text_mixed(draw, right_col_x, right_y, max_text_width, year_str, text_str, fonts)
    else:
        right_y = draw_text_mixed(draw, right_col_x, right_y, max_text_width, "", todays_event, fonts)

    # NOVÁ SEKCIA: FAKTY (Vedeli ste že...) - nahrádza Word of the Day
    right_y += 15
    
    # Kategória spojená s nadpisom
    label_facts = "Vedeli ste že...?"
    if fact_category:
        label_facts += f" ({fact_category})"
        
    draw.text((right_col_x, right_y), label_facts, font=fonts['regular'], fill=TEXT_COLOR)
    right_y += 25
    
    if fact_text:
        # Zobrazenie textu faktu
        # Zvýšená šírka pre zalamovanie (pôvodne 50 -> teraz 60)
        # Font 'small' je Arial 15. Max šírka stĺpca je cca 430px. 
        # Priemerne 1 znak = 7-8px. 60 znakov * 7.5 = 450px (trochu na tesno, ale ok)
        wrapped_fact = textwrap.wrap(fact_text, width=60) 
        
        for line in wrapped_fact:
            # Kontrola, či neprekračujeme do TV programu
            if right_y > TV_PROGRAM_FIXED_Y - 10:
                break
            draw.text((right_col_x, right_y), line, font=fonts['small'], fill=TEXT_COLOR)
            right_y += 18
            
    else:
         draw.text((right_col_x, right_y), "Dáta faktov nedostupné", font=fonts['small'], fill=TEXT_COLOR)
         right_y += 45

    # TV PROGRAM - FIXNÁ POZÍCIA
    tv_start_y = TV_PROGRAM_FIXED_Y
    
    # Kreslíme vždy (ak sa zmestí na obrazovku, čo by mal)
    if tv_start_y < HEIGHT - 20:
        draw.text((right_col_x, tv_start_y), "TV Program:", font=fonts['regular'], fill=TEXT_COLOR)
        tv_y = tv_start_y + 25
        for item in tv_program_list:
            if tv_y > HEIGHT - 35: break # Ochrana proti pretečeniu dole
            draw.text((right_col_x, tv_y), item['station'], font=fonts['small'], fill=TEXT_COLOR)
            draw.text((right_col_x + 80, tv_y), item['time'], font=fonts['small'], fill=TEXT_COLOR)
            title = item['title']
            if len(title) > 35: title = title[:32] + "..."
            draw.text((right_col_x + 135, tv_y), title, font=fonts['small'], fill=TEXT_COLOR)
            tv_y += 18

    # E. PÄTIČKA
    update_text = f"Aktualizované: {last_updated}"
    w_update = draw.textlength(update_text, font=fonts['small'])
    draw.text((WIDTH - w_update - 20, HEIGHT - 30), update_text, font=fonts['small'], fill=TEXT_COLOR)

    return img

def main():
    print("Sťahujem dáta a generujem dashboard...")
    image = create_dashboard()
    output_filename = "dashboard_output.bmp"
    image.save(output_filename)
    print(f"Hotovo. Obrázok uložený ako {output_filename}")
    image.show()

if __name__ == "__main__":

    main()
