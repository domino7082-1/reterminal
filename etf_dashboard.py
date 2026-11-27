import csv
import datetime
import io
import json
import math
import os
import time
import requests
from PIL import Image, ImageDraw, ImageFont

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    cffi_requests = None

try:
    import yfinance as yf
except ImportError:
    yf = None

SCRIPT_VERSION = "2026-11-27-v15-exact-daily-data"
CACHE_VERSION = 2  # Zvýšenie zneplatní starú cache z mesačných/týždenných sviečok

# --- KONFIGURÁCIA (reTerminal E1001 · 800x480 1-bit BMP) ---
WIDTH = 800
HEIGHT = 480
RENDER_MODE = 'L'
THRESHOLD_ON_WHITE = 155  # Plnšie čierne ťahy (znamenká +, − a číslice) na bielom pozadí
THRESHOLD_ON_BLACK = 110  # Plnšie biele ťahy v čiernych hlavičkách a štítkoch
BACKGROUND_COLOR = 255    # Biela
TEXT_COLOR = 0            # Čierna
MINUS_SIGN = "\u2212"     # Skutočné matematické mínus (−), rovnaká šírka aj hrúbka ako +
ATH_INVERT_THRESHOLD = -10.0  # Hranica poklesu od ATH, od ktorej je výplň lišty plne čierna
PERF_TABLE_STYLE = "stitky"   # Výkonnosť 1M/3M/6M/1R: "linky" alebo "stitky" (čierne štítky)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "etf_output.bmp")
CACHE_FILE = os.path.join(BASE_DIR, "etf_cache.json")  # posledné úspešne stiahnuté dáta

DAYS_SHORT = ["Pon", "Uto", "Str", "Štv", "Pia", "So", "Ne"]

# Definícia 4 ETF fondov (Xetra, EUR) + záložné dáta (záverečné ceny) pri výpadku všetkých API
ETF_CONFIG = [
    {
        "ticker": "SXR8",
        "yahoo": "SXR8.DE",
        "stooq": "sxr8.de",
        "name": "Core S&P 500",
        "region": "USA",
        "fallback_price": 719.18,
        "fallback_day_pct": 0.00,
        "fallback_ath": 754.68,
        "fallback_ath_date": "10/26",
        "fallback_min_52w": 562.40,
        "fallback_max_52w": 754.68,
        "fallback_perf": {"1m": -4.2, "3m": -2.8, "6m": 1.1, "1y": 14.6},
    },
    {
        "ticker": "EXUS",
        "yahoo": "EXUS.DE",
        "stooq": "exus.de",
        "name": "MSCI World ex USA",
        "region": "EX-US",
        "fallback_price": 39.915,
        "fallback_day_pct": 0.00,
        "fallback_ath": 41.110,
        "fallback_ath_date": "11/26",
        "fallback_min_52w": 33.420,
        "fallback_max_52w": 41.110,
        "fallback_perf": {"1m": -3.1, "3m": -1.4, "6m": 1.2, "1y": 11.4},
    },
    {
        "ticker": "IS3N",
        "yahoo": "IS3N.DE",
        "stooq": "is3n.de",
        "name": "Core MSCI EM IMI",
        "region": "EM",
        "fallback_price": 43.495,
        "fallback_day_pct": 0.00,
        "fallback_ath": 50.690,
        "fallback_ath_date": "06/26",
        "fallback_min_52w": 38.120,
        "fallback_max_52w": 50.690,
        "fallback_perf": {"1m": -6.8, "3m": -9.2, "6m": -10.7, "1y": 4.8},
    },
    {
        "ticker": "IUSN",
        "yahoo": "IUSN.DE",
        "stooq": "iusn.de",
        "name": "MSCI World Small Cap",
        "region": "SMALL",
        "fallback_price": 9.117,
        "fallback_day_pct": 0.00,
        "fallback_ath": 9.327,
        "fallback_ath_date": "08/26",
        "fallback_min_52w": 7.410,
        "fallback_max_52w": 9.327,
        "fallback_perf": {"1m": -3.4, "3m": -2.1, "6m": 1.2, "1y": 12.1},
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "sk-SK,sk;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Dni v slovenskom kalendári, keď sa zobrazuje sviatok namiesto menín
NO_NAMEDAY_HOLIDAYS = {
    (1, 1): "Nový rok",
    (5, 1): "Sviatok práce",
    (11, 1): "Sviatok všetkých svätých",
    (11, 2): "Pamiatka zosnulých",
    (12, 25): "1. sviatok vianočný",
}

# Pevné slovenské sviatky
FIXED_HOLIDAYS_SK = {
    (1, 1): "Nový rok",
    (1, 6): "Zjavenie Pána (Traja králi)",
    (5, 1): "Sviatok práce",
    (5, 8): "Deň víťazstva nad fašizmom",
    (7, 5): "Sviatok sv. Cyrila a Metoda",
    (8, 29): "Výročie SNP",
    (9, 15): "Sedembolestná Panna Mária",
    (11, 1): "Sviatok všetkých svätých",
    (11, 17): "Deň boja za slobodu a demokraciu",
    (12, 24): "Štedrý deň",
    (12, 25): "1. sviatok vianočný",
    (12, 26): "2. sviatok vianočný",
}

# Kompletný vstavaný slovenský meninový kalendár (366 dní, 100 % offline)
SLOVAK_NAMEDAYS = {
    (1, 2): "Alexandra, Karina", (1, 3): "Daniela", (1, 4): "Drahoslav",
    (1, 5): "Andrea", (1, 6): "Antónia", (1, 7): "Bohuslava",
    (1, 8): "Severín", (1, 9): "Alexej", (1, 10): "Dáša",
    (1, 11): "Malvína", (1, 12): "Ernest", (1, 13): "Rastislav",
    (1, 14): "Radovan", (1, 15): "Dobroslav", (1, 16): "Kristína",
    (1, 17): "Nataša", (1, 18): "Bohdana", (1, 19): "Drahomíra, Mário",
    (1, 20): "Dalibor, Sebastián", (1, 21): "Vincent", (1, 22): "Zora",
    (1, 23): "Miloš", (1, 24): "Timotej", (1, 25): "Gejza",
    (1, 26): "Tamara", (1, 27): "Bohuš", (1, 28): "Alfonz",
    (1, 29): "Gašpar", (1, 30): "Ema", (1, 31): "Emil",
    (2, 1): "Tatiana", (2, 2): "Erik, Erika", (2, 3): "Blažej",
    (2, 4): "Veronika", (2, 5): "Agáta", (2, 6): "Dorota",
    (2, 7): "Vanda", (2, 8): "Zoja", (2, 9): "Zdenko",
    (2, 10): "Gabriela", (2, 11): "Dezider", (2, 12): "Perla",
    (2, 13): "Arpád", (2, 14): "Valentín", (2, 15): "Pravoslav",
    (2, 16): "Ida, Liana", (2, 17): "Miloslava", (2, 18): "Jaromír",
    (2, 19): "Vlasta", (2, 20): "Lívia", (2, 21): "Eleonóra",
    (2, 22): "Etela", (2, 23): "Roman, Romana", (2, 24): "Matej",
    (2, 25): "Frederik, Frederika", (2, 26): "Viktor", (2, 27): "Alexander",
    (2, 28): "Zlatica", (2, 29): "Radomír",
    (3, 1): "Albín", (3, 2): "Anežka", (3, 3): "Bohumil, Bohumila",
    (3, 4): "Kazimír", (3, 5): "Fridrich", (3, 6): "Radoslav, Radoslava",
    (3, 7): "Tomáš", (3, 8): "Alan, Alana", (3, 9): "Františka",
    (3, 10): "Branislav, Bruno", (3, 11): "Angela, Angelika", (3, 12): "Gregor",
    (3, 13): "Vlastimil", (3, 14): "Matilda", (3, 15): "Svetlana",
    (3, 16): "Boleslav", (3, 17): "Ľubica", (3, 18): "Eduard",
    (3, 19): "Jozef", (3, 20): "Víťazoslav, Klaudius", (3, 21): "Blahoslav",
    (3, 22): "Beňadik", (3, 23): "Adrián", (3, 24): "Gabriel",
    (3, 25): "Marián", (3, 26): "Emanuel", (3, 27): "Alena",
    (3, 28): "Soňa", (3, 29): "Miroslav", (3, 30): "Vieroslava",
    (3, 31): "Benjamín",
    (4, 1): "Hugo", (4, 2): "Zita", (4, 3): "Richard",
    (4, 4): "Izidor", (4, 5): "Miroslava", (4, 6): "Irena",
    (4, 7): "Zoltán", (4, 8): "Albert", (4, 9): "Milena",
    (4, 10): "Igor", (4, 11): "Július", (4, 12): "Estera",
    (4, 13): "Aleš", (4, 14): "Justína", (4, 15): "Fedor",
    (4, 16): "Dana, Danica", (4, 17): "Rudolf", (4, 18): "Valér",
    (4, 19): "Jela", (4, 20): "Marcel", (4, 21): "Ervín",
    (4, 22): "Slavomír", (4, 23): "Vojtech", (4, 24): "Juraj",
    (4, 25): "Marek", (4, 26): "Jaroslava", (4, 27): "Jaroslav",
    (4, 28): "Jarmila", (4, 29): "Lea", (4, 30): "Anastázia",
    (5, 2): "Žigmund", (5, 3): "Galina", (5, 4): "Florián",
    (5, 5): "Lesana, Lesia", (5, 6): "Hermína", (5, 7): "Monika",
    (5, 8): "Ingrida", (5, 9): "Roland", (5, 10): "Viktória",
    (5, 11): "Blažena", (5, 12): "Pankrác", (5, 13): "Servác",
    (5, 14): "Bonifác", (5, 15): "Žofia", (5, 16): "Svetozár",
    (5, 17): "Gizela", (5, 18): "Viola", (5, 19): "Gertrúda",
    (5, 20): "Bernard", (5, 21): "Zina", (5, 22): "Júlia, Juliana",
    (5, 23): "Želmíra", (5, 24): "Ela", (5, 25): "Urban",
    (5, 26): "Dušan", (5, 27): "Iveta", (5, 28): "Viliam",
    (5, 29): "Vilma", (5, 30): "Ferdinand", (5, 31): "Petronela, Petrana",
    (6, 1): "Žaneta", (6, 2): "Xénia, Oxana", (6, 3): "Karolína",
    (6, 4): "Lenka", (6, 5): "Laura", (6, 6): "Norbert",
    (6, 7): "Róbert", (6, 8): "Medard", (6, 9): "Stanislava",
    (6, 10): "Margaréta", (6, 11): "Dobroslava", (6, 12): "Zlatko",
    (6, 13): "Anton", (6, 14): "Vasil", (6, 15): "Vít",
    (6, 16): "Blanka", (6, 17): "Adolf", (6, 18): "Vratislav",
    (6, 19): "Alfréd", (6, 20): "Valéria", (6, 21): "Alojz",
    (6, 22): "Paulína", (6, 23): "Sidónia", (6, 24): "Ján",
    (6, 25): "Tadeáš, Olívia", (6, 26): "Adriana", (6, 27): "Ladislav, Ladislava",
    (6, 28): "Beáta", (6, 29): "Peter, Pavol, Petra", (6, 30): "Melánia",
    (7, 1): "Diana", (7, 2): "Berta", (7, 3): "Miloslav",
    (7, 4): "Prokop", (7, 5): "Cyril, Metod", (7, 6): "Patrik, Patrícia",
    (7, 7): "Oliver", (7, 8): "Ivan", (7, 9): "Lujza",
    (7, 10): "Amália", (7, 11): "Milota", (7, 12): "Nina",
    (7, 13): "Margita", (7, 14): "Kamil", (7, 15): "Henrich",
    (7, 16): "Drahomír, Drahomíra", (7, 17): "Bohuslav", (7, 18): "Kamila",
    (7, 19): "Dušana", (7, 20): "Eliáš, Iľja", (7, 21): "Daniel",
    (7, 22): "Magdaléna", (7, 23): "Oľga", (7, 24): "Vladimír",
    (7, 25): "Jakub", (7, 26): "Anna, Hana", (7, 27): "Božena",
    (7, 28): "Krištof", (7, 29): "Marta", (7, 30): "Libuša",
    (7, 31): "Ignác",
    (8, 1): "Božidara", (8, 2): "Gustáv", (8, 3): "Jerguš",
    (8, 4): "Dominik, Dominika", (8, 5): "Hortenzia", (8, 6): "Jozefína",
    (8, 7): "Štefánia", (8, 8): "Oskar", (8, 9): "Ľubomíra",
    (8, 10): "Vavrinec", (8, 11): "Zuzana", (8, 12): "Darina",
    (8, 13): "Ľubomír", (8, 14): "Mojmír", (8, 15): "Marcela",
    (8, 16): "Leonard", (8, 17): "Milica", (8, 18): "Elena, Helena",
    (8, 19): "Lýdia", (8, 20): "Anabela", (8, 21): "Jana",
    (8, 22): "Tichomír", (8, 23): "Filip", (8, 24): "Bartolomej",
    (8, 25): "Ľudovít", (8, 26): "Samuel", (8, 27): "Silvia",
    (8, 28): "Augustín", (8, 29): "Nikola, Nikolaj", (8, 30): "Ružena",
    (8, 31): "Nora",
    (9, 1): "Drahoslava", (9, 2): "Linda, Rebeka", (9, 3): "Belo",
    (9, 4): "Rozália", (9, 5): "Regína", (9, 6): "Alica",
    (9, 7): "Marianna", (9, 8): "Miriama", (9, 9): "Martina",
    (9, 10): "Oleg", (9, 11): "Bystrík", (9, 12): "Mária",
    (9, 13): "Ctibor", (9, 14): "Ľudomil", (9, 15): "Jolana",
    (9, 16): "Ľudmila", (9, 17): "Olympia", (9, 18): "Eugénia",
    (9, 19): "Konštantín", (9, 20): "Ľuboslav, Ľuboslava", (9, 21): "Matúš",
    (9, 22): "Móric", (9, 23): "Zdenka", (9, 24): "Ľuboš, Ľubor",
    (9, 25): "Vladislav", (9, 26): "Edita", (9, 27): "Cyprián",
    (9, 28): "Václav", (9, 29): "Michal, Michaela", (9, 30): "Jarolím",
    (10, 1): "Arnold", (10, 2): "Levoslav", (10, 3): "Stela",
    (10, 4): "František", (10, 5): "Viera", (10, 6): "Natália",
    (10, 7): "Eliška", (10, 8): "Brigita", (10, 9): "Dionýz",
    (10, 10): "Slavomíra", (10, 11): "Valentína", (10, 12): "Maximilián",
    (10, 13): "Koloman", (10, 14): "Boris", (10, 15): "Terézia",
    (10, 16): "Vladimíra", (10, 17): "Hedviga", (10, 18): "Lukáš",
    (10, 19): "Kristián", (10, 20): "Vendelín", (10, 21): "Uršuľa",
    (10, 22): "Sergej", (10, 23): "Alojzia", (10, 24): "Kvetoslava",
    (10, 25): "Aurel", (10, 26): "Demeter", (10, 27): "Sabína",
    (10, 28): "Dobromila", (10, 29): "Klára", (10, 30): "Šimon, Simona",
    (10, 31): "Aurélia",
    (11, 3): "Hubert", (11, 4): "Karol", (11, 5): "Imrich",
    (11, 6): "Renáta", (11, 7): "René", (11, 8): "Bohumír",
    (11, 9): "Teodor", (11, 10): "Tibor", (11, 11): "Martin, Maroš",
    (11, 12): "Svätopluk", (11, 13): "Stanislav", (11, 14): "Irma",
    (11, 15): "Leopold", (11, 16): "Agnesa", (11, 17): "Klaudia",
    (11, 18): "Eugen", (11, 19): "Alžbeta", (11, 20): "Félix",
    (11, 21): "Elvíra", (11, 22): "Cecília", (11, 23): "Klement",
    (11, 24): "Emília", (11, 25): "Katarína", (11, 26): "Kornel",
    (11, 27): "Milan", (11, 28): "Henrieta", (11, 29): "Vratko",
    (11, 30): "Ondrej, Andrej",
    (12, 1): "Edmund", (12, 2): "Bibiána", (12, 3): "Oldrich",
    (12, 4): "Barbora", (12, 5): "Oto", (12, 6): "Mikuláš",
    (12, 7): "Ambróz", (12, 8): "Marína", (12, 9): "Izabela",
    (12, 10): "Radúz", (12, 11): "Hilda", (12, 12): "Otília",
    (12, 13): "Lucia", (12, 14): "Branislava, Bronislava", (12, 15): "Ivica",
    (12, 16): "Albína", (12, 17): "Kornélia", (12, 18): "Sláva, Slávka",
    (12, 19): "Judita", (12, 20): "Dagmara", (12, 21): "Bohdan",
    (12, 22): "Adela", (12, 23): "Nadežda", (12, 24): "Adam, Eva",
    (12, 26): "Štefan", (12, 27): "Filoména", (12, 28): "Ivana, Ivona",
    (12, 29): "Milada", (12, 30): "Dávid", (12, 31): "Silvester",
}


def get_fonts():
    """Uprednostní DejaVu Sans Bold pre maximálnu čitateľnosť z diaľky na 1-bit E-Ink."""
    fonts = {}
    font_candidates = [
        (
            os.path.join(BASE_DIR, "DejaVuSans-Bold.ttf"),
            os.path.join(BASE_DIR, "DejaVuSans.ttf"),
        ),
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ),
        (
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
        ),
        (
            os.path.join(BASE_DIR, "arialbd.ttf"),
            os.path.join(BASE_DIR, "arial.ttf"),
        ),
    ]

    font_bold = None
    font_reg = None
    for cand_b, cand_r in font_candidates:
        if os.path.exists(cand_b) and os.path.exists(cand_r):
            font_bold, font_reg = cand_b, cand_r
            break

    try:
        if not font_bold or not font_reg:
            raise IOError("Fonty nenájdené")

        fonts["header"] = ImageFont.truetype(font_bold, 18)
        fonts["header_date"] = ImageFont.truetype(font_bold, 14)
        fonts["price_lg"] = ImageFont.truetype(font_bold, 28)
        fonts["ticker"] = ImageFont.truetype(font_bold, 16)
        fonts["bold_15"] = ImageFont.truetype(font_bold, 15)
        fonts["bold_14"] = ImageFont.truetype(font_bold, 14)
        fonts["bold_13"] = ImageFont.truetype(font_bold, 13)
        fonts["bold_12"] = ImageFont.truetype(font_bold, 12)
        fonts["bold_11"] = ImageFont.truetype(font_bold, 11)
        fonts["reg_13"] = ImageFont.truetype(font_reg, 13)
    except IOError:
        default = ImageFont.load_default()
        keys = [
            "header", "header_date", "price_lg", "ticker", "bold_15",
            "bold_14", "bold_13", "bold_12", "bold_11", "reg_13",
        ]
        fonts = {k: default for k in keys}
    return fonts


def get_now_bratislava():
    if ZoneInfo is not None:
        try:
            return datetime.datetime.now(ZoneInfo("Europe/Bratislava"))
        except Exception:
            pass
    try:
        os.environ["TZ"] = "Europe/Bratislava"
        time.tzset()
    except AttributeError:
        pass
    return datetime.datetime.now()


def ts_to_bratislava(ts):
    """Prevedie Unix timestamp na lokálny bratislavský čas."""
    if ZoneInfo is not None:
        try:
            return datetime.datetime.fromtimestamp(ts, tz=ZoneInfo("Europe/Bratislava"))
        except Exception:
            pass
    return datetime.datetime.fromtimestamp(ts)


def subtract_months(date_obj, months):
    """Odpočíta kalendárne mesiace od dátumu (ošetruje 29./30./31. deň v mesiaci)."""
    total_months = date_obj.year * 12 + (date_obj.month - 1) - months
    year = total_months // 12
    month = (total_months % 12) + 1
    if month == 12:
        next_month_first = datetime.date(year + 1, 1, 1)
    else:
        next_month_first = datetime.date(year, month + 1, 1)
    last_day = (next_month_first - datetime.timedelta(days=1)).day
    return datetime.date(year, month, min(date_obj.day, last_day))


# --- MENINY A SVIATKY (DOLNÁ LIŠTA) ---

def get_easter_sunday(year):
    """Meeus/Jones/Butcher algoritmus pre výpočet Veľkonočnej nedele."""
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
    return datetime.date(year, month, day)


def get_slovak_holiday(date_obj):
    key = (date_obj.month, date_obj.day)
    if key in FIXED_HOLIDAYS_SK:
        return FIXED_HOLIDAYS_SK[key]
    easter = get_easter_sunday(date_obj.year)
    if date_obj == easter - datetime.timedelta(days=2):
        return "Veľký piatok"
    if date_obj == easter:
        return "Veľkonočná nedeľa"
    if date_obj == easter + datetime.timedelta(days=1):
        return "Veľkonočný pondelok"
    return None


def get_nameday_or_holiday(now):
    """Vráti text pre dolnú lištu z vstavaného SK kalendára (100 % offline)."""
    today_date = now.date()
    key = (today_date.month, today_date.day)

    if key in NO_NAMEDAY_HOLIDAYS:
        return f"Sviatok: {NO_NAMEDAY_HOLIDAYS[key]}"

    meniny = SLOVAK_NAMEDAYS.get(key)
    if meniny:
        return f"Meniny: {meniny}"

    holiday = get_slovak_holiday(today_date)
    if holiday:
        return f"Sviatok: {holiday}"

    return ""


# --- FORMÁTOVANIE ČÍSEL A PRESNÉ ZAROVNANIE TEXTU ---

def fmt_eur(val, with_symbol=True):
    s = f"{val:.2f}".replace(".", ",") if abs(val) >= 100 else f"{val:.3f}".replace(".", ",")
    return f"{s} €" if with_symbol else s


def fmt_pct(val, show_plus=True, decimals=1, with_percent=True, arrow=False):
    """Naformátuje percento so skutočným matematickým mínus (−), bez falošného „−0,0%“."""
    if val is None or not math.isfinite(val):
        return "—"
    rounded = round(float(val), decimals)
    if rounded == 0.0:
        sign = ""
        num_val = 0.0
        prefix = ""
    elif rounded < 0:
        sign = MINUS_SIGN
        num_val = abs(rounded)
        prefix = "▼ " if arrow else ""
    else:
        sign = "+" if show_plus else ""
        num_val = rounded
        prefix = "▲ " if arrow else ""
    num_str = f"{num_val:.{decimals}f}".replace(".", ",")
    suffix = "%" if with_percent else ""
    return f"{prefix}{sign}{num_str}{suffix}"


def format_day_change(e, now):
    """Denná zmena s dňom, z ktorého naozaj je.

    „Dnes: ▼ −3,51%“ len pri dátach z dnešného dňa; cez víkend/sviatok/pred otvorením
    burzy „Pia: ▼ −3,51%“, pri starších dátach „20.11. ▼ −3,51%“.
    Natvrdo zadané záložné dáta (bez času kurzu) → „Záloha: −3,51%“.
    """
    ts = e.get("market_ts")
    if not ts:
        return f"Záloha: {fmt_pct(e['day_pct'], decimals=2)}"
    pct = fmt_pct(e["day_pct"], decimals=2, arrow=True)
    data_date = ts_to_bratislava(ts).date()
    age_days = (now.date() - data_date).days
    if age_days <= 0:
        return f"Dnes: {pct}"
    if age_days < 7:
        return f"{DAYS_SHORT[data_date.weekday()]}: {pct}"
    return f"{data_date.strftime('%d.%m.')} {pct}"


def draw_text_aligned(draw, x, y, text, font, fill=TEXT_COLOR, align="left"):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    if align == "right":
        cur_x = round(x - tw - bbox[0])
    elif align == "center":
        cur_x = round(x - tw / 2.0 - bbox[0])
    else:
        cur_x = round(x - bbox[0])
    draw.text((cur_x, y), text, font=font, fill=fill)


def draw_text_centered_in_box(draw, x0, y0, x1, y1, text, font, fill=TEXT_COLOR):
    """Presne vycentruje text horizontálne aj vertikálne podľa reálnych pixelov (textbbox)."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = round(x0 + ((x1 - x0) - tw) / 2.0 - bbox[0])
    ty = round(y0 + ((y1 - y0) - th) / 2.0 - bbox[1])
    draw.text((tx, ty), text, font=font, fill=fill)


def paste_inverted_block(img_1bit, x0, y0, x1, y1, draw_fn):
    """Vykreslí čierny blok s bielym textom s vlastným prahom, aby biele písmo ostalo plné."""
    w = int(x1 - x0)
    h = int(y1 - y0)
    if w <= 0 or h <= 0:
        return
    sub_gray = Image.new(RENDER_MODE, (w, h), TEXT_COLOR)
    sub_draw = ImageDraw.Draw(sub_gray)
    draw_fn(sub_draw, w, h)
    sub_1bit = sub_gray.point(
        lambda p: BACKGROUND_COLOR if p >= THRESHOLD_ON_BLACK else TEXT_COLOR,
        mode='1',
    )
    img_1bit.paste(sub_1bit, (int(x0), int(y0)))


# --- SŤAHOVANIE ETF DÁT: 1) YAHOO (period1..now 1d) -> 2) YFINANCE -> 3) STOOQ CSV -> 4) YAHOO 2y ---

class YahooClient:
    """Spravuje HTTP reláciu pre Yahoo Finance (curl_cffi Chrome TLS + cookie/crumb + retry)."""

    def __init__(self):
        if cffi_requests is not None:
            self.session = cffi_requests.Session(impersonate="chrome")
            self.backend = "curl_cffi"
        else:
            self.session = requests.Session()
            self.session.headers.update(HEADERS)
            self.backend = "requests"
        self.crumb = None
        self._warmed_up = False

    def _warm_up_cookie_crumb(self):
        if self._warmed_up:
            return
        self._warmed_up = True
        try:
            self.session.get("https://fc.yahoo.com", timeout=10)
            resp = self.session.get(
                "https://query2.finance.yahoo.com/v1/test/getcrumb",
                timeout=10,
            )
            if resp.status_code == 200:
                txt = resp.text.strip()
                if txt and "Too Many Requests" not in txt and "<" not in txt:
                    self.crumb = txt
        except Exception as e:
            print(f"[Yahoo] cookie/crumb poznámka: {e}")

    def fetch_chart(self, symbol, range_str="max", interval_str="1d", period1=None):
        """Stiahne graf z Yahoo Finance.

        Pre plnú dennú históriu posiela explicitný rozsah `period1..period2` namiesto
        `range=max`, pretože `range=max&interval=1d` Yahoo ticho zhrubuje na mesačné/týždenné bary.
        """
        hosts = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
        last_err = None

        for attempt in range(3):
            host = hosts[attempt % len(hosts)]
            if period1 is not None:
                now_ts = int(time.time()) + 86400
                params = f"period1={int(period1)}&period2={now_ts}&interval={interval_str}&includePrePost=false"
            elif range_str == "max" and interval_str == "1d":
                now_ts = int(time.time()) + 86400
                params = f"period1=0&period2={now_ts}&interval=1d&includePrePost=false"
            else:
                params = f"range={range_str}&interval={interval_str}&includePrePost=false"
            if self.crumb:
                params += f"&crumb={self.crumb}"
            url = f"https://{host}/v8/finance/chart/{symbol}?{params}"

            try:
                resp = self.session.get(url, timeout=14)
                if resp.status_code == 200:
                    data = resp.json()
                    result = data.get("chart", {}).get("result")
                    if result:
                        chart = result[0]
                        gran = chart.get("meta", {}).get("dataGranularity")
                        if interval_str == "1d" and gran and gran != "1d":
                            print(f"[Yahoo] {symbol}: odmietam nečakanú granularitu '{gran}' (očakávané '1d')")
                            return None
                        return chart
                    last_err = f"Prázdny výsledok ({host})"
                elif resp.status_code in (401, 403, 429):
                    last_err = f"HTTP {resp.status_code} ({host}, {self.backend})"
                    print(f"[Yahoo] {symbol}: {last_err} – pokus {attempt + 1}/3")
                    self._warm_up_cookie_crumb()
                    time.sleep(1.5 * (attempt + 1))
                elif resp.status_code in (400, 404, 422):
                    last_err = f"HTTP {resp.status_code} ({host})"
                    break
                else:
                    last_err = f"HTTP {resp.status_code} ({host})"
                    time.sleep(1.0)
            except Exception as e:
                last_err = str(e)
                time.sleep(1.0)

        if last_err:
            print(f"[Yahoo] {symbol} zlyhal: {last_err}")
        return None


def fetch_etf_via_yfinance(symbol):
    """Záložné stiahnutie plnej dennej histórie cez knižnicu yfinance (ak je nainštalovaná)."""
    if yf is None:
        return None
    try:
        tk = yf.Ticker(symbol)
        hist = tk.history(period="max", interval="1d", auto_adjust=False)
        if hist is None or hist.empty:
            return None

        timestamps = []
        closes = []
        for idx_ts, val in zip(hist.index, hist["Close"].tolist()):
            if val is None:
                continue
            fval = float(val)
            if math.isfinite(fval) and fval > 0:
                timestamps.append(int(idx_ts.timestamp()))
                closes.append(fval)

        if not closes:
            return None

        meta = {
            "dataGranularity": "1d",
            "regularMarketPrice": closes[-1],
            "regularMarketTime": timestamps[-1],
            "regularMarketPreviousClose": closes[-2] if len(closes) >= 2 else None,
        }
        return {
            "meta": meta,
            "timestamp": timestamps,
            "indicators": {"quote": [{"close": closes}]},
        }
    except Exception as e:
        print(f"[yfinance] {symbol} zlyhal: {e}")
        return None


def fetch_etf_via_stooq(stooq_symbol):
    """Nezávislá záloha mimo Yahoo: plná denná história z Stooq.com CSV (Xetra)."""
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol.lower()}&i=d"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=14)
        if resp.status_code != 200:
            print(f"[Stooq] {stooq_symbol}: HTTP {resp.status_code}")
            return None
        text = resp.text.strip()
        if not text or not text.startswith("Date,"):
            first_line = text.splitlines()[0][:80] if text else "prázdna odpoveď"
            print(f"[Stooq] {stooq_symbol}: neplatné CSV ({first_line})")
            return None

        tz = ZoneInfo("Europe/Bratislava") if ZoneInfo is not None else None
        rows = []
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            date_s = (row.get("Date") or "").strip()
            close_s = (row.get("Close") or "").strip()
            if not date_s or not close_s:
                continue
            try:
                y, m, d = map(int, date_s.split("-"))
                c_val = float(close_s)
                if not (math.isfinite(c_val) and c_val > 0):
                    continue
                dt = datetime.datetime(y, m, d, 17, 30, tzinfo=tz) if tz else datetime.datetime(y, m, d, 17, 30)
                ts = int(dt.timestamp())
                rows.append((ts, c_val))
            except ValueError:
                continue

        if not rows:
            return None

        rows.sort(key=lambda r: r[0])
        timestamps = [r[0] for r in rows]
        closes = [r[1] for r in rows]

        meta = {
            "dataGranularity": "1d",
            "regularMarketPrice": closes[-1],
            "regularMarketTime": timestamps[-1],
            "regularMarketPreviousClose": closes[-2] if len(closes) >= 2 else None,
        }
        return {
            "meta": meta,
            "timestamp": timestamps,
            "indicators": {"quote": [{"close": closes}]},
        }
    except Exception as e:
        print(f"[Stooq] {stooq_symbol} zlyhal: {e}")
        return None


def extract_daily_points(chart):
    """Vráti vyčistený zoznam denných záverov `[(date, ts, close), ...]` bez bad ticks."""
    timestamps = chart.get("timestamp") or []
    quotes = chart.get("indicators", {}).get("quote") or [{}]
    raw_closes = quotes[0].get("close") or []

    # 1) Len kladné konečné záverečné ceny (ochrana pred None, NaN, inf a 0.0)
    raw_points = []
    for idx in range(min(len(timestamps), len(raw_closes))):
        c_val = raw_closes[idx]
        if c_val is not None:
            val = float(c_val)
            if math.isfinite(val) and val > 0:
                raw_points.append((int(timestamps[idx]), val))

    if not raw_points:
        return []

    # 2) Jeden záznam na obchodný deň v bratislavskom čase (odstráni duplicitné bary)
    raw_points.sort(key=lambda p: p[0])
    by_day = {}
    for ts, val in raw_points:
        day = ts_to_bratislava(ts).date()
        by_day[day] = (ts, val)
    points = [(d, by_day[d][0], by_day[d][1]) for d in sorted(by_day)]

    # 3) Ochrana pred chybným prvým záznamom (napr. 10x skok v deň zalistovania)
    if len(points) >= 3:
        v0, v1, v2 = points[0][2], points[1][2], points[2][2]
        if abs(v0 / v1 - 1.0) > 0.25 and abs(v1 / v2 - 1.0) < 0.12:
            points = points[1:]

    # 4) Filter na jednodňové „bad ticks“ v Close (skok > 20 %, ktorý sa na ďalší deň vráti)
    #    Reálny split ani krach trhu neodstráni, lebo vtedy sa nasledujúci deň nevráti k prev_v.
    if len(points) >= 3:
        cleaned = [points[0]]
        for i in range(1, len(points) - 1):
            prev_v = cleaned[-1][2]
            curr_v = points[i][2]
            next_v = points[i + 1][2]
            if (
                abs(curr_v / prev_v - 1.0) > 0.20
                and abs(curr_v / next_v - 1.0) > 0.20
                and abs(next_v / prev_v - 1.0) < 0.12
            ):
                continue
            cleaned.append(points[i])
        cleaned.append(points[-1])
        points = cleaned

    return points


def validate_daily_series(daily_points, meta, symbol, source_name):
    """Overí, že ide skutočne o denné dáta (nie týždenné ani mesačné)."""
    gran = meta.get("dataGranularity")
    if gran and gran != "1d":
        print(f"[{source_name}] {symbol}: odmietam granularitu '{gran}' namiesto '1d'")
        return False

    if len(daily_points) < 2:
        print(f"[{source_name}] {symbol}: príliš málo záznamov ({len(daily_points)})")
        return False

    # Empirická kontrola rozostupu dní za posledných max. 60 obchodných dní:
    # pri denných dátach je medián vždy 1 deň (týždenné = 7, mesačné ~30).
    sample = daily_points[-61:]
    gaps = [
        (sample[i][0] - sample[i - 1][0]).days
        for i in range(1, len(sample))
    ]
    if gaps:
        gaps.sort()
        median_gap = gaps[len(gaps) // 2]
        if median_gap > 2:
            print(f"[{source_name}] {symbol}: odmietam nedenné dáta (medián rozostupu {median_gap} dní)")
            return False

    return True


def get_return_over_months(daily_points, ref_date, latest_price, months_back):
    """Vypočíta % výkonnosť oproti poslednému obchodnému dňu k dátumu pred `months_back` mesiacmi."""
    if not daily_points or latest_price <= 0:
        return None
    target_date = subtract_months(ref_date, months_back)

    # Ak fond v danom období ešte neexistoval (> 14 dní po cieľovom dátume)
    if daily_points[0][0] > target_date + datetime.timedelta(days=14):
        return None

    # Štandardná burzová konvencia: posledný obchodný deň <= target_date
    ref_price = None
    ref_day = None
    for d, _ts, close_val in daily_points:
        if d <= target_date:
            ref_day = d
            ref_price = close_val
        else:
            break

    if ref_price is None:
        first_d, _first_ts, first_val = daily_points[0]
        if (first_d - target_date).days <= 14:
            ref_day = first_d
            ref_price = first_val
    elif (target_date - ref_day).days > 14:
        return None

    if ref_price and ref_price > 0:
        return ((latest_price / ref_price) - 1.0) * 100.0
    return None


# --- CACHE POSLEDNÝCH ÚSPEŠNÝCH DÁT (etf_cache.json) ---

CACHE_FIELDS = (
    "price", "day_pct", "ath", "ath_date", "drawdown_pct",
    "perf_1m", "perf_3m", "perf_6m", "perf_1y",
    "low_52w", "high_52w", "pos_52w", "market_ts", "source",
)
CACHE_REQUIRED_NUMERIC = ("price", "ath", "drawdown_pct", "low_52w", "high_52w", "pos_52w")


def load_cache():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"[Cache] {CACHE_FILE} sa nedá načítať ({e}) – ignorujem")
        return {}


def save_cache(cache):
    """Atomický zápis (cez .tmp + os.replace), aby výpadok uprostred zápisu nepoškodil súbor."""
    tmp = CACHE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, CACHE_FILE)
    except Exception as e:
        print(f"[Cache] uloženie zlyhalo: {e}")


def update_cache(cache, etfs):
    """Uloží do cache iba ETF so živými a validnými dennými dátami."""
    changed = False
    for e in etfs:
        if e.get("live"):
            entry = {k: e.get(k) for k in CACHE_FIELDS}
            entry["cache_version"] = CACHE_VERSION
            entry["saved_at"] = int(time.time())
            cache[e["ticker"]] = entry
            changed = True
    return changed


def load_cached_etf(cache, cfg):
    """Vráti dáta ETF z cache (označené ako offline), alebo None, ak v cache nie sú platné."""
    entry = (cache or {}).get(cfg["ticker"])
    if not isinstance(entry, dict):
        return None
    if entry.get("cache_version") != CACHE_VERSION:
        return None
    try:
        for k in CACHE_REQUIRED_NUMERIC:
            v = float(entry[k])
            if not math.isfinite(v):
                return None
        if float(entry["price"]) <= 0:
            return None
    except (KeyError, TypeError, ValueError):
        return None

    result = {k: entry.get(k) for k in CACHE_FIELDS}
    result.update({
        "ticker": cfg["ticker"],
        "name": cfg["name"],
        "region": cfg["region"],
        "live": False,
        "offline": True,
        "source": "cache",
    })
    return result


def parse_chart_into_etf(chart, source_name, is_full_history, cfg, cached_entry=None):
    """Spracuje a zvaliduje surový graf do kompletných denných metrík ETF, alebo vráti None."""
    meta = chart.get("meta") or {}
    daily_points = extract_daily_points(chart)
    if not validate_daily_series(daily_points, meta, cfg["ticker"], source_name):
        return None

    # 1) Aktuálna cena a čas kurzu
    price = None
    reg_price = meta.get("regularMarketPrice")
    if reg_price is not None:
        rp = float(reg_price)
        if math.isfinite(rp) and rp > 0:
            price = rp
    if price is None:
        price = daily_points[-1][2]

    reg_time = meta.get("regularMarketTime")
    market_ts = int(reg_time) if reg_time else daily_points[-1][1]
    mkt_date = ts_to_bratislava(market_ts).date()

    # 2) Predošlý záver: striktne posledný obchodný deň PRIAMO PRED dátumom kurzu (d < mkt_date)
    prev_close = None
    prev_day = None
    for d, _ts, val in reversed(daily_points):
        if d < mkt_date:
            prev_day = d
            prev_close = val
            break

    # Záložne meta.regularMarketPreviousClose, len ak v denných dátach chýba alebo je medzera > 10 dní
    if prev_close is None or (prev_day is not None and (mkt_date - prev_day).days > 10):
        meta_prev = meta.get("regularMarketPreviousClose")
        if meta_prev is not None:
            mp = float(meta_prev)
            if math.isfinite(mp) and mp > 0:
                prev_close = mp

    # Poistka proti poškodenému API feedu alebo neprispôsobenému splitu (> 45 % za 1 deň)
    if prev_close and prev_close > 0:
        if abs(price / prev_close - 1.0) > 0.45:
            print(
                f"[{source_name}] {cfg['ticker']}: podozrivý jednodňový skok "
                f"({prev_close:.3f} -> {price:.3f}) – odmietam zdroj"
            )
            return None
        day_pct = ((price / prev_close) - 1.0) * 100.0
    else:
        day_pct = None

    # 3) Synchronizácia dnešného záznamu s aktuálnym kurzom (napr. záverečná aukcia 17:35)
    if daily_points[-1][0] == mkt_date:
        daily_points[-1] = (mkt_date, market_ts, price)

    # 4) Výkonnosť za presné kalendárne obdobia (1M / 3M / 6M / 1R)
    perf_1m = get_return_over_months(daily_points, mkt_date, price, 1)
    perf_3m = get_return_over_months(daily_points, mkt_date, price, 3)
    perf_6m = get_return_over_months(daily_points, mkt_date, price, 6)
    perf_1y = get_return_over_months(daily_points, mkt_date, price, 12)

    # 5) 52-týždňové rozpätie výhradne zo ZÁVEREČNÝCH cien
    cutoff_52w = subtract_months(mkt_date, 12)
    closes_52w = [val for d, _ts, val in daily_points if d >= cutoff_52w]
    if closes_52w:
        low_52w = min(min(closes_52w), price)
        high_52w = max(max(closes_52w), price)
    else:
        low_52w = price
        high_52w = price

    # 6) ATH výhradne z denných ZÁVEREČNÝCH cien (vrátane dnešnej aktuálnej ceny)
    best_day, _best_ts, best_val = max(daily_points, key=lambda p: p[2])
    if price > best_val:
        ath = price
        ath_day = mkt_date
    else:
        ath = best_val
        ath_day = best_day
    ath_date_str = ath_day.strftime("%m/%y")

    # Pri núdzovej skrátenej histórii (2y) nezahodíme známe vyššie ATH z platnej cache
    if not is_full_history and cached_entry is not None:
        try:
            c_ath = float(cached_entry["ath"])
            if math.isfinite(c_ath) and c_ath > ath:
                ath = c_ath
                ath_date_str = cached_entry.get("ath_date") or ath_date_str
        except (KeyError, TypeError, ValueError):
            pass

    drawdown_pct = ((price / ath) - 1.0) * 100.0 if ath > 0 else 0.0
    span_52w = high_52w - low_52w
    pos_52w = (price - low_52w) / span_52w if span_52w > 0 else 0.5
    pos_52w = max(0.0, min(1.0, pos_52w))

    print(
        f"  {cfg['ticker']}: {price:.3f} € "
        f"(pred: {prev_close:.3f} €, {fmt_pct(day_pct, decimals=2)}) | "
        f"ATH {ath:.3f} € ({ath_day.strftime('%d.%m.%Y')}, {drawdown_pct:.1f}%) | "
        f"{len(daily_points)} dní | zdroj={source_name}"
    )

    return {
        "ticker": cfg["ticker"],
        "name": cfg["name"],
        "region": cfg["region"],
        "price": price,
        "day_pct": day_pct,
        "ath": ath,
        "ath_date": ath_date_str,
        "drawdown_pct": drawdown_pct,
        "perf_1m": perf_1m,
        "perf_3m": perf_3m,
        "perf_6m": perf_6m,
        "perf_1y": perf_1y,
        "low_52w": low_52w,
        "high_52w": high_52w,
        "pos_52w": pos_52w,
        "live": True,
        "offline": False,
        "source": source_name,
        "market_ts": market_ts,
    }


def fetch_etf_data(cfg, client, cache=None):
    """Stiahne cenu, čas kurzu, 1M/3M/6M/1R výkonnosť, 52T rozpätie a ATH z presných denných dát.

    Poradie zdrojov (všetky overené na 1d granularitu):
    1) Yahoo Finance (plná 1d história: period1=0, prípadne od 2000-01-01)
    2) yfinance (plná 1d história)
    3) Stooq CSV (plná 1d história)
    4) Yahoo Finance (2y 1d záloha + zlúčenie s cache ATH)
    5) lokálna cache (etf_cache.json)
    6) záložné dáta z ETF_CONFIG
    """
    symbol = cfg["yahoo"]
    stooq_symbol = cfg.get("stooq", symbol.lower())
    cached_etf = load_cached_etf(cache, cfg)

    candidates = [
        ("Yahoo Finance", True, lambda: client.fetch_chart(symbol, "max", "1d", period1=0)),
        ("Yahoo Finance", True, lambda: client.fetch_chart(symbol, "max", "1d", period1=946684800)),
        ("Yahoo Finance", True, lambda: fetch_etf_via_yfinance(symbol)),
        ("Stooq", True, lambda: fetch_etf_via_stooq(stooq_symbol)),
        ("Yahoo Finance", False, lambda: client.fetch_chart(symbol, "2y", "1d")),
    ]

    for source_name, is_full_history, fetcher in candidates:
        try:
            chart = fetcher()
            if chart is None:
                continue
            parsed = parse_chart_into_etf(chart, source_name, is_full_history, cfg, cached_etf)
            if parsed is not None:
                return parsed
        except Exception as e:
            print(f"[{source_name}] Chyba spracovania {symbol}: {e}")

    # Bez živých dát: najprv posledné úspešne stiahnuté dáta z cache
    if cached_etf is not None:
        when = (
            ts_to_bratislava(cached_etf["market_ts"]).strftime("%d.%m.%Y %H:%M")
            if cached_etf.get("market_ts")
            else "?"
        )
        print(f"  {cfg['ticker']}: OFFLINE – posledné dáta z cache ({when})")
        return cached_etf

    # Posledná záchrana: natvrdo zadané záložné hodnoty z ETF_CONFIG
    price = cfg["fallback_price"]
    ath = max(cfg["fallback_ath"], price)
    low_52w = min(cfg["fallback_min_52w"], price)
    high_52w = max(cfg["fallback_max_52w"], price)
    drawdown_pct = ((price / ath) - 1.0) * 100.0 if ath > 0 else 0.0
    span_52w = high_52w - low_52w
    pos_52w = max(0.0, min(1.0, (price - low_52w) / span_52w if span_52w > 0 else 0.5))

    print(f"  {cfg['ticker']}: OFFLINE – záložné dáta z konfigurácie")
    return {
        "ticker": cfg["ticker"],
        "name": cfg["name"],
        "region": cfg["region"],
        "price": price,
        "day_pct": cfg["fallback_day_pct"],
        "ath": ath,
        "ath_date": cfg["fallback_ath_date"],
        "drawdown_pct": drawdown_pct,
        "perf_1m": cfg["fallback_perf"]["1m"],
        "perf_3m": cfg["fallback_perf"]["3m"],
        "perf_6m": cfg["fallback_perf"]["6m"],
        "perf_1y": cfg["fallback_perf"]["1y"],
        "low_52w": low_52w,
        "high_52w": high_52w,
        "pos_52w": pos_52w,
        "live": False,
        "offline": True,
        "source": "fallback",
        "market_ts": None,
    }


# --- KRESLIACE POMOCNÉ FUNKCIE (E-INK) ---

def _text_ink_width(draw, text, font):
    """Vráti skutočnú pixelovú šírku vykresleného textu podľa textbbox."""
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def _ath_scale_params(drawdown_pct):
    """Vráti (scale_max, step_pct) pre stupnicu poklesu od ATH."""
    dd_abs = abs(min(0.0, drawdown_pct))
    if dd_abs <= 25.0:
        return 25.0, 5.0
    # Pri hlbšom poklese stupnica po 10 % až po najbližšiu desiatku (−30, −40 …),
    # aby sa posledné dva popisky neprekrývali
    return float(math.ceil(dd_abs / 10.0) * 10), 10.0


def draw_dashed_vline(draw, x, y0, y1, dash=2, gap=2, color=TEXT_COLOR):
    y = y0
    while y < y1:
        draw.line([(x, y), (x, min(y + dash, y1))], fill=color, width=1)
        y += dash + gap


def draw_hatched_rect(draw, x0, y0, x1, y1, step=4, fill_solid=False):
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    if x1 <= x0 or y1 <= y0:
        return
    if fill_solid:
        draw.rectangle([x0, y0, x1, y1], fill=TEXT_COLOR, outline=TEXT_COLOR)
        return
    draw.rectangle([x0, y0, x1, y1], fill=BACKGROUND_COLOR, outline=TEXT_COLOR, width=1)
    w = x1 - x0
    h = y1 - y0
    for k in range(step, w + h, step):
        sx = x0 + max(0, k - h)
        sy = y0 + min(h, k)
        ex = x0 + min(w, k)
        ey = y0 + max(0, k - w)
        draw.line([(sx, sy), (ex, ey)], fill=TEXT_COLOR, width=1)


def draw_ath_drawdown_meter_rtl(draw, x0, x1, title_baseline, bar_y0, bar_y1, drawdown_pct, fonts,
                                scale_y=None, left_pad=None):
    """Vykreslí graf poklesu od ATH sprava doľava (0% na pravom okraji, −25% na ľavom).

    Nad lištou je nadpis s hodnotou, napr. „Pokles od ATH: −8,1%“
    (popisok 12B + výraznejšia hodnota 14B, zarovnané na spoločnú účiarie).
    Ak je zadané `left_pad`, všetky riadky majú rovnakú dĺžku lišty.
    """
    label_font = fonts["bold_12"]
    value_font = fonts["bold_14"]
    scale_font = fonts["bold_11"]

    dd_abs = abs(min(0.0, drawdown_pct))
    scale_max, step_pct = _ath_scale_params(drawdown_pct)

    # 1) Nadpis s hodnotou poklesu nad lištou, zarovnaný doľava
    label = "Pokles od ATH: "
    value = "0,0%" if dd_abs < 0.05 else fmt_pct(drawdown_pct, show_plus=False, decimals=1)
    draw.text((x0, title_baseline), label, font=label_font, fill=TEXT_COLOR, anchor="ls")
    value_x = x0 + draw.textlength(label, font=label_font)
    draw.text((value_x, title_baseline), value, font=value_font, fill=TEXT_COLOR, anchor="ls")

    bar_y0 = int(bar_y0)
    bar_y1 = int(bar_y1)

    # 2) Rezerva vľavo/vpravo = polovica šírky krajných popiskov stupnice,
    #    aby „−25%“ ani „0%“ neprečnievali cez okraj stĺpca (a deliace čiary)
    def _half_w(txt):
        return int(math.ceil(_text_ink_width(draw, txt, scale_font) / 2.0))

    eff_left_pad = left_pad if left_pad is not None else _half_w(f"{MINUS_SIGN}{int(scale_max)}")
    bar_x0 = int(x0 + eff_left_pad + 1)
    bar_x1 = int(x1 - _half_w("0%") - 1)
    bar_w = bar_x1 - bar_x0
    if bar_w <= 20:
        return

    # Vonkajší rámik lišty
    draw.rectangle([bar_x0, bar_y0, bar_x1, bar_y1], fill=BACKGROUND_COLOR, outline=TEXT_COLOR, width=2)

    # Výplň rastie sprava doľava od bar_x1 (0%) smerom k bar_x0 (-scale_max%)
    if dd_abs > 0.05:
        fill_w = max(2, int((min(dd_abs, scale_max) / scale_max) * (bar_w - 2)))
        draw_hatched_rect(
            draw,
            bar_x1 - 1 - fill_w,
            bar_y0 + 1,
            bar_x1 - 1,
            bar_y1 - 1,
            step=4,
            fill_solid=(drawdown_pct <= ATH_INVERT_THRESHOLD),
        )

    # Zvislé rysky a popisky: vpravo 0%, vľavo -25% (alebo -scale_max%)
    tick_vals = []
    cur = 0.0
    while cur < scale_max:
        tick_vals.append(cur)
        cur += step_pct
    tick_vals.append(scale_max)

    # scale_y = y pozícia textu stupnice (None = hneď pod lištou)
    tick_lbl_y = bar_y1 + 4 if scale_y is None else scale_y
    for val in tick_vals:
        tx = bar_x1 - int(round((val / scale_max) * bar_w))
        if 0 < val < scale_max:
            draw_dashed_vline(draw, tx, bar_y0 + 2, bar_y1 - 2, dash=2, gap=2)
        draw.line([(tx, bar_y1), (tx, bar_y1 + 3)], fill=TEXT_COLOR, width=1)

        # Znak % len pri nule (pravý okraj), aby sa popisky nedotýkali
        lbl_txt = "0%" if val == 0 else f"{MINUS_SIGN}{int(val)}"
        draw_text_aligned(draw, tx, tick_lbl_y, lbl_txt, scale_font, align="center")


def draw_52w_slider(draw, x0, x1, center_y, low_52w, high_52w, pos_52w, fonts, side_w=None):
    """52-týždňový posuvník: min | ——■—— | max cez celú šírku x0..x1, zvislo vycentrovaný na center_y.

    Ak je zadané `side_w`, rezervuje zhodnú šírku pre popisky vľavo aj vpravo,
    aby mali všetky riadky posuvník presne rovnakej dĺžky.
    """
    font = fonts["bold_12"]
    low_txt = fmt_eur(low_52w, with_symbol=False)
    high_txt = fmt_eur(high_52w, with_symbol=False)

    # Číslice (bez čiarky) zvislo vycentrované na čiaru posuvníka
    digit_bb = draw.textbbox((0, 0), "0123456789", font=font)
    text_y = round(center_y - (digit_bb[1] + digit_bb[3]) / 2.0)
    draw_text_aligned(draw, x0, text_y, low_txt, font, align="left")
    draw_text_aligned(draw, x1, text_y, high_txt, font, align="right")

    if side_w is not None:
        low_w = side_w
        high_w = side_w
    else:
        low_w = _text_ink_width(draw, low_txt, font)
        high_w = _text_ink_width(draw, high_txt, font)

    bar_x0 = int(math.ceil(x0 + low_w + 8))
    bar_x1 = int(math.floor(x1 - high_w - 8))
    bar_y = int(center_y)
    if bar_x1 <= bar_x0 + 14:
        return
    draw.line([(bar_x0, bar_y), (bar_x1, bar_y)], fill=TEXT_COLOR, width=2)
    draw.line([(bar_x0, bar_y - 5), (bar_x0, bar_y + 5)], fill=TEXT_COLOR, width=2)
    draw.line([(bar_x1, bar_y - 5), (bar_x1, bar_y + 5)], fill=TEXT_COLOR, width=2)
    marker_x = bar_x0 + int(round(pos_52w * (bar_x1 - bar_x0)))
    draw.rectangle([marker_x - 3, bar_y - 6, marker_x + 3, bar_y + 6], fill=TEXT_COLOR)


def draw_perf_table(draw, x0, x1, label_y, value_y, items, fonts, inverted_tasks, style=None):
    """Výkonnosť v rovnako širokých, vycentrovaných stĺpcoch.

    Horný riadok: obdobia (1M · 3M · 6M · 1R), dolný riadok: percentá.
    style="linky":  obdobie + krátka hrubá linka pod ním (stĺpce oddelené medzerou)
    style="stitky": obdobie ako čierny štítok s bielym písmom
    """
    style = style or PERF_TABLE_STYLE
    lbl_font = fonts["bold_11"]
    val_font = fonts["bold_12"]
    n = len(items)
    if n == 0:
        return
    col_w = (x1 - x0) / float(n)
    gap = 6  # medzera medzi linkami/štítkami susedných stĺpcov

    lbl_bb = draw.textbbox((0, 0), "1M", font=lbl_font)
    lbl_top = label_y + lbl_bb[1]
    lbl_bot = label_y + lbl_bb[3]

    for i, (lbl, val) in enumerate(items):
        cx0 = int(round(x0 + i * col_w))
        cx1 = int(round(x0 + (i + 1) * col_w))
        cx = (cx0 + cx1) / 2.0
        seg_x0 = cx0 + gap // 2
        seg_x1 = cx1 - (gap - gap // 2)

        if style == "stitky":
            cell_y0 = lbl_top - 4
            cell_y1 = lbl_bot + 4

            def _cell(sd, sw, sh, _t=lbl):
                draw_text_centered_in_box(sd, 0, 0, sw, sh, _t, lbl_font, fill=BACKGROUND_COLOR)

            inverted_tasks.append((seg_x0, cell_y0, seg_x1, cell_y1, _cell))
        else:
            draw_text_aligned(draw, cx, label_y, lbl, lbl_font, align="center")
            rule_y = lbl_bot + 5
            draw.rectangle([seg_x0, rule_y, seg_x1 - 1, rule_y + 1], fill=TEXT_COLOR)

        draw_text_aligned(draw, cx, value_y, fmt_pct(val, decimals=1), val_font, align="center")


# --- HLAVNÉ VYKRESLENIE DASHBOARDU (4 ŠIROKÉ RIADKY) ---

def create_etf_dashboard():
    img_gray = Image.new(RENDER_MODE, (WIDTH, HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img_gray)
    fonts = get_fonts()
    now = get_now_bratislava()

    client = YahooClient()
    print(f"Backend HTTP: {client.backend} | yfinance={'áno' if yf else 'nie'}")

    cache = load_cache()
    etfs = []
    for idx, cfg in enumerate(ETF_CONFIG):
        if idx > 0:
            time.sleep(0.6)
        etfs.append(fetch_etf_data(cfg, client, cache))

    if update_cache(cache, etfs):
        save_cache(cache)

    live_etfs = [e for e in etfs if e["live"]]
    offline_etfs = [e for e in etfs if not e["live"]]
    live_sources = sorted({e["source"] for e in live_etfs})
    live_times = [e["market_ts"] for e in live_etfs if e.get("market_ts")]
    offline_times = [e["market_ts"] for e in offline_etfs if e.get("market_ts")]
    footer_nameday_text = get_nameday_or_holiday(now)
    print(f"Dátum (BA): {now.strftime('%d.%m.%Y %H:%M')} | {footer_nameday_text}")

    header_h = 46
    inverted_tasks = []

    # ==========================================================
    # A. HLAVIČKA (y = 0..46): Názov | Dátum a čas (bez priemerov)
    # ==========================================================
    def draw_header(hd, hw, hh):
        title_left = "ETF PORTFÓLIO · XETRA"
        hd.text((12, 13), title_left, font=fonts["header"], fill=BACKGROUND_COLOR)

        date_right = f"{DAYS_SHORT[now.weekday()]} {now.strftime('%d.%m.%Y  %H:%M')}"
        w_date = hd.textlength(date_right, font=fonts["header_date"])
        right_start_x = hw - w_date - 12
        hd.text((right_start_x, 15), date_right, font=fonts["header_date"], fill=BACKGROUND_COLOR)

    inverted_tasks.append((0, 0, WIDTH, header_h, draw_header))

    # ==========================================================
    # B. 4 ŠIROKÉ RIADKY ETF (x = 8..792, y = 50..448)
    # ==========================================================
    margin_x = 8
    row_w = WIDTH - 2 * margin_x  # 784 px
    start_y = 50
    gap_y = 6
    row_h = 96  # 4 * 96 + 3 * 6 = 402 px (50..452)

    visible_etfs = etfs[:4]

    # Spoločné šírky popiskov cez všetky 4 riadky → zhodná dĺžka posuvníkov aj ATH líšt
    slider_side_w = max(
        (
            max(
                _text_ink_width(draw, fmt_eur(e["low_52w"], with_symbol=False), fonts["bold_12"]),
                _text_ink_width(draw, fmt_eur(e["high_52w"], with_symbol=False), fonts["bold_12"]),
            )
            for e in visible_etfs
        ),
        default=0,
    )
    ath_left_pad = max(
        (
            int(math.ceil(
                _text_ink_width(
                    draw,
                    f"{MINUS_SIGN}{int(_ath_scale_params(e['drawdown_pct'])[0])}",
                    fonts["bold_11"],
                ) / 2.0
            ))
            for e in visible_etfs
        ),
        default=0,
    )

    def make_centered_inverted_drawer(label_text, font_obj):
        def _draw(sd, sw, sh):
            draw_text_centered_in_box(sd, 0, 0, sw, sh, label_text, font_obj, fill=BACKGROUND_COLOR)
        return _draw

    for idx, e in enumerate(visible_etfs):
        rx = margin_x
        ry = start_y + idx * (row_h + gap_y)
        r_right = rx + row_w

        draw.rectangle([rx, ry, r_right, ry + row_h], outline=TEXT_COLOR, width=2)

        # 1. Ľavý blok (x = 18..206): Ticker štítok + Región + Názov + ATH
        c1_x = rx + 10
        inverted_tasks.append((
            c1_x,
            ry + 9,
            c1_x + 64,
            ry + 33,
            make_centered_inverted_drawer(e["ticker"], fonts["ticker"]),
        ))
        if e.get("offline"):
            # Riadok bez živých dát: namiesto regiónu čierny štítok OFFLINE
            inverted_tasks.append((
                c1_x + 70,
                ry + 12,
                c1_x + 70 + 60,
                ry + 30,
                make_centered_inverted_drawer("OFFLINE", fonts["bold_11"]),
            ))
        else:
            draw.text((c1_x + 72, ry + 13), e["region"], font=fonts["bold_13"], fill=TEXT_COLOR)
        draw.text((c1_x, ry + 38), e["name"], font=fonts["reg_13"], fill=TEXT_COLOR)
        draw.text(
            (c1_x, ry + 62),
            f"ATH: {fmt_eur(e['ath'])} ({e['ath_date']})",
            font=fonts["bold_13"],
            fill=TEXT_COLOR,
        )

        # Zvislé deliace čiary: cena | graf | výkonnosť
        div1_x = rx + 327   # medzi cenou a grafom (x = 335)
        div2_x = rx + 535   # medzi grafom a pravým blokom (x = 543)
        for dx in (div1_x, div2_x):
            draw.line([(dx, ry + 8), (dx, ry + row_h - 8)], fill=TEXT_COLOR, width=1)

        # 2. Stredný ľavý blok (x = 190..327): Veľká cena (28B) + Dnes: (15B)
        c2_r = div1_x - 8
        draw_text_aligned(draw, c2_r, ry + 14, fmt_eur(e["price"]), fonts["price_lg"], align="right")
        draw_text_aligned(
            draw,
            c2_r,
            ry + 55,
            format_day_change(e, now),
            fonts["bold_15"],
            align="right",
        )

        # Spoločná mriežka riadku pre stĺpce 2 a 3:
        #   horný riadok (ry+17..27): „Pokles od ATH: −X,X%“  |  52T posuvník
        #   dolný riadok (ry+72..81): stupnica grafu           |  percentá výkonnosti
        top_center_y = ry + 22
        value_row_y = ry + 69

        # 3. Stredný pravý blok (x = 343..535): „Pokles od ATH: −X,X%“ nad obráteným grafom
        c3_x0 = div1_x + 8
        c3_x1 = div2_x - 8
        draw_ath_drawdown_meter_rtl(
            draw,
            c3_x0,
            c3_x1,
            ry + 27,           # účiarie nadpisu (v línii s posuvníkom)
            ry + 43,           # horný okraj lišty
            ry + 62,           # dolný okraj lišty → výška 20 px, v strede so štítkami 1M…1R
            e["drawdown_pct"],
            fonts,
            scale_y=value_row_y,  # stupnica v línii s percentami výkonnosti
            left_pad=ath_left_pad,
        )

        # 4. Pravý blok (x = 551..785): 52T posuvník + tabuľka výkonnosti 1M · 3M · 6M · 1R
        c4_x0 = div2_x + 8
        c4_x1 = r_right - 7
        draw_52w_slider(
            draw, c4_x0, c4_x1, top_center_y,
            e["low_52w"], e["high_52w"], e["pos_52w"], fonts,
            side_w=slider_side_w,
        )

        # Výkonnosť: obdobia v štítkoch, percentá pod nimi (v línii so stupnicou grafu)
        draw_perf_table(
            draw,
            c4_x0,
            c4_x1,
            ry + 46,
            value_row_y,
            [
                ("1M", e["perf_1m"]),
                ("3M", e["perf_3m"]),
                ("6M", e["perf_6m"]),
                ("1R", e["perf_1y"]),
            ],
            fonts,
            inverted_tasks,
        )

    # ==========================================================
    # C. PÄTIČKA (y = 452..480) — zdroj + čas dát + meniny/sviatok
    # ==========================================================
    draw.line([(0, 452), (WIDTH, 452)], fill=TEXT_COLOR, width=1)

    def _fmt_ts(ts):
        return ts_to_bratislava(ts).strftime("%d.%m.%Y %H:%M")

    if live_etfs:
        status_txt = " / ".join(live_sources)
        if live_times:
            status_txt += f" · Dáta: {_fmt_ts(max(live_times))}"
        if offline_etfs:
            status_txt += " · Offline: " + ", ".join(e["ticker"] for e in offline_etfs)
    elif offline_times:
        # Všetky API zlyhali, ale máme posledné dáta z cache
        status_txt = f"API nedostupné · Posledné dáta: {_fmt_ts(max(offline_times))}"
    else:
        status_txt = f"ZÁLOŽNÉ DÁTA · API nedostupné · {now.strftime('%d.%m.%Y %H:%M')}"

    if footer_nameday_text:
        status_txt = f"{status_txt} · {footer_nameday_text}"

    max_footer_w = 628
    while draw.textlength(status_txt, font=fonts["bold_12"]) > max_footer_w and len(status_txt) > 6:
        status_txt = status_txt[:-2].rstrip() + "…"

    draw.text((12, 459), status_txt, font=fonts["bold_12"], fill=TEXT_COLOR)

    # Krok 2: Ostrý 1-bit prevod s optimalizovaným prahom pre biele pozadie
    img_1bit = img_gray.point(
        lambda p: BACKGROUND_COLOR if p >= THRESHOLD_ON_WHITE else TEXT_COLOR,
        mode='1',
    )

    # Krok 3: Vloženie čiernych blokov s vlastným prahom pre plný biely text
    for x0, y0, x1, y1, fn in inverted_tasks:
        paste_inverted_block(img_1bit, x0, y0, x1, y1, fn)

    return img_1bit


def main():
    print(f"Spúšťam etf_dashboard.py ({SCRIPT_VERSION})...")
    image = create_etf_dashboard()
    image.save(OUTPUT_FILE)
    print(f"Hotovo. Uložené do: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
