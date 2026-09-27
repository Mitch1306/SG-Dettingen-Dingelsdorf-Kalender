import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup


TEAM_ID = "011MIDEIGO000000VTVG0001VTR8C1K7"
OUTPUT_FILE = "kalender.ics"
LOCAL_TZ = ZoneInfo("Europe/Berlin")

MATCHPLAN_URL = (
    "https://www.fussball.de/ajax.team.matchplan/-/"
    "mode/PAGE/"
    f"team-id/{TEAM_ID}"
)


def fetch_url(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:
        return response.read().decode(
            "utf-8",
            errors="replace"
        )


# ============================================================
# KOORDINATEN AUS JSON
# ============================================================

def find_coordinates_in_json(data):
    if isinstance(data, dict):

        latitude = None
        longitude = None

        for key in data:

            key_lower = str(key).lower()

            if key_lower in (
                "latitude",
                "lat"
            ):
                latitude = data[key]

            if key_lower in (
                "longitude",
                "lng",
                "lon"
            ):
                longitude = data[key]

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

    elif isinstance(data, list):

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

        # latitude / longitude
        (
            r'"latitude"\s*:\s*'
            r'([-+]?\d+(?:\.\d+)?)'
            r'.{0,500}?'
            r'"longitude"\s*:\s*'
            r'([-+]?\d+(?:\.\d+)?)'
        ),

        # lat / lng
        (
            r'"lat"\s*:\s*'
            r'([-+]?\d+(?:\.\d+)?)'
            r'.{0,500}?'
            r'"(?:lng|lon|longitude)"\s*:\s*'
            r'([-+]?\d+(?:\.\d+)?)'
        ),

        # geo:48.123,9.123
        (
            r'geo:'
            r'([-+]?\d+(?:\.\d+)?),'
            r'([-+]?\d+(?:\.\d+)?)'
        ),

        # Google Maps @48.123,9.123
        (
            r'@'
            r'([-+]?\d+(?:\.\d+)?),'
            r'([-+]?\d+(?:\.\d+)?)'
        ),

        # Google Maps !3d48.123!4d9.123
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

        if match:

            try:

                latitude = float(
                    match.group(1)
                )

                longitude = float(
                    match.group(2)
                )

                # Deutschland ungefähr
                # 47–55° N / 5–16° E
                # verhindert versehentliches
                # Auslesen anderer Zahlen.
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

        # Beispiel:
        # https://www.google.com/maps/@47.123,9.123,17z
        (
            r'@'
            r'([-+]?\d+(?:\.\d+)?),'
            r'([-+]?\d+(?:\.\d+)?)'
        ),

        # Beispiel:
        # !3d47.123!4d9.123
        (
            r'!3d'
            r'([-+]?\d+(?:\.\d+)?)'
            r'!4d'
            r'([-+]?\d+(?:\.\d+)?)'
        ),

        # Beispiel:
        # q=47.123,9.123
        (
            r'[?&]q='
            r'([-+]?\d+(?:\.\d+)?),'
            r'([-+]?\d+(?:\.\d+)?)'
        ),

        # Beispiel:
        # query=47.123,9.123
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

        if match:

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
# ADRESSE AUS SPIELSTÄTTE HERAUSFILTERN
# ============================================================

def extract_clean_address(location):

    if not location:
        return ""

    location = re.sub(
        r"\s+",
        " ",
        location
    ).strip()

    # --------------------------------------------------------
    # Straße + Hausnummer + PLZ + Ort
    # --------------------------------------------------------

    pattern_with_number = re.compile(
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

    match = pattern_with_number.search(
        location
    )

    if match:
        return match.group(1).strip()

    # --------------------------------------------------------
    # "An der ..." + Hausnummer + PLZ + Ort
    # --------------------------------------------------------

    pattern_an_der = re.compile(
        r"("
        r"An\s+der\s+"
        r"[A-Za-zÄÖÜäöüßÀ-ÿ0-9 .'\-/]+"
        r"\s+\d+[A-Za-z]?"
        r"\s*,\s*"
        r"\d{5}"
        r"\s+"
        r"[A-Za-zÄÖÜäöüßÀ-ÿ0-9 .'\-/]+"
        r")$",
        re.IGNORECASE
    )

    match = pattern_an_der.search(
        location
    )

    if match:
        return match.group(1).strip()

    # --------------------------------------------------------
    # Straße ohne Hausnummer
    # --------------------------------------------------------

    pattern_without_number = re.compile(
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

    match = pattern_without_number.search(
        location
    )

    if match:
        return match.group(1).strip()

    # --------------------------------------------------------
    # PLZ + Ort vorhanden:
    # letzten Teil vor der PLZ untersuchen
    # --------------------------------------------------------

    postal_match = re.search(
        r"(\d{5}\s+"
        r"[A-Za-zÄÖÜäöüßÀ-ÿ0-9 .'\-/]+)$",
        location
    )

    if postal_match:

        postal_part = postal_match.group(1)

        before_postal = location[
            :postal_match.start()
        ].rstrip(" ,")

        parts = before_postal.split(",")

        if parts:

            possible_street = (
                parts[-1].strip()
            )

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

    # Wenn keine Adresse erkannt wurde:
    # komplette Angabe zurückgeben.
    return location


# ============================================================
# SPIELORT LADEN
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

        # ----------------------------------------------------
        # 1. JSON-LD durchsuchen
        # ----------------------------------------------------

        json_scripts = soup.select(
            'script[type="application/ld+json"]'
        )

        for script in json_scripts:

            script_text = script.string

            if not script_text:

                script_text = script.get_text(
                    strip=True
                )

            if not script_text:
                continue

            try:

                data = json.loads(
                    script_text
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

        # ----------------------------------------------------
        # 2. Google-Maps-Link durchsuchen
        # ----------------------------------------------------

        google_links = soup.select(
            'a[href*="google."]'
        )

        for link in google_links:

            href = link.get(
                "href",
                ""
            )

            # Wenn im Google-Link selbst
            # Koordinaten stehen, verwenden wir
            # diese zuerst.
            coordinates = (
                find_coordinates_in_google_link(
                    href
                )
            )

            if coordinates:

                latitude = coordinates[0]
                longitude = coordinates[1]

            # Text des Links ist normalerweise
            # die Spielstätte / Adresse.
            location_text = link.get_text(
                " ",
                strip=True
            )

            if location_text:

                location = location_text

                # Wir haben unseren Google-Link
                # gefunden. Deshalb nicht unnötig
                # weitere Links durchsuchen.
                break

        # ----------------------------------------------------
        # 3. Falls noch keine Koordinaten vorhanden:
        # HTML durchsuchen
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # 4. Falls kein Google-Link gefunden:
        # Seiteninhalt durchsuchen
        # ----------------------------------------------------

        if not location:

            page_text = soup.get_text(
                " ",
                strip=True
            )

            location_patterns = [

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
            ]

            for pattern in location_patterns:

                match = re.search(
                    pattern,
                    page_text,
                    re.IGNORECASE
                )

                if match:

                    location = (
                        match.group(1)
                        .strip()
                    )

                    location = re.sub(
                        r"\s+",
                        " ",
                        location
                    )

                    break

        # ----------------------------------------------------
        # 5. Saubere Adresse erzeugen
        # ----------------------------------------------------

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
            "Spielort konnte nicht geladen "
            f"werden: {game_url}"
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
# SPIELE LADEN
# ============================================================

def get_games():

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

        # Nur Meisterschaftsspiele
        if "ME" not in text:
            continue

        # ----------------------------------------------------
        # Spiel-ID
        # ----------------------------------------------------

        number_match = re.search(
            r"\b(\d{9})\b",
            text
        )

        match_id = (
            number_match.group(1)
            if number_match
            else None
        )

        # ----------------------------------------------------
        # Datum
        # ----------------------------------------------------

        date_match = re.search(
            r"(\d{2}\.\d{2}\.\d{2,4})",
            text
        )

        if not date_match:
            continue

        parts = (
            date_match.group(1)
            .split(".")
        )

        day = int(parts[0])
        month = int(parts[1])
        year = int(parts[2])

        if year < 100:
            year += 2000

        # ----------------------------------------------------
        # Uhrzeit
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Mannschaften
        # ----------------------------------------------------

        team_row = (
            row.find_next_sibling(
                "tr"
            )
        )

        if not team_row:
            continue

        clubs = team_row.select(
            ".club-name"
        )

        if len(clubs) < 2:
            continue

        home = clubs[0].get_text(
            " ",
            strip=True
        )

        away = clubs[1].get_text(
            " ",
            strip=True
        )

        # ----------------------------------------------------
        # Spiel-Link
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Fallback-Schlüssel
        # ----------------------------------------------------

        fallback_key = (
            f"{year:04d}-"
            f"{month:02d}-"
            f"{day:02d}|"
            f"{home}|"
            f"{away}"
        )

        # ----------------------------------------------------
        # Doppelte Spiele entfernen
        # ----------------------------------------------------

        if match_id:

            if match_id in seen_ids:

                print(
                    "Doppeltes Spiel ignoriert: "
                    f"{match_id} – "
                    f"{home} – "
                    f"{away}"
                )

                continue

            seen_ids.add(
                match_id
            )

        else:

            if fallback_key in seen_fallback:

                print(
                    "Doppeltes Spiel ignoriert: "
                    f"{fallback_key}"
                )

                continue

            seen_fallback.add(
                fallback_key
            )

            match_id = (
                fallback_key.replace(
                    "|",
                    "-"
                )
            )

        # ----------------------------------------------------
        # Spielort laden
        # ----------------------------------------------------

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

            if location:

                print(
                    "  Spielstätte: "
                    f"{location}"
                )

            if address:

                print(
                    "  Adresse: "
                    f"{address}"
                )

            if (
                latitude is not None
                and longitude is not None
            ):

                print(
                    "  Koordinaten: "
                    f"{latitude}, "
                    f"{longitude}"
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
        key=lambda game:
        game["datetime"]
    )

    return games


# ============================================================
# iCAL ESCAPING
# ============================================================

def escape_ics(text):

    return (
        str(text)
        .replace(
            "\\",
            "\\\\"
        )
        .replace(
            ";",
            "\\;"
        )
        .replace(
            ",",
            "\\,"
        )
        .replace(
            "\n",
            "\\n"
        )
    )


def escape_ics_parameter(text):

    return (
        str(text)
        .replace(
            "\\",
            "\\\\"
        )
        .replace(
            '"',
            '\\"'
        )
        .replace(
            ";",
            "\\;"
        )
        .replace(
            ",",
            "\\,"
        )
        .replace(
            "\n",
            "\\n"
        )
    )


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

        # ----------------------------------------------------
        # Eindeutige ID
        # ----------------------------------------------------

        lines.append(
            "UID:sgdd-"
            + escape_ics(
                game["id"]
            )
            + "@github.com"
        )

        # ----------------------------------------------------
        # Erstellungszeit
        # ----------------------------------------------------

        lines.append(
            "DTSTAMP:"
            + datetime.now(
                timezone.utc
            ).strftime(
                "%Y%m%dT%H%M%SZ"
            )
        )

        # ----------------------------------------------------
        # Spiele ohne Uhrzeit
        # ----------------------------------------------------

        if game["all_day"]:

            start_date = dt.date()

            # Falls FUSSBALL.DE nur Sonntag
            # ohne Uhrzeit liefert, zeigen wir
            # Samstag + Sonntag als Wochenendtermin.
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

        # ----------------------------------------------------
        # Normales Spiel mit Uhrzeit
        # ----------------------------------------------------

        else:

            start_local = (
                dt.astimezone(
                    LOCAL_TZ
                )
            )

            end_local = (
                start_local
                + timedelta(hours=2)
            )

            lines.append(
                "DTSTART;TZID=Europe/Berlin:"
                + start_local.strftime(
                    "%Y%m%dT%H%M%S"
                )
            )

            lines.append(
                "DTEND;TZID=Europe/Berlin:"
                + end_local.strftime(
                    "%Y%m%dT%H%M%S"
                )
            )

        # ----------------------------------------------------
        # Spieltitel
        # ----------------------------------------------------

        lines.append(
            "SUMMARY:"
            + escape_ics(
                f"{game['home']} – "
                f"{game['away']}"
            )
        )

        # ----------------------------------------------------
        # LOCATION
        #
        # WICHTIG:
        # Die normale Location bleibt die Adresse.
        #
        # Dadurch kann Apple die Adresse selbst
        # erkennen und als Kartenort verwenden.
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # KOORDINATEN + APPLE STRUCTURED LOCATION
        # ----------------------------------------------------

        if (
            game["latitude"] is not None
            and game["longitude"] is not None
        ):

            latitude = (
                game["latitude"]
            )

            longitude = (
                game["longitude"]
            )

            # Apple-Titel:
            # die komplette Spielstätte.
            apple_title = (
                game["location"]
                or game["address"]
            )

            if len(apple_title) > 120:

                apple_title = (
                    apple_title[:120]
                )

            apple_title = (
                escape_ics_parameter(
                    apple_title
                )
            )

            # Apple-Adresse:
            # exakt unsere ermittelte Adresse,
            # ohne künstliches "Deutschland".
            apple_address = (
                game["address"]
                or game["location"]
            )

            apple_address = (
                escape_ics_parameter(
                    apple_address
                )
            )

            # Standard-iCalendar-Koordinaten
            lines.append(
                f"GEO:{latitude};{longitude}"
            )

            # Apple-spezifische strukturierte
            # Location mit Adresse + GPS.
            lines.append(
                "X-APPLE-STRUCTURED-LOCATION;"
                "VALUE=URI;"
                "X-ADDRESS="
                + apple_address
                + ";X-APPLE-RADIUS=71;"
                "X-TITLE="
                + apple_title
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

        # Vollständige Spielstätte zusätzlich
        # in den Details anzeigen.
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

        # Direkter FUSSBALL.DE-Link
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

    return (
        "\n".join(lines)
        + "\n"
    )


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

    games = get_games()

    print()

    print(
        f"{len(games)} eindeutige "
        f"Spiele gefunden."
    )

    print()

    calendar = make_ics(
        games
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            calendar
        )

    print(
        "kalender.ics erfolgreich aktualisiert."
    )

    print(
        "========================================"
    )


if __name__ == "__main__":

    main()