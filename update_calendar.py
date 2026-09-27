import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup


# ============================================================
# EINSTELLUNGEN
# ============================================================

TEAM_ID = "011MIDEIGO000000VTVG0001VTR8C1K7"

OUTPUT_FILE = "kalender.ics"
VENUES_FILE = "spielstaetten.json"

LOCAL_TZ = ZoneInfo("Europe/Berlin")

MATCHPLAN_URL = (
    "https://www.fussball.de/ajax.team.matchplan/-/"
    "mode/PAGE/"
    f"team-id/{TEAM_ID}"
)

BASE_DIR = Path(__file__).resolve().parent


# ============================================================
# INTERNET / TEXT
# ============================================================

def fetch_url(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:
        return response.read().decode(
            "utf-8",
            errors="replace"
        )


def normalize_text(text):
    if not text:
        return ""

    text = str(text).lower()
    text = text.replace("ß", "ss")

    text = re.sub(
        r"[^a-z0-9äöü ]+",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


# ============================================================
# SPIELSTÄTTEN-DATENBANK
# ============================================================

def load_venues():

    path = BASE_DIR / VENUES_FILE

    if not path.exists():
        raise FileNotFoundError(
            f"{VENUES_FILE} wurde nicht gefunden."
        )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(file)

    clubs = data.get(
        "clubs",
        {}
    )

    if not clubs:
        raise RuntimeError(
            "Keine Vereine in spielstaetten.json gefunden."
        )

    print(
        f"{len(clubs)} Vereine aus "
        f"{VENUES_FILE} geladen."
    )

    return clubs


def find_club(clubs, home_team):

    home = normalize_text(
        home_team
    )

    # Exakte Übereinstimmung
    for club_name, club_data in clubs.items():

        if normalize_text(
            club_name
        ) == home:

            return (
                club_name,
                club_data
            )

    # Leichte Abweichungen
    for club_name, club_data in clubs.items():

        normalized = normalize_text(
            club_name
        )

        if (
            normalized in home
            or home in normalized
        ):

            return (
                club_name,
                club_data
            )

    return (
        None,
        None
    )


def choose_fixed_venue(
    clubs,
    home_team,
    fussball_location
):

    club_name, club_data = find_club(
        clubs,
        home_team
    )

    if not club_data:
        return None

    venues = club_data.get(
        "venues",
        []
    )

    if not venues:
        return None

    # Nur eine Spielstätte
    if len(venues) == 1:
        return venues[0]

    scraped = normalize_text(
        fussball_location
    )

    if not scraped:
        return None

    # Zuerst Aliases prüfen
    for venue in venues:

        for alias in venue.get(
            "aliases",
            []
        ):

            alias_normalized = normalize_text(
                alias
            )

            if (
                alias_normalized
                and (
                    alias_normalized in scraped
                    or scraped in alias_normalized
                )
            ):

                return venue

    # Danach den normalen Namen prüfen
    for venue in venues:

        venue_name = normalize_text(
            venue.get(
                "name",
                ""
            )
        )

        if (
            venue_name
            and (
                venue_name in scraped
                or scraped in venue_name
            )
        ):

            return venue

    print(
        "  Keine eindeutige feste "
        f"Spielstätte für {home_team} gefunden."
    )

    return None


# ============================================================
# KOORDINATEN AUS JSON
# ============================================================

def find_coordinates_in_json(data):

    if isinstance(
        data,
        dict
    ):

        latitude = None
        longitude = None

        for key, value in data.items():

            key_lower = str(
                key
            ).lower()

            if key_lower in (
                "latitude",
                "lat"
            ):

                latitude = value

            if key_lower in (
                "longitude",
                "lng",
                "lon"
            ):

                longitude = value

        if (
            latitude is not None
            and longitude is not None
        ):

            try:

                return (
                    float(latitude),
                    float(longitude)
                )

            except (
                TypeError,
                ValueError
            ):

                pass

        for value in data.values():

            result = find_coordinates_in_json(
                value
            )

            if result:
                return result

    elif isinstance(
        data,
        list
    ):

        for item in data:

            result = find_coordinates_in_json(
                item
            )

            if result:
                return result

    return None


# ============================================================
# KOORDINATEN AUS HTML
# ============================================================

def find_coordinates_in_html(html):

    patterns = [

        (
            r'"latitude"\s*:\s*'
            r'([-+]?\d+(?:\.\d+)?)'
            r'.{0,500}?'
            r'"longitude"\s*:\s*'
            r'([-+]?\d+(?:\.\d+)?)'
        ),

        (
            r'"lat"\s*:\s*'
            r'([-+]?\d+(?:\.\d+)?)'
            r'.{0,500}?'
            r'"(?:lng|lon|longitude)"\s*:\s*'
            r'([-+]?\d+(?:\.\d+)?)'
        ),

        (
            r'geo:'
            r'([-+]?\d+(?:\.\d+)?),'
            r'([-+]?\d+(?:\.\d+)?)'
        ),

        (
            r'@'
            r'([-+]?\d+(?:\.\d+)?),'
            r'([-+]?\d+(?:\.\d+)?)'
        ),

        (
            r'!3d'
            r'([-+]?\d+(?:\.\d+)?)'
            r'!4d'
            r'([-+]?\d+(?:\.\d+)?)'
        )
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            html,
            re.IGNORECASE | re.DOTALL
        )

        if not match:
            continue

        try:

            latitude = float(
                match.group(1)
            )

            longitude = float(
                match.group(2)
            )

            if (
                47 <= latitude <= 55
                and 5 <= longitude <= 16
            ):

                return (
                    latitude,
                    longitude
                )

        except (
            ValueError,
            TypeError
        ):

            pass

    return None


# ============================================================
# KOORDINATEN AUS GOOGLE-MAPS-LINK
# ============================================================

def find_coordinates_in_google_link(href):

    if not href:
        return None

    patterns = [

        (
            r'@'
            r'([-+]?\d+(?:\.\d+)?),'
            r'([-+]?\d+(?:\.\d+)?)'
        ),

        (
            r'!3d'
            r'([-+]?\d+(?:\.\d+)?)'
            r'!4d'
            r'([-+]?\d+(?:\.\d+)?)'
        ),

        (
            r'[?&]q='
            r'([-+]?\d+(?:\.\d+)?),'
            r'([-+]?\d+(?:\.\d+)?)'
        ),

        (
            r'[?&]query='
            r'([-+]?\d+(?:\.\d+)?),'
            r'([-+]?\d+(?:\.\d+)?)'
        )
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            href,
            re.IGNORECASE
        )

        if not match:
            continue

        try:

            latitude = float(
                match.group(1)
            )

            longitude = float(
                match.group(2)
            )

            if (
                47 <= latitude <= 55
                and 5 <= longitude <= 16
            ):

                return (
                    latitude,
                    longitude
                )

        except (
            ValueError,
            TypeError
        ):

            pass

    return None


# ============================================================
# ADRESSE BEREINIGEN
# ============================================================

def extract_clean_address(location):

    if not location:
        return ""

    location = re.sub(
        r"\s+",
        " ",
        location
    ).strip()

    # Straße + Hausnummer + PLZ + Ort
    pattern = re.compile(
        r"("
        r"[A-Za-zÄÖÜäöüßÀ-ÿ0-9]"
        r"[A-Za-zÄÖÜäöüßÀ-ÿ0-9 .'\-/]*"
        r"\s+\d+[A-Za-z]?"
        r"\s*,\s*"
        r"\d{5}"
        r"\s+"
        r"[A-Za-zÄÖÜäöüßÀ-ÿ0-9 .'\-/]+"
        r")$",
        re.IGNORECASE
    )

    match = pattern.search(
        location
    )

    if match:
        return match.group(1).strip()

    # Straße ohne Hausnummer
    pattern = re.compile(
        r"("
        r"[A-Za-zÄÖÜäöüßÀ-ÿ0-9]"
        r"[A-Za-zÄÖÜäöüßÀ-ÿ0-9 .'\-/]*"
        r"(?:str\.|straße|weg|allee|platz|"
        r"ring|gasse|ufer|chaussee)"
        r"\s*,\s*"
        r"\d{5}"
        r"\s+"
        r"[A-Za-zÄÖÜäöüßÀ-ÿ0-9 .'\-/]+"
        r")$",
        re.IGNORECASE
    )

    match = pattern.search(
        location
    )

    if match:
        return match.group(1).strip()

    # Fallback PLZ + Ort
    postal = re.search(
        r"(\d{5}\s+"
        r"[A-Za-zÄÖÜäöüßÀ-ÿ0-9 .'\-/]+)$",
        location
    )

    if postal:

        postal_part = postal.group(1)

        before = location[
            :postal.start()
        ].rstrip(" ,")

        parts = before.split(",")

        if parts:

            possible_street = parts[-1].strip()

            if (
                re.search(
                    r"\d",
                    possible_street
                )
                or re.search(
                    r"(str\.|straße|weg|allee|platz|"
                    r"ring|gasse|ufer|chaussee)",
                    possible_street,
                    re.IGNORECASE
                )
            ):

                return (
                    possible_street
                    + ", "
                    + postal_part
                ).strip()

    return location


# ============================================================
# SPIELORT VON FUSSBALL.DE
# ============================================================

def get_game_location(game_url):

    if not game_url:

        return {
            "location": "",
            "address": "",
            "latitude": None,
            "longitude": None
        }

    try:

        html = fetch_url(
            game_url
        )

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        location = ""
        latitude = None
        longitude = None

        # JSON-LD
        scripts = soup.select(
            'script[type="application/ld+json"]'
        )

        for script in scripts:

            text = script.string

            if not text:

                text = script.get_text(
                    strip=True
                )

            if not text:
                continue

            try:

                data = json.loads(
                    text
                )

                coordinates = (
                    find_coordinates_in_json(
                        data
                    )
                )

                if coordinates:

                    latitude = coordinates[0]
                    longitude = coordinates[1]

            except Exception:
                pass

        # Google Maps Link
        google_links = soup.select(
            'a[href*="google."]'
        )

        for link in google_links:

            href = link.get(
                "href",
                ""
            )

            coordinates = (
                find_coordinates_in_google_link(
                    href
                )
            )

            if coordinates:

                latitude = coordinates[0]
                longitude = coordinates[1]

            link_text = link.get_text(
                " ",
                strip=True
            )

            if link_text:

                location = link_text
                break

        # HTML nach Koordinaten
        if (
            latitude is None
            or longitude is None
        ):

            coordinates = (
                find_coordinates_in_html(
                    html
                )
            )

            if coordinates:

                latitude = coordinates[0]
                longitude = coordinates[1]

        # Fallback für Spielstätten-Text
        if not location:

            page_text = soup.get_text(
                " ",
                strip=True
            )

            pattern = (
                r"((?:Rasenplatz|"
                r"Kunstrasenplatz|"
                r"Sportplatz|"
                r"Stadion|"
                r"Sportanlage|"
                r"Kunstrasen).*?)"
                r"(?=\s+(?:Schiedsrichter|"
                r"Assistenten|"
                r"Zuschauer|"
                r"Staffel-ID|"
                r"Spielberichte|"
                r"News|$))"
            )

            match = re.search(
                pattern,
                page_text,
                re.IGNORECASE
            )

            if match:

                location = re.sub(
                    r"\s+",
                    " ",
                    match.group(1).strip()
                )

        address = extract_clean_address(
            location
        )

        return {
            "location": location,
            "address": address,
            "latitude": latitude,
            "longitude": longitude
        }

    except Exception as error:

        print(
            "Spielort konnte nicht geladen werden:"
        )

        print(
            game_url
        )

        print(
            f"Fehler: {error}"
        )

        return {
            "location": "",
            "address": "",
            "latitude": None,
            "longitude": None
        }


# ============================================================
# APPLE-MAPS-LINK
# ============================================================

def create_apple_maps_url(
    name,
    latitude,
    longitude
):

    if (
        latitude is None
        or longitude is None
    ):

        return ""

    # Apple Maps Unified URL
    #
    # Der Ort wird über die Koordinaten eindeutig
    # bestimmt. Der Name dient als Such-/Anzeigetext.

    query = quote(
        name or "Spielstätte",
        safe=""
    )

    return (
        "https://maps.apple.com/"
        "?ll="
        + str(latitude)
        + "%2C"
        + str(longitude)
        + "&q="
        + query
    )


# ============================================================
# iCAL ESCAPING
# ============================================================

def escape_ics(text):

    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def escape_ics_parameter(text):

    return (
        str(text)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


# ============================================================
# SPIELE LADEN
# ============================================================

def get_games(clubs):

    print(
        "Hole Spielplan von FUSSBALL.DE..."
    )

    html = fetch_url(
        MATCHPLAN_URL
    )

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    games = []

    seen_ids = set()
    seen_fallback = set()

    rows = soup.select(
        "div.club-matchplan-table "
        "tr.row-competition"
    )

    for row in rows:

        text = row.get_text(
            " ",
            strip=True
        )

        # Nur Meisterschaft
        if "ME" not in text:
            continue

        # Spiel-ID
        id_match = re.search(
            r"\b(\d{9})\b",
            text
        )

        match_id = (
            id_match.group(1)
            if id_match
            else None
        )

        # Datum
        date_match = re.search(
            r"(\d{2}\.\d{2}\.\d{2,4})",
            text
        )

        if not date_match:
            continue

        day, month, year = map(
            int,
            date_match.group(1).split(".")
        )

        if year < 100:
            year += 2000

        # Uhrzeit
        time_match = re.search(
            r"(\d{1,2}):(\d{2})",
            text
        )

        if time_match:

            hour = int(
                time_match.group(1)
            )

            minute = int(
                time_match.group(2)
            )

            dt = datetime(
                year,
                month,
                day,
                hour,
                minute,
                tzinfo=LOCAL_TZ
            )

            all_day = False

        else:

            dt = datetime(
                year,
                month,
                day,
                tzinfo=LOCAL_TZ
            )

            all_day = True

        # Mannschaften
        team_row = (
            row.find_next_sibling("tr")
        )

        if not team_row:
            continue

        team_elements = team_row.select(
            ".club-name"
        )

        if len(team_elements) < 2:
            continue

        home = team_elements[0].get_text(
            " ",
            strip=True
        )

        away = team_elements[1].get_text(
            " ",
            strip=True
        )

        # Spiel-Link
        game_url = ""

        game_link = team_row.select_one(
            'a[href*="/spiel/"]'
        )

        if not game_link:

            game_link = row.select_one(
                'a[href*="/spiel/"]'
            )

        if game_link:

            game_url = game_link.get(
                "href",
                ""
            )

        if game_url.startswith("/"):

            game_url = (
                "https://www.fussball.de"
                + game_url
            )

        # Doppelte Spiele vermeiden
        fallback_key = (
            f"{year:04d}-"
            f"{month:02d}-"
            f"{day:02d}|"
            f"{home}|"
            f"{away}"
        )

        if match_id:

            if match_id in seen_ids:

                print(
                    "Doppeltes Spiel ignoriert: "
                    f"{match_id}"
                )

                continue

            seen_ids.add(
                match_id
            )

        else:

            if fallback_key in seen_fallback:
                continue

            seen_fallback.add(
                fallback_key
            )

            match_id = fallback_key.replace(
                "|",
                "-"
            )

        # FUSSBALL.DE Spielort
        location = ""
        address = ""
        latitude = None
        longitude = None

        if game_url:

            print(
                f"Lade Spielort: "
                f"{home} – {away}"
            )

            location_data = (
                get_game_location(
                    game_url
                )
            )

            location = (
                location_data["location"]
            )

            address = (
                location_data["address"]
            )

            latitude = (
                location_data["latitude"]
            )

            longitude = (
                location_data["longitude"]
            )

        # Unsere feste Spielstätte
        fixed_venue = choose_fixed_venue(
            clubs,
            home,
            location
        )

        if fixed_venue:

            print(
                "  ✓ Feste Spielstätte: "
                + fixed_venue.get(
                    "name",
                    ""
                )
            )

            location = fixed_venue.get(
                "name",
                location
            )

            address = fixed_venue.get(
                "address",
                address
            )

            fixed_latitude = fixed_venue.get(
                "latitude"
            )

            fixed_longitude = fixed_venue.get(
                "longitude"
            )

            if (
                fixed_latitude is not None
                and fixed_longitude is not None
            ):

                latitude = fixed_latitude
                longitude = fixed_longitude

            print(
                "  ✓ Adresse: "
                + address
            )

            if (
                latitude is not None
                and longitude is not None
            ):

                print(
                    "  ✓ Koordinaten: "
                    f"{latitude}, {longitude}"
                )

        else:

            if location:

                print(
                    "  FUSSBALL.DE Spielstätte: "
                    + location
                )

            if address:

                print(
                    "  FUSSBALL.DE Adresse: "
                    + address
                )

        games.append({
            "id": match_id,
            "home": home,
            "away": away,
            "datetime": dt,
            "all_day": all_day,
            "location": location,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "game_url": game_url
        })

    if not games:

        raise RuntimeError(
            "Keine Meisterschaftsspiele "
            "von FUSSBALL.DE gefunden."
        )

    games.sort(
        key=lambda game: game["datetime"]
    )

    return games


# ============================================================
# iCAL ERSTELLEN
# ============================================================

def make_ics(games):

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SG Dettingen-Dingelsdorf//"
        "Landesliga 3//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:"
        "SG Dettingen-Dingelsdorf",
        "X-WR-TIMEZONE:"
        "Europe/Berlin"
    ]

    for game in games:

        dt = game["datetime"]

        lines.append(
            "BEGIN:VEVENT"
        )

        # ID
        lines.append(
            "UID:sgdd-"
            + escape_ics(
                game["id"]
            )
            + "@github.com"
        )

        # Erstellungszeit
        lines.append(
            "DTSTAMP:"
            + datetime.now(
                timezone.utc
            ).strftime(
                "%Y%m%dT%H%M%SZ"
            )
        )

        # Termine ohne Uhrzeit
        if game["all_day"]:

            start_date = dt.date()

            # Sonntag → Samstag bis Montag
            if start_date.weekday() == 6:

                saturday = (
                    start_date
                    - timedelta(days=1)
                )

            else:

                saturday = start_date

            monday = (
                saturday
                + timedelta(days=2)
            )

            lines.append(
                "DTSTART;VALUE=DATE:"
                + saturday.strftime(
                    "%Y%m%d"
                )
            )

            lines.append(
                "DTEND;VALUE=DATE:"
                + monday.strftime(
                    "%Y%m%d"
                )
            )

        # Termine mit Uhrzeit
        else:

            start = dt.astimezone(
                LOCAL_TZ
            )

            end = (
                start
                + timedelta(hours=2)
            )

            lines.append(
                "DTSTART;TZID=Europe/Berlin:"
                + start.strftime(
                    "%Y%m%dT%H%M%S"
                )
            )

            lines.append(
                "DTEND;TZID=Europe/Berlin:"
                + end.strftime(
                    "%Y%m%dT%H%M%S"
                )
            )

        # Titel
        lines.append(
            "SUMMARY:"
            + escape_ics(
                f"{game['home']} – "
                f"{game['away']}"
            )
        )

        # LOCATION bleibt die Adresse
        if game["address"]:

            lines.append(
                "LOCATION:"
                + escape_ics(
                    game["address"]
                )
            )

        elif game["location"]:

            lines.append(
                "LOCATION:"
                + escape_ics(
                    game["location"]
                )
            )

        # GEO + Apple Structured Location
        if (
            game["latitude"] is not None
            and game["longitude"] is not None
        ):

            latitude = game["latitude"]
            longitude = game["longitude"]

            apple_title = (
                game["location"]
                or game["address"]
            )

            apple_address = (
                game["address"]
                or game["location"]
            )

            lines.append(
                f"GEO:{latitude};{longitude}"
            )

            lines.append(
                "X-APPLE-STRUCTURED-LOCATION;"
                "VALUE=URI;"
                "X-ADDRESS="
                + escape_ics_parameter(
                    apple_address
                )
                + ";X-APPLE-RADIUS=71;"
                "X-TITLE="
                + escape_ics_parameter(
                    apple_title
                )
                + ":geo:"
                + str(latitude)
                + ","
                + str(longitude)
            )

        # ----------------------------------------------------
        # BESCHREIBUNG
        # ----------------------------------------------------

        description = (
            "Landesliga Südbaden Staffel 3"
        )

        # Spielstätte
        if (
            game["location"]
            and game["location"]
            != game["address"]
        ):

            description += (
                "\\nSpielstätte: "
                + escape_ics(
                    game["location"]
                )
            )

        # Apple Maps Link
        apple_maps_url = create_apple_maps_url(
            game["location"]
            or game["address"],
            game["latitude"],
            game["longitude"]
        )

        if apple_maps_url:

            description += (
                "\\nApple Maps: "
                + apple_maps_url
            )

        # FUSSBALL.DE Link
        if game["game_url"]:

            description += (
                "\\nSpiel bei FUSSBALL.DE: "
                + game["game_url"]
            )

        lines.append(
            "DESCRIPTION:"
            + description
        )

        lines.append(
            "END:VEVENT"
        )

    lines.append(
        "END:VCALENDAR"
    )

    return "\n".join(
        lines
    ) + "\n"


# ============================================================
# HAUPTPROGRAMM
# ============================================================

def main():

    print(
        "========================================"
    )

    print(
        "SG Dettingen-Dingelsdorf Kalender"
    )

    print(
        "========================================"
    )

    # Spielstätten laden
    clubs = load_venues()

    print()

    # Spielplan laden
    games = get_games(
        clubs
    )

    print()

    print(
        f"{len(games)} eindeutige "
        "Spiele gefunden."
    )

    print()

    # Kalender erzeugen
    calendar = make_ics(
        games
    )

    # Datei speichern
    output_path = (
        BASE_DIR
        / OUTPUT_FILE
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            calendar
        )

    print(
        "kalender.ics erfolgreich "
        "aktualisiert."
    )

    print(
        "========================================"
    )


if __name__ == "__main__":

    main()