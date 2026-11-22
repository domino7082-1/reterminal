import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

# --- KONFIGURÁCIA ---
WIDTH, HEIGHT = 800, 480
OUTPUT_FILE = "world_news_output.bmp"
TZ_LOCAL = ZoneInfo("Europe/Bratislava")
NEWSPAPER_TITLE = "SVETOVÝ DENNÍK"

# Zobrazovať prísne len správy vydané v aktuálny deň
ONLY_TODAY = True

# Súradnice pre počasie (Šamorín)
WEATHER_CITY = "Šamorín"
WEATHER_LAT = 48.0279
WEATHER_LON = 17.3106

# Svetové časy v hlavičke (Názov, IANA časové pásmo)
WORLD_CLOCKS = [
    ("BRATISLAVA", "Europe/Bratislava"),
    ("LONDÝN", "Europe/London"),
    ("NEW YORK", "America/New_York"),
    ("TOKIO", "Asia/Tokyo"),
]

# 5 pevných pozícií: (Hlavná kategória, Náhradná kategória)
# Pozícia 0 = hlavná správa hore, pozície 1..4 = mriežka 2×2
SLOTS = [
    {
        "primary": ("SVET", "svet"),
        "fallback": ("DOMOV", "domov"),
    },
    {
        "primary": ("EKONOMIKA A TRHY", "ekonomika"),
        "fallback": ("ENERGIE A BÝVANIE", "energie_byvanie"),
    },
    {
        "primary": ("AI A TECH", "ai_tech"),
        "fallback": ("GADGETY A IT", "gadgety_it"),
    },
    {
        "primary": ("VEDA A VESMÍR", "veda_vesmir"),
        "fallback": ("ZDRAVIE A PRÍRODA", "zdravie_priroda"),
    },
    {
        "primary": ("ŠPORT", "sport"),
        "fallback": ("AUTO A MOBILITA", "auto"),
    },
]

# RSS zdroje: (Krátky názov zdroja, Názov vydavateľa do pätičky, Kategórie zdroja, URL)
FEEDS = [
    # SVET
    ("SME Svet", "SME", ("svet",), "https://svet.sme.sk/rss"),
    ("Denník N", "Denník N", ("svet",), "https://dennikn.sk/svet/feed/"),
    ("Aktuality", "Aktuality", ("svet",), "https://www.aktuality.sk/rss/zahranicne/"),
    ("TASR", "TASR", ("svet",), "https://www.teraz.sk/rss/zahranicie.rss"),
    # DOMOV
    ("SME Domov", "SME", ("domov",), "https://domov.sme.sk/rss"),
    ("Denník N", "Denník N", ("domov",), "https://dennikn.sk/slovensko/feed/"),
    ("Aktuality", "Aktuality", ("domov",), "https://www.aktuality.sk/rss/domace/"),
    ("TASR", "TASR", ("domov",), "https://www.teraz.sk/rss/slovensko.rss"),
    # EKONOMIKA A TRHY
    ("SME Index", "SME", ("ekonomika",), "https://index.sme.sk/rss"),
    ("Denník E", "Denník N", ("ekonomika",), "https://e.dennikn.sk/feed/"),
    ("Aktuality", "Aktuality", ("ekonomika",), "https://www.aktuality.sk/rss/ekonomika/"),
    ("TASR", "TASR", ("ekonomika",), "https://www.teraz.sk/rss/ekonomika.rss"),
    ("Pravda", "Pravda", ("ekonomika",), "https://ekonomika.pravda.sk/rss/xml/"),
    # TECH / AI / GADGETY
    ("Živé.sk", "Živé.sk", ("tech",), "https://zive.aktuality.sk/rss/najnovsie/"),
    ("SME Tech", "SME", ("tech",), "https://tech.sme.sk/rss"),
    ("TouchIT", "TouchIT", ("tech",), "https://touchit.sk/feed/"),
    # VEDA A VESMÍR
    ("Denník N", "Denník N", ("veda",), "https://dennikn.sk/veda/feed/"),
    ("Pravda Veda", "Pravda", ("veda",), "https://veda.pravda.sk/rss/xml/"),
    # ZDRAVIE A PRÍRODA
    ("SME Primár", "SME", ("zdravie",), "https://primar.sme.sk/rss"),
    ("Pravda Zdravie", "Pravda", ("zdravie",), "https://zdravie.pravda.sk/rss/xml/"),
    # ŠPORT
    ("Šport.sk", "Šport.sk", ("sport",), "https://sport.aktuality.sk/rss/"),
    ("Denník N", "Denník N", ("sport",), "https://dennikn.sk/sport/feed/"),
    ("TASR Šport", "TASR", ("sport",), "https://www.teraz.sk/rss/sport.rss"),
    ("Pravda Šport", "Pravda", ("sport",), "https://sport.pravda.sk/rss/xml/"),
    # AUTO A MOBILITA
    ("SME Auto", "SME", ("auto",), "https://auto.sme.sk/rss"),
    ("Pravda Auto", "Pravda", ("auto",), "https://auto.pravda.sk/rss/xml/"),
]

# Kľúčové slová pre jemné triedenie podkategórií (podporujú celé slová cez regex aj korene slov)
KEYWORDS = {
    "energie_byvanie": [
        "energi", "elektrin", "plyn", "tepl", "bývan", "nehnuteľn", "hypoték",
        "realit", "nájom", "fotovoltik", "solár", "jadrov", "elektráreň",
        "zateplen", "stavebn", "byty", "bytov", "úrokov", "teplárn",
    ],
    "ai_tech": [
        r"\bai\b", "umelá inteligencia", "umelej inteligenc", "openai", "chatgpt",
        "gemini", "claude", "anthropic", "nvidia", "čip", "procesor", "kvantov",
        "kyber", "hacker", "robot", "algoritm", "deepseek", "llm", "neurónov",
        "dátov", "cloud", "microsoft", "google", "apple", "meta", "amazon",
    ],
    "gadgety_it": [
        "smartfón", "mobil", "iphone", "samsung", "xiaomi", "android", "windows",
        "notebook", "laptop", "tablet", "aplikáci", "operátor", "orange", "telekom",
        r"\bo2\b", "4ka", "internet", "wi-fi", "aktualizáci", "recenzi", "konzol",
        "slúchadl", "hodink", "fotoaparát", "displej",
    ],
    "veda_vesmir": [
        "vesmír", "nasa", "spacex", "esa", "raket", "mesiac", "mars", "satelit",
        "astronaut", "kozmonaut", "planét", "hviezd", "galaxi", "teleskop",
        "výskum", "vedci", "vedeck", "štúdi", "fyzik", "archeológ", "fosíli",
        "objav", "laboratór", "fúzi", "dna", "genetik",
    ],
    "zdravie_priroda": [
        "zdravi", "lekár", "nemocnic", "liek", "vakcín", "vírus", "rakovin",
        "chorob", "spánok", "mozog", "srdc", "imunit", "vitamín", "pacient",
        "prírod", "klím", "ekológi", "zvierat", "živočích", "les", "oceán",
        "zemetrasen", "sopk", "medveď", "chránen", "ovzduš",
    ],
    "auto": [
        "automobil", "elektromobil", "škoda", "volkswagen", "bmw", "mercedes",
        "audi", "hyundai", "kia", "tesla", "volvo", "peugeot", "toyota", "motor",
        "diaľnic", "doprav", "vlak", "železnic", "vodič", "nabíjačk", "emisi",
        "pneumatik", "stk", "mýto", "cestná",
    ],
}

DAYS_SK = ["PONDELOK", "UTOROK", "STREDA", "ŠTVRTOK", "PIATOK", "SOBOTA", "NEDEĽA"]

# Slovenský preklad WMO kódov počasia (Open-Meteo)
WMO_SK = {
    0: "Jasno",
    1: "Skoro jasno",
    2: "Polooblačno",
    3: "Zamračené",
    45: "Hmla",
    48: "Hmla",
    51: "Mrholenie",
    53: "Mrholenie",
    55: "Mrholenie",
    56: "Mrznúce mrholenie",
    57: "Mrznúce mrholenie",
    61: "Slabý dážď",
    63: "Dážď",
    65: "Silný dážď",
    66: "Mrznúci dážď",
    67: "Mrznúci dážď",
    71: "Slabé sneženie",
    73: "Sneženie",
    75: "Silné sneženie",
    77: "Snehové zrná",
    80: "Prehánky",
    81: "Prehánky",
    82: "Silné prehánky",
    85: "Snehové prehánky",
    86: "Snehové prehánky",
    95: "Búrka",
    96: "Búrka s krúpami",
    99: "Búrka s krúpami",
}


def load_font(candidates, size):
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def clean_text(raw):
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s*(Čítajte viac|Viac sa dočítate|Celý článok).*$", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def parse_date(date_str):
    if not date_str:
        return None
    raw = date_str.strip()
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ_LOCAL)
        return dt.astimezone(TZ_LOCAL)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ_LOCAL)
        return dt.astimezone(TZ_LOCAL)
    except Exception:
        return None


def fetch_weather():
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
        f"&current=temperature_2m,weather_code"
        f"&timezone=Europe%2FBratislava"
    )
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; EInkWorldDaily/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        current = data.get("current", {})
        temp = current.get("temperature_2m")
        code = current.get("weather_code")
        if temp is None:
            return f"{WEATHER_CITY}: -- °C"
        temp_int = int(round(temp))
        desc = WMO_SK.get(code, "")
        return f"{WEATHER_CITY}: {temp_int} °C · {desc}" if desc else f"{WEATHER_CITY}: {temp_int} °C"
    except Exception as e:
        print(f"Chyba pri načítaní počasia: {e}")
        return f"{WEATHER_CITY}: -- °C"


def normalize_key(title):
    cleaned = re.sub(r"[^a-z0-9áčďéíĺľňóôŕšťúýž]+", "", title.lower())
    return cleaned[:48]


def has_keyword(text, category_key):
    patterns = KEYWORDS.get(category_key, [])
    haystack = text.lower()
    for pat in patterns:
        if pat.startswith(r"\b"):
            if re.search(pat, haystack):
                return True
        elif pat in haystack:
            return True
    return False


def fetch_single_feed(feed_cfg, today, per_feed_limit=15):
    source, publisher, groups, url = feed_cfg
    dc_date_tag = "{http://purl.org/dc/elements/1.1/}date"
    results = []

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; EInkWorldDaily/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
    except Exception as e:
        print(f"Chyba pri načítaní {source} ({url}): {e}")
        return results

    items = root.findall(".//item")
    is_atom = False
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        is_atom = True

    count = 0
    for item in items:
        if count >= per_feed_limit:
            break

        if is_atom:
            ns = "{http://www.w3.org/2005/Atom}"
            title = clean_text(item.findtext(f"{ns}title"))
            summary = clean_text(
                item.findtext(f"{ns}summary") or item.findtext(f"{ns}content")
            )
            pub_raw = item.findtext(f"{ns}published") or item.findtext(f"{ns}updated")
        else:
            title = clean_text(item.findtext("title"))
            summary = clean_text(item.findtext("description"))
            pub_raw = item.findtext("pubDate") or item.findtext(dc_date_tag)

        if not title or len(title) < 12:
            continue

        dt = parse_date(pub_raw)
        if dt is None:
            continue
        if ONLY_TODAY and dt.date() != today:
            continue

        key = normalize_key(title)
        if summary and normalize_key(summary) == key:
            summary = ""

        results.append(
            {
                "key": key,
                "source": source,
                "publisher": publisher,
                "groups": set(groups),
                "title": title,
                "summary": summary,
                "dt": dt,
            }
        )
        count += 1

    return results


def fetch_articles(feeds, per_feed_limit=15):
    today = datetime.now(TZ_LOCAL).date()
    all_raw = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(fetch_single_feed, cfg, today, per_feed_limit)
            for cfg in feeds
        ]
        for fut in as_completed(futures):
            all_raw.extend(fut.result())

    # Zoradenie od najnovšieho a odstránenie duplicít (zlúčením skupín pri rovnakom článku)
    all_raw.sort(key=lambda x: x["dt"], reverse=True)
    by_key = {}
    ordered = []

    for art in all_raw:
        k = art["key"]
        if k not in by_key:
            by_key[k] = art
            ordered.append(art)
        else:
            existing = by_key[k]
            existing["groups"].update(art["groups"])
            if not existing["summary"] and art["summary"]:
                existing["summary"] = art["summary"]

    return ordered


def matches_category(art, cat_key):
    groups = art["groups"]
    text = f"{art['title']} {art['summary']}"

    if cat_key == "svet":
        return "svet" in groups
    if cat_key == "domov":
        return "domov" in groups
    if cat_key == "ekonomika":
        return "ekonomika" in groups
    if cat_key == "energie_byvanie":
        return (
            bool(groups & {"ekonomika", "domov", "tech", "svet"})
            and has_keyword(text, "energie_byvanie")
        )
    if cat_key == "ai_tech":
        return "tech" in groups and has_keyword(text, "ai_tech")
    if cat_key == "gadgety_it":
        return "tech" in groups
    if cat_key == "veda_vesmir":
        return "veda" in groups or (
            bool(groups & {"tech", "svet", "domov"}) and has_keyword(text, "veda_vesmir")
        )
    if cat_key == "zdravie_priroda":
        return "zdravie" in groups or (
            bool(groups & {"veda", "svet", "domov"}) and has_keyword(text, "zdravie_priroda")
        )
    if cat_key == "sport":
        return "sport" in groups
    if cat_key == "auto":
        return "auto" in groups or (
            bool(groups & {"ekonomika", "tech", "domov"}) and has_keyword(text, "auto")
        )
    return False


def pick_best_for_category(articles, cat_key, used_keys):
    candidates = [
        a for a in articles
        if a["key"] not in used_keys and matches_category(a, cat_key)
    ]
    if not candidates:
        return None

    # Pri Gadgety a IT uprednostníme články priamo o gadgetoch/IT pred všeobecným techom
    if cat_key == "gadgety_it":
        gadget_matches = [
            a for a in candidates
            if has_keyword(f"{a['title']} {a['summary']}", "gadgety_it")
        ]
        if gadget_matches:
            candidates = gadget_matches

    # Uprednostníme najnovší článok s perexom; ak žiaden nemá perex, berieme najnovší
    with_summary = [a for a in candidates if a["summary"]]
    chosen = with_summary[0] if with_summary else candidates[0]
    used_keys.add(chosen["key"])
    return chosen


def select_slot_articles(articles):
    used_keys = set()
    slot_results = []

    for idx, slot in enumerate(SLOTS, start=1):
        p_label, p_key = slot["primary"]
        f_label, f_key = slot["fallback"]

        art = pick_best_for_category(articles, p_key, used_keys)
        if art is not None:
            entry = dict(art, display_tag=p_label, is_fallback=False)
            slot_results.append(entry)
            print(f"Slot {idx} [{p_label}]: {art['source']} ({art['dt'].strftime('%d.%m. %H:%M')}) - {art['title'][:60]}")
            continue

        art = pick_best_for_category(articles, f_key, used_keys)
        if art is not None:
            entry = dict(art, display_tag=f_label, is_fallback=True)
            slot_results.append(entry)
            print(f"Slot {idx} [ZÁLOHA: {f_label}]: {art['source']} ({art['dt'].strftime('%d.%m. %H:%M')}) - {art['title'][:60]}")
            continue

        slot_results.append({"display_tag": p_label, "empty": True})
        print(f"Slot {idx} [{p_label} / {f_label}]: dnes zatiaľ bez nových správ")

    return slot_results


def wrap_text(draw, text, font, max_width, max_lines):
    words = text.split()
    if not words:
        return []

    lines = []
    current = ""
    truncated = False

    for i, word in enumerate(words):
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
                if len(lines) == max_lines:
                    truncated = True
                    current = ""
                    break
                current = word
            else:
                trimmed = word
                while trimmed and draw.textlength(trimmed + "…", font=font) > max_width:
                    trimmed = trimmed[:-1]
                lines.append(trimmed + "…")
                if len(lines) == max_lines:
                    truncated = i < len(words) - 1
                    current = ""
                    break
                current = ""

    if current and len(lines) < max_lines:
        if draw.textlength(current, font=font) <= max_width:
            lines.append(current)
        else:
            trimmed = current
            while trimmed and draw.textlength(trimmed + "…", font=font) > max_width:
                trimmed = trimmed[:-1]
            lines.append(trimmed + "…")

    if truncated and lines and not lines[-1].endswith("…"):
        last = lines[-1].rstrip(".,;:!?-–— ")
        while last and draw.textlength(last + "…", font=font) > max_width:
            last = last[:-1].rstrip(".,;:!?-–— ")
        lines[-1] = (last + "…") if last else "…"

    return lines[:max_lines]


def render_dashboard(slot_articles, weather_str):
    # 1-bit plátno: 1 = biela, 0 = čierna
    img = Image.new("1", (WIDTH, HEIGHT), 1)
    draw = ImageDraw.Draw(img)

    serif_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    sans_bold = [
        "arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    sans_reg = [
        "arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    f_masthead = load_font(serif_bold, 25)
    f_hdr_meta = load_font(sans_bold, 12)
    f_clock = load_font(sans_bold, 12)
    f_badge = load_font(sans_bold, 11)
    f_badge_sm = load_font(sans_bold, 10)
    f_meta = load_font(sans_bold, 12)
    f_meta_sm = load_font(sans_bold, 11)
    f_lead_title = load_font(sans_bold, 20)
    f_lead_body = load_font(sans_reg, 14)
    f_grid_title = load_font(sans_bold, 15)
    f_grid_body = load_font(sans_reg, 13)
    f_footer = load_font(sans_reg, 11)
    f_footer_bold = load_font(sans_bold, 11)

    now = datetime.now(TZ_LOCAL)
    margin_x = 16
    right_x = WIDTH - margin_x
    content_w = right_x - margin_x

    # --- 1. HLAVIČKA (MASTHEAD) ---
    draw.line((margin_x, 8, right_x, 8), fill=0, width=3)
    date_str = f"{DAYS_SK[now.weekday()]}, {now.strftime('%d. %m. %Y')}"
    upd_str = f"OBNOVENÉ {now.strftime('%H:%M')}"

    draw.text((margin_x, 28), date_str, font=f_hdr_meta, fill=0, anchor="lm")
    draw.text((WIDTH // 2, 27), NEWSPAPER_TITLE, font=f_masthead, fill=0, anchor="mm")
    draw.text((right_x, 28), upd_str, font=f_hdr_meta, fill=0, anchor="rm")

    # --- 2. PÁS SO SVETOVÝMI ČASMI ---
    draw.line((margin_x, 46, right_x, 46), fill=0, width=1)
    slot_w = content_w // len(WORLD_CLOCKS)
    for idx, (city, tz_name) in enumerate(WORLD_CLOCKS):
        city_time = datetime.now(ZoneInfo(tz_name)).strftime("%H:%M")
        cx = margin_x + idx * slot_w + slot_w // 2
        draw.text((cx, 58), f"{city}  {city_time}", font=f_clock, fill=0, anchor="mm")
        if idx > 0:
            vx = margin_x + idx * slot_w
            draw.line((vx, 51, vx, 65), fill=0, width=1)

    draw.line((margin_x, 70, right_x, 70), fill=0, width=1)
    draw.line((margin_x, 73, right_x, 73), fill=0, width=2)

    # --- 3. HLAVNÁ SPRÁVA (SLOT 1: SVET / DOMOV) ---
    lead = slot_articles[0]
    badge_txt = f" {lead['display_tag']} "
    badge_w = int(draw.textlength(badge_txt, font=f_badge)) + 8
    draw.rectangle((margin_x, 80, margin_x + badge_w, 98), fill=0)
    draw.text((margin_x + 4, 89), badge_txt, font=f_badge, fill=1, anchor="lm")
    draw.text((right_x, 89), "HLAVNÁ SPRÁVA", font=f_meta_sm, fill=0, anchor="rm")

    if lead.get("empty"):
        draw.text(
            (margin_x, 126),
            "Dnes zatiaľ neboli vydané nové správy v kategórii Svet ani Domov.",
            font=f_lead_body,
            fill=0,
        )
    else:
        lead_meta = f"{lead['dt'].strftime('%H:%M')} · {lead['source'].upper()}"
        draw.text((margin_x + badge_w + 10, 89), lead_meta, font=f_meta, fill=0, anchor="lm")

        y = 103
        lead_lines = wrap_text(draw, lead["title"], f_lead_title, content_w, max_lines=2)
        for line in lead_lines:
            draw.text((margin_x, y), line, font=f_lead_title, fill=0)
            y += 23

        if lead["summary"]:
            y += 5
            max_sum_lines = 3 if len(lead_lines) == 1 else 2
            for line in wrap_text(draw, lead["summary"], f_lead_body, content_w, max_lines=max_sum_lines):
                draw.text((margin_x, y), line, font=f_lead_body, fill=0)
                y += 18

    draw.line((margin_x, 195, right_x, 195), fill=0, width=2)

    # --- 4. MRIEŽKA 2×2 (SLOTY 2 – 5) ---
    draw.line((WIDTH // 2, 202, WIDTH // 2, 450), fill=0, width=1)
    draw.line((margin_x, 327, right_x, 327), fill=0, width=1)

    cell_w = 372
    cells = [
        (margin_x, 203),          # Horná ľavá: Ekonomika / Energie a bývanie
        (WIDTH // 2 + 12, 203),   # Horná pravá: AI a Tech / Gadgety a IT
        (margin_x, 335),          # Dolná ľavá: Veda a vesmír / Zdravie a príroda
        (WIDTH // 2 + 12, 335),   # Dolná pravá: Šport / Auto a mobilita
    ]

    for art, (cx, cy) in zip(slot_articles[1:5], cells):
        b_txt = f" {art['display_tag']} "
        b_w = int(draw.textlength(b_txt, font=f_badge_sm)) + 6
        draw.rectangle((cx, cy, cx + b_w, cy + 16), fill=0)
        draw.text((cx + 3, cy + 8), b_txt, font=f_badge_sm, fill=1, anchor="lm")

        if art.get("empty"):
            draw.text(
                (cx, cy + 32),
                "Dnes zatiaľ bez nových správ v tejto kategórii.",
                font=f_grid_body,
                fill=0,
            )
            continue

        meta = f"{art['dt'].strftime('%H:%M')} · {art['source'].upper()}"
        draw.text((cx + b_w + 8, cy + 8), meta, font=f_meta_sm, fill=0, anchor="lm")

        ty = cy + 21
        t_lines = wrap_text(draw, art["title"], f_grid_title, cell_w, max_lines=2)
        for line in t_lines:
            draw.text((cx, ty), line, font=f_grid_title, fill=0)
            ty += 18

        if art["summary"]:
            ty += 4
            s_max = 4 if len(t_lines) == 1 else 3
            for line in wrap_text(draw, art["summary"], f_grid_body, cell_w, max_lines=s_max):
                draw.text((cx, ty), line, font=f_grid_body, fill=0)
                ty += 16

    # --- 5. PÄTIČKA (VYDAVATELIA + POČASIE ŠAMORÍN) ---
    draw.line((margin_x, 456, right_x, 456), fill=0, width=1)
    publishers = " · ".join(dict.fromkeys(f[1] for f in FEEDS))
    draw.text((margin_x, 468), f"Zdroje: {publishers}", font=f_footer, fill=0, anchor="lm")
    draw.text((right_x, 468), weather_str, font=f_footer_bold, fill=0, anchor="rm")

    img.save(OUTPUT_FILE)
    filled = sum(1 for a in slot_articles if not a.get("empty"))
    print(f"Vygenerované: {OUTPUT_FILE} ({filled}/5 obsadených pozícií | {weather_str})")


if __name__ == "__main__":
    all_articles = fetch_articles(FEEDS)
    slots_selected = select_slot_articles(all_articles)
    weather = fetch_weather()
    render_dashboard(slots_selected, weather)
