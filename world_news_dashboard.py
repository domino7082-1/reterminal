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

# Počet správ na displeji: 1 hlavná + 3 ďalšie = 4
TOTAL_ARTICLES = 4

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

# 5 hlavných kategórií (mixujú sa do 4 pozícií)
MAIN_CATEGORIES = [
    ("SVET", "svet"),
    ("EKONOMIKA A TRHY", "ekonomika"),
    ("AI A TECH", "ai_tech"),
    ("VEDA A VESMÍR", "veda_vesmir"),
    ("ŠPORT", "sport"),
]

# 5 záložných kategórií (použijú sa len vtedy, ak hlavné nestačia na 4 správy)
FALLBACK_CATEGORIES = [
    ("DOMOV", "domov"),
    ("ENERGIE A BÝVANIE", "energie_byvanie"),
    ("GADGETY A IT", "gadgety_it"),
    ("ZDRAVIE A PRÍRODA", "zdravie_priroda"),
    ("AUTO A MOBILITA", "auto"),
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

# Kľúčové slová pre jemné triedenie podkategórií
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

# Bežné slovenské skratky, po ktorých bodka neukončuje vetu
ABBREV_RE = re.compile(
    r"(?:\b(?:napr|tzv|mil|mld|tis|hod|min|sek|dr|ing|mgr|prof|mudr|judr|sv|st|č|r|str|pozn|resp|atď|t\.?\s*j)|^\d+|\s\d+)\.$",
    re.IGNORECASE,
)

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


def split_sentences(text):
    """Rozdelí slovenský text na celé vety bez lámania na radových číslovkách a skratkách."""
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = []
    for part in parts:
        if not part:
            continue
        if sentences and ABBREV_RE.search(sentences[-1]):
            sentences[-1] = f"{sentences[-1]} {part}"
        else:
            sentences.append(part)
    return sentences


def clean_text(raw, is_summary=False):
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    # Odstránenie typických RSS a WordPress dodatkov
    text = re.sub(
        r"\s*(Čítajte viac|Viac sa dočítate|Celý článok|Príspevok .*? sa (prvýkrát|najprv) objavil|The post .*? appeared first).*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip()

    if is_summary and text:
        # Ak samotný RSS feed usekol perex znakmi [...], […] alebo ...
        had_feed_ellipsis = bool(re.search(r"(\[\s*(?:\.\.\.|…)\s*\]|\.\.\.|…)\s*$", text))
        if had_feed_ellipsis:
            stripped = re.sub(r"\s*(\[\s*(?:\.\.\.|…)\s*\]|\.\.\.|…)\s*$", "", text).strip()
            sentences = split_sentences(stripped)
            complete = [s for s in sentences if s and s[-1] in ".!?"]
            if complete:
                text = " ".join(complete)
            else:
                text = stripped.rstrip(",;:–—- ")
                if text and text[-1] not in ".!?":
                    text += "."

    return text


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
            title = clean_text(item.findtext(f"{ns}title"), is_summary=False)
            raw_summary = item.findtext(f"{ns}summary") or item.findtext(f"{ns}content")
            summary = clean_text(raw_summary, is_summary=True)
            pub_raw = item.findtext(f"{ns}published") or item.findtext(f"{ns}updated")
        else:
            title = clean_text(item.findtext("title"), is_summary=False)
            raw_summary = item.findtext("description")
            summary = clean_text(raw_summary, is_summary=True)
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

        # Poznačenie, či mal RSS perex už od zdroja neúplné tri bodky
        raw_cut = bool(raw_summary and re.search(r"(\[\s*(?:\.\.\.|…)\s*\]|\.\.\.|…)\s*$", re.sub(r"<[^>]+>", "", html.unescape(raw_summary)).strip()))

        results.append(
            {
                "key": key,
                "source": source,
                "publisher": publisher,
                "groups": set(groups),
                "title": title,
                "summary": summary,
                "raw_cut": raw_cut,
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
            if (not existing["summary"] or existing["raw_cut"]) and art["summary"] and not art["raw_cut"]:
                existing["summary"] = art["summary"]
                existing["raw_cut"] = False

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

    if cat_key == "gadgety_it":
        gadget_matches = [
            a for a in candidates
            if has_keyword(f"{a['title']} {a['summary']}", "gadgety_it")
        ]
        if gadget_matches:
            candidates = gadget_matches

    # Uprednostníme najčerstvejší článok s kompletným perexom bez RSS useknutia
    clean_complete = [a for a in candidates if a["summary"] and not a["raw_cut"]]
    if clean_complete:
        chosen = clean_complete[0]
    else:
        with_summary = [a for a in candidates if a["summary"]]
        chosen = with_summary[0] if with_summary else candidates[0]

    used_keys.add(chosen["key"])
    return chosen


def select_mixed_articles(articles):
    """
    Vyberie 4 správy (1 hlavná + 3 ďalšie):
    - Najprv mixuje medzi všetkými 5 hlavnými kategóriami (každú hodinu sa poradie rotuje,
      takže všetkých 5 dostáva rovnaký priestor).
    - Ak hlavné kategórie neposkytnú 4 dnešné správy, doplní zvyšok zo 5 záložných kategórií.
    - Najnovšia hlavná správa sa zobrazí navrchu ako HLAVNÁ SPRÁVA.
    """
    now = datetime.now(TZ_LOCAL)
    rotation_seed = now.timetuple().tm_yday * 24 + now.hour

    def rotated(items):
        offset = rotation_seed % len(items)
        return items[offset:] + items[:offset]

    used_keys = set()
    selected = []

    # 1. Kolo: mix z 5 hlavných kategórií
    for label, key in rotated(MAIN_CATEGORIES):
        if len(selected) >= TOTAL_ARTICLES:
            break
        art = pick_best_for_category(articles, key, used_keys)
        if art is not None:
            selected.append(dict(art, display_tag=label, is_fallback=False))

    # 2. Kolo: doplnenie zo 5 záložných kategórií iba ak chýbajú hlavné
    if len(selected) < TOTAL_ARTICLES:
        for label, key in rotated(FALLBACK_CATEGORIES):
            if len(selected) >= TOTAL_ARTICLES:
                break
            art = pick_best_for_category(articles, key, used_keys)
            if art is not None:
                selected.append(dict(art, display_tag=label, is_fallback=True))

    # Hlavné kategórie vždy pred záložnými, v rámci nich od najnovšej
    selected.sort(key=lambda a: (a["is_fallback"], -a["dt"].timestamp()))

    for idx, art in enumerate(selected, start=1):
        role = "ZÁLOHA" if art["is_fallback"] else "HLAVNÁ KAT."
        pos = "HLAVNÁ SPRÁVA" if idx == 1 else f"SPRÁVA {idx}"
        print(
            f"{pos} [{role}: {art['display_tag']}]: "
            f"{art['source']} ({art['dt'].strftime('%d.%m. %H:%M')}) - {art['title']}"
        )

    return selected


def wrap_text_full(draw, text, font, max_width):
    """Zalomí celý text podľa šírky v pixeloch bez skracovania a bez troch bodiek."""
    words = text.split()
    if not words:
        return []

    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
                current = word
            else:
                # Extrémne dlhé jedno slovo (napr. URL) rozdelí bez straty znakov
                chunk = ""
                for ch in word:
                    if draw.textlength(chunk + ch, font=font) <= max_width:
                        chunk += ch
                    else:
                        if chunk:
                            lines.append(chunk)
                        chunk = ch
                current = chunk
    if current:
        lines.append(current)
    return lines


def compute_blocks(draw, articles, preset, content_w):
    blocks = []
    for idx, art in enumerate(articles):
        is_lead = idx == 0
        f_title = preset["lead_title"] if is_lead else preset["item_title"]
        f_body = preset["lead_body"] if is_lead else preset["item_body"]
        lh_title = preset["lead_lh_t"] if is_lead else preset["item_lh_t"]
        lh_body = preset["lead_lh_b"] if is_lead else preset["item_lh_b"]
        badge_h = preset["lead_badge_h"] if is_lead else preset["item_badge_h"]
        gap_after_badge = preset["gap_badge"]
        gap_after_title = preset["gap_title"]

        t_lines = wrap_text_full(draw, art["title"], f_title, content_w)
        s_lines = wrap_text_full(draw, art["summary"], f_body, content_w) if art["summary"] else []

        h = badge_h + gap_after_badge + len(t_lines) * lh_title
        if s_lines:
            h += gap_after_title + len(s_lines) * lh_body

        blocks.append(
            {
                "art": art,
                "is_lead": is_lead,
                "t_lines": t_lines,
                "s_lines": s_lines,
                "f_title": f_title,
                "f_body": f_body,
                "lh_title": lh_title,
                "lh_body": lh_body,
                "badge_h": badge_h,
                "gap_after_badge": gap_after_badge,
                "gap_after_title": gap_after_title,
                "height": h,
            }
        )
    return blocks


def fit_articles_to_canvas(draw, articles, presets, content_w, avail_h):
    """
    Nájde najčitateľnejšiu sadu písiem, pri ktorej sa zmestia všetky články celé.
    Ak by niektorý RSS feed mal extrémne dlhý odsek, skráti ho len po celých vetách (nikdy na '...').
    """
    min_div_space = 10

    for p_idx, preset in enumerate(presets):
        blocks = compute_blocks(draw, articles, preset, content_w)
        total_h = sum(b["height"] for b in blocks) + min_div_space * max(0, len(blocks) - 1)
        if total_h <= avail_h:
            return blocks, preset, p_idx + 1

    # Záložný režim pri extrémne dlhých perexoch: použijeme najkompaktnejšie písmo
    # a z najdlhšieho perexu uberáme po celých vetách, kým sa nezmestí bez '...'
    preset = presets[-1]
    trimmed = [dict(a) for a in articles]

    while True:
        blocks = compute_blocks(draw, trimmed, preset, content_w)
        total_h = sum(b["height"] for b in blocks) + min_div_space * max(0, len(blocks) - 1)
        if total_h <= avail_h:
            return blocks, preset, len(presets)

        # Nájdeme článok s najdlhším perexom, ktorý má viac než 1 vetu
        candidates = [
            (i, split_sentences(a["summary"]))
            for i, a in enumerate(trimmed)
            if a["summary"]
        ]
        multi = [(i, sents) for i, sents in candidates if len(sents) > 1]
        if multi:
            target_i, sents = max(multi, key=lambda x: len(trimmed[x[0]]["summary"]))
            trimmed[target_i]["summary"] = " ".join(sents[:-1]).strip()
            continue

        # Posledná poistka: ak ostali už len 1-vetové extrémne dlhé perexy, skryjeme najdlhší perex
        any_sum = [i for i, a in enumerate(trimmed) if a["summary"]]
        if any_sum:
            target_i = max(any_sum, key=lambda i: len(trimmed[i]["summary"]))
            trimmed[target_i]["summary"] = ""
            continue

        return blocks, preset, len(presets)


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
    f_footer = load_font(sans_reg, 11)
    f_footer_bold = load_font(sans_bold, 11)

    # Sady písiem od najčitateľnejšej po kompaktnejšiu (aby sa vždy zmestili celé správy)
    presets = [
        {
            "badge_lead": load_font(sans_bold, 11),
            "badge_item": load_font(sans_bold, 10),
            "meta_lead": load_font(sans_bold, 12),
            "meta_item": load_font(sans_bold, 11),
            "lead_title": load_font(sans_bold, 19),
            "lead_body": load_font(sans_reg, 14),
            "item_title": load_font(sans_bold, 15),
            "item_body": load_font(sans_reg, 13),
            "lead_badge_h": 18,
            "item_badge_h": 16,
            "lead_lh_t": 22,
            "lead_lh_b": 17,
            "item_lh_t": 18,
            "item_lh_b": 16,
            "gap_badge": 4,
            "gap_title": 4,
        },
        {
            "badge_lead": load_font(sans_bold, 11),
            "badge_item": load_font(sans_bold, 10),
            "meta_lead": load_font(sans_bold, 11),
            "meta_item": load_font(sans_bold, 11),
            "lead_title": load_font(sans_bold, 18),
            "lead_body": load_font(sans_reg, 13),
            "item_title": load_font(sans_bold, 14),
            "item_body": load_font(sans_reg, 12),
            "lead_badge_h": 17,
            "item_badge_h": 15,
            "lead_lh_t": 20,
            "lead_lh_b": 16,
            "item_lh_t": 17,
            "item_lh_b": 15,
            "gap_badge": 3,
            "gap_title": 3,
        },
        {
            "badge_lead": load_font(sans_bold, 10),
            "badge_item": load_font(sans_bold, 10),
            "meta_lead": load_font(sans_bold, 11),
            "meta_item": load_font(sans_bold, 10),
            "lead_title": load_font(sans_bold, 16),
            "lead_body": load_font(sans_reg, 12),
            "item_title": load_font(sans_bold, 13),
            "item_body": load_font(sans_reg, 11),
            "lead_badge_h": 16,
            "item_badge_h": 15,
            "lead_lh_t": 19,
            "lead_lh_b": 14,
            "item_lh_t": 16,
            "item_lh_b": 13,
            "gap_badge": 3,
            "gap_title": 2,
        },
    ]

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

    # --- PÄTIČKA (VYDAVATELIA + POČASIE ŠAMORÍN) ---
    def draw_footer():
        draw.line((margin_x, 456, right_x, 456), fill=0, width=1)
        publishers = " · ".join(dict.fromkeys(f[1] for f in FEEDS))
        draw.text((margin_x, 468), f"Zdroje: {publishers}", font=f_footer, fill=0, anchor="lm")
        draw.text((right_x, 468), weather_str, font=f_footer_bold, fill=0, anchor="rm")

    if not selected_articles:
        msg = (
            "Dnes zatiaľ neboli vydané nové správy."
            if ONLY_TODAY
            else "Nepodarilo sa načítať správy z RSS zdrojov."
        )
        draw.text((WIDTH // 2, HEIGHT // 2), msg, font=presets[0]["lead_title"], fill=0, anchor="mm")
        draw_footer()
        img.save(OUTPUT_FILE)
        print(f"Vygenerované: {OUTPUT_FILE} (0 správ | {weather_str})")
        return

    # --- 3. VYKRESLENIE 1 HLAVNEJ + 3 ĎALŠÍCH SPRÁV NA CELÚ ŠÍRKU ---
    top_y = 80
    bottom_y = 450
    avail_h = bottom_y - top_y

    blocks, preset, used_preset_num = fit_articles_to_canvas(
        draw, selected_articles, presets, content_w, avail_h
    )

    total_blocks_h = sum(b["height"] for b in blocks)
    n_gaps = max(0, len(blocks) - 1)
    extra_h = max(0, avail_h - total_blocks_h)

    # Rovnomerné rozdelenie voľného priestoru medzi oddeľovače a okraje
    if n_gaps > 0:
        div_space = min(24, max(10, extra_h // (n_gaps + 1)))
        remaining = max(0, extra_h - div_space * n_gaps)
        y = top_y + min(10, remaining // 2)
    else:
        div_space = 0
        y = top_y

    for idx, b in enumerate(blocks):
        art = b["art"]
        is_lead = b["is_lead"]
        f_badge = preset["badge_lead"] if is_lead else preset["badge_item"]
        f_meta = preset["meta_lead"] if is_lead else preset["meta_item"]
        badge_h = b["badge_h"]

        # Štítok kategórie (inverzný čierny obdĺžnik)
        badge_txt = f" {art['display_tag']} "
        badge_w = int(draw.textlength(badge_txt, font=f_badge)) + 8
        draw.rectangle((margin_x, y, margin_x + badge_w, y + badge_h), fill=0)
        draw.text((margin_x + 4, y + badge_h // 2), badge_txt, font=f_badge, fill=1, anchor="lm")

        meta_str = f"{art['dt'].strftime('%H:%M')} · {art['source'].upper()}"
        draw.text((margin_x + badge_w + 10, y + badge_h // 2), meta_str, font=f_meta, fill=0, anchor="lm")

        if is_lead:
            draw.text((right_x, y + badge_h // 2), "HLAVNÁ SPRÁVA", font=preset["meta_item"], fill=0, anchor="rm")

        cy = y + badge_h + b["gap_after_badge"]
        for line in b["t_lines"]:
            draw.text((margin_x, cy), line, font=b["f_title"], fill=0)
            cy += b["lh_title"]

        if b["s_lines"]:
            cy += b["gap_after_title"]
            for line in b["s_lines"]:
                draw.text((margin_x, cy), line, font=b["f_body"], fill=0)
                cy += b["lh_body"]

        # Oddeľovač pod článkom (hrubší pod hlavnou správou, tenší medzi ďalšími)
        if idx < len(blocks) - 1:
            div_y = cy + div_space // 2
            line_w = 2 if is_lead else 1
            draw.line((margin_x, div_y, right_x, div_y), fill=0, width=line_w)
            y = cy + div_space
        else:
            y = cy

    draw_footer()

    img.save(OUTPUT_FILE)
    print(
        f"Vygenerované: {OUTPUT_FILE} ({len(blocks)}/{TOTAL_ARTICLES} správ | "
        f"Písmo: sada {used_preset_num} | {weather_str})"
    )


if __name__ == "__main__":
    all_articles = fetch_articles(FEEDS)
    selected = select_mixed_articles(all_articles)
    weather = fetch_weather()
    render_dashboard(selected, weather)
