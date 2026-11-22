import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

# --- KONFIGURÁCIA ---
WIDTH, HEIGHT = 800, 480
OUTPUT_FILE = "world_news_output.bmp"
TZ_LOCAL = ZoneInfo("Europe/Bratislava")
NEWSPAPER_TITLE = "SVETOVÝ DENNÍK"

# Rozloženie: 1 hlavná správa (celá šírka) + 2 doplnkové (ľavý a pravý stĺpec)
TOTAL_ARTICLES = 3

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

# 5 hlavných kategórií
MAIN_CATEGORIES = [
    ("SVET", "svet"),
    ("EKONOMIKA A TRHY", "ekonomika"),
    ("AI A TECH", "ai_tech"),
    ("VEDA A VESMÍR", "veda_vesmir"),
    ("ŠPORT", "sport"),
]

# 5 záložných kategórií (použijú sa len ak hlavné nemajú dosť kvalitných správ)
FALLBACK_CATEGORIES = [
    ("DOMOV", "domov"),
    ("ENERGIE A BÝVANIE", "energie_byvanie"),
    ("GADGETY A IT", "gadgety_it"),
    ("ZDRAVIE A PRÍRODA", "zdravie_priroda"),
    ("AUTO A MOBILITA", "auto"),
]

# Priorita kategórií pre výber HLAVNEJ SPRÁVY (kategórie s najvyššou pridanou hodnotou)
LEAD_PRIORITY_BONUS = {
    "svet": 22,
    "ekonomika": 18,
    "ai_tech": 14,
    "veda_vesmir": 14,
    "domov": 12,
    "energie_byvanie": 8,
    "zdravie_priroda": 6,
    "gadgety_it": 4,
    "auto": 2,
    "sport": -25,  # Šport patrí prednostne do spodných stĺpcov, nie ako hlavná správa
}

# RSS zdroje: (Krátky názov zdroja, Kategórie zdroja, URL)
FEEDS = [
    # SVET
    ("SME Svet", ("svet",), "https://svet.sme.sk/rss"),
    ("Denník N", ("svet",), "https://dennikn.sk/svet/feed/"),
    ("Aktuality", ("svet",), "https://www.aktuality.sk/rss/zahranicne/"),
    ("TASR", ("svet",), "https://www.teraz.sk/rss/zahranicie.rss"),
    # DOMOV
    ("SME Domov", ("domov",), "https://domov.sme.sk/rss"),
    ("Denník N", ("domov",), "https://dennikn.sk/slovensko/feed/"),
    ("Aktuality", ("domov",), "https://www.aktuality.sk/rss/domace/"),
    ("TASR", ("domov",), "https://www.teraz.sk/rss/slovensko.rss"),
    # EKONOMIKA A TRHY
    ("SME Index", ("ekonomika",), "https://index.sme.sk/rss"),
    ("Denník E", ("ekonomika",), "https://e.dennikn.sk/feed/"),
    ("Aktuality", ("ekonomika",), "https://www.aktuality.sk/rss/ekonomika/"),
    ("TASR", ("ekonomika",), "https://www.teraz.sk/rss/ekonomika.rss"),
    ("Pravda", ("ekonomika",), "https://ekonomika.pravda.sk/rss/xml/"),
    # TECH / AI / GADGETY
    ("Živé.sk", ("tech",), "https://zive.aktuality.sk/rss/najnovsie/"),
    ("SME Tech", ("tech",), "https://tech.sme.sk/rss"),
    ("TouchIT", ("tech",), "https://touchit.sk/feed/"),
    # VEDA A VESMÍR
    ("Denník N", ("veda",), "https://dennikn.sk/veda/feed/"),
    ("Pravda Veda", ("veda",), "https://veda.pravda.sk/rss/xml/"),
    # ZDRAVIE A PRÍRODA
    ("SME Primár", ("zdravie",), "https://primar.sme.sk/rss"),
    ("Pravda Zdravie", ("zdravie",), "https://zdravie.pravda.sk/rss/xml/"),
    # ŠPORT
    ("Šport.sk", ("sport",), "https://sport.aktuality.sk/rss/"),
    ("Denník N", ("sport",), "https://dennikn.sk/sport/feed/"),
    ("TASR Šport", ("sport",), "https://www.teraz.sk/rss/sport.rss"),
    ("Pravda Šport", ("sport",), "https://sport.pravda.sk/rss/xml/"),
    # AUTO A MOBILITA
    ("SME Auto", ("auto",), "https://auto.sme.sk/rss"),
    ("Pravda Auto", ("auto",), "https://auto.pravda.sk/rss/xml/"),
]

# Kľúčové slová pre triedenie podkategórií
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

# Vzory pre vyradenie video článkov, online prenosov, galérií a neinformatívneho obsahu
UNWANTED_RE = re.compile(
    r"(?:"
    r"\(\s*\+?\s*video\s*\)|\[\s*video\s*\]|\bvideo\b|\bvideoreportáž|\bvideorozhovor"
    r"|pozrite\s+si\s+(?:video|záznam)|vo\s+videu|v\s+priloženom\s+videu"
    r"|\bpodcast\b|\bfotogaléri|\(\s*\+?\s*foto\s*\)|\bfoto\s*:"
    r"|^online\b|\bonline\s*:|\bonline\s+prenos|\bpriamy\s+prenos|\bsledujte\s+naživo"
    r"|\bminúta\s+po\s+minúte|^live\b|\blive\s*:|^naživo\b|\bnaživo\s*:"
    r"|kde\s+sledovať|\bkurzy\b|tipy\s+na\s+stávk|\bkvíz\b|\banketa\b|\bhoroskop\b|\bsúťaž\b"
    r")",
    re.IGNORECASE,
)

# Slabé clickbaitové alebo prázdne formulácie (znižujú skóre relevancie)
CLICKBAIT_RE = re.compile(
    r"(?:zistite[, ]|pozrite\s+si|neuveríte|šokujúc|toto\s+ste\s+nevedeli|"
    r"vyzerajú\s+tak\s+strašne|nikdy\s+nerobte|týchto\s+\d+\s+vecí|rebríček\s+naj)",
    re.IGNORECASE,
)

# Perexy, ktoré začínajú ako vytrhnutá druhá veta bez kontextu (časté v agentúrnych správach)
DANGLING_START_RE = re.compile(
    r"^(?:zároveň|tiež|taktiež|dodal|dodala|uviedol\s+to|uviedla\s+to|"
    r"informoval[ao]?\s+o\s+tom|podľa\s+(?:neho|nej|nich)|píše\s+o\s+tom)\b",
    re.IGNORECASE,
)

# Signály vecného, prínosného obsahu
FACTUAL_SIGNALS_RE = re.compile(
    r"(?:\d+\s*(?:%|percent|mil\.|milión|mld\.|miliard|tisíc|eur|dolár|km|gw|mw)|"
    r"\b(?:výskum|štúdi|analýz|ekonomik|infláci|sadzb|banka|vlád|parlament|komisi|"
    r"dohod|zmluv|sankci|investíci|zákon|opatreni|technológi|objav|rekord|nárast|pokles)\w*)",
    re.IGNORECASE,
)

# Bežné slovenské skratky, po ktorých bodka neukončuje vetu
ABBREV_RE = re.compile(
    r"(?:\b(?:napr|tzv|mil|mld|tis|hod|min|sek|dr|ing|mgr|prof|mudr|judr|sv|st|č|r|str|pozn|resp|atď|t\.?\s*j)|^\d+|\s\d+)\.$",
    re.IGNORECASE,
)

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

# Pevné slovenské sviatky a významné dni
SVIATKY_SK = {
    (1, 1): "Deň vzniku SR (Nový rok)",
    (1, 6): "Zjavenie Pána (Traja králi)",
    (5, 1): "Sviatok práce",
    (5, 8): "Deň víťazstva nad fašizmom",
    (7, 5): "Sviatok sv. Cyrila a Metoda",
    (8, 29): "Výročie SNP",
    (9, 1): "Deň Ústavy SR",
    (9, 15): "Sedembolestná Panna Mária",
    (11, 1): "Sviatok všetkých svätých",
    (11, 2): "Pamiatka zosnulých (Dušičky)",
    (11, 17): "Deň boja za slobodu a demokraciu",
    (12, 24): "Štedrý deň",
    (12, 25): "1. sviatok vianočný",
    (12, 26): "2. sviatok vianočný",
}

# Kompletný slovenský kalendár menín (mesiac -> zoznam dní od 1.)
MENINY_BY_MONTH = {
    1: [
        "", "Alexandra", "Daniela", "Drahoslav", "Andrea", "Antónia", "Bohuslava",
        "Severín", "Alexej", "Dáša", "Malvína", "Ernest", "Rastislav", "Radovan",
        "Dobroslav", "Kristína", "Nataša", "Bohdana", "Drahomíra", "Dalibor",
        "Vincent", "Zora", "Miloš", "Timotej", "Gejza", "Tamara", "Bohuš",
        "Alfonz", "Gašpar", "Ema", "Emil",
    ],
    2: [
        "Tatiana", "Erik, Erika", "Blažej", "Veronika", "Agáta", "Dorota", "Vanda",
        "Zoja", "Zdenko", "Gabriela", "Dezider", "Perla", "Arpád", "Valentín",
        "Pravoslav", "Ida, Liana", "Miloslava", "Jaromír", "Vlasta", "Lívia",
        "Eleonóra", "Etela", "Roman, Romana", "Matej", "Frederik, Frederika",
        "Viktor", "Alexander", "Zlatica", "Radomír",
    ],
    3: [
        "Albín", "Anežka", "Bohumil, Bohumila", "Kazimír", "Fridrich",
        "Radoslav, Radoslava", "Tomáš", "Alan, Alana", "Františka",
        "Bruno, Branislav", "Angela, Angelika", "Gregor", "Vlastimil", "Matilda",
        "Svetlana", "Boleslav", "Ľubica", "Eduard", "Jozef", "Víťazoslav",
        "Blahoslav", "Beňadik", "Adrián", "Gabriel", "Marián", "Emanuel", "Alena",
        "Soňa", "Miroslav", "Vieroslava", "Benjamín",
    ],
    4: [
        "Hugo", "Zita", "Richard", "Izidor", "Miroslava", "Irena", "Zoltán",
        "Albert", "Milena", "Igor", "Július", "Estera", "Aleš", "Justína", "Fedor",
        "Dana, Danica", "Rudolf", "Valér", "Jela", "Marcel", "Ervín", "Slavomír",
        "Vojtech", "Juraj", "Marek", "Jaroslava", "Jaroslav", "Jarmila", "Lea",
        "Anastázia",
    ],
    5: [
        "", "Žigmund", "Galina", "Florián", "Lesana, Lesia", "Hermína", "Monika",
        "Ingrida", "Roland", "Viktória", "Blažena", "Pankrác", "Servác", "Bonifác",
        "Žofia", "Svetozár", "Gizela", "Viola", "Gertrúda", "Bernard", "Zina",
        "Júlia, Juliána", "Želmíra", "Ela", "Urban", "Dušan", "Iveta", "Viliam",
        "Vilma", "Ferdinand", "Petrana, Petronela",
    ],
    6: [
        "Žaneta", "Xénia, Oxana", "Karolína", "Lenka", "Laura", "Norbert",
        "Róbert", "Medard", "Stanislava", "Margaréta", "Dobroslava", "Zlatko",
        "Anton", "Vasil", "Vít", "Blanka, Bianka", "Adolf", "Vratislav", "Alfréd",
        "Valéria", "Alojz", "Paulína", "Sidónia", "Ján", "Tadeáš, Olívia",
        "Adriána", "Ladislav, Ladislava", "Beáta", "Peter, Pavol, Petra", "Melánia",
    ],
    7: [
        "Diana", "Berta", "Miloslav", "Prokop", "Cyril, Metod", "Patrik, Patrícia",
        "Oliver", "Ivan", "Lujza", "Amália", "Milota", "Nina", "Margita", "Kamil",
        "Henrich", "Drahomír", "Bohuslav", "Kamila", "Dušana", "Iľja, Eliáš",
        "Daniel", "Magdaléna", "Oľga", "Vladimír", "Jakub", "Anna, Hana", "Božena",
        "Krištof", "Marta", "Libuša", "Ignác",
    ],
    8: [
        "Božidara", "Gustáv", "Jerguš", "Dominik, Dominika", "Hortenzia",
        "Jozefína", "Štefánia", "Oskar", "Ľubomíra", "Vavrinec", "Zuzana",
        "Darina", "Ľubomír", "Mojmír", "Marcela", "Leonard", "Milica",
        "Elena, Helena", "Lýdia", "Anabela", "Jana", "Tichomír", "Filip",
        "Bartolomej", "Ľudovít", "Samuel", "Silvia", "Augustín", "Nikola, Nikolaj",
        "Ružena", "Nora",
    ],
    9: [
        "Drahoslava", "Linda", "Belo", "Rozália", "Regína", "Alica", "Marianna",
        "Miriama", "Martina", "Oleg", "Bystrík", "Mária", "Ctibor", "Ľudomil",
        "Jolana", "Ľudmila", "Olympia", "Eugénia", "Konštantín",
        "Ľuboslav, Ľuboslava", "Matúš", "Móric", "Zdenka", "Ľuboš, Ľubor",
        "Vladislav", "Edita", "Cyprián", "Václav", "Michal, Michaela", "Jarolím",
    ],
    10: [
        "Arnold", "Levoslav", "Stela", "František", "Viera", "Natália", "Eliška",
        "Brigita", "Dionýz", "Slavomíra", "Valentína", "Maximilián", "Koloman",
        "Boris", "Terézia", "Vladimíra", "Hedviga", "Lukáš", "Kristián",
        "Vendelín", "Uršuľa", "Sergej", "Alojzia", "Kvetoslava", "Aurel",
        "Demeter", "Sabína", "Dobromila", "Klára", "Šimon, Simona", "Aurélia",
    ],
    11: [
        "Denis, Denisa", "", "Hubert", "Karol", "Imrich", "Renáta", "René",
        "Bohumír", "Teodor", "Tibor", "Martin, Maroš", "Svätopluk", "Stanislav",
        "Irma", "Leopold", "Agnesa", "Klaudia", "Eugen", "Alžbeta", "Félix",
        "Elvíra", "Cecília", "Klement", "Emília", "Katarína", "Kornel", "Milan",
        "Henrieta", "Vratko", "Ondrej, Andrej",
    ],
    12: [
        "Edmund", "Bibiána", "Oldrich", "Barbora", "Oto", "Mikuláš", "Ambróz",
        "Marína", "Izabela", "Radúz", "Hilda", "Otília", "Lucia",
        "Branislava, Bronislava", "Ivica", "Albína", "Kornélia", "Sláva, Slávka",
        "Judita", "Dagmara", "Bohdan", "Adela", "Nadežda", "Adam, Eva", "",
        "Štefan", "Filoména", "Ivana, Ivona", "Milada", "Dávid", "Silvester",
    ],
}


def easter_sunday(year):
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
    return date(year, month, day)


def get_day_footer_text(d):
    """Vráti reťazec so sviatkom a/alebo meninami pre daný dátum."""
    easter = easter_sunday(d.year)
    movable = {
        easter - timedelta(days=2): "Veľký piatok",
        easter: "Veľkonočná nedeľa",
        easter + timedelta(days=1): "Veľkonočný pondelok",
    }

    holiday = movable.get(d) or SVIATKY_SK.get((d.month, d.day), "")
    month_names = MENINY_BY_MONTH.get(d.month, [])
    nameday = month_names[d.day - 1] if 1 <= d.day <= len(month_names) else ""

    if holiday and nameday:
        return f"Sviatok: {holiday} · Meniny: {nameday}"
    if holiday:
        return f"Sviatok: {holiday}"
    if nameday:
        return f"Meniny: {nameday}"
    return ""


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
    # Odstránenie typických RSS / WordPress / TouchIT dodatkov
    text = re.sub(
        r"\s*(?:"
        r"Čítajte viac|Viac sa dočítate|Celý článok|"
        r"Článok\s+.*?\s+je zobrazený ako prvý na|"
        r"Príspevok\s+.*?\s+sa (?:prvýkrát|najprv) objavil|"
        r"The post\s+.*?\s+appeared first"
        r").*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip()

    if is_summary and text:
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


def is_unwanted_article(title, summary):
    """Vyradí video články, živé/online prenosy, galérie, podcasty a kvízy."""
    return bool(UNWANTED_RE.search(title) or UNWANTED_RE.search(summary))


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


def score_article(art, now):
    """
    Ohodnotí pridanú hodnotu a informačnú bohatosť článku:
    - Uprednostňuje vecné, viacvetné správy s konkrétnymi údajmi.
    - Penalizuje krátke 1-vetové útržky, vytrhnuté vety a clickbait.
    """
    title = art["title"]
    summary = art["summary"]
    s_len = len(summary)
    sentences = split_sentences(summary)
    n_sent = len(sentences)

    score = 0.0

    # 1. Informačná hustota a dĺžka perexu
    if s_len == 0:
        score -= 60
    elif s_len < 85:
        score -= 35
    elif s_len < 130:
        score -= 10
    elif s_len <= 420:
        score += 32 + min(14, (s_len - 130) / 18.0)
    else:
        score += 36  # Bohatý perex (prípadne sa oreže po celých vetách)

    # 2. Viac vetné vysvetlenie (kontext + dopad)
    if n_sent >= 2:
        score += 18
    elif n_sent == 1 and s_len < 120:
        score -= 15

    # 3. Kompletnosť bez pôvodného RSS useknutia
    if summary and not art["raw_cut"]:
        score += 12

    # 4. Penalizácia vytrhnutých agentúrnych viet bez kontextu ("Zároveň upozornil...")
    if summary and DANGLING_START_RE.search(summary):
        score -= 28

    # 5. Penalizácia clickbaitu a otázok typu "Zistite..."
    if CLICKBAIT_RE.search(f"{title} {summary}"):
        score -= 26
    if title.endswith("?") and s_len < 140:
        score -= 10

    # 6. Bonus za konkrétne fakty, čísla a analytické kľúčové slová
    factual_hits = len(FACTUAL_SIGNALS_RE.findall(f"{title} {summary}"))
    score += min(18, factual_hits * 4)

    # 7. Mierny bonus za čerstvosť (aby kvalita vždy prevážila nad prázdnou novinkou)
    age_hours = max(0.0, (now - art["dt"]).total_seconds() / 3600.0)
    score += max(0.0, 10.0 - age_hours * 0.7)

    return round(score, 1)


def fetch_single_feed(feed_cfg, today, now, per_feed_limit=20):
    source, groups, url = feed_cfg
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

        if not title or len(title) < 15:
            continue
        if is_unwanted_article(title, summary):
            continue

        dt = parse_date(pub_raw)
        if dt is None:
            continue
        if ONLY_TODAY and dt.date() != today:
            continue

        key = normalize_key(title)
        if summary and normalize_key(summary) == key:
            summary = ""

        raw_plain = re.sub(r"<[^>]+>", "", html.unescape(raw_summary)).strip() if raw_summary else ""
        raw_cut = bool(raw_plain and re.search(r"(\[\s*(?:\.\.\.|…)\s*\]|\.\.\.|…)\s*$", raw_plain))

        art = {
            "key": key,
            "source": source,
            "groups": set(groups),
            "title": title,
            "summary": summary,
            "raw_cut": raw_cut,
            "dt": dt,
        }
        art["score"] = score_article(art, now)
        results.append(art)
        count += 1

    return results


def fetch_articles(feeds, per_feed_limit=20):
    now = datetime.now(TZ_LOCAL)
    today = now.date()
    all_raw = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(fetch_single_feed, cfg, today, now, per_feed_limit)
            for cfg in feeds
        ]
        for fut in as_completed(futures):
            all_raw.extend(fut.result())

    # Deduplikácia so zachovaním verzie s vyšším informačným skóre
    all_raw.sort(key=lambda x: (x["score"], x["dt"].timestamp()), reverse=True)
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


def pick_best_for_category(articles, cat_key, used_keys, min_score=None):
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

    candidates.sort(key=lambda a: (a["score"], a["dt"].timestamp()), reverse=True)
    if min_score is not None:
        quality = [a for a in candidates if a["score"] >= min_score]
        if not quality:
            return None
        return quality[0]

    return candidates[0]


def select_three_articles(articles):
    """
    Vyberie 3 správy s najvyššou pridanou hodnotou:
    1. HLAVNÁ SPRÁVA: najsilnejší vecný článok z kľúčových kategórií (Svet, Ekonomika, AI/Tech, Veda).
    2. + 3. DOPLNKOVÉ SPRÁVY: 2 kvalitné správy zo zvyšných hlavných kategórií (mixovaných podľa hodiny);
       záložné kategórie zaskočia iba vtedy, ak hlavné kategórie nemajú dostatok kvalitných správ.
    """
    if not articles:
        return []

    now = datetime.now(TZ_LOCAL)
    rotation_seed = now.timetuple().tm_yday * 24 + now.hour

    def rotated(items):
        offset = rotation_seed % len(items)
        return items[offset:] + items[:offset]

    used_keys = set()
    used_cats = set()

    # --- 1. Výber HLAVNEJ SPRÁVY s najvyššou pridanou hodnotou ---
    lead_candidates = []
    for label, key in MAIN_CATEGORIES:
        art = pick_best_for_category(articles, key, used_keys, min_score=15)
        if art is not None:
            lead_score = art["score"] + LEAD_PRIORITY_BONUS.get(key, 0)
            lead_candidates.append((lead_score, label, key, False, art))

    if not lead_candidates:
        for label, key in FALLBACK_CATEGORIES:
            art = pick_best_for_category(articles, key, used_keys, min_score=10)
            if art is not None:
                lead_score = art["score"] + LEAD_PRIORITY_BONUS.get(key, 0)
                lead_candidates.append((lead_score, label, key, True, art))

    # Posledná poistka (napr. veľmi skoro ráno) bez prahu min_score
    if not lead_candidates:
        for is_fb, cat_list in ((False, MAIN_CATEGORIES), (True, FALLBACK_CATEGORIES)):
            for label, key in cat_list:
                art = pick_best_for_category(articles, key, used_keys, min_score=None)
                if art is not None:
                    lead_score = art["score"] + LEAD_PRIORITY_BONUS.get(key, 0)
                    lead_candidates.append((lead_score, label, key, is_fb, art))
            if lead_candidates:
                break

    if not lead_candidates:
        return []

    lead_candidates.sort(key=lambda x: (x[0], x[4]["dt"].timestamp()), reverse=True)
    _, lead_label, lead_key, lead_fb, lead_art = lead_candidates[0]
    lead_entry = dict(lead_art, display_tag=lead_label, is_fallback=lead_fb)
    used_keys.add(lead_art["key"])
    used_cats.add(lead_key)

    # --- 2. Výber 2 DOPLNKOVÝCH SPRÁV (mix zo zvyšných hlavných, potom záložné) ---
    extras = []
    remaining_main = [(l, k) for l, k in rotated(MAIN_CATEGORIES) if k not in used_cats]
    remaining_fb = [(l, k) for l, k in rotated(FALLBACK_CATEGORIES) if k not in used_cats]

    # Najprv hľadáme kvalitné články (min_score=15) z hlavných kategórií
    main_pool = []
    for order_idx, (label, key) in enumerate(remaining_main):
        art = pick_best_for_category(articles, key, used_keys, min_score=15)
        if art is not None:
            # Kombinácia kvality a jemného mixovania kategórií podľa hodiny
            mix_score = art["score"] - order_idx * 3.0
            main_pool.append((mix_score, label, key, art))

    main_pool.sort(key=lambda x: x[0], reverse=True)
    for _, label, key, art in main_pool:
        if len(extras) >= TOTAL_ARTICLES - 1:
            break
        if art["key"] in used_keys:
            continue
        extras.append(dict(art, display_tag=label, is_fallback=False))
        used_keys.add(art["key"])
        used_cats.add(key)

    # Ak hlavné kategórie nedali 2 kvalitné správy, doplníme kvalitné zo záložných
    if len(extras) < TOTAL_ARTICLES - 1:
        fb_pool = []
        for order_idx, (label, key) in enumerate(remaining_fb):
            art = pick_best_for_category(articles, key, used_keys, min_score=10)
            if art is not None:
                mix_score = art["score"] - order_idx * 3.0
                fb_pool.append((mix_score, label, key, art))
        fb_pool.sort(key=lambda x: x[0], reverse=True)
        for _, label, key, art in fb_pool:
            if len(extras) >= TOTAL_ARTICLES - 1:
                break
            if art["key"] in used_keys:
                continue
            extras.append(dict(art, display_tag=label, is_fallback=True))
            used_keys.add(art["key"])
            used_cats.add(key)

    # Záchranný priechod bez prahu skóre (iba skoro ráno pri malom počte dnešných správ)
    if len(extras) < TOTAL_ARTICLES - 1:
        for is_fb, cat_list in ((False, remaining_main), (True, remaining_fb)):
            for label, key in cat_list:
                if len(extras) >= TOTAL_ARTICLES - 1:
                    break
                if key in used_cats:
                    continue
                art = pick_best_for_category(articles, key, used_keys, min_score=None)
                if art is not None:
                    extras.append(dict(art, display_tag=label, is_fallback=is_fb))
                    used_keys.add(art["key"])
                    used_cats.add(key)

    selected = [lead_entry] + extras
    for idx, art in enumerate(selected, start=1):
        role = "ZÁLOHA" if art["is_fallback"] else "HLAVNÁ KAT."
        pos = "HLAVNÁ SPRÁVA" if idx == 1 else ("ĽAVÝ STĹPEC" if idx == 2 else "PRAVÝ STĹPEC")
        print(
            f"{pos} [{role}: {art['display_tag']} | skóre {art['score']}]: "
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


def build_block(draw, art, preset, max_width, is_lead):
    f_title = preset["lead_title"] if is_lead else preset["col_title"]
    f_body = preset["lead_body"] if is_lead else preset["col_body"]
    lh_title = preset["lead_lh_t"] if is_lead else preset["col_lh_t"]
    lh_body = preset["lead_lh_b"] if is_lead else preset["col_lh_b"]
    badge_h = preset["lead_badge_h"] if is_lead else preset["col_badge_h"]
    gap_badge = preset["gap_badge"]
    gap_title = preset["gap_title"]

    t_lines = wrap_text_full(draw, art["title"], f_title, max_width)
    s_lines = wrap_text_full(draw, art["summary"], f_body, max_width) if art["summary"] else []

    h = badge_h + gap_badge + len(t_lines) * lh_title
    if s_lines:
        h += gap_title + len(s_lines) * lh_body

    return {
        "art": art,
        "is_lead": is_lead,
        "t_lines": t_lines,
        "s_lines": s_lines,
        "f_title": f_title,
        "f_body": f_body,
        "lh_title": lh_title,
        "lh_body": lh_body,
        "badge_h": badge_h,
        "gap_badge": gap_badge,
        "gap_title": gap_title,
        "height": h,
    }


def fit_1_plus_2_layout(draw, articles, presets, full_w, col_w, avail_h):
    """
    Nájde najčitateľnejšiu sadu písiem, pri ktorej sa zmestí 1 hlavná správa (celá šírka)
    + 2 stĺpcové správy pod ňou CELÉ bez '...'.
    """
    min_div_gap = 18

    def measure(arts, preset):
        lead_blk = build_block(draw, arts[0], preset, full_w, is_lead=True)
        col_blks = [build_block(draw, a, preset, col_w, is_lead=False) for a in arts[1:3]]
        bottom_h = max((b["height"] for b in col_blks), default=0)
        total_h = lead_blk["height"] + (min_div_gap + bottom_h if col_blks else 0)
        return lead_blk, col_blks, total_h

    for p_idx, preset in enumerate(presets):
        lead_blk, col_blks, total_h = measure(articles, preset)
        if total_h <= avail_h:
            return lead_blk, col_blks, preset, p_idx + 1

    # Ak by bol niektorý RSS perex extrémne dlhý, uberáme po celých vetách (nikdy na '...')
    preset = presets[-1]
    trimmed = [dict(a) for a in articles]

    while True:
        lead_blk, col_blks, total_h = measure(trimmed, preset)
        if total_h <= avail_h:
            return lead_blk, col_blks, preset, len(presets)

        # Vyberieme najdlhší viacvetný perex z blokov, ktoré najviac tlačia na výšku
        candidates = []
        for idx, art in enumerate(trimmed):
            sents = split_sentences(art["summary"])
            if len(sents) > 1:
                candidates.append((idx, sents))

        if candidates:
            target_i, sents = max(candidates, key=lambda x: len(trimmed[x[0]]["summary"]))
            trimmed[target_i]["summary"] = " ".join(sents[:-1]).strip()
            continue

        return lead_blk, col_blks, preset, len(presets)


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
    f_footer = load_font(sans_bold, 11)

    # Sady písiem od najčitateľnejšej po kompaktnejšiu (pre 3 správy je dosť miesta na veľké písmo)
    presets = [
        {
            "badge_lead": load_font(sans_bold, 11),
            "badge_col": load_font(sans_bold, 11),
            "meta_lead": load_font(sans_bold, 12),
            "meta_col": load_font(sans_bold, 11),
            "lead_title": load_font(sans_bold, 21),
            "lead_body": load_font(sans_reg, 15),
            "col_title": load_font(sans_bold, 16),
            "col_body": load_font(sans_reg, 14),
            "lead_badge_h": 19,
            "col_badge_h": 17,
            "lead_lh_t": 25,
            "lead_lh_b": 19,
            "col_lh_t": 20,
            "col_lh_b": 18,
            "gap_badge": 6,
            "gap_title": 6,
        },
        {
            "badge_lead": load_font(sans_bold, 11),
            "badge_col": load_font(sans_bold, 10),
            "meta_lead": load_font(sans_bold, 12),
            "meta_col": load_font(sans_bold, 11),
            "lead_title": load_font(sans_bold, 19),
            "lead_body": load_font(sans_reg, 14),
            "col_title": load_font(sans_bold, 15),
            "col_body": load_font(sans_reg, 13),
            "lead_badge_h": 18,
            "col_badge_h": 16,
            "lead_lh_t": 23,
            "lead_lh_b": 17,
            "col_lh_t": 18,
            "col_lh_b": 16,
            "gap_badge": 5,
            "gap_title": 5,
        },
        {
            "badge_lead": load_font(sans_bold, 10),
            "badge_col": load_font(sans_bold, 10),
            "meta_lead": load_font(sans_bold, 11),
            "meta_col": load_font(sans_bold, 10),
            "lead_title": load_font(sans_bold, 17),
            "lead_body": load_font(sans_reg, 13),
            "col_title": load_font(sans_bold, 14),
            "col_body": load_font(sans_reg, 12),
            "lead_badge_h": 16,
            "col_badge_h": 15,
            "lead_lh_t": 20,
            "lead_lh_b": 16,
            "col_lh_t": 17,
            "col_lh_b": 15,
            "gap_badge": 4,
            "gap_title": 4,
        },
    ]

    now = datetime.now(TZ_LOCAL)
    margin_x = 16
    right_x = WIDTH - margin_x
    content_w = right_x - margin_x
    col_gap = 24
    col_w = (content_w - col_gap) // 2

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

    # --- 5. PÄTIČKA (MENINY / SVIATOK + POČASIE ŠAMORÍN) ---
    day_info = get_day_footer_text(now.date())

    def draw_footer():
        draw.line((margin_x, 456, right_x, 456), fill=0, width=1)
        if day_info:
            draw.text((margin_x, 468), day_info, font=f_footer, fill=0, anchor="lm")
        draw.text((right_x, 468), weather_str, font=f_footer, fill=0, anchor="rm")

    if not selected_articles:
        msg = (
            "Dnes zatiaľ neboli vydané nové správy."
            if ONLY_TODAY
            else "Nepodarilo sa načítať správy z RSS zdrojov."
        )
        draw.text((WIDTH // 2, HEIGHT // 2), msg, font=presets[0]["lead_title"], fill=0, anchor="mm")
        draw_footer()
        img.save(OUTPUT_FILE)
        print(f"Vygenerované: {OUTPUT_FILE} (0 správ | {day_info} | {weather_str})")
        return

    # --- 3. + 4. VÝPOČET A VYKRESLENIE (1 HLAVNÁ + 2 STĹPCE POD ŇOU) ---
    top_y = 82
    bottom_y = 450
    avail_h = bottom_y - top_y

    lead_blk, col_blks, preset, used_preset_num = fit_1_plus_2_layout(
        draw, selected_articles, presets, content_w, col_w, avail_h
    )

    def draw_article_block(blk, x, y, show_lead_label=False):
        art = blk["art"]
        is_lead = blk["is_lead"]
        f_badge = preset["badge_lead"] if is_lead else preset["badge_col"]
        f_meta = preset["meta_lead"] if is_lead else preset["meta_col"]
        badge_h = blk["badge_h"]

        badge_txt = f" {art['display_tag']} "
        badge_w = int(draw.textlength(badge_txt, font=f_badge)) + 8
        draw.rectangle((x, y, x + badge_w, y + badge_h), fill=0)
        draw.text((x + 4, y + badge_h // 2), badge_txt, font=f_badge, fill=1, anchor="lm")

        meta_str = f"{art['dt'].strftime('%H:%M')} · {art['source'].upper()}"
        draw.text((x + badge_w + 10, y + badge_h // 2), meta_str, font=f_meta, fill=0, anchor="lm")

        if show_lead_label:
            draw.text((right_x, y + badge_h // 2), "HLAVNÁ SPRÁVA", font=preset["meta_col"], fill=0, anchor="rm")

        cy = y + badge_h + blk["gap_badge"]
        for line in blk["t_lines"]:
            draw.text((x, cy), line, font=blk["f_title"], fill=0)
            cy += blk["lh_title"]

        if blk["s_lines"]:
            cy += blk["gap_title"]
            for line in blk["s_lines"]:
                draw.text((x, cy), line, font=blk["f_body"], fill=0)
                cy += blk["lh_body"]

        return cy

    # Vyvážené zvislé rozloženie medzi hlavnou správou a spodnými stĺpcami
    bottom_h = max((b["height"] for b in col_blks), default=0)
    extra_h = max(0, avail_h - lead_blk["height"] - bottom_h)

    if col_blks:
        div_gap = min(28, max(18, extra_h // 2))
        lead_y = top_y + min(8, max(0, (extra_h - div_gap) // 4))
    else:
        div_gap = 0
        lead_y = top_y

    # Vykreslenie HLAVNEJ SPRÁVY cez celú šírku
    lead_end_y = draw_article_block(lead_blk, margin_x, lead_y, show_lead_label=True)

    # Vykreslenie 2 DOPLNKOVÝCH SPRÁV pod ňou (ľavý a pravý stĺpec)
    if col_blks:
        div_y = lead_end_y + div_gap // 2
        draw.line((margin_x, div_y, right_x, div_y), fill=0, width=2)

        cols_top_y = lead_end_y + div_gap
        draw.line((WIDTH // 2, div_y + 10, WIDTH // 2, bottom_y - 2), fill=0, width=1)

        col_xs = [margin_x, WIDTH // 2 + col_gap // 2]
        for blk, cx in zip(col_blks, col_xs):
            draw_article_block(blk, cx, cols_top_y, show_lead_label=False)

    draw_footer()

    img.save(OUTPUT_FILE)
    print(
        f"Vygenerované: {OUTPUT_FILE} ({1 + len(col_blks)}/{TOTAL_ARTICLES} správ | "
        f"Písmo: sada {used_preset_num} | {day_info} | {weather_str})"
    )


if __name__ == "__main__":
    all_articles = fetch_articles(FEEDS)
    selected = select_three_articles(all_articles)
    weather = fetch_weather()
    render_dashboard(selected, weather)