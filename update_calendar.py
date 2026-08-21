import re
import urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup


TEAM_ID = "011MIDEIGO000000VTVG0001VTR8C1K7"
OUTPUT_FILE = "kalender.ics"
LOCAL_TZ = ZoneInfo("Europe/Berlin")

URL = (
    "https://www.fussball.de/ajax.team.matchplan/-/"
    "mode/PAGE/"
    f"team-id/{TEAM_ID}"
)


def get_games():
    request = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:
        html = response.read().decode(
            "utf-8",
            errors="replace"
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

        # Spiel-ID suchen
        number_match = re.search(
            r"\b(\d{9})\b",
            text
        )

        match_id = None

        if number_match:
            match_id = number_match.group(1)

        # Datum suchen
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

        # Uhrzeit suchen
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

        # Mannschaftszeile holen
        team_row = row.find_next_sibling("tr")

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

        # Falls keine Spiel-ID vorhanden ist,
        # verwenden wir Heim + Gast + Datum.
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
                    f"{match_id} – {home} – {away}"
                )
                continue

            seen_ids.add(match_id)

        else:

            if fallback_key in seen_fallback:
                print(
                    f"Doppeltes Spiel ignoriert: "
                    f"{fallback_key}"
                )
                continue

            seen_fallback.add(fallback_key)

            match_id = fallback_key.replace(
                "|",
                "-"
            )

        games.append({
            "id": match_id,
            "home": home,
            "away": away,
            "datetime": dt,
            "all_day": all_day
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

        if game["all_day"]:

            lines.append(
                "DTSTART;VALUE=DATE:"
                + dt.strftime(
                    "%Y%m%d"
                )
            )

            lines.append(
                "DTEND;VALUE=DATE:"
                + (
                    dt + timedelta(days=1)
                ).strftime(
                    "%Y%m%d"
                )
            )

        else:

            start = dt.astimezone(
                timezone.utc
            )

            # Standardmäßig 2 Stunden Spieldauer
            end = start + timedelta(
                hours=2
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

        lines.append(
            "SUMMARY:"
            + escape_ics(
                f"{game['home']} – {game['away']}"
            )
        )

        lines.append(
            "DESCRIPTION:"
            "Landesliga Südbaden Staffel 3"
        )

        lines.append(
            "END:VEVENT"
        )

    lines.append(
        "END:VCALENDAR"
    )

    return "\n".join(lines) + "\n"


def main():

    print(
        "Hole Spielplan von FUSSBALL.DE..."
    )

    games = get_games()

    print(
        f"{len(games)} eindeutige Spiele gefunden."
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


if __name__ == "__main__":
    main()
