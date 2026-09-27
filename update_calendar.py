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
    """
    Ruft eine Webseite von FUSSBALL.DE ab.
    """

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


def find_coordinates_in_json(data):
    """
    Sucht rekursiv nach Latitude/Longitude
    in JSON-LD-Daten.
    """

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


def find_coordinates_in_html(html):
    """
    Sucht Koordinaten direkt im HTML.
    """

    patterns = [
        (
            r'"latitude"\s*:\s*([-+]?\d+(?:\.\d+)?)'
            r'.{0,500}?'
            r'"longitude"\s*:\s*([-+]?\d+(?:\.\d+)?)'
        ),
        (
            r'"lat"\s*:\s*([-+]?\d+(?:\.\d+)?)'
            r'.{0,500}?'
            r'"(?:lng|lon|longitude)"\s*:\s*'
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

                return (
                    float(match.group(1)),
                    float(match.group(2))
                )

            except (
                ValueError,
                TypeError
            ):
                pass

    # Google Maps @LAT,LON

    google_pattern = (
        r'google[^"\']*'
        r'@([-+]?\d+(?:\.\d+)),'
        r'([-+]?\d+(?:\.\d+)?)'
    )

    match = re.search(
        google_pattern,
        html,
        re.IGNORECASE
    )

    if match:

        try:

            return (
                float(match.group(1)),
                float(match.group(2))
            )

        except (
            ValueError,
            TypeError
        ):
            pass

    # geo:LAT,LON

    geo_pattern = (
        r'geo:'
        r'([-+]?\d+(?:\.\d+)),'
        r'([-+]?\d+(?:\.\d+)?)'
    )

    match = re.search(
        geo_pattern,
        html,
        re.IGNORECASE
    )

    if match:

        try:

            return (
                float(match.group(1)),
                float(match.group(2))
            )

        except (
            ValueError,
            TypeError
        ):
            pass

    return None


def extract_clean_address(location):
    """
    Versucht aus dem vollständigen Spielort
    nur die eigentliche Adresse herauszufiltern.

    Beispiele:

    Rasenplatz, k-tech-Arena Dettingen,
    Allensbacher Str. 43, 78465 Konstanz

    wird zu:

    Allensbacher Str. 43, 78465 Konstanz
    """

    if not location:
        return ""

    location = re.sub(
        r"\s+",
        " ",
        location
    ).strip()

    # --------------------------------------------------
    # Adresse mit Hausnummer
    # --------------------------------------------------

    pattern_with_number = re.compile(
        r"("
        r"[A-Za-zÄÖÜäöüßÀ-ÿ0-9 .'\-/]+"
        r"\s+\d+[A-Za-z]?"
        r"\s*,\s*"
        r"\d{5}"
        r"\s+"
        r"[A-Za-zÄÖÜäöüßÀ-ÿ .'\-/]+"
        r")$"
    )

    match = pattern_with_number.search(
        location
    )

    if match:

        return match.group(1).strip()

    # --------------------------------------------------
    # Adresse ohne Hausnummer
    #
    # Beispiel:
    # Winterspürer Str., 78333 Stockach
    # --------------------------------------------------

    pattern_without_number = re.compile(
        r"("
        r"[A-Za-zÄÖÜäöüßÀ-ÿ0-9 .'\-/]+"
        r"(?:str\.|straße|weg|allee|platz|"
        r"ring|gasse|ufer|chaussee)"
        r"\s*,\s*"
        r"\d{5}"
        r"\s+"
        r"[A-Za-zÄÖÜäöüßÀ-ÿ .'\-/]+"
        r")$",
        re.IGNORECASE
    )

    match = pattern_without_number.search(
        location
    )

    if match:

        return match.group(1).strip()

    # --------------------------------------------------
    # Falls nichts sicher erkannt wird:
    # ursprünglichen Wert behalten
    # --------------------------------------------------

    return location


def get_game_location(game_url):
    """
    Liest Spielort, Adresse und Koordinaten
    von der jeweiligen FUSSBALL.DE-Spielseite.
    """

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

        # --------------------------------------------------
        # JSON-LD
        # --------------------------------------------------

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

        # --------------------------------------------------
        # HTML-Koordinaten
        # --------------------------------------------------

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

        # --------------------------------------------------
        # Google-Maps-Link
        # --------------------------------------------------

        google_links = soup.select(
            'a[href*="google."]'
        )

        for link in google_links:

            location_text = link.get_text(
                " ",
                strip=True
            )

            if location_text:

                location = location_text
                break

        # --------------------------------------------------
        # Fallback: Spielort aus Seitentext
        # --------------------------------------------------

        if not location:

            page_text = soup.get_text(
                " ",
                strip=True
            )

            location_patterns = [
                r"((?:Rasenplatz|Kunstrasenplatz|"
                r"Sportplatz|Stadion|Sportanlage|"
                r"Kunstrasen).*?)"
                r"(?=\s+(?:Schiedsrichter|Assistenten|"
                r"Zuschauer|Staffel-ID|Spielberichte|"
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

        # --------------------------------------------------
        # REINE ADRESSE ERMITTELN
        # --------------------------------------------------

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
            f"Spielort konnte nicht geladen werden: "
            f"{game_url}"
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
        "div.club-matchplan-table tr.row-competition"
    )

    for row in rows:

        text = row.get_text(
            " ",
            strip=True
        )

        # Nur Meisterschaftsspiele

        if "ME" not in text:
            continue

        # --------------------------------------------------
        # SPIEL-ID
        # --------------------------------------------------

        number_match = re.search(
            r"\b(\d{9})\b",
            text
        )

        match_id = None

        if number_match:

            match_id = (
                number_match.group(1)
            )

        # --------------------------------------------------
        # DATUM
        # --------------------------------------------------

        date_match = re.search(
            r"(\d{2}\.\d{2}\.\d{2,4})",
            text
        )

        if not date_match:
            continue

        date_string = (
            date_match.group(1)
        )

        parts = date_string.split(".")

        day = int(parts[0])
        month = int(parts[1])
        year = int(parts[2])

        if year < 100:
            year += 2000

        # --------------------------------------------------
        # UHRZEIT
        # --------------------------------------------------

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

            # Keine Uhrzeit bekannt:
            # komplettes Wochenende.

            dt = datetime(
                year,
                month,
                day,
                tzinfo=LOCAL_TZ
            )

            all_day = True

        # --------------------------------------------------
        # MANNSCHAFTEN
        # --------------------------------------------------

        team_row = row.find_next_sibling(
            "tr"
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

        # --------------------------------------------------
        # SPIEL-URL
        # --------------------------------------------------

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

        # --------------------------------------------------
        # FALLBACK-ID
        # --------------------------------------------------

        fallback_key = (
            f"{year:04d}-"
            f"{month:02d}-"
            f"{day:02d}|"
            f"{home}|"
            f"{away}"
        )

        # --------------------------------------------------
        # DOPPELTE SPIELE
        # --------------------------------------------------

        if match_id:

            if match_id in seen_ids:

                print(
                    f"Doppeltes Spiel ignoriert: "
                    f"{match_id} – "
                    f"{home} – {away}"
                )

                continue

            seen_ids.add(
                match_id
            )

        else:

            if fallback_key in seen_fallback:

                print(
                    f"Doppeltes Spiel ignoriert: "
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

        # --------------------------------------------------
        # SPIELORT
        # --------------------------------------------------

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
                    f"  Spielstätte: {location}"
                )

            if address:

                print(
                    f"  Adresse: {address}"
                )

            if (
                latitude is not None
                and longitude is not None
            ):

                print(
                    f"  Koordinaten: "
                    f"{latitude}, {longitude}"
                )

        # --------------------------------------------------
        # SPIEL SPEICHERN
        # --------------------------------------------------

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


def make_ics(games):

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SG Dettingen-Dingelsdorf//Landesliga 3//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:SG Dettingen-Dingelsdorf",
        "X-WR-TIMEZONE:Europe/Berlin"
    ]

    for game in games:

        dt = game["datetime"]

        lines.append(
            "BEGIN:VEVENT"
        )

        lines.append(
            f"UID:sgdd-{escape_ics(game['id'])}@github.com"
        )

        lines.append(
            "DTSTAMP:"
            + datetime.now(
                timezone.utc
            ).strftime(
                "%Y%m%dT%H%M%SZ"
            )
        )

        # --------------------------------------------------
        # OHNE UHRZEIT
        # --------------------------------------------------

        if game["all_day"]:

            start_date = dt.date()

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

        # --------------------------------------------------
        # MIT UHRZEIT
        # --------------------------------------------------

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

        # --------------------------------------------------
        # TITEL
        # --------------------------------------------------

        lines.append(
            "SUMMARY:"
            + escape_ics(
                f"{game['home']} – {game['away']}"
            )
        )

        # --------------------------------------------------
        # ORT
        #
        # WICHTIG:
        # Hier verwenden wir jetzt bevorzugt
        # die reine Adresse.
        # --------------------------------------------------

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

        # --------------------------------------------------
        # KOORDINATEN
        # --------------------------------------------------

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

            lines.append(
                "GEO:"
                f"{latitude};{longitude}"
            )

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

            apple_address = (
                game["address"]
                or game["location"]
            )

            apple_address = (
                escape_ics_parameter(
                    apple_address
                )
            )

            lines.append(
                "X-APPLE-STRUCTURED-LOCATION;"
                "VALUE=URI;"
                "X-ADDRESS="
                + apple_address
                + ";"
                "X-APPLE-RADIUS=71;"
                "X-TITLE="
                + apple_title
                + ":geo:"
                + str(latitude)
                + ","
                + str(longitude)
            )

        # --------------------------------------------------
        # DETAILS
        # --------------------------------------------------

        description = (
            "Landesliga Südbaden Staffel 3"
        )

        # Spielstättenname zusätzlich in die Details

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
        f"{len(games)} eindeutige Spiele gefunden."
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