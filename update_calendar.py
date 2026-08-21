import json
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TEAM_ID = "011MIDEIGO000000VTVG0001VTR8C1K7"

URL = (
    "https://www.fussball.de/ajax.team.matchplan/"
    "-/mime-type/JSON/mode/PAGE/prev-season-allowed/false/"
    "show-filter/false/"
    f"team-id/{TEAM_ID}/max/1000/"
    "datum-von/2026-07-01/datum-bis/2027-07-15/offset/0"
)

OUTPUT_FILE = "kalender.ics"
LOCAL_TZ = ZoneInfo("Europe/Berlin")


def get_games():
    request = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    return find_games(data)


def find_games(data):
    games = []

    def search(obj):
        if isinstance(obj, dict):
            if (
                "homeTeam" in obj
                and "awayTeam" in obj
                and "matchMoment" in obj
            ):
                games.append(obj)

            for value in obj.values():
                search(value)

        elif isinstance(obj, list):
            for item in obj:
                search(item)

    search(data)

    # Doppelte Spiele entfernen
    unique = {}
    for game in games:
        game_id = str(game.get("id", ""))
        if game_id:
            unique[game_id] = game

    return list(unique.values())


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
        game_id = str(game.get("id", ""))

        home = game.get("homeTeam", {})
        away = game.get("awayTeam", {})

        home_name = home.get("name", "Unbekannt")
        away_name = away.get("name", "Unbekannt")

        match_time = game.get("matchMoment")

        if not match_time:
            continue

        try:
            dt = datetime.fromisoformat(
                match_time.replace("Z", "+00:00")
            )
            dt = dt.astimezone(LOCAL_TZ)
        except Exception:
            continue

        location = game.get("location", "") or ""

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:sgdd-{game_id}@github.com",
            f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{dt.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{dt.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{escape_ics(home_name)} – {escape_ics(away_name)}",
            f"LOCATION:{escape_ics(location)}",
            "DESCRIPTION:Landesliga Südbaden Staffel 3",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")

    return "\n".join(lines) + "\n"


def main():
    games = get_games()

    if not games:
        raise RuntimeError("Keine Spiele von FUSSBALL.DE gefunden.")

    calendar = make_ics(games)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        file.write(calendar)

    print(f"{len(games)} Spiele in {OUTPUT_FILE} geschrieben.")


if __name__ == "__main__":
    main()