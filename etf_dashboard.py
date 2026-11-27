import csv
import datetime
import io
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

SCRIPT_VERSION = "2026-11-27-v3"

# --- KONFIGURÁCIA (reTerminal E1001 · 800x480 1-bit BMP) ---
WIDTH = 800
HEIGHT = 480
RENDER_MODE = 'L'
THRESHOLD_ON_WHITE = 155  # Plnšie čierne ťahy (znamenká +, − a číslice) na bielom pozadí
THRESHOLD_ON_BLACK = 110  # Plnšie biele ťahy v čiernych hlavičkách a štítkoch
BACKGROUND_COLOR = 255    # Biela
TEXT_COLOR = 0            # Čierna
MINUS_SIGN = "\u2212"     # Skutočné matematické mínus (−), rovnaká šírka aj hrúbka ako +
ATH_INVERT_THRESHOLD = -10.0  # Hranica poklesu od ATH pre inverzný čierny štítok

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "etf_output.bmp")

# Definícia 4 ETF fondov (Xetra, EUR) + záložné dáta pri výpadku všetkých API
ETF_CONFIG = [
    {
        "ticker": "SXR8",
        "yahoo": "SXR8.DE",
        "stooq": "sxr8.de",
        "name": "Core S&P 500",
        "region": "USA",
        "fallback_price": 694.06,
        "fallback_day_pct": -3.51,
        "fallback_ath": 755.30,
        "fallback_ath_date": "10/26",
        "fallback_min_52w": 562.40,
        "fallback_max_52w": 755.30,
        "fallback_perf": {"1m": -4.2, "3m": -2.8, "6m": 1.1, "1y": 14.6},
    },
    {
        "ticker": "EXUS",
        "yahoo": "EXUS.DE",
        "stooq": "exus.de",
        "name": "MSCI World ex USA",
        "region": "EX-US",
        "fallback_price": 38.500,
        "fallback_day_pct": -2.37,
        "fallback_ath": 41.180,
        "fallback_ath_date": "11/26",
        "fallback_min_52w": 33.420,
        "fallback_max_52w": 41.180,
        "fallback_perf": {"1m": -3.1, "3m": -1.4, "6m": 1.2, "1y": 11.4},
    },
    {
        "ticker": "IS3N",
        "yahoo": "IS3N.DE",
        "stooq": "is3n.de",
        "name": "Core MSCI EM IMI",
        "region": "EM",
        "fallback_price": 40.955,
        "fallback_day_pct": -4.93,
        "fallback_ath": 51.006,
        "fallback_ath_date": "06/26",
        "fallback_min_52w": 38.120,
        "fallback_max_52w": 51.006,
        "fallback_perf": {"1m": -6.8, "3m": -9.2, "6m": -10.7, "1y": 4.8},
    },
    {
        "ticker": "IUSN",
        "yahoo": "IUSN.DE",
        "stooq": "iusn.de",
        "name": "MSCI World Small Cap",
        "region": "SMALL",
        "fallback_price": 8.728,
        "fallback_day_pct": -2.50,
        "fallback_ath": 9.362,
        "fallback_ath_date": "08/26",
        "fallback_min_52w": 7.410,
        "fallback_max_52w": 9.362,
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
    # Január
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
    # Február
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
    # Marec
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
    # Apríl
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
    # Máj
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
    # Jún
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
    # Júl
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
    # August
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
    # September
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
    # Október
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
    # November
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
    # December
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
        fonts["price_lg"] = ImageFont.truetype(font_bold, 26)
        fonts["ticker"] = ImageFont.truetype(font_bold, 16)
        fonts["bold_14"] = ImageFont.truetype(font_bold, 14)
        fonts["bold_13"] = ImageFont.truetype(font_bold, 13)
        fonts["bold_12"] = ImageFont.truetype(font_bold, 12)
        fonts["bold_11"] = ImageFont.truetype(font_bold, 11)
        fonts["reg_13"] = ImageFont.truetype(font_reg, 13)
    except IOError:
        default = ImageFont.load_default()
        keys = [
            "header", "header_date", "price_lg", "ticker",
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


def fmt_pct(val, show_plus=True, decimals=1, with_percent=True):
    """Naformátuje percento so skutočným matematickým mínus (−), ktoré má rovnakú šírku ako +."""
    if val is None:
        return "—"
    if val < 0:
        sign = MINUS_SIGN
        num_val = abs(val)
    elif show_plus and val > 0:
        sign = "+"
        num_val = val
    else:
        sign = ""
        num_val = abs(val)
    num_str = f"{num_val:.{decimals}f}".replace(".", ",")
    suffix = "%" if with_percent else ""
    return f"{sign}{num_str}{suffix}"


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


# --- SŤAHOVANIE ETF DÁT: 1) YAHOO (curl_cffi/requests) -> 2) YFINANCE -> 3) STOOQ CSV ---

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

    def fetch_chart(self, symbol, range_str="max", interval_str="1d"):
        hosts = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
        last_err = None

        for attempt in range(3):
            host = hosts[attempt % len(hosts)]
            params = f"range={range_str}&interval={interval_str}&includePrePost=false"
            if self.crumb:
                params += f"&crumb={self.crumb}"
            url = f"https://{host}/v8/finance/chart/{symbol}?{params}"

            try:
                resp = self.session.get(url, timeout=12)
                if resp.status_code == 200:
                    data = resp.json()
                    result = data.get("chart", {}).get("result")
                    if result:
                        return result[0]
                    last_err = f"Prázdny výsledok ({host})"
                elif resp.status_code in (401, 403, 429):
                    last_err = f"HTTP {resp.status_code} ({host}, {self.backend})"
                    print(f"[Yahoo] {symbol}: {last_err} – pokus {attempt + 1}/3")
                    self._warm_up_cookie_crumb()
                    time.sleep(1.5 * (attempt + 1))
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
    """Záložné stiahnutie cez knižnicu yfinance (ak je nainštalovaná)."""
    if yf is None:
        return None
    try:
        tk = yf.Ticker(symbol)
        hist = tk.history(period="max", interval="1d", auto_adjust=False)
        if hist is None or hist.empty:
            return None

        timestamps = [int(ts.timestamp()) for ts in hist.index]
        closes = [None if math.isnan(v) else float(v) for v in hist["Close"].tolist()]
        lows = [None if math.isnan(v) else float(v) for v in hist["Low"].tolist()]
        highs = [None if math.isnan(v) else float(v) for v in hist["High"].tolist()]

        valid_closes = [v for v in closes if v is not None]
        if not valid_closes:
            return None

        meta = {
            "regularMarketPrice": valid_closes[-1],
            "regularMarketTime": timestamps[-1],
            "regularMarketPreviousClose": valid_closes[-2] if len(valid_closes) >= 2 else None,
        }
        return {
            "meta": meta,
            "timestamp": timestamps,
            "indicators": {"quote": [{"close": closes, "low": lows, "high": highs}]},
        }
    except Exception as e:
        print(f"[yfinance] {symbol} zlyhal: {e}")
        return None


def fetch_etf_via_stooq(stooq_symbol):
    """Nezávislá záloha mimo Yahoo: denná história z Stooq.com CSV (Xetra)."""
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol.lower()}&i=d"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
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
                dt = datetime.datetime(y, m, d, 17, 30, tzinfo=tz) if tz else datetime.datetime(y, m, d, 17, 30)
                ts = int(dt.timestamp())
                c_val = float(close_s)
                h_val = float(row["High"]) if row.get("High") else c_val
                l_val = float(row["Low"]) if row.get("Low") else c_val
                rows.append((ts, c_val, l_val, h_val))
            except ValueError:
                continue

        if not rows:
            return None

        rows.sort(key=lambda r: r[0])
        timestamps = [r[0] for r in rows]
        closes = [r[1] for r in rows]
        lows = [r[2] for r in rows]
        highs = [r[3] for r in rows]

        meta = {
            "regularMarketPrice": closes[-1],
            "regularMarketTime": timestamps[-1],
            "regularMarketPreviousClose": closes[-2] if len(closes) >= 2 else None,
        }
        return {
            "meta": meta,
            "timestamp": timestamps,
            "indicators": {"quote": [{"close": closes, "low": lows, "high": highs}]},
        }
    except Exception as e:
        print(f"[Stooq] {stooq_symbol} zlyhal: {e}")
        return None


def get_return_over_days(points, latest_price, days_back):
    """Vypočíta % výkonnosť oproti najbližšiemu obchodnému dňu spred `days_back` dní."""
    if not points or latest_price <= 0:
        return None
    latest_ts = points[-1][0]
    target_ts = latest_ts - days_back * 86400

    if points[0][0] > target_ts + 14 * 86400:
        return None

    best_price = None
    best_diff = float("inf")
    for ts, close_val in points:
        diff = abs(ts - target_ts)
        if diff < best_diff:
            best_diff = diff
            best_price = close_val

    if best_price and best_price > 0:
        return ((latest_price / best_price) - 1.0) * 100.0
    return None


def fetch_etf_data(cfg, client):
    """Stiahne cenu, čas kurzu, 1M/3M/6M/1R výkonnosť, 52T rozpätie a ATH (Yahoo -> yfinance -> Stooq)."""
    symbol = cfg["yahoo"]
    stooq_symbol = cfg.get("stooq", symbol.lower())
    live = False
    source = "fallback"
    market_ts = None

    price = cfg["fallback_price"]
    day_pct = cfg["fallback_day_pct"]
    ath = cfg["fallback_ath"]
    ath_date_str = cfg["fallback_ath_date"]
    low_52w = cfg["fallback_min_52w"]
    high_52w = cfg["fallback_max_52w"]
    perf_1m = cfg["fallback_perf"]["1m"]
    perf_3m = cfg["fallback_perf"]["3m"]
    perf_6m = cfg["fallback_perf"]["6m"]
    perf_1y = cfg["fallback_perf"]["1y"]

    try:
        chart = client.fetch_chart(symbol, "max", "1d")
        if chart is not None:
            source = "Yahoo Finance"
        else:
            chart = client.fetch_chart(symbol, "2y", "1d")
            if chart is not None:
                source = "Yahoo Finance"

        if chart is None:
            chart = fetch_etf_via_yfinance(symbol)
            if chart is not None:
                source = "Yahoo Finance"

        if chart is None:
            chart = fetch_etf_via_stooq(stooq_symbol)
            if chart is not None:
                source = "Stooq"

        if chart:
            meta = chart.get("meta", {})
            timestamps = chart.get("timestamp", [])
            quote = chart.get("indicators", {}).get("quote", [{}])[0]
            raw_closes = quote.get("close", [])
            raw_lows = quote.get("low", [])
            raw_highs = quote.get("high", [])

            points = []
            for idx in range(min(len(timestamps), len(raw_closes))):
                c_val = raw_closes[idx]
                if c_val is not None:
                    points.append((int(timestamps[idx]), float(c_val)))

            reg_price = meta.get("regularMarketPrice")
            if reg_price is not None:
                price = float(reg_price)
                live = True
            elif points:
                price = points[-1][1]
                live = True

            reg_time = meta.get("regularMarketTime")
            if reg_time:
                market_ts = int(reg_time)
            elif points:
                market_ts = points[-1][0]

            prev_close = meta.get("regularMarketPreviousClose")
            if prev_close is None and len(points) >= 2:
                prev_close = points[-2][1]
            if prev_close and float(prev_close) > 0:
                day_pct = ((price / float(prev_close)) - 1.0) * 100.0

            if points:
                latest_ts = points[-1][0]
                cutoff_1y = latest_ts - 365 * 86400

                r1m = get_return_over_days(points, price, 30)
                r3m = get_return_over_days(points, price, 91)
                r6m = get_return_over_days(points, price, 183)
                r1y = get_return_over_days(points, price, 365)

                if r1m is not None:
                    perf_1m = r1m
                if r3m is not None:
                    perf_3m = r3m
                if r6m is not None:
                    perf_6m = r6m
                if r1y is not None:
                    perf_1y = r1y

                lows_1y = [
                    float(raw_lows[i])
                    for i in range(min(len(timestamps), len(raw_lows)))
                    if timestamps[i] >= cutoff_1y and raw_lows[i] is not None
                ]
                highs_1y = [
                    float(raw_highs[i])
                    for i in range(min(len(timestamps), len(raw_highs)))
                    if timestamps[i] >= cutoff_1y and raw_highs[i] is not None
                ]

                meta_low = meta.get("fiftyTwoWeekLow")
                meta_high = meta.get("fiftyTwoWeekHigh")
                if meta_low:
                    low_52w = float(meta_low)
                elif lows_1y:
                    low_52w = min(lows_1y)

                if meta_high:
                    high_52w = float(meta_high)
                elif highs_1y:
                    high_52w = max(highs_1y)

                # Historické ATH a dátum maxima (MM/RR) priamo z dennej histórie
                best_val = 0.0
                best_ts = None
                for idx in range(len(timestamps)):
                    h_val = raw_highs[idx] if idx < len(raw_highs) else None
                    c_val = raw_closes[idx] if idx < len(raw_closes) else None
                    cand = h_val if h_val is not None else c_val
                    if cand is not None and float(cand) > best_val:
                        best_val = float(cand)
                        best_ts = timestamps[idx]

                if best_val > 0:
                    ath = max(best_val, price, high_52w)
                    if best_ts:
                        dt = ts_to_bratislava(best_ts)
                        ath_date_str = dt.strftime("%m/%y")
    except Exception as e:
        print(f"Chyba spracovania {symbol}: {e} (používam záložné dáta)")

    if price > ath:
        ath = price
        ath_date_str = get_now_bratislava().strftime("%m/%y")
    low_52w = min(low_52w, price)
    high_52w = max(high_52w, price)

    drawdown_pct = ((price / ath) - 1.0) * 100.0 if ath > 0 else 0.0
    needed_gain_pct = ((ath / price) - 1.0) * 100.0 if (0 < price < ath) else 0.0

    span_52w = high_52w - low_52w
    pos_52w = (price - low_52w) / span_52w if span_52w > 0 else 0.5
    pos_52w = max(0.0, min(1.0, pos_52w))

    print(f"  {cfg['ticker']}: {price:.3f} EUR | ATH {ath:.3f} ({drawdown_pct:.1f}%) | zdroj={source}")

    return {
        "ticker": cfg["ticker"],
        "name": cfg["name"],
        "region": cfg["region"],
        "price": price,
        "day_pct": day_pct,
        "ath": ath,
        "ath_date": ath_date_str,
        "drawdown_pct": drawdown_pct,
        "needed_gain_pct": needed_gain_pct,
        "perf_1m": perf_1m,
        "perf_3m": perf_3m,
        "perf_6m": perf_6m,
        "perf_1y": perf_1y,
        "low_52w": low_52w,
        "high_52w": high_52w,
        "pos_52w": pos_52w,
        "live": live,
        "source": source,
        "market_ts": market_ts,
    }


# --- KRESLIACE POMOCNÉ FUNKCIE (E-INK) ---

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


def draw_ath_drawdown_meter(draw, x0, y0, x1, drawdown_pct, fonts):
    """Vykreslí popis 'Pokles od ATH' v rovnakom riadku ako lištu s presne vycentrovanou stupnicou."""
    label = "Pokles od ATH"
    label_font = fonts["bold_12"]
    scale_font = fonts["bold_11"]

    bar_h = 20
    bar_y0 = y0
    bar_y1 = y0 + bar_h

    # Popis zarovnaný vľavo a vertikálne vycentrovaný k lište grafu
    lbl_bbox = draw.textbbox((0, 0), label, font=label_font)
    lbl_w = lbl_bbox[2] - lbl_bbox[0]
    lbl_h = lbl_bbox[3] - lbl_bbox[1]
    lbl_y = round(bar_y0 + (bar_h - lbl_h) / 2.0 - lbl_bbox[1])
    draw.text((round(x0 - lbl_bbox[0]), lbl_y), label, font=label_font, fill=TEXT_COLOR)

    # Rezerva vpravo (-19 px), aby bolo −25% presne vycentrované pod pravou ryskami a neprečnievalo
    bar_x0 = int(x0 + lbl_w + 13)
    bar_x1 = int(x1 - 19)
    bar_w = bar_x1 - bar_x0
    if bar_w <= 20:
        return

    dd_abs = abs(min(0.0, drawdown_pct))
    scale_max = max(25.0, float(math.ceil(dd_abs / 5.0) * 5))
    step_pct = 5.0 if scale_max <= 25.0 else 10.0

    # Vonkajší rámik lišty
    draw.rectangle([bar_x0, bar_y0, bar_x1, bar_y1], fill=BACKGROUND_COLOR, outline=TEXT_COLOR, width=2)

    # Výplň aktuálneho poklesu (od -10% plná čierna, pod 10% šrafovaná)
    if dd_abs > 0.05:
        fill_w = max(2, int((min(dd_abs, scale_max) / scale_max) * (bar_w - 2)))
        draw_hatched_rect(
            draw,
            bar_x0 + 1,
            bar_y0 + 1,
            bar_x0 + 1 + fill_w,
            bar_y1 - 1,
            step=4,
            fill_solid=(drawdown_pct <= ATH_INVERT_THRESHOLD),
        )

    # Zvislé deliace rysky a popisky vycentrované presne na stred každej rysky
    tick_vals = []
    cur = 0.0
    while cur < scale_max:
        tick_vals.append(cur)
        cur += step_pct
    tick_vals.append(scale_max)

    tick_lbl_y = bar_y1 + 5
    for val in tick_vals:
        tx = bar_x0 + int(round((val / scale_max) * bar_w))
        if 0 < val < scale_max:
            draw_dashed_vline(draw, tx, bar_y0 + 2, bar_y1 - 2, dash=2, gap=2)
        draw.line([(tx, bar_y1), (tx, bar_y1 + 3)], fill=TEXT_COLOR, width=1)

        lbl_txt = "0%" if val == 0 else f"{MINUS_SIGN}{int(val)}%"
        draw_text_aligned(draw, tx, tick_lbl_y, lbl_txt, scale_font, align="center")


# --- HLAVNÉ VYKRESLENIE DASHBOARDU (KARTY 2×2) ---

def create_etf_dashboard():
    # Krok 1: Všetky čierne prvky na bielom pozadí kreslíme do odtieňov sivej ('L')
    img_gray = Image.new(RENDER_MODE, (WIDTH, HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img_gray)
    fonts = get_fonts()
    now = get_now_bratislava()

    client = YahooClient()
    print(f"Backend HTTP: {client.backend} | yfinance={'áno' if yf else 'nie'}")

    etfs = []
    for idx, cfg in enumerate(ETF_CONFIG):
        if idx > 0:
            time.sleep(0.6)
        etfs.append(fetch_etf_data(cfg, client))

    live_sources = sorted({e["source"] for e in etfs if e["live"]})
    any_live = len(live_sources) > 0
    market_times = [e["market_ts"] for e in etfs if e.get("market_ts")]
    latest_market_dt = ts_to_bratislava(max(market_times)) if market_times else now
    footer_nameday_text = get_nameday_or_holiday(now)
    print(f"Dátum (BA): {now.strftime('%d.%m.%Y %H:%M')} | {footer_nameday_text}")

    header_h = 46
    inverted_tasks = []  # Čierne bloky s bielym textom (vykreslia sa s vlastným prahom)

    # ==========================================================
    # A. HLAVIČKA (y = 0..46): Názov | Dátum a čas
    # ==========================================================
    def draw_header(hd, hw, hh):
        title_left = "ETF PORTFÓLIO · XETRA"
        hd.text((12, 13), title_left, font=fonts["header"], fill=BACKGROUND_COLOR)

        days_short = ["Pon", "Uto", "Str", "Štv", "Pia", "So", "Ne"]
        date_right = f"{days_short[now.weekday()]} {now.strftime('%d.%m.%Y  %H:%M')}"
        w_date = hd.textlength(date_right, font=fonts["header_date"])
        right_start_x = hw - w_date - 12
        hd.text((right_start_x, 15), date_right, font=fonts["header_date"], fill=BACKGROUND_COLOR)

    inverted_tasks.append((0, 0, WIDTH, header_h, draw_header))

    # ==========================================================
    # B. MRIEŽKA 2×2 ETF KARIET (x = 8..792, y = 50..448)
    # ==========================================================
    margin_x = 8
    gap_x = 8
    card_w = (WIDTH - 2 * margin_x - gap_x) // 2  # 388 px

    start_y = 50
    gap_y = 8
    card_h = 195  # 50 + 195 + 8 + 195 = 448 px (4 px odstup od pätičky y = 452)

    def make_centered_inverted_drawer(label_text, font_obj):
        def _draw(sd, sw, sh):
            draw_text_centered_in_box(sd, 0, 0, sw, sh, label_text, font_obj, fill=BACKGROUND_COLOR)
        return _draw

    for idx, e in enumerate(etfs[:4]):
        col = idx % 2
        row = idx // 2
        cx = margin_x + col * (card_w + gap_x)
        cy = start_y + row * (card_h + gap_y)
        inner_l = cx + 10
        inner_r = cx + card_w - 10

        # Vonkajší rámik karty (2 px)
        draw.rectangle([cx, cy, cx + card_w, cy + card_h], outline=TEXT_COLOR, width=2)

        # 1. Horný riadok karty: Ticker štítok + Región | ATH štítok (inverzný pri <= -10%)
        inverted_tasks.append((
            inner_l,
            cy + 9,
            inner_l + 64,
            cy + 34,
            make_centered_inverted_drawer(e["ticker"], fonts["ticker"]),
        ))
        draw.text((inner_l + 72, cy + 13), e["region"], font=fonts["bold_13"], fill=TEXT_COLOR)

        if abs(e["drawdown_pct"]) < 0.05:
            ath_badge_txt = "NA MAXIME"
        else:
            ath_badge_txt = f"ATH {fmt_pct(e['drawdown_pct'], show_plus=False, decimals=1)}"

        badge_x0 = inner_r - 126
        badge_y0 = cy + 9
        badge_x1 = inner_r
        badge_y1 = cy + 35

        if e["drawdown_pct"] <= ATH_INVERT_THRESHOLD:
            inverted_tasks.append((
                badge_x0,
                badge_y0,
                badge_x1,
                badge_y1,
                make_centered_inverted_drawer(ath_badge_txt, fonts["bold_14"]),
            ))
        else:
            draw.rectangle([badge_x0, badge_y0, badge_x1, badge_y1], outline=TEXT_COLOR, width=2)
            draw_text_centered_in_box(
                draw, badge_x0, badge_y0, badge_x1, badge_y1, ath_badge_txt, fonts["bold_14"], fill=TEXT_COLOR
            )

        # 2. Názov fondu, veľká cena (vľavo) + Dnes, ATH a Na ATH (vpravo)
        draw.text((inner_l, cy + 39), e["name"], font=fonts["reg_13"], fill=TEXT_COLOR)
        draw.text((inner_l, cy + 56), fmt_eur(e["price"]), font=fonts["price_lg"], fill=TEXT_COLOR)

        day_str = f"Dnes: {fmt_pct(e['day_pct'], decimals=2)}"
        draw_text_aligned(draw, inner_r, cy + 40, day_str, fonts["bold_14"], align="right")

        ath_info = f"ATH: {fmt_eur(e['ath'])} ({e['ath_date']})"
        draw_text_aligned(draw, inner_r, cy + 60, ath_info, fonts["bold_12"], align="right")

        na_ath_str = (
            "Na ATH: 0,0%"
            if e["needed_gain_pct"] < 0.05
            else f"Na ATH: {fmt_pct(e['needed_gain_pct'], show_plus=True, decimals=1)}"
        )
        draw_text_aligned(draw, inner_r, cy + 76, na_ath_str, fonts["bold_12"], align="right")

        # 3. Jednoriadkový merač poklesu od ATH ("Pokles od ATH" + lišta + centrovaná stupnica)
        draw_ath_drawdown_meter(draw, inner_l, cy + 101, inner_r, e["drawdown_pct"], fonts)

        # 4. 52-týždňový rozsah (52T + 18 px medzera + Min | posuvník | Max)
        row_52w_y = cy + 148
        lbl_52t = "52T"
        low_txt = fmt_eur(e["low_52w"], with_symbol=False)
        high_txt = fmt_eur(e["high_52w"], with_symbol=False)

        draw.text((inner_l, row_52w_y), lbl_52t, font=fonts["bold_12"], fill=TEXT_COLOR)
        lbl_52t_w = draw.textlength(lbl_52t, font=fonts["bold_12"])

        low_x = int(inner_l + lbl_52t_w + 18)  # Zväčšená medzera za "52T"
        draw.text((low_x, row_52w_y), low_txt, font=fonts["bold_12"], fill=TEXT_COLOR)
        draw_text_aligned(draw, inner_r, row_52w_y, high_txt, fonts["bold_12"], align="right")

        low_w = draw.textlength(low_txt, font=fonts["bold_12"])
        high_w = draw.textlength(high_txt, font=fonts["bold_12"])
        bar_x0 = int(low_x + low_w + 10)
        bar_x1 = int(inner_r - high_w - 10)
        bar_y = row_52w_y + 7
        if bar_x1 > bar_x0 + 16:
            draw.line([(bar_x0, bar_y), (bar_x1, bar_y)], fill=TEXT_COLOR, width=2)
            draw.line([(bar_x0, bar_y - 4), (bar_x0, bar_y + 4)], fill=TEXT_COLOR, width=1)
            draw.line([(bar_x1, bar_y - 4), (bar_x1, bar_y + 4)], fill=TEXT_COLOR, width=1)
            marker_x = bar_x0 + int(e["pos_52w"] * (bar_x1 - bar_x0))
            draw.rectangle([marker_x - 3, bar_y - 5, marker_x + 3, bar_y + 5], fill=TEXT_COLOR)

        # 5. Výkonnostný riadok (1M · 3M · 6M · 1R)
        draw.line([(inner_l, cy + 168), (inner_r, cy + 168)], fill=TEXT_COLOR, width=1)
        perf_y = cy + 173
        draw_text_aligned(
            draw, inner_l, perf_y, f"1M {fmt_pct(e['perf_1m'], decimals=1)}", fonts["bold_12"], align="left"
        )
        draw_text_aligned(
            draw, cx + 148, perf_y, f"3M {fmt_pct(e['perf_3m'], decimals=1)}", fonts["bold_12"], align="center"
        )
        draw_text_aligned(
            draw, cx + 242, perf_y, f"6M {fmt_pct(e['perf_6m'], decimals=1)}", fonts["bold_12"], align="center"
        )
        draw_text_aligned(
            draw, inner_r, perf_y, f"1R {fmt_pct(e['perf_1y'], decimals=1)}", fonts["bold_12"], align="right"
        )

    # ==========================================================
    # C. PÄTIČKA (y = 452..480) — zdroj + čas dát + meniny/sviatok
    #    (rezerva vpravo od x = 640 pre Battery: XX% na reTerminale)
    # ==========================================================
    draw.line([(0, 452), (WIDTH, 452)], fill=TEXT_COLOR, width=1)
    if any_live:
        src_label = " / ".join(live_sources)
        data_time_str = latest_market_dt.strftime("%d.%m.%Y %H:%M")
        status_txt = f"{src_label} · Dáta: {data_time_str}"
    else:
        status_txt = f"ZÁLOŽNÉ DÁTA · API nedostupné · {now.strftime('%d.%m.%Y %H:%M')}"

    if footer_nameday_text:
        status_txt = f"{status_txt} · {footer_nameday_text}"

    max_footer_w = 628  # x = 12..640 (neprekryje sa s "Battery: XX%" vpravo dole)
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
