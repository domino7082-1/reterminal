import gzip
import html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

# --- KONFIGURÁCIA ---
WIDTH, HEIGHT = 800, 480
OUTPUT_FILE = "world_news_output.bmp"
CACHE_FILE = "summary_cache.json"
CAROUSEL_STATE_KEY = "__carousel__"
RECENT_HISTORY_LIMIT = 18
TZ_LOCAL = ZoneInfo("Europe/Bratislava")
NEWSPAPER_TITLE = "SVETOVÝ DENNÍK"

# Rozloženie: 3 rovnocenné správy pod sebou na celú šírku (písmo 17 / 14 px)
TOTAL_ARTICLES = 3

# Zobrazovať prísne len správy vydané v aktuálny deň
ONLY_TODAY = True

# Súradnice pre počasie (Šamorín)
WEATHER_CITY = "Šamorín"
WEATHER_LAT = 48.0279
WEATHER_LON = 17.3106

# AI konfigurácia (kľúče sa načítajú bezpečne z GitHub Secrets)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-3.8-flash"]
GROQ_FALLBACK_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
APP_UA = "EInkSvetovyDennik/2.3 github.com/domino7082-1"

# Interný stav behu (zabraňuje opakovanému skúšaniu nefunkčných modelov a 429 na doménach)
_DEAD_GEMINI_MODELS = set()
_DEAD_GROQ_MODELS = set()
_DISCOVERED_GEMINI_MODELS = None
_DISCOVERED_GROQ_MODELS = None
_DOMAIN_LOCKS = {}
_DOMAIN_LAST_HIT = {}
_DOMAIN_META_LOCK = threading.Lock()

# Svetové časy v hlavičke (Názov, IANA časové pásmo)
WORLD_CLOCKS = [
    ("BRATISLAVA", "Europe/Bratislava"),
    ("LONDÝN", "Europe/London"),
    ("NEW YORK", "America/New_York"),
    ("TOKIO", "Asia/Tokyo"),
]

# 10 rovnocenných kategórií v poradí plynulého kolotoča (príbuzné témy sú od seba oddelené)
CATEGORIES = [
    ("SVET", "svet"),
    ("AI A TECH", "ai_tech"),
    ("ŠPORT", "sport"),
    ("DOMOV", "domov"),
    ("VEDA A VESMÍR", "veda_vesmir"),
    ("EKONOMIKA A TRHY", "ekonomika"),
    ("ZDRAVIE A PRÍRODA", "zdravie_priroda"),
    ("GADGETY A IT", "gadgety_it"),
    ("AUTO A MOBILITA", "auto"),
    ("ENERGIE A BÝVANIE", "energie_byvanie"),
]

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
    # TECH / AI / GADGETY
    ("Živé.sk", ("tech",), "https://zive.aktuality.sk/rss/najnovsie/"),
    ("SME Tech", ("tech",), "https://tech.sme.sk/rss"),
    ("TouchIT", ("tech",), "https://touchit.sk/feed/"),
    # VEDA A VESMÍR
    ("Denník N", ("veda",), "https://dennikn.sk/veda/feed/"),
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
        r"\bo2\b", "4ka", "internet", "wi-fi", "aktualizáci", "konzol",
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

# Vzory pre vyradenie videí, online prenosov, galérií, nákupných poradní, darčekových tipov a PR obsahu
UNWANTED_RE = re.compile(
    r"(?:"
    r"\(\s*\+?\s*video\s*\)|\[\s*video\s*\]|\bvideo\b|\bvideoreportáž|\bvideorozhovor"
    r"|pozrite\s+si\s+(?:video|záznam)|vo\s+videu|v\s+priloženom\s+videu"
    r"|\bpodcast\b|\bfotogaléri|\(\s*\+?\s*foto\s*\)|\bfoto\s*:"
    r"|^online\b|\bonline\s*:|\bonline\s+prenos|\bpriamy\s+prenos|\bsledujte\s+naživo"
    r"|\bminúta\s+po\s+minúte|^live\b|\blive\s*:|^naživo\b|\bnaživo\s*:"
    r"|kde\s+sledovať|\bkurzy\b|tipy\s+na\s+stávk|\bkvíz\b|\banketa\b|\bhoroskop\b|\bsúťaž\b"
    r"|\bporadňa\s*:|vianočn[áýéo]\s+(?:poradň|sprievodc|tipy|darček|nákup)"
    r"|nákupn[ýáéí]\s+sprievodc|sprievodc[au]\s+(?:výberom|nákupom|darček)"
    r"|(?:^|:\s*)vyberáme\b|pod\s+stromček|tipy\s+na\s+darček|darček(?:y|ov)?\s+pre\b"
    r"|ako\s+vybrať\s+(?:správn|najlepš|nov|smart|mobil|notebook|hodink|darček|televízor|slúchadl)"
    r"|black\s+friday|cyber\s+monday|za\s+super\s+cenu|akciov[áýé]\s+ponuk"
    r"|\b(?:pr|komerčný|sponzorovaný)\s+článok\b|platen[áýé]\s+spoluprác|\bpartner\s+článku\b"
    r"|\b(?:top|najlepších)\s+\d+\s+(?:tipov|darčekov|modelov|smartfónov|hodiniek|aplikácií|filmov|seriálov)"
    r")",
    re.IGNORECASE,
)

# Slabé clickbaitové alebo prázdne formulácie
CLICKBAIT_RE = re.compile(
    r"(?:zistite[, ]|pozrite\s+si|neuveríte|šokujúc|toto\s+ste\s+nevedeli|"
    r"vyzerajú\s+tak\s+strašne|nikdy\s+nerobte|týchto\s+\d+\s+vecí|rebríček\s+naj)",
    re.IGNORECASE,
)

# Formulácie typické pre upútavky, ktoré zamlčujú pointu do tela článku
TEASER_RE = re.compile(
    r"(?:o\s+tom,\s*(?:prečo|ako|čo)|vysvetľuje,\s*(?:prečo|ako)|prezradil|"
    r"urobili\s+presne\s+to,\s*čo\s+mali|týždeň\s+v(?:o)?\s+svetovej|rozhovor\s*:)",
    re.IGNORECASE,
)

# Meta-opisy bez konkrétnych faktov (keď text len opisuje, o čom je sprievodca/článok)
META_SUMMARY_RE = re.compile(
    r"(?:"
    r"\btento\s+(?:vianočný\s+|nákupný\s+)?(?:článok|sprievodca|prehľad|zoznam|test|výber|text|rozhovor)\b"
    r"|\b(?:vianočný|nákupný)\s+sprievodca\b"
    r"|\bčlánok\s+(?:podrobne\s+|tiež\s+|zároveň\s+)?(?:hodnotí|porovnáva|predstavuje|prináša|ponúka|zhŕňa|sa\s+venuje|vysvetľuje|radí|ukazuje)\b"
    r"|\b(?:sprievodca|prehľad|autor)\s+(?:uľahčuje\s+výber|porovnáva|radí,\s*ako\s+vybrať|ponúka\s+tipy)\b"
    r"|\b(?:dozviete\s+sa|viac\s+si\s+prečítate|nájdete\s+v\s+článku)\b"
    r")",
    re.IGNORECASE,
)

# Perexy začínajúce ako vytrhnutá druhá veta bez kontextu
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

# Znaky platobnej brány (paywallu) v texte článku
PAYWALL_RE = re.compile(
    r"(?:tento\s+článok\s+je\s+(?:zamknutý|dostupný\s+len\s+pre\s+predplatiteľov)|"
    r"odomknite\s+si\s+(?:tento\s+článok|celý\s+článok|prístup)|"
    r"pokračujte\s+v\s+čítaní\s+s\s+predplatným|"
    r"pridajte\s+sa\s+k\s+predplatiteľom|staňte\s+sa\s+predplatiteľom|"
    r"čítajte\s+bez\s+obmedzení\s+s\s+predplatným|"
    r"obsah\s+je\s+prístupný\s+iba\s+predplatiteľom)",
    re.IGNORECASE,
)

# Vata na stránkach, ktorá nepatrí do tela článku
BOILERPLATE_P_RE = re.compile(
    r"(?:súbory\s+cookie|cookies|ochrana\s+osobných\s+údajov|všetky\s+práva\s+vyhradené|"
    r"prihláste\s+sa\s+na\s+odber|newsletter|zdieľať\s+článok|súvisiace\s+články|"
    r"čítajte\s+aj:|prečítajte\s+si\s+aj|reklama|inzercia|copyright|©|"
    r"viac\s+si\s+prečítate\s+v\s+našej|predplatné\s+sme|predplatné\s+denníka)",
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

# Slovenský preklad symbolov pre zálohu 1 (Yr.no / MET Norway)
METNO_SK = {
    "clearsky": "Jasno",
    "fair": "Skoro jasno",
    "partlycloudy": "Polooblačno",
    "cloudy": "Zamračené",
    "fog": "Hmla",
    "lightrain": "Slabý dážď",
    "rain": "Dážď",
    "heavyrain": "Silný dážď",
    "lightrainshowers": "Prehánky",
    "rainshowers": "Prehánky",
    "heavyrainshowers": "Silné prehánky",
    "lightsleet": "Dážď so snehom",
    "sleet": "Dážď so snehom",
    "heavysleet": "Dážď so snehom",
    "lightsleetshowers": "Prehánky so snehom",
    "sleetshowers": "Prehánky so snehom",
    "heavysleetshowers": "Prehánky so snehom",
    "lightsnow": "Slabé sneženie",
    "snow": "Sneženie",
    "heavysnow": "Silné sneženie",
    "lightsnowshowers": "Snehové prehánky",
    "snowshowers": "Snehové prehánky",
    "heavysnowshowers": "Snehové prehánky",
}

# Slovenský preklad WWO kódov pre zálohu 2 (wttr.in)
WTTR_SK = {
    113: "Jasno",
    116: "Polooblačno",
    119: "Zamračené",
    122: "Zamračené",
    143: "Hmla",
    176: "Prehánky",
    179: "Snehové prehánky",
    182: "Dážď so snehom",
    185: "Mrznúce mrholenie",
    200: "Búrka",
    227: "Sneženie",
    230: "Silné sneženie",
    248: "Hmla",
    260: "Hmla",
    263: "Mrholenie",
    266: "Mrholenie",
    281: "Mrznúce mrholenie",
    284: "Mrznúce mrholenie",
    293: "Slabý dážď",
    296: "Slabý dážď",
    299: "Dážď",
    302: "Dážď",
    305: "Silný dážď",
    308: "Silný dážď",
    311: "Mrznúci dážď",
    314: "Mrznúci dážď",
    317: "Dážď so snehom",
    320: "Dážď so snehom",
    323: "Slabé sneženie",
    326: "Slabé sneženie",
    329: "Sneženie",
    332: "Sneženie",
    335: "Silné sneženie",
    338: "Silné sneženie",
    350: "Snehové zrná",
    353: "Prehánky",
    356: "Silné prehánky",
    359: "Silný dážď",
    362: "Dážď so snehom",
    365: "Dážď so snehom",
    368: "Snehové prehánky",
    371: "Snehové prehánky",
    374: "Krúpy",
    377: "Krúpy",
    386: "Búrka",
    389: "Búrka",
    392: "Búrka so snehom",
    395: "Búrka so snehom",
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


# --- POMOCNÉ FUNKCIE: KALENDÁR, TEXT, HTTP ---

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
    text = re.sub(
        r"\s*(?:"
        r"Čítajte viac|Viac sa dočítate|Viac si prečítate|Celý článok|"
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
    """Vyradí videá, online prenosy, galérie, nákupné poradne, darčekové tipy a PR obsah."""
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


def _root_domain(url):
    host = (urlparse(url).hostname or "").lower()
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _throttle_domain(url, min_interval=0.8):
    """Zabraňuje chybám 429 (najmä na sme.sk) pri paralelnom sťahovaní viacerých rubrík."""
    dom = _root_domain(url)
    effective_interval = 2.2 if dom == "sme.sk" else min_interval
    with _DOMAIN_META_LOCK:
        lock = _DOMAIN_LOCKS.setdefault(dom, threading.Lock())
    with lock:
        now_t = time.monotonic()
        last = _DOMAIN_LAST_HIT.get(dom, 0.0)
        wait = effective_interval - (now_t - last)
        if wait > 0:
            time.sleep(wait)
        _DOMAIN_LAST_HIT[dom] = time.monotonic()


def http_get_text(url, timeout=10, extra_headers=None, throttle=False):
    if throttle:
        _throttle_domain(url)
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "sk,cs;q=0.9,en;q=0.5",
        "Accept-Encoding": "gzip",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding", "").lower() == "gzip":
            raw = gzip.decompress(raw)
        charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


# --- SŤAHOVANIE PLNÉHO TEXTU ČLÁNKOV + CACHE + AI ZHRNUTIE ---

class ArticleParagraphExtractor(HTMLParser):
    """Jednoduchý extraktor odsekov z HTML stránky bez externých knižníc."""

    SKIP_TAGS = {
        "script", "style", "noscript", "nav", "header", "footer",
        "aside", "form", "button", "figure", "figcaption", "iframe", "svg",
    }

    def __init__(self):
        super().__init__()
        self.skip_depth = 0
        self.in_p = False
        self.buf = []
        self.paragraphs = []

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in self.SKIP_TAGS:
            self.skip_depth += 1
        elif t == "p" and self.skip_depth == 0:
            self.in_p = True
            self.buf = []

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in self.SKIP_TAGS and self.skip_depth > 0:
            self.skip_depth -= 1
        elif t == "p" and self.in_p:
            self.in_p = False
            text = re.sub(r"\s+", " ", html.unescape("".join(self.buf))).strip()
            if len(text) >= 40 and not BOILERPLATE_P_RE.search(text):
                self.paragraphs.append(text)
            self.buf = []

    def handle_data(self, data):
        if self.in_p and self.skip_depth == 0:
            self.buf.append(data)


def fetch_article_body(url):
    """
    Stiahne a vyčistí text článku z webu.
    Vráti dvojicu (text, is_paywalled).
    """
    if not url:
        return "", False
    try:
        page_html = http_get_text(url, timeout=10, throttle=True)
    except Exception as e:
        print(f"Nepodarilo sa stiahnuť článok ({url}): {e}")
        return "", False

    parser = ArticleParagraphExtractor()
    try:
        parser.feed(page_html)
    except Exception:
        return "", False

    seen_p = set()
    clean_p = []
    total_chars = 0
    for p in parser.paragraphs:
        norm = p[:80].lower()
        if norm in seen_p:
            continue
        seen_p.add(norm)
        clean_p.append(p)
        total_chars += len(p)
        if total_chars >= 4500:
            break

    body_text = "\n".join(clean_p)
    has_paywall_hint = bool(PAYWALL_RE.search(page_html))
    is_paywalled = has_paywall_hint and len(body_text) < 1200
    return body_text, is_paywalled


def load_summary_cache(today):
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        cutoff = (today - timedelta(days=2)).isoformat()
        cleaned = {}
        for k, v in data.items():
            if not isinstance(v, dict):
                continue
            if k == CAROUSEL_STATE_KEY:
                cleaned[k] = v
            elif v.get("date", "") >= cutoff:
                cleaned[k] = v
        return cleaned
    except Exception as e:
        print(f"Chyba pri čítaní cache ({CACHE_FILE}): {e}")
        return {}


def save_summary_cache(cache):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as e:
        print(f"Chyba pri ukladaní cache ({CACHE_FILE}): {e}")


AI_SYSTEM_PROMPT = (
    "Si prísny a vecný slovenský spravodajský editor pre E-Ink noviny. "
    "Tvojou úlohou je napísať ucelené, samostatne zrozumiteľné faktické zhrnutie článku po slovensky. "
    "Pravidlá:\n"
    "1. Napíš presne 2 až 3 hutné, úplné vety v rozsahu približne 200 až 290 znakov (maximálne 320 znakov).\n"
    "2. Píš priamo konkrétne fakty, čísla, zistenia a pointu: čo presne sa stalo, prečo a aký je výsledok alebo dopad.\n"
    "3. Nikdy neopisuj článok zvonka. Prísne zakázané sú frázy ako 'Tento článok', 'Tento sprievodca', 'Článok hodnotí/porovnáva/sa venuje', 'dozviete sa', 'viac si prečítate'.\n"
    "4. Vychádzaj výhradne z poskytnutého textu, nič si nevymýšľaj. Žiadne odrážky, žiadny markdown, žiadne tri bodky na konci.\n"
    "5. Ak je text zjavne neúplný alebo zamknutý (paywall) a neobsahuje odpoveď ani rozuzlenie, odpovedz presne jediným slovom: PAYWALL\n"
    "6. Ak nejde o skutočnú správu, udalosť, objav ani konkrétne zistenie, ale iba o nákupného sprievodcu, poradňu pri výbere, tipy na darčeky, katalóg/porovnanie produktov, promo/PR článok, zľavovú akciu alebo prázdnu upútavku bez reálnej informačnej hodnoty, odpovedz presne jediným slovom: SKIP"
)


def _clean_ai_output(text):
    if not text:
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"\*{1,2}|`", "", text)
    text = re.sub(r"\s+", " ", text).strip().strip('"„“\'')
    upper = text.upper()
    if upper.startswith("PAYWALL"):
        return "PAYWALL"
    if upper.startswith("SKIP"):
        return "SKIP"
    if re.search(r"(\.\.\.|…)\s*$", text):
        stripped = re.sub(r"\s*(\.\.\.|…)\s*$", "", text).strip()
        sents = split_sentences(stripped)
        complete = [s for s in sents if s and s[-1] in ".!?"]
        text = " ".join(complete) if complete else stripped.rstrip(",;:–—- ") + "."
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _discover_gemini_models():
    """Dynamicky zistí dostupné Gemini Flash modely, ak by sa názvy v budúcnosti zmenili."""
    global _DISCOVERED_GEMINI_MODELS
    if _DISCOVERED_GEMINI_MODELS is not None:
        return _DISCOVERED_GEMINI_MODELS

    found = []
    try:
        req = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": GEMINI_API_KEY, "User-Agent": APP_UA},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        exclude = ("tts", "image", "audio", "embedding", "robotics", "computer-use", "live", "veo")
        for m in data.get("models") or []:
            methods = m.get("supportedGenerationMethods") or []
            if "generateContent" not in methods:
                continue
            mid = (m.get("name") or "").replace("models/", "")
            low = mid.lower()
            if "gemini" not in low or any(x in low for x in exclude):
                continue
            found.append(mid)

        def rank_gemini(mid):
            low = mid.lower()
            is_lite = 0 if "flash-lite" in low else (1 if "flash" in low else 2)
            ver_match = re.search(r"gemini-(\d+(?:\.\d+)?)", low)
            ver = float(ver_match.group(1)) if ver_match else 0.0
            is_preview = 1 if ("preview" in low or "exp" in low) else 0
            return (is_lite, -ver, is_preview)

        found.sort(key=rank_gemini)
        if found:
            print(f"Auto-objavené Gemini modely: {', '.join(found[:4])}")
    except Exception as e:
        print(f"Chyba pri zisťovaní Gemini modelov: {e}")

    _DISCOVERED_GEMINI_MODELS = found[:4]
    return _DISCOVERED_GEMINI_MODELS


def _call_gemini(user_prompt):
    if not GEMINI_API_KEY:
        return None, None

    payload_base = {
        "system_instruction": {"parts": [{"text": AI_SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1024,
        },
    }
    body_bytes = json.dumps(payload_base).encode("utf-8")

    models_to_try = [m for m in GEMINI_MODELS if m not in _DEAD_GEMINI_MODELS]
    if not models_to_try:
        models_to_try = [m for m in _discover_gemini_models() if m not in _DEAD_GEMINI_MODELS]

    for phase in (1, 2):
        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            req = urllib.request.Request(
                url,
                data=body_bytes,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": GEMINI_API_KEY,
                    "User-Agent": APP_UA,
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates") or []
                if not candidates:
                    continue
                parts = candidates[0].get("content", {}).get("parts") or []
                answer_parts = [
                    p.get("text", "") for p in parts
                    if p.get("text") and not p.get("thought")
                ]
                out = _clean_ai_output(" ".join(answer_parts))
                if out:
                    return out, f"Gemini/{model}"
            except urllib.error.HTTPError as e:
                err_body = ""
                try:
                    err_body = e.read().decode("utf-8", errors="replace")[:220]
                except Exception:
                    pass
                print(f"Chyba Gemini [{model}] HTTP {e.code}: {err_body}")
                if e.code == 404:
                    _DEAD_GEMINI_MODELS.add(model)
            except Exception as e:
                print(f"Chyba Gemini [{model}]: {e}")

        if phase == 1 and all(m in _DEAD_GEMINI_MODELS for m in GEMINI_MODELS):
            models_to_try = [
                m for m in _discover_gemini_models()
                if m not in _DEAD_GEMINI_MODELS and m not in GEMINI_MODELS
            ]
            if not models_to_try:
                break
        else:
            break

    return None, None


def _discover_groq_models():
    """Dynamicky načíta aktuálne dostupné textové chat modely z Groq API."""
    global _DISCOVERED_GROQ_MODELS
    if _DISCOVERED_GROQ_MODELS is not None:
        return _DISCOVERED_GROQ_MODELS

    found = []
    try:
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "User-Agent": APP_UA},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        exclude = (
            "whisper", "tts", "audio", "guard", "safeguard", "moderation",
            "playai", "orpheus", "allam", "compound", "embed", "vision",
        )
        for m in data.get("data") or []:
            mid = m.get("id") or ""
            low = mid.lower()
            if not mid or any(x in low for x in exclude):
                continue
            if m.get("active") is False:
                continue
            found.append(mid)

        def rank_groq(mid):
            low = mid.lower()
            if "gpt-oss-120b" in low:
                return (0, mid)
            if "qwen" in low:
                return (1, mid)
            if "llama" in low and ("70b" in low or "maverick" in low or "scout" in low):
                return (2, mid)
            if "gpt-oss-20b" in low:
                return (3, mid)
            if "llama" in low:
                return (4, mid)
            return (5, mid)

        found.sort(key=rank_groq)
        if found:
            print(f"Auto-objavené Groq modely: {', '.join(found[:4])}")
    except Exception as e:
        print(f"Chyba pri zisťovaní Groq modelov: {e}")

    _DISCOVERED_GROQ_MODELS = found[:4] if found else list(GROQ_FALLBACK_MODELS)
    return _DISCOVERED_GROQ_MODELS


def _call_groq(user_prompt):
    if not GROQ_API_KEY:
        return None, None

    models_to_try = [m for m in _discover_groq_models() if m not in _DEAD_GROQ_MODELS]
    for model in models_to_try:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": AI_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 400,
        }
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "User-Agent": APP_UA,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices") or []
            if not choices:
                continue
            content = choices[0].get("message", {}).get("content", "")
            out = _clean_ai_output(content)
            if out:
                return out, f"Groq/{model}"
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:220]
            except Exception:
                pass
            print(f"Chyba Groq [{model}] HTTP {e.code}: {err_body}")
            if e.code == 404:
                _DEAD_GROQ_MODELS.add(model)
        except Exception as e:
            print(f"Chyba Groq [{model}]: {e}")

    return None, None


def summarize_article_with_ai(art, cache, today_iso):
    """
    Vytvorí alebo načíta z cache ucelené faktické AI zhrnutie článku.
    Vráti stav: ("ok", text, provider) | ("paywall", "", reason) | ("skip", "", reason) | ("fallback", rss, "RSS").
    """
    cache_key = art["url"] or art["key"]
    cached = cache.get(cache_key)
    if cached and cache_key != CAROUSEL_STATE_KEY:
        status = cached.get("status")
        if status == "ok" and cached.get("summary"):
            if META_SUMMARY_RE.search(cached["summary"]):
                cache[cache_key] = {"status": "skip", "date": today_iso}
                print(f"Vyradený meta-opis z cache: {art['title']}")
                return "skip", "", "cache:meta-skip"
            return "ok", cached["summary"], f"cache:{cached.get('provider', 'AI')}"
        if status == "paywall":
            return "paywall", "", "cache:paywall"
        if status == "skip":
            return "skip", "", "cache:skip"

    if not GEMINI_API_KEY and not GROQ_API_KEY:
        return "fallback", art["summary"], "RSS"

    body_text, is_paywalled = fetch_article_body(art["url"])
    if is_paywalled or len(body_text) < 320:
        if is_paywalled:
            cache[cache_key] = {"status": "paywall", "date": today_iso}
            return "paywall", "", "paywall-html"
        return "fallback", art["summary"], "RSS"

    user_prompt = (
        f"Titulok: {art['title']}\n"
        f"Zdroj: {art['source']}\n"
        f"RSS perex: {art['summary']}\n\n"
        f"Text článku:\n{body_text}"
    )

    summary, provider = _call_gemini(user_prompt)
    if not summary:
        summary, provider = _call_groq(user_prompt)

    if summary == "PAYWALL":
        cache[cache_key] = {"status": "paywall", "date": today_iso}
        return "paywall", "", "paywall-ai"

    if summary == "SKIP" or (summary and META_SUMMARY_RE.search(summary)):
        cache[cache_key] = {"status": "skip", "date": today_iso}
        print(f"Vyradený neinformatívny článok ({provider or 'filter'}): {art['title']}")
        return "skip", "", "skip-ai"

    if summary and 70 <= len(summary) <= 520:
        cache[cache_key] = {
            "status": "ok",
            "summary": summary,
            "provider": provider,
            "date": today_iso,
        }
        return "ok", summary, provider

    return "fallback", art["summary"], "RSS"


# --- POČASIE PRE ŠAMORÍN (3 NEZÁVISLÉ ZDROJE) ---

def _fetch_weather_open_meteo():
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
        f"&current=temperature_2m,weather_code"
        f"&timezone=Europe%2FBratislava"
    )
    data = json.loads(http_get_text(url, timeout=10, extra_headers={"User-Agent": APP_UA}))
    current = data.get("current", {})
    temp = current.get("temperature_2m")
    code = current.get("weather_code")
    if temp is None:
        raise ValueError("Open-Meteo nevrátil teplotu")
    return int(round(float(temp))), WMO_SK.get(code, "")


def _fetch_weather_met_no():
    """Záloha 1: Nórsky meteorologický inštitút (Yr.no / MET Norway)."""
    url = (
        f"https://api.met.no/weatherapi/locationforecast/2.0/compact"
        f"?lat={WEATHER_LAT}&lon={WEATHER_LON}"
    )
    data = json.loads(http_get_text(url, timeout=10, extra_headers={"User-Agent": APP_UA}))
    ts = data["properties"]["timeseries"][0]["data"]
    temp = ts["instant"]["details"]["air_temperature"]
    sym = (
        ts.get("next_1_hours", {}).get("summary", {}).get("symbol_code")
        or ts.get("next_6_hours", {}).get("summary", {}).get("symbol_code")
        or ""
    )
    base_sym = sym.split("_")[0]
    desc = "Búrka" if "thunder" in base_sym else METNO_SK.get(base_sym, "")
    return int(round(float(temp))), desc


def _fetch_weather_wttr():
    """Záloha 2: wttr.in JSON API."""
    url = f"https://wttr.in/{WEATHER_LAT},{WEATHER_LON}?format=j1"
    data = json.loads(http_get_text(url, timeout=10, extra_headers={"User-Agent": APP_UA}))
    cur = data["current_condition"][0]
    temp = cur.get("temp_C")
    if temp is None:
        raise ValueError("wttr.in nevrátil teplotu")
    code = int(cur.get("weatherCode", -1))
    return int(round(float(temp))), WTTR_SK.get(code, "")


def fetch_weather():
    """Získa počasie pre Šamorín s automatickou zálohou cez 3 nezávislé zdroje."""
    providers = [
        ("Open-Meteo", _fetch_weather_open_meteo),
        ("MET Norway (Yr.no)", _fetch_weather_met_no),
        ("wttr.in", _fetch_weather_wttr),
    ]

    for name, fn in providers:
        attempts = 2 if name == "Open-Meteo" else 1
        for attempt in range(1, attempts + 1):
            try:
                temp_int, desc = fn()
                result = (
                    f"{WEATHER_CITY}: {temp_int} °C · {desc}"
                    if desc
                    else f"{WEATHER_CITY}: {temp_int} °C"
                )
                print(f"Počasie načítané cez {name}: {result}")
                return result
            except Exception as e:
                print(f"Chyba počasia [{name}, pokus {attempt}]: {e}")
                if attempt < attempts:
                    time.sleep(1)

    return f"{WEATHER_CITY}: -- °C"


# --- NAČÍTANIE, BODOVANIE A VÝBER SPRÁV (PLYNULÝ KOLOTOČ 10 KATEGÓRIÍ) ---

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


def is_teaser_rss(art):
    """Rozpozná RSS perex, ktorý bez plného článku nedáva zmysel alebo zamlčuje pointu."""
    text = f"{art['title']} {art['summary']}"
    if TEASER_RE.search(text) or META_SUMMARY_RE.search(art["summary"]):
        return True
    if not art["summary"] or len(art["summary"]) < 130:
        return True
    if DANGLING_START_RE.search(art["summary"]):
        return True
    return False


def score_article(art, now):
    """Ohodnotí pridanú hodnotu a informačnú bohatosť článku."""
    title = art["title"]
    summary = art["summary"]
    s_len = len(summary)
    sentences = split_sentences(summary)
    n_sent = len(sentences)

    score = 0.0

    # 1. Informačná hustota a dĺžka perexu
    if s_len == 0:
        score -= 50
    elif s_len < 85:
        score -= 28
    elif s_len < 130:
        score -= 8
    elif s_len <= 420:
        score += 30 + min(14, (s_len - 130) / 18.0)
    else:
        score += 34

    # 2. Viacvetné vysvetlenie
    if n_sent >= 2:
        score += 16
    elif n_sent == 1 and s_len < 120:
        score -= 12

    # 3. Kompletnosť bez pôvodného RSS useknutia
    if summary and not art["raw_cut"]:
        score += 10

    # 4. Penalizácia vytrhnutých viet bez kontextu a clickbaitu
    if summary and DANGLING_START_RE.search(summary):
        score -= 24
    if CLICKBAIT_RE.search(f"{title} {summary}"):
        score -= 28
    if title.endswith("?") and s_len < 140:
        score -= 10

    # 5. Mierna preferencia odomknutých zdrojov (väčšia šanca na plný text pre AI)
    if art["source"] in ("Denník N", "Denník E"):
        score -= 8

    # 6. Bonus za konkrétne fakty, čísla a vecné témy
    factual_hits = len(FACTUAL_SIGNALS_RE.findall(f"{title} {summary}"))
    score += min(18, factual_hits * 4)

    # 7. Mierny bonus za čerstvosť
    age_hours = max(0.0, (now - art["dt"]).total_seconds() / 3600.0)
    score += max(0.0, 10.0 - age_hours * 0.7)

    return round(score, 1)


def fetch_single_feed(feed_cfg, today, now, per_feed_limit=20):
    source, groups, url = feed_cfg
    dc_date_tag = "{http://purl.org/dc/elements/1.1/}date"
    results = []

    try:
        xml_data = http_get_text(url, timeout=10, throttle=True).encode("utf-8")
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
            link_el = item.find(f"{ns}link")
            link = (link_el.attrib.get("href", "") if link_el is not None else "").strip()
        else:
            title = clean_text(item.findtext("title"), is_summary=False)
            raw_summary = item.findtext("description")
            summary = clean_text(raw_summary, is_summary=True)
            pub_raw = item.findtext("pubDate") or item.findtext(dc_date_tag)
            link = (item.findtext("link") or "").strip()

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
            "url": link,
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

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [
            executor.submit(fetch_single_feed, cfg, today, now, per_feed_limit)
            for cfg in feeds
        ]
        for fut in as_completed(futures):
            all_raw.extend(fut.result())

    all_raw.sort(key=lambda x: (x["score"], x["dt"].timestamp()), reverse=True)
    by_key = {}
    ordered = []

    for art in all_raw:
        k = art["key"]
        if k not in by_key:
            by_key[k] = art
            ordered.append(art)
        else:
            by_key[k]["groups"].update(art["groups"])
            if not by_key[k]["url"] and art["url"]:
                by_key[k]["url"] = art["url"]

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


def get_candidates_for_category(articles, cat_key, used_keys, min_score=None, recent_keys=None):
    candidates = [
        a for a in articles
        if a["key"] not in used_keys and matches_category(a, cat_key)
    ]
    if not candidates:
        return []

    if cat_key == "gadgety_it":
        gadget_matches = [
            a for a in candidates
            if has_keyword(f"{a['title']} {a['summary']}", "gadgety_it")
        ]
        if gadget_matches:
            candidates = gadget_matches

    if min_score is not None:
        candidates = [a for a in candidates if a["score"] >= min_score]

    recent_set = set(recent_keys or [])
    # Uprednostní ešte nezobrazené dnešné články; v rámci nich triedi podľa skóre a čerstvosti
    candidates.sort(
        key=lambda a: (0 if a["key"] in recent_set else 1, a["score"], a["dt"].timestamp()),
        reverse=True,
    )
    return candidates


def pick_complete_article_for_category(
    articles, cat_key, used_keys, min_score, cache, today_iso, recent_keys
):
    """
    Pre danú kategóriu nájde najkvalitnejší odomknutý, faktický článok s uceleným AI zhrnutím.
    Preskakuje paywall, nákupné sprievodce aj prázdne meta-opisy (max 5 pokusov na kategóriu).
    """
    candidates = get_candidates_for_category(
        articles, cat_key, used_keys, min_score=min_score, recent_keys=recent_keys
    )
    if not candidates:
        return None

    rss_backup = None
    fallback_candidates = []

    for cand in candidates[:5]:
        status, summary_text, provider = summarize_article_with_ai(cand, cache, today_iso)
        if status == "ok":
            return dict(cand, summary=summary_text, ai_provider=provider)
        if status in ("paywall", "skip"):
            continue
        fallback_candidates.append(cand)
        if (
            status == "fallback"
            and not is_teaser_rss(cand)
            and not META_SUMMARY_RE.search(summary_text)
            and rss_backup is None
        ):
            rss_backup = dict(cand, summary=summary_text, ai_provider=provider)

    if rss_backup is not None:
        return rss_backup

    if min_score is None and fallback_candidates:
        for cand in fallback_candidates:
            if (
                cand["summary"]
                and not TEASER_RE.search(f"{cand['title']} {cand['summary']}")
                and not META_SUMMARY_RE.search(cand["summary"])
            ):
                return dict(cand, ai_provider="RSS-fallback")
        return dict(fallback_candidates[0], ai_provider="RSS-fallback")

    return None


def select_three_articles(articles, cache):
    """
    Vyberie 3 rovnocenné ucelené správy plynulým kolotočom cez všetkých 10 kategórií:
    - Všetkých 10 kategórií má rovnakú prioritu a pri každom behu sa posúva štart kolotoča.
    - Prázdne alebo vyradené kategórie sa ticho preskočia bez zaseknutia.
    - V rámci kategórie uprednostňuje články, ktoré ešte neboli nedávno zobrazené.
    """
    if not articles:
        return []

    now = datetime.now(TZ_LOCAL)
    today_iso = now.date().isoformat()
    n_cats = len(CATEGORIES)

    state = cache.get(CAROUSEL_STATE_KEY)
    if not isinstance(state, dict):
        state = {}

    start_idx = int(state.get("next_index", 0)) % n_cats
    recent_keys = state.get("recent_keys") if isinstance(state.get("recent_keys"), list) else []

    used_keys = set()
    used_cats = set()
    selected = []
    last_pass1_idx = None

    # 1. Kolo: plynulý prechod kolotočom od start_idx (kvalitné ucelené faktické články)
    for step in range(n_cats):
        if len(selected) >= TOTAL_ARTICLES:
            break
        idx = (start_idx + step) % n_cats
        label, cat_key = CATEGORIES[idx]
        if cat_key in used_cats:
            continue

        chosen = pick_complete_article_for_category(
            articles, cat_key, used_keys, min_score=8,
            cache=cache, today_iso=today_iso, recent_keys=recent_keys,
        )
        if chosen is None or chosen["key"] in used_keys:
            continue

        chosen["display_tag"] = label
        selected.append(chosen)
        used_keys.add(chosen["key"])
        used_cats.add(cat_key)
        last_pass1_idx = idx

    # 2. Záchranné kolo (skoro ráno pri malom počte dnešných článkov, bez limitu skóre)
    used_rescue = False
    if len(selected) < TOTAL_ARTICLES:
        used_rescue = True
        for step in range(n_cats):
            if len(selected) >= TOTAL_ARTICLES:
                break
            idx = (start_idx + step) % n_cats
            label, cat_key = CATEGORIES[idx]
            if cat_key in used_cats:
                continue

            chosen = pick_complete_article_for_category(
                articles, cat_key, used_keys, min_score=None,
                cache=cache, today_iso=today_iso, recent_keys=recent_keys,
            )
            if chosen is None or chosen["key"] in used_keys:
                continue

            chosen["display_tag"] = label
            selected.append(chosen)
            used_keys.add(chosen["key"])
            used_cats.add(cat_key)

    # Výpočet ďalšej pozície kolotoča a uloženie zobrazených článkov do pamäte
    if not used_rescue and last_pass1_idx is not None:
        next_index = (last_pass1_idx + 1) % n_cats
    else:
        next_index = (start_idx + TOTAL_ARTICLES) % n_cats

    updated_recent = [k for k in recent_keys if k not in used_keys]
    updated_recent.extend(art["key"] for art in selected)
    updated_recent = updated_recent[-RECENT_HISTORY_LIMIT:]

    cache[CAROUSEL_STATE_KEY] = {
        "next_index": next_index,
        "recent_keys": updated_recent,
        "date": today_iso,
    }

    print(
        f"Kolotoč kategórií: štart #{start_idx + 1} ({CATEGORIES[start_idx][0]}) "
        f"→ ďalší beh #{next_index + 1} ({CATEGORIES[next_index][0]})"
    )
    for idx, art in enumerate(selected, start=1):
        print(
            f"SPRÁVA {idx} [{art['display_tag']} | skóre {art['score']} | {art.get('ai_provider', 'RSS')}]: "
            f"{art['source']} ({art['dt'].strftime('%d.%m. %H:%M')}) - {art['title']}"
        )

    return selected


# --- VYKRESLENIE 1-BIT BMP (800×480, 3 ROVNOCENNÉ SPRÁVY, PÍSMO 17/14) ---

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


def compute_equal_blocks(draw, articles, preset, content_w):
    blocks = []
    for art in articles:
        t_lines = wrap_text_full(draw, art["title"], preset["title"], content_w)
        s_lines = wrap_text_full(draw, art["summary"], preset["body"], content_w) if art["summary"] else []

        h = preset["badge_h"] + preset["gap_badge"] + len(t_lines) * preset["lh_t"]
        if s_lines:
            h += preset["gap_title"] + len(s_lines) * preset["lh_b"]

        blocks.append(
            {
                "art": art,
                "t_lines": t_lines,
                "s_lines": s_lines,
                "height": h,
            }
        )
    return blocks


def fit_three_equal_articles(draw, articles, presets, content_w, avail_h):
    """
    Primárne vykreslí všetky 3 správy písmom 17 / 14 px.
    Ak sú všetky 3 extrémne dlhé, plynulo zmenší na záložnú sadu a prípadne skráti
    najdlhší text po celých vetách (nikdy na '...').
    """
    min_div_space = 16

    for p_idx, preset in enumerate(presets):
        blocks = compute_equal_blocks(draw, articles, preset, content_w)
        total_h = sum(b["height"] for b in blocks) + min_div_space * max(0, len(blocks) - 1)
        if total_h <= avail_h:
            return blocks, preset, p_idx + 1

    preset = presets[-1]
    trimmed = [dict(a) for a in articles]

    while True:
        blocks = compute_equal_blocks(draw, trimmed, preset, content_w)
        total_h = sum(b["height"] for b in blocks) + min_div_space * max(0, len(blocks) - 1)
        if total_h <= avail_h:
            return blocks, preset, len(presets)

        multi = [
            (i, split_sentences(a["summary"]))
            for i, a in enumerate(trimmed)
            if len(split_sentences(a["summary"])) > 1
        ]
        if multi:
            target_i, sents = max(multi, key=lambda x: len(trimmed[x[0]]["summary"]))
            trimmed[target_i]["summary"] = " ".join(sents[:-1]).strip()
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
    f_footer = load_font(sans_bold, 11)

    # Primárne písmo presne 17 / 14 px, s kompaktnými zálohami pri extrémne dlhých textoch
    presets = [
        {
            "name": "17/14",
            "badge": load_font(sans_bold, 11),
            "meta": load_font(sans_bold, 11),
            "title": load_font(sans_bold, 17),
            "body": load_font(sans_reg, 14),
            "badge_h": 18,
            "lh_t": 21,
            "lh_b": 18,
            "gap_badge": 5,
            "gap_title": 4,
        },
        {
            "name": "16/13",
            "badge": load_font(sans_bold, 10),
            "meta": load_font(sans_bold, 11),
            "title": load_font(sans_bold, 16),
            "body": load_font(sans_reg, 13),
            "badge_h": 17,
            "lh_t": 19,
            "lh_b": 16,
            "gap_badge": 4,
            "gap_title": 3,
        },
        {
            "name": "15/12",
            "badge": load_font(sans_bold, 10),
            "meta": load_font(sans_bold, 10),
            "title": load_font(sans_bold, 15),
            "body": load_font(sans_reg, 12),
            "badge_h": 16,
            "lh_t": 18,
            "lh_b": 15,
            "gap_badge": 3,
            "gap_title": 3,
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

    # --- 4. PÄTIČKA (MENINY / SVIATOK + POČASIE ŠAMORÍN) ---
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
        draw.text((WIDTH // 2, HEIGHT // 2), msg, font=presets[0]["title"], fill=0, anchor="mm")
        draw_footer()
        img.save(OUTPUT_FILE)
        print(f"Vygenerované: {OUTPUT_FILE} (0 správ | {day_info} | {weather_str})")
        return

    # --- 3. VYKRESLENIE 3 ROVNOCENNÝCH SPRÁV POD SEBOU ---
    top_y = 82
    bottom_y = 450
    avail_h = bottom_y - top_y

    blocks, preset, _ = fit_three_equal_articles(
        draw, selected_articles, presets, content_w, avail_h
    )

    total_blocks_h = sum(b["height"] for b in blocks)
    n_gaps = max(0, len(blocks) - 1)
    extra_h = max(0, avail_h - total_blocks_h)

    if n_gaps > 0:
        div_space = min(30, max(16, extra_h // (n_gaps + 1)))
        remaining = max(0, extra_h - div_space * n_gaps)
        y = top_y + min(12, remaining // 2)
    else:
        div_space = 0
        y = top_y

    badge_h = preset["badge_h"]
    for idx, b in enumerate(blocks):
        art = b["art"]

        # Štítok kategórie (rovnaký pre všetky 3 správy)
        badge_txt = f" {art['display_tag']} "
        badge_w = int(draw.textlength(badge_txt, font=preset["badge"])) + 8
        draw.rectangle((margin_x, y, margin_x + badge_w, y + badge_h), fill=0)
        draw.text((margin_x + 4, y + badge_h // 2), badge_txt, font=preset["badge"], fill=1, anchor="lm")

        meta_str = f"{art['dt'].strftime('%H:%M')} · {art['source'].upper()}"
        draw.text((margin_x + badge_w + 10, y + badge_h // 2), meta_str, font=preset["meta"], fill=0, anchor="lm")

        cy = y + badge_h + preset["gap_badge"]
        for line in b["t_lines"]:
            draw.text((margin_x, cy), line, font=preset["title"], fill=0)
            cy += preset["lh_t"]

        if b["s_lines"]:
            cy += preset["gap_title"]
            for line in b["s_lines"]:
                draw.text((margin_x, cy), line, font=preset["body"], fill=0)
                cy += preset["lh_b"]

        if idx < len(blocks) - 1:
            div_y = cy + div_space // 2
            draw.line((margin_x, div_y, right_x, div_y), fill=0, width=1)
            y = cy + div_space
        else:
            y = cy

    draw_footer()

    img.save(OUTPUT_FILE)
    print(
        f"Vygenerované: {OUTPUT_FILE} ({len(blocks)}/{TOTAL_ARTICLES} správ | "
        f"Písmo: {preset['name']} | {day_info} | {weather_str})"
    )


if __name__ == "__main__":
    today_local = datetime.now(TZ_LOCAL).date()
    summary_cache = load_summary_cache(today_local)
    all_articles = fetch_articles(FEEDS)
    selected = select_three_articles(all_articles, summary_cache)
    save_summary_cache(summary_cache)
    weather = fetch_weather()
    render_dashboard(selected, weather)
