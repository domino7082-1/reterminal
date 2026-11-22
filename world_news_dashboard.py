import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
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

# Pomer správ v rozložení 1 + 4 (spolu 5 správ: cieľ 3× Svet + 2× Tech)
TECH_SLOTS = 2

# Svetové časy v hlavičke (Názov, IANA časové pásmo)
WORLD_CLOCKS = [
    ("BRATISLAVA", "Europe/Bratislava"),
    ("LONDÝN", "Europe/London"),
    ("NEW YORK", "America/New_York"),
    ("TOKIO", "Asia/Tokyo"),
]

# RSS zdroje: (Názov zdroja, Skupina "world"/"tech", URL)
FEEDS = [
    ("SME Svet", "world", "https://svet.sme.sk/rss"),
    ("Denník N", "world", "https://dennikn.sk/svet/feed/"),
    ("Aktuality", "world", "https://www.aktuality.sk/rss/zahranicne/"),
    ("TASR", "world", "https://www.teraz.sk/rss/zahranicie.rss"),
    ("Živé.sk", "tech", "https://zive.aktuality.sk/rss/najnovsie/"),
    ("SME Tech", "tech", "https://tech.sme.sk/rss"),
]

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

# Automatické priraďovanie štítkov podľa kľúčových slov v titulku a perexe
TAG_RULES = [
    ("AI / TECH", ["umelá inteligencia", "umelej inteligenc", "openai", "chatgpt", "gemini", "claude", "nvidia", "čip", "kvantov"]),
    ("VESMÍR", ["nasa", "spacex", "vesmír", "raket", "mesiac", "mars", "satelit", "astronaut"]),
    ("USA", ["usa", "ameri", "trump", "washington", "biely dom", "pentag", "new york", "kaliforn", "fed"]),
    ("EURÓPA", ["európ", "eú", "brusel", "nemeck", "francúz", "britán", "londýn", "poľsk", "česk", "ukrajin", "rusk", "maďarsk", "taliansk", "španielsk"]),
    ("ÁZIA", ["čín", "japonsk", "tokio", "taiwan", "indii", "indi", "kóre", "peking", "ázi"]),
    ("BL. VÝCHOD", ["izrael", "gaz", "irán", "sýri", "libanon", "blízk", "saudsk"]),
]


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


def detect_tag(title, summary, group):
    haystack = f"{title} {summary}".lower()
    if group == "tech":
        for tag, keywords in TAG_RULES[:2]:
            if any(k in haystack for k in keywords):
                return tag
        return "TECH"
    for tag, keywords in TAG_RULES[2:]:
        if any(k in haystack for k in keywords):
            return tag
    return "SVET"


def normalize_key(title):
    cleaned = re.sub(r"[^a-z0-9áčďéíĺľňóôŕšťúýž]+", "", title.lower())
    return cleaned[:48]


def fetch_articles(feeds, per_feed_limit=15):
    articles = []
    seen = set()
    today = datetime.now(TZ_LOCAL).date()
    dc_date_tag = "{http://purl.org/dc/elements/1.1/}date"

    for source, group, url in feeds:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; EInkWorldDaily/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
        except Exception as e:
            print(f"Chyba pri načítaní {source}: {e}")
            continue

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
            if key in seen:
                continue
            seen.add(key)

            if summary and normalize_key(summary) == key:
                summary = ""

            articles.append(
                {
                    "source": source,
                    "group": group,
                    "tag": detect_tag(title, summary, group),
                    "title": title,
                    "summary": summary,
                    "dt": dt,
                }
            )
            count += 1

    articles.sort(key=lambda x: x["dt"], reverse=True)
    return articles


def pick_diverse(pool, count, used_keys):
    selected = []
    used_sources = set()

    for art in pool:
        if len(selected) >= count:
            break
        k = normalize_key(art["title"])
        if k in used_keys or art["source"] in used_sources or not art["summary"]:
            continue
        selected.append(art)
        used_keys.add(k)
        used_sources.add(art["source"])

    for art in pool:
        if len(selected) >= count:
            break
        k = normalize_key(art["title"])
        if k in used_keys:
            continue
        selected.append(art)
        used_keys.add(k)

    return selected


def select_five_articles(articles):
    if not articles:
        return []

    world_pool = [a for a in articles if a["group"] == "world"]
    tech_pool = [a for a in articles if a["group"] == "tech"]
    used_keys = set()

    lead_candidates = pick_diverse(world_pool, 1, used_keys)
    if not lead_candidates:
        lead_candidates = pick_diverse(tech_pool, 1, used_keys)
    lead = lead_candidates[0]

    tech_picks = pick_diverse(tech_pool, TECH_SLOTS, used_keys)
    world_needed = 4 - len(tech_picks)
    world_picks = pick_diverse(world_pool, world_needed, used_keys)

    grid = world_picks + tech_picks
    if len(grid) < 4:
        grid.extend(pick_diverse(articles, 4 - len(grid), used_keys))

    grid.sort(key=lambda x: x["dt"], reverse=True)
    return [lead] + grid[:4]


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


def render_dashboard(selected_articles, weather_str):
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

    # --- 5. PÄTIČKA (vykreslí sa vždy, aj skoro ráno pri 0 správach) ---
    def draw_footer():
        draw.line((margin_x, 456, right_x, 456), fill=0, width=1)
        sources_used = " · ".join(dict.fromkeys(f[0] for f in FEEDS))
        draw.text((margin_x, 468), f"Zdroje: {sources_used}", font=f_footer, fill=0, anchor="lm")
        draw.text((right_x, 468), weather_str, font=f_footer_bold, fill=0, anchor="rm")

    if not selected_articles:
        msg = (
            "Zatiaľ neboli vydané dnešné správy."
            if ONLY_TODAY
            else "Nepodarilo sa načítať správy z RSS zdrojov."
        )
        draw.text((WIDTH // 2, HEIGHT // 2), msg, font=f_lead_title, fill=0, anchor="mm")
        draw_footer()
        img.save(OUTPUT_FILE)
        print(f"Vygenerované: {OUTPUT_FILE} (0 dnešných správ | {weather_str})")
        return

    # --- 3. HLAVNÁ SPRÁVA (1) CEZ CELÚ ŠÍRKU ---
    lead = selected_articles[0]
    badge_txt = f" {lead['tag']} "
    badge_w = int(draw.textlength(badge_txt, font=f_badge)) + 8
    draw.rectangle((margin_x, 80, margin_x + badge_w, 98), fill=0)
    draw.text((margin_x + 4, 89), badge_txt, font=f_badge, fill=1, anchor="lm")

    lead_meta = f"{lead['dt'].strftime('%H:%M')} · {lead['source'].upper()}"
    draw.text((margin_x + badge_w + 10, 89), lead_meta, font=f_meta, fill=0, anchor="lm")
    draw.text((right_x, 89), "HLAVNÁ SPRÁVA", font=f_meta_sm, fill=0, anchor="rm")

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

    # --- 4. MRIEŽKA 2×2 (4 SPRÁVY S PEREXOM) ---
    draw.line((WIDTH // 2, 202, WIDTH // 2, 450), fill=0, width=1)
    draw.line((margin_x, 327, right_x, 327), fill=0, width=1)

    cell_w = 372
    cells = [
        (margin_x, 203),          # Horná ľavá
        (WIDTH // 2 + 12, 203),   # Horná pravá
        (margin_x, 335),          # Dolná ľavá
        (WIDTH // 2 + 12, 335),   # Dolná pravá
    ]

    for art, (cx, cy) in zip(selected_articles[1:5], cells):
        b_txt = f" {art['tag']} "
        b_w = int(draw.textlength(b_txt, font=f_badge_sm)) + 6
        draw.rectangle((cx, cy, cx + b_w, cy + 16), fill=0)
        draw.text((cx + 3, cy + 8), b_txt, font=f_badge_sm, fill=1, anchor="lm")

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

    draw_footer()

    img.save(OUTPUT_FILE)
    dates_log = ", ".join(f"{a['source']} ({a['dt'].strftime('%d.%m. %H:%M')})" for a in selected_articles)
    print(f"Vygenerované: {OUTPUT_FILE} ({len(selected_articles)} správ | {weather_str})")
    print(f"Vybrané články: {dates_log}")


if __name__ == "__main__":
    all_articles = fetch_articles(FEEDS)
    top_five = select_five_articles(all_articles)
    weather = fetch_weather()
    render_dashboard(top_five, weather)
