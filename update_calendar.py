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


def get_game_location(game_url):
    """
    Liest den Spielort von der jeweiligen
    FUSSBALL.DE-Spielseite aus.
    """

    if not game_url:
        return ""

    try:

        html = fetch_url(game_url)

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        # --------------------------------------------------
        # 1. Bevorzugte Methode:
        # Google-Maps-Link der Spielstätte
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
                return location_text

        # --------------------------------------------------
        # 2. Fallback:
        # Nach typischen Spielstätten-Begriffen suchen
        # --------------------------------------------------

        page_text = soup.get_text(
            " ",
            strip=True
        )

        location_patterns = [
            r"((?:Rasenplatz|Kunstrasenplatz|Sportplatz|"
            r"Stadion|Sportanlage|Kunstrasen|Rasenplatz).*?)"
            r"(?=\s+(?:Schiedsrichter|Assistenten|Zuschauer|"
            r"Staffel-ID|Spielberichte|News|$))"
        ]

        for pattern in location_patterns:

            match = re.search(
                pattern,
                page_text,
                re.IGNORECASE
            )

            if match:

                location = match.group(1).strip()

                # Überflüssige Leerzeichen entfernen
                location = re.sub(
                    r"\s+",
                    " ",
                    location
                )

                return location

    except Exception as error:

        print(
            f"Spielort konnte nicht geladen werden: "
            f"{game_url}"
        )

        print(
            f"Fehler: {error}"
        )

    return ""


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

        # --------------------------------------------------
        # NUR MEISTERSCHAFTSSPIELE
        # --------------------------------------------------

        if "ME" not in text:
            continue

        # --------------------------------------------------
        # SPIEL-ID SUCHEN
        # --------------------------------------------------

        number_match = re.search(
            r"\b(\d{9})\b",
            text
        )

        match_id = None

        if number_match:
            match_id = number_match.group(1)

        # --------------------------------------------------
        # DATUM SUCHEN
        # --------------------------------------------------

        date_match = re.search(
            r"(\d{2}\.\d{2}\.\d{2,4})",
            text
        )

        if not date_match:
            continue

        date_string = date_match.group(1)

        parts = date_string.split(".")

        day = int(parts[0])
        month = int(parts[1])
        year = int(parts[2])

        if year < 100:
            year += 2000

        # --------------------------------------------------
        # UHRZEIT SUCHEN
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

            # Keine Uhrzeit bekannt.
            #
            # Das Spiel wird später als
            # komplettes Wochenende dargestellt.

            dt = datetime(
                year,
                month,
                day,
                tzinfo=LOCAL_TZ
            )

            all_day = True

        # --------------------------------------------------
        # MANNSCHAFTSZEILE
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
        # SPIEL-URL SUCHEN
        # --------------------------------------------------

        game_url = ""

        # Zuerst in der Mannschaftszeile suchen
        game_link = team_row.select_one(
            'a[href*="/spiel/"]'
        )

        # Falls dort nichts gefunden wurde,
        # in der gesamten Matchplan-Zeile suchen
        if not game_link:

            game_link = row.select_one(
                'a[href*="/spiel/"]'
            )

        if game_link:

            game_url = game_link.get(
                "href",
                ""
            )

        # Relative URLs absichern
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
        # DOPPELTE SPIELE VERHINDERN
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

            match_id = fallback_key.replace(
                "|",
                "-"
            )

        # --------------------------------------------------
        # SPIELORT LADEN
        # --------------------------------------------------

        location = ""

        if game_url:

            print(
                f"Lade Spielort: "
                f"{home} – {away}"
            )

            location = get_game_location(
                game_url
            )

            if location:

                print(
                    f"  Spielort: {location}"
                )

            else:

                print(
                    "  Kein Spielort gefunden."
                )

        else:

            print(
                f"Keine Spiel-URL gefunden: "
                f"{home} – {away}"
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
            "game_url": game_url
        })

    if not games:

        raise RuntimeError(
            "Keine Meisterschaftsspiele "
            "von FUSSBALL.DE gefunden."
        )

    # Chronologisch sortieren
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
        # SPIEL OHNE UHRZEIT
        # --------------------------------------------------

        if game["all_day"]:

            start_date = dt.date()

            # Das entsprechende Wochenende bestimmen.
            #
            # Samstag = 5
            # Sonntag = 6
            #
            # Bei Sonntag gehen wir einen Tag zurück.
            # Bei Samstag bleiben wir auf Samstag.

            if start_date.weekday() == 6:

                saturday = (
                    start_date
                    - timedelta(days=1)
                )

            else:

                saturday = start_date

            # DTEND ist exklusiv.
            # Samstag + Sonntag bedeutet daher Montag.

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
        # SPIEL MIT UHRZEIT
        # --------------------------------------------------

        else:

            start = dt.astimezone(
                timezone.utc
            )

            # Standardmäßig 2 Stunden Spieldauer
            end = (
                start
                + timedelta(hours=2)
            )

            lines.append(
                "DTSTART:"
                + start.strftime(
                    "%Y%m%dT%H%M%SZ"
                )
            )

            lines.append(
                "DTEND:"
                + end.strftime(
                    "%Y%m%dT%H%M%SZ"
                )
            )

        # --------------------------------------------------
        # SPIELTITEL
        # --------------------------------------------------

        lines.append(
            "SUMMARY:"
            + escape_ics(
                f"{game['home']} – {game['away']}"
            )
        )

        # --------------------------------------------------
        # SPIELORT
        # --------------------------------------------------

        if game["location"]:

            lines.append(
                "LOCATION:"
                + escape_ics(
                    game["location"]
                )
            )

        # --------------------------------------------------
        # BESCHREIBUNG
        # --------------------------------------------------

        description = (
            "Landesliga Südbaden Staffel 3"
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

    print(
        ""
    )

    print(
        f"{len(games)} eindeutige Spiele gefunden."
    )

    print(
        ""
    )

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