import re
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup


TEAM_ID = "011MIDEIGO000000VTVG0001VTR8C1K7"
OUTPUT_FILE = "kalender.ics"
LOCAL_TZ = ZoneInfo("Europe/Berlin")


def get_matchplan_url():
    return (
        "https://www.fussball.de/ajax.team.matchplan/-/"
        "mime-type/HTML/"
        "show-venues/true/"
        f"team-id/{TEAM_ID}/"
        "wettkampftyp/1/"
        "max/1000/"
        "datum-von/2026-07-01/"
        "datum-bis/2027-07-31/"
        "offset/0"
    )


def get_games():
    url = get_matchplan_url()

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8", errors="replace")

    soup = BeautifulSoup(html, "html.parser")

    games = []

    table = soup.select_one("#id-team-matchplan-table")

    if not table:
        raise RuntimeError(
            "FUSSBALL.DE-Spielplantabelle wurde nicht gefunden."
        )

    rows = table.select("tbody tr")

    for row in rows:
        clubs = row.select("td.column-club .club-name")

        if len(clubs) < 2:
            continue

        home_team = clubs[0].get_text(" ", strip=True)
        away_team = clubs[1].get_text(" ", strip=True)

        date_cell = row.select_one("td.column-date")

        if not date_cell:
            continue

        date_text = date_cell.get_text(" ", strip=True)

        # Datum suchen
        date_match = re.search(
            r"(\d{2}\.\d{2}\.\d{4})",
            date_text
        )

        if not date_match:
            continue

        date_string = date_match.group(1)

        # Uhrzeit suchen
        time_match = re.search(
            r"(\d{1,2}):(\d{2})",
            date_text
        )

        day, month, year = map(
            int,
            date_string.split(".")
        )

        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))

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
            # Noch keine genaue Uhrzeit festgelegt
            dt = datetime(
                year,
                month,
                day,
                tzinfo=LOCAL_TZ
            )

            all_day = True

        # Spiel-ID suchen
        match_link = row.select_one("td:last-child a")

        if match_link:
            href = match_link.get("href", "")
            match_id_match = re.search(
                r"match-id/([A-Z0-9]+)",
                href
            )

            if match_id_match:
                match_id = match_id_match.group(1)
            else:
                match_id = f"{year}{month:02d}{day:02d}-{home_team}-{away_team}"

        else:
            match_id = f"{year}{month:02d}{day:02d}-{home_team}-{away_team}"

        games.append({
            "id": match_id,
            "home": home_team,
            "away": away_team,
            "datetime": dt,
            "all_day": all_day,
        })

    if not games:
        raise RuntimeError(
            "Keine Spiele in der FUSSBALL.DE-Spielplantabelle gefunden."
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
        "X-WR-TIMEZONE:Europe/Berlin",
    ]

    for game in games:

        dt = game["datetime"]

        lines.append("BEGIN:VEVENT")

        lines.append(
            f"UID:sgdd-{escape_ics(game['id'])}@github.com"
        )

        lines.append(
            "DTSTAMP:"
            + datetime.now(timezone.utc).strftime(
                "%Y%m%dT%H%M%SZ"
            )
        )

        if game["all_day"]:

            lines.append(
                f"DTSTART;VALUE=DATE:{dt.strftime('%Y%m%d')}"
            )

            lines.append(
                f"DTEND;VALUE=DATE:{dt.strftime('%Y%m%d')}"
            )

        else:

            utc_dt = dt.astimezone(timezone.utc)

            end_dt = utc_dt.replace(
                hour=utc_dt.hour
            )

            lines.append(
                f"DTSTART:{utc_dt.strftime('%Y%m%dT%H%M%SZ')}"
            )

            lines.append(
                f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%SZ')}"
            )

        summary = (
            f"{game['home']} – {game['away']}"
        )

        lines.append(
            f"SUMMARY:{escape_ics(summary)}"
        )

        lines.append(
            "DESCRIPTION:Landesliga Südbaden Staffel 3"
        )

        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")

    return "\n".join(lines) + "\n"


def main():

    print("Hole Spielplan von FUSSBALL.DE...")

    games = get_games()

    print(
        f"{len(games)} Spiele gefunden."
    )

    calendar = make_ics(games)

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(calendar)

    print(
        f"{OUTPUT_FILE} erfolgreich aktualisiert."
    )


if __name__ == "__main__":
    main()