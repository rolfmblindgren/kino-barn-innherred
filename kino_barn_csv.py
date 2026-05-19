#!/usr/bin/env python3
"""Lag CSV med barne- og familiefilmer for Verdal og Steinkjer kino."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path


VERDAL_URL = "https://www.nfkino.no/kino/verdal"
STEINKJER_URL = "https://www.steinkjerkino.no/"

CSV_FIELDS = [
  "kino",
  "film",
  "dato",
  "ukedag",
  "klokkeslett",
  "sal",
  "aldersgrense",
  "kategori",
  "sprak_og_tekst",
  "kilde",
]

CHILD_WORDS = {
  "barnefilm",
  "children's movie",
  "familiefilm",
  "family",
}

CHILDISH_LOW_AGE_GENRES = {
  "animasjon",
  "animation",
  "eventyr",
  "adventure",
  "sing a long",
  "sing-along",
}

EXTRA_TITLE_KEYWORDS = {
  "the amazing digital circus",
}

WEEKDAYS = [
  "mandag",
  "tirsdag",
  "onsdag",
  "torsdag",
  "fredag",
  "lørdag",
  "søndag",
]


@dataclass(frozen=True)
class Showing:
  kino: str
  film: str
  dato: str
  ukedag: str
  klokkeslett: str
  sal: str
  aldersgrense: str
  kategori: str
  sprak_og_tekst: str
  kilde: str


def main() -> int:
  parser = argparse.ArgumentParser(
    description="Hent barne- og familievisninger fra Verdal og Steinkjer kino."
  )
  parser.add_argument(
    "-o",
    "--output",
    default="barnefilmer_kino.csv",
    help="CSV-fil som skal skrives. Standard: %(default)s",
  )
  parser.add_argument(
    "--verdal-html",
    type=Path,
    help="Les Verdal fra lokal HTML-fil i stedet for nettet.",
  )
  parser.add_argument(
    "--steinkjer-html",
    type=Path,
    help="Les Steinkjer fra lokal HTML-fil i stedet for nettet.",
  )
  parser.add_argument(
    "--steinkjer-lookahead-days",
    type=int,
    default=45,
    help="Hvor mange dager frem Steinkjer-datosider skal sjekkes. Standard: %(default)s",
  )
  args = parser.parse_args()

  verdal_html = read_html(args.verdal_html, VERDAL_URL)
  steinkjer_html = read_html(args.steinkjer_html, STEINKJER_URL)

  rows = parse_verdal(verdal_html) + parse_steinkjer(steinkjer_html)
  if not args.steinkjer_html:
    for show_date in steinkjer_future_dates(steinkjer_html, args.steinkjer_lookahead_days):
      url = steinkjer_program_url(show_date)
      rows.extend(parse_steinkjer(read_html(None, url), source_url=url))

  rows = sorted(
    unique_rows(rows),
    key=lambda row: (row.dato, row.klokkeslett, row.kino, row.film, row.sal),
  )

  write_csv(Path(args.output), rows)
  print(f"Skrev {len(rows)} visninger til {args.output}")
  return 0


def read_html(local_file: Path | None, url: str) -> str:
  if local_file:
    return local_file.read_text(encoding="utf-8")

  request = urllib.request.Request(
    url,
    headers={
      "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) kino-barn-csv/1.0"
      )
    },
  )
  with urllib.request.urlopen(request, timeout=30) as response:
    charset = response.headers.get_content_charset() or "utf-8"
    return response.read().decode(charset, errors="replace")


def write_csv(path: Path, rows: list[Showing]) -> None:
  with path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for row in rows:
      writer.writerow({field: getattr(row, field) for field in CSV_FIELDS})


def unique_rows(rows: list[Showing]) -> list[Showing]:
  seen = set()
  unique = []
  for row in rows:
    key = (
      row.kino,
      row.film,
      row.dato,
      row.klokkeslett,
      row.sal,
      row.sprak_og_tekst,
    )
    if key in seen:
      continue
    seen.add(key)
    unique.append(row)
  return unique


def parse_verdal(source: str) -> list[Showing]:
  rows: list[Showing] = []
  for article in re.findall(
    r'<article\b[^>]*node--type-movie[^>]*>.*?</article>',
    source,
    flags=re.S | re.I,
  ):
    title = first_text(
      article,
      r'<span[^>]*field--name-title[^>]*>(.*?)</span>',
    )
    if not title:
      continue

    age = first_text(article, r'<div class="censorship">\s*Aldersgrense:\s*(.*?)</div>')
    day_blocks = re.finditer(
      r'<time\s+datetime="(?P<date>\d{4}-\d{2}-\d{2})"[^>]*>.*?</time>'
      r'(?P<body>.*?)(?=<time\s+datetime=|<div class="warn_4dx"|</article>)',
      article,
      flags=re.S | re.I,
    )
    for day in day_blocks:
      day_date = day.group("date")
      for link in re.findall(
        r'<a\b[^>]*movies-screenings-button-link[^>]*>(.*?)</a>',
        day.group("body"),
        flags=re.S | re.I,
      ):
        room = first_text(link, r'<div class="room">\s*(.*?)\s*</div>')
        start = first_text(link, r'<div class="time">.*?(\d{1,2}[.:]\d{2}).*?</div>')
        details = normalize_space(
          strip_tags(first_text(link, r'<div class="version">\s*(.*?)\s*</div>'))
        )
        if not start or not is_child_showing(title, age, details, []):
          continue

        rows.append(
          Showing(
            kino="Verdal",
            film=title,
            dato=day_date,
            ukedag=weekday_name(day_date),
            klokkeslett=start.replace(".", ":"),
            sal=room,
            aldersgrense=age,
            kategori=category_from_text(details),
            sprak_og_tekst=details,
            kilde=VERDAL_URL,
          )
        )
  return rows


def parse_steinkjer(source: str, source_url: str = STEINKJER_URL) -> list[Showing]:
  blocks = decode_mars_blocks(source)
  movies = steinkjer_movie_map(blocks)
  screen_names = screen_name_map(blocks)
  rows: list[Showing] = []

  for block in blocks:
    if block.get("_blockName") != "Card2":
      continue
    title = str(block.get("title") or "").strip()
    showtimes = block.get("showtimes") or []
    genres = [str(genre) for genre in block.get("genres") or []]
    age = age_label(block.get("ageRating"))
    if not title or not showtimes or not is_child_showing(title, age, "", genres):
      continue

    for showtime in showtimes:
      start_time = str(showtime.get("startTime") or "")
      parsed = parse_local_iso(start_time)
      if not parsed:
        continue

      notes = ", ".join(str(note) for note in showtime.get("notes") or [])
      screen_id = showtime.get("screenId")
      rows.append(
        Showing(
          kino="Steinkjer",
          film=title,
          dato=parsed.date().isoformat(),
          ukedag=weekday_name(parsed.date().isoformat()),
          klokkeslett=parsed.strftime("%H:%M"),
          sal=screen_names.get(str(screen_id), f"Sal {screen_id}" if screen_id else ""),
          aldersgrense=age,
          kategori=", ".join(genres),
          sprak_og_tekst=notes,
          kilde=source_url,
        )
      )

  for block in blocks:
    if block.get("_blockName") != "MovieShowtimes":
      continue
    for showtime in flatten_showtime_groups(block.get("showtimes") or []):
      movie = movies.get(str(showtime.get("movieId")), {})
      title = str(movie.get("title") or "").strip()
      genres = [str(genre) for genre in movie.get("genres") or []]
      age = age_label(movie.get("ageRating"))
      notes = ", ".join(note_name(note) for note in showtime.get("notes") or [])
      if not title or not is_child_showing(title, age, notes, genres):
        continue

      start_time = str(showtime.get("startTime") or "")
      parsed = parse_local_iso(start_time)
      if not parsed:
        continue

      screen_id = showtime.get("screenId")
      rows.append(
        Showing(
          kino="Steinkjer",
          film=title,
          dato=parsed.date().isoformat(),
          ukedag=weekday_name(parsed.date().isoformat()),
          klokkeslett=parsed.strftime("%H:%M"),
          sal=str(showtime.get("screenName") or screen_names.get(str(screen_id), "")),
          aldersgrense=age,
          kategori=", ".join(genres),
          sprak_og_tekst=notes,
          kilde=source_url,
        )
      )
  return rows


def steinkjer_future_dates(source: str, lookahead_days: int) -> list[str]:
  today = date.today()
  max_date = today + timedelta(days=lookahead_days)
  blocks = decode_mars_blocks(source)
  dates = set()

  for movie in steinkjer_movie_map(blocks).values():
    title = str(movie.get("title") or "").strip()
    genres = [str(genre) for genre in movie.get("genres") or []]
    age = age_label(movie.get("ageRating"))
    if not is_child_showing(title, age, "", genres):
      continue
    for show_date in dates_from_popularity(movie.get("popularity")):
      parsed = date.fromisoformat(show_date)
      if today <= parsed <= max_date:
        dates.add(show_date)

  return sorted(dates)


def steinkjer_program_url(show_date: str) -> str:
  return f"https://www.steinkjerkino.no/program/{show_date}/popularity/all/all"


def decode_mars_blocks(source: str) -> list[dict]:
  blocks = []
  pattern = r'JSON\.parse\(decodeURIComponent\("(?P<payload>.*?)"\)\)'
  for match in re.finditer(pattern, source, flags=re.S):
    try:
      blocks.append(json.loads(urllib.parse.unquote(match.group("payload"))))
    except json.JSONDecodeError:
      continue
  return blocks


def steinkjer_movie_map(blocks: list[dict]) -> dict[str, dict]:
  movies: dict[str, dict] = {}
  for block in blocks:
    candidates = []
    if block.get("_blockName") == "Card2" and block.get("movieId"):
      candidates.append(block)
    if block.get("_blockName") == "QuickBuyWidget":
      candidates.extend(block.get("movies") or [])

    for movie in candidates:
      movie_id = movie.get("movieId")
      if movie_id:
        movies[str(movie_id)] = movie
  return movies


def screen_name_map(blocks: list[dict]) -> dict[str, str]:
  names: dict[str, str] = {}
  for block in blocks:
    if block.get("_blockName") != "MovieShowtimes":
      continue
    for group in block.get("showtimes") or []:
      for showtime in group:
        screen_id = showtime.get("screenId")
        screen_name = showtime.get("screenName")
        if screen_id and screen_name:
          names[str(screen_id)] = str(screen_name)
  return names


def flatten_showtime_groups(groups: list) -> list[dict]:
  showtimes = []
  for group in groups:
    if isinstance(group, list):
      showtimes.extend(item for item in group if isinstance(item, dict))
    elif isinstance(group, dict):
      showtimes.append(group)
  return showtimes


def note_name(note: object) -> str:
  if isinstance(note, dict):
    return str(note.get("name") or note.get("title") or "").strip()
  return str(note).strip()


def dates_from_popularity(value: object) -> set[str]:
  dates = set()
  if isinstance(value, dict):
    for key, child in value.items():
      maybe_date = parse_dmy_date(str(key))
      if maybe_date:
        dates.add(maybe_date)
      dates.update(dates_from_popularity(child))
  elif isinstance(value, list):
    for item in value:
      dates.update(dates_from_popularity(item))
  return dates


def parse_dmy_date(value: str) -> str | None:
  match = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", value)
  if not match:
    return None
  day, month, year = match.groups()
  return f"{year}-{month}-{day}"


def is_child_showing(title: str, age: str, details: str, genres: list[str]) -> bool:
  text_parts = [title, age, details, *genres]
  text = " ".join(text_parts).casefold()
  if any(keyword in title.casefold() for keyword in EXTRA_TITLE_KEYWORDS):
    return True
  if any(word in text for word in CHILD_WORDS):
    return True
  if low_child_age(age) and any(genre in text for genre in CHILDISH_LOW_AGE_GENRES):
    return True
  return False


def low_child_age(age: str) -> bool:
  normalized = age.casefold()
  return (
    "alle" in normalized
    or "tillatt for alle" in normalized
    or re.search(r"\b(?:[036]|9)\s*(år|ar)?\b", normalized) is not None
  )


def age_label(value: object) -> str:
  if value is None:
    return ""
  text = str(value).strip()
  if text == "-1":
    return "Ikke sensurert"
  if text.casefold() in {"0", "g", "alle"}:
    return "Alle"
  if text.isdigit():
    return f"{text} år"
  return text


def category_from_text(text: str) -> str:
  categories = []
  folded = text.casefold()
  for word in ["Barnefilm", "Familiefilm", "Studentkino", "Kinoklubb", "Kinofest"]:
    if word.casefold() in folded:
      categories.append(word)
  return ", ".join(categories)


def parse_local_iso(value: str) -> datetime | None:
  if not value:
    return None
  try:
    return datetime.fromisoformat(value[:19])
  except ValueError:
    return None


def weekday_name(iso_date: str) -> str:
  parsed = date.fromisoformat(iso_date)
  return WEEKDAYS[parsed.weekday()]


def first_text(source: str, pattern: str) -> str:
  match = re.search(pattern, source, flags=re.S | re.I)
  if not match:
    return ""
  return normalize_space(strip_tags(match.group(1)))


def strip_tags(value: str) -> str:
  return re.sub(r"<[^>]+>", " ", html.unescape(value))


def normalize_space(value: str) -> str:
  return re.sub(r"\s+", " ", value).strip()


if __name__ == "__main__":
  sys.exit(main())


# Local Variables:
# mode: python
# python-indent-offset: 2
# End:
