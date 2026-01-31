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
STATE_FILE = "dashboard_state.json" 

# Súradnice Šamorín
LAT = 48.0282
LON = 17.3097

def get_fonts():
    fonts = {}
    try:
        font_path_bold = "arialbd.ttf"
        font_path_reg = "arial.ttf"
        
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
        
        fonts['label'] = ImageFont.truetype(font_path_reg, 14)
        fonts['value'] = ImageFont.truetype(font_path_bold, 22)
        fonts['value_reg'] = ImageFont.truetype(font_path_reg, 22)
        
    except IOError:
        print("POZOR: Systémové fonty sa nenašli, používam predvolený.")
        default = ImageFont.load_default()
        fonts = {k: default for k in ['huge', 'large', 'medium', 'regular', 'small', 'tiny', 'bold_small', 'bold_tiny', 'label', 'value', 'value_reg']}
    
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

def scrape_tv_program():
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
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        html_content = response.text
        pattern = r"program_desc\[\d+\]\s*=\s*\{(.*?)\}"
        matches = re.findall(pattern, html_content, re.DOTALL)
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
            else:
                results.append({"station": target['display_name'], "time": "--:--", "title": "Dáta nedostupné"})
    except Exception as e:
        print(f"Chyba pri sťahovaní TV programu: {e}")
        return []
    return results

def scrape_wikipedia_events_facts():
    """
    Stiahne udalosti z Hlavnej stránky a zaujímavosti z NÁHODNÉHO portálu.
    """
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    events = []
    facts = []

    # 1. UDALOSTI (V tento deň) - z Hlavnej stránky
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

    # 2. ZAUJÍMAVOSTI (Vedeli ste, že) - z náhodného portálu
    portals = [
        "https://sk.wikipedia.org/wiki/Port%C3%A1l:Astron%C3%B3mia/Zauj%C3%ADmavosti",
        "https://sk.wikipedia.org/wiki/Port%C3%A1l:Biol%C3%B3gia/arch%C3%ADv_zauj%C3%ADmavost%C3%AD",
        "https://sk.wikipedia.org/wiki/Port%C3%A1l:Kozmonautika/Zauj%C3%ADmavosti",
    ]
    
    # Skúsime až 5 rôznych portálov
    MAX_RETRIES = 5
    
    for attempt in range(MAX_RETRIES):
        selected_portal_url = random.choice(portals)
        print(f"Pokus {attempt+1}/{MAX_RETRIES}: Sťahujem zaujímavosti z: {selected_portal_url}")
        
        try:
            response_portal = requests.get(selected_portal_url, headers=headers, timeout=8)
            response_portal.encoding = 'utf-8'
            html_portal = response_portal.text
            
            # NOVÁ STRATÉGIA:
            # Hľadáme všetky <li> položky, aj keď majú atribúty (preto <li[^>]*>)
            raw_items = re.findall(r'<li[^>]*>(.*?)</li>', html_portal, re.DOTALL)
            temp_facts = []
            
            for item in raw_items:
                clean_text = remove_html_tags(item).strip()
                
                # Heuristika pre "Vedeli ste, že":
                is_fact = False
                if clean_text.endswith('?') and len(clean_text) > 20:
                    is_fact = True
                elif (clean_text.startswith('...') or clean_text.startswith('…')) and len(clean_text) > 20:
                    is_fact = True
                
                if is_fact:
                    # Čistenie formátovania
                    clean_text = re.sub(r'^[\s\.\…]+', '', clean_text) # Odstráni počiatočné bodky
                    clean_text = clean_text.strip()
                    if len(clean_text) > 0:
                        clean_text = clean_text[0].upper() + clean_text[1:]
                    if not clean_text.endswith('?'):
                        clean_text += "?"
                    
                    # Filtrovanie dĺžky (aby sa zmestilo na displej)
                    if len(clean_text) < 360:
                        temp_facts.append(clean_text)

            if temp_facts:
                facts = temp_facts
                break # Úspech, končíme hľadanie
            else:
                print(f"Na {selected_portal_url} sa nenašli žiadne položky vyzerajúce ako fakty.")
            
        except Exception as e:
            print(f"Chyba pri sťahovaní z {selected_portal_url}: {e}")
            continue

    if not events: events = ["Dáta nedostupné."]
    
    # ZÁCHRANNÁ BRZDA (Fallback):
    if not facts or facts == ["Dáta nedostupné."]:
        print("POZOR: Nepodarilo sa stiahnuť fakty zo žiadneho portálu. Používam záložné dáta.")
        facts = [
            "Slnko tvorí 99,86 % hmotnosti celej Slnečnej sústavy?",
            "Venuša sa točí okolo svojej osi v opačnom smere ako ostatné planéty?",
            "Med je jediná potravina, ktorá sa pri správnom skladovaní nikdy nepokazí?",
            "Chobotnice majú tri srdcia a modrú krv?",
            "Banány sú z botanického hľadiska bobule, ale jahody nie?",
            "Ľudské oko dokáže rozoznať asi 10 miliónov rôznych farieb?",
            "Voda je jediná látka, ktorá sa v prírode vyskytuje v troch skupenstvách?",
            "Najdlhšia zaznamenaná doba letu sliepky je 13 sekúnd?"
        ]
    
    return events, facts

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
        print(f"Chyba pri sťahovaní menín: {e}")
    return None, None

def scrape_international_day(day, month):
    url = "https://sk.wikipedia.org/wiki/Zoznam_medzin%C3%A1rodn%C3%BDch_dn%C3%AD_a_sviatkov"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    months = ["január", "február", "marec", "apríl", "máj", "jún", "júl", "august", "september", "október", "november", "december"]
    search_date = f"{day}. {months[month - 1]}"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        match = re.search(fr'<li[^>]*>\s*<a[^>]*title="{re.escape(search_date)}"[^>]*>.*?</a>(.*?)(?:</li>|<br)', response.text, re.IGNORECASE | re.DOTALL)
        if match:
            return re.sub(r'^[\s–\-—:]+', '', remove_html_tags(match.group(1))).strip()
    except Exception: pass
    return ""

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
                    state['index_dyk'] = 0
                    current_index = 0
        except Exception as e: pass
    
    safe_index = current_index % len(events)
    selected_event = events[safe_index]
    
    # Pre zaujímavosti (dyk) chceme posunúť index, ale keďže portál sa mení náhodne, 
    # zoznam 'events' (v tomto prípade facts) je iný pri každom spustení.
    # To nevadí, modulo to ošetrí.
    state['date'] = today_str
    state[index_key] = current_index + 1
    try:
        with open(STATE_FILE, 'w') as f: json.dump(state, f)
    except: pass
    return selected_event

def get_slovak_date():
    # Nastavíme časovú zónu na Bratislavu (funguje na Linux/GitHub serveroch)
    try:
        os.environ['TZ'] = 'Europe/Bratislava'
        time.tzset()
    except AttributeError:
        # Na Windows (lokálne) time.tzset neexistuje, ale tam je čas zvyčajne správny
        pass

    now = datetime.datetime.now()
    days = ["Pondelok", "Utorok", "Streda", "Štvrtok", "Piatok", "Sobota", "Nedeľa"]
    months = ["Január", "Február", "Marec", "Apríl", "Máj", "Jún", "Júl", "August", "September", "Október", "November", "December"]
    date_str = f"{days[now.weekday()]}, {now.day}. {months[now.month-1]} {now.year}"
    return now, date_str

def draw_text_mixed(draw, x_start, y_start, max_width, year_text, body_text, fonts):
    x = x_start
    y = y_start
    line_height = 20
    year_font = fonts['bold_small']
    body_font = fonts['small']
    if year_text:
        draw.text((x, y), year_text, font=year_font, fill=TEXT_COLOR)
        year_width = draw.textlength(year_text, font=year_font)
        x += year_width + 6
    words = body_text.split()
    space_width = draw.textlength(" ", font=body_font)
    for word in words:
        word_width = draw.textlength(word, font=body_font)
        if x + word_width > x_start + max_width:
            x = x_start
            y += line_height
            if y > HEIGHT - 50: return y 
        draw.text((x, y), word, font=body_font, fill=TEXT_COLOR)
        x += word_width + space_width
    return y + line_height 

def create_dashboard():
    img = Image.new(MODE, (WIDTH, HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)
    fonts = get_fonts()
    now, date_str = get_slovak_date()
    
    meniny_today, meniny_tomorrow = scrape_meniny_kto_ma_meniny()
    
    # Wiki: events (Udalosti) z Hlavnej stránky, facts (Zaujímavosti) z náhodného portálu
    all_events, all_facts = scrape_wikipedia_events_facts()
    
    intl_day = scrape_international_day(now.day, now.month)
    weather_list, sunrise, sunset = scrape_weather_detailed()
    tv_program_list = scrape_tv_program()
    
    todays_event = get_next_event_cyclic(all_events, key_suffix="otd")
    todays_fact = get_next_event_cyclic(all_facts, key_suffix="dyk")
    last_updated = now.strftime("%H:%M:%S")

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
    draw.text((left_col_x, col_y_start), "Dnes má meniny:", font=fonts['regular'], fill=TEXT_COLOR)
    
    y_names = col_y_start + 25
    if meniny_today and meniny_tomorrow:
        draw.text((left_col_x, y_names), meniny_today, font=fonts['value'], fill=TEXT_COLOR)
        w1 = draw.textlength(meniny_today, font=fonts['value'])
        txt_spojka = ", zajtra "
        draw.text((left_col_x + w1, y_names + 3), txt_spojka, font=fonts['regular'], fill=TEXT_COLOR)
        w2 = draw.textlength(txt_spojka, font=fonts['regular'])
        draw.text((left_col_x + w1 + w2, y_names), meniny_tomorrow, font=fonts['value'], fill=TEXT_COLOR)
    else:
        draw.text((left_col_x, y_names), "Dáta nedostupné", font=fonts['value'], fill=TEXT_COLOR)
    
    current_y = col_y_start + 90
    if intl_day:
        draw.text((left_col_x, current_y), "Medzinárodný deň:", font=fonts['regular'], fill=TEXT_COLOR)
        wrapped_intl = textwrap.wrap(intl_day, width=36)
        current_y += 25
        for line in wrapped_intl:
            draw.text((left_col_x, current_y), line, font=fonts['small'], fill=TEXT_COLOR)
            current_y += 18
    else:
        current_y += 10 
    
    current_y = max(current_y + 35, 220)
    draw.text((left_col_x, current_y), "Predpoveď (Šamorín):", font=fonts['regular'], fill=TEXT_COLOR)
    current_y += 30
    
    if weather_list:
        row_height = 35
        for day_data in weather_list:
            if current_y > HEIGHT - 30: break
            draw_weather_icon(draw, left_col_x, current_y, 24, day_data['desc'])
            text_x = left_col_x + 35
            draw.text((text_x, current_y), day_data['day'], font=fonts['bold_small'], fill=TEXT_COLOR)
            draw.text((text_x, current_y + 19), day_data['desc'], font=fonts['tiny'], fill=TEXT_COLOR)
            temp_vals = f"{day_data['max']} | {day_data['min']}"
            draw.text((text_x + 75, current_y), temp_vals, font=fonts['bold_small'], fill=TEXT_COLOR)
            if day_data['wind']:
                 draw.text((text_x + 135, current_y), day_data['wind'], font=fonts['tiny'], fill=TEXT_COLOR)
            if day_data['prob'] and day_data['prob'] != "0%":
                 draw.text((text_x + 195, current_y), day_data['prob'], font=fonts['tiny'], fill=TEXT_COLOR)
            current_y += row_height
    else:
        draw.text((left_col_x, current_y), "Dáta počasia nedostupné", font=fonts['small'], fill=TEXT_COLOR)

    # C. ODDELOVACIA ČIARA
    draw.line([(320, header_height + 20), (320, HEIGHT - 20)], fill=TEXT_COLOR, width=3)

    # D. PRAVÝ STĹPEC
    right_col_x = 350
    max_text_width = WIDTH - right_col_x - 20 
    
    draw.text((right_col_x, col_y_start), "V tento deň:", font=fonts['regular'], fill=TEXT_COLOR)
    right_y = col_y_start + 35
    
    parts = todays_event.split(':', 1)
    if len(parts) == 2:
        year_str = parts[0] + ":"
        text_str = parts[1].strip()
        right_y = draw_text_mixed(draw, right_col_x, right_y, max_text_width, year_str, text_str, fonts)
    else:
        right_y = draw_text_mixed(draw, right_col_x, right_y, max_text_width, "", todays_event, fonts)

    # ZMENA: "Vedeli ste, že" teraz zobrazuje aj zdroj (napr. Astronómia)
    right_y += 15
    available_space = (HEIGHT - 40) - right_y - (len(tv_program_list) * 20 + 40)
    if available_space > 60:
        draw.text((right_col_x, right_y), "Vedeli ste, že...?", font=fonts['regular'], fill=TEXT_COLOR)
        right_y += 25
        right_y = draw_text_mixed(draw, right_col_x, right_y, max_text_width, "", todays_fact, fonts)

    tv_height = len(tv_program_list) * 20 + 40
    tv_start_y = max(right_y + 10, HEIGHT - 40 - tv_height)
    
    if tv_start_y < HEIGHT - 40:
        draw.text((right_col_x, tv_start_y), "TV Program (Dnes):", font=fonts['regular'], fill=TEXT_COLOR)
        tv_y = tv_start_y + 25
        for item in tv_program_list:
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
