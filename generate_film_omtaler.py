#!/usr/bin/env python3
"""Lag korte norske filmomtaler basert på kinoenes omtaletekster."""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import kino_barn_csv


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")


@dataclass
class MovieSource:
  title: str
  age: str = ""
  genres: list[str] = field(default_factory=list)
  language: str = ""
  runtime: str = ""
  overview: str = ""
  short_description: str = ""
  showing_notes: set[str] = field(default_factory=set)
  source_urls: set[str] = field(default_factory=set)


def main() -> int:
  parser = argparse.ArgumentParser(
    description="Hent filmomtaler og lag korte AI-sammendrag for webappen."
  )
  parser.add_argument(
    "--csv",
    default="barnefilmer_kino.csv",
    help="CSV-fil med kinovisninger. Standard: %(default)s",
  )
  parser.add_argument(
    "-o",
    "--output",
    default="film_omtaler.json",
    help="JSON-fil som skal skrives. Standard: %(default)s",
  )
  parser.add_argument(
    "--model",
    default=DEFAULT_MODEL,
    help="OpenAI-modell. Standard: OPENAI_MODEL eller %(default)s",
  )
  parser.add_argument(
    "--reuse-existing",
    action="store_true",
    help="Behold eksisterende omtaler hvis tittelen allerede finnes i output-filen.",
  )
  args = parser.parse_args()

  if not os.environ.get("OPENAI_API_KEY"):
    raise SystemExit("OPENAI_API_KEY mangler i miljøet.")

  csv_rows = read_csv(Path(args.csv))
  titles = sorted({row["film"] for row in csv_rows if row.get("film")})
  sources = collect_sources(csv_rows)
  existing = read_existing(Path(args.output)) if args.reuse_existing else {}

  movies = {}
  for title in titles:
    if title in existing:
      movies[title] = existing[title]
      continue

    source = sources.get(title) or MovieSource(title=title)
    movies[title] = generate_summary(source, args.model)
    print(f"Omtale: {title}", file=sys.stderr)
    time.sleep(0.2)

  output = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "model": args.model,
    "movies": movies,
  }
  Path(args.output).write_text(
    json.dumps(output, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
  )
  print(f"Skrev omtaler for {len(movies)} filmer til {args.output}")
  return 0


def read_csv(path: Path) -> list[dict[str, str]]:
  with path.open(encoding="utf-8", newline="") as handle:
    return list(csv.DictReader(handle))


def read_existing(path: Path) -> dict:
  if not path.exists():
    return {}
  data = json.loads(path.read_text(encoding="utf-8"))
  return data.get("movies") or {}


def collect_sources(rows: list[dict[str, str]]) -> dict[str, MovieSource]:
  sources: dict[str, MovieSource] = {}
  needed_titles = {row["film"] for row in rows if row.get("film")}
  verdal_html = safe_read_url(kino_barn_csv.VERDAL_URL)
  if verdal_html:
    collect_verdal_sources(verdal_html, needed_titles, sources)

  for url in sorted({row.get("kilde", "") for row in rows if "steinkjerkino.no" in row.get("kilde", "")}):
    source = safe_read_url(url)
    if source:
      collect_steinkjer_sources(source, sources)

  apply_csv_context(rows, sources)
  return sources


def apply_csv_context(rows: list[dict[str, str]], sources: dict[str, MovieSource]) -> None:
  for row in rows:
    title = row.get("film")
    if not title:
      continue
    source = sources.setdefault(title, MovieSource(title=title))
    source.age = source.age or row.get("aldersgrense", "")
    if row.get("kategori"):
      for genre in re.split(r",\s*", row["kategori"]):
        if genre and genre not in source.genres:
          source.genres.append(genre)
    if row.get("sprak_og_tekst"):
      source.showing_notes.add(row["sprak_og_tekst"])


def collect_verdal_sources(
  program_html: str,
  needed_titles: set[str],
  sources: dict[str, MovieSource],
) -> None:
  for article in re.findall(
    r'<article\b[^>]*node--type-movie[^>]*>.*?</article>',
    program_html,
    flags=re.S | re.I,
  ):
    title = kino_barn_csv.first_text(
      article,
      r'<span[^>]*field--name-title[^>]*>(.*?)</span>',
    )
    if title not in needed_titles:
      continue

    movie_url = first_url(article, r'<a href="(/film/[^"]+)"')
    if not movie_url:
      continue

    full_url = urllib.parse.urljoin(kino_barn_csv.VERDAL_URL, movie_url)
    movie_html = safe_read_url(full_url)
    if not movie_html:
      continue

    source = sources.setdefault(title, MovieSource(title=title))
    source.source_urls.add(full_url)
    source.age = source.age or kino_barn_csv.first_text(
      article,
      r'<div class="censorship">\s*Aldersgrense:\s*(.*?)</div>',
    )
    source.short_description = source.short_description or extract_nfkino_field(
      movie_html,
      "field-short-description",
    )
    source.overview = source.overview or extract_nfkino_field(movie_html, "body")
    source.genres.extend(
      genre for genre in extract_nfkino_genres(movie_html) if genre not in source.genres
    )


def collect_steinkjer_sources(source_html: str, sources: dict[str, MovieSource]) -> None:
  blocks = kino_barn_csv.decode_mars_blocks(source_html)
  for movie in kino_barn_csv.steinkjer_movie_map(blocks).values():
    title = str(movie.get("title") or "").strip()
    if not title:
      continue

    source = sources.setdefault(title, MovieSource(title=title))
    source.age = source.age or kino_barn_csv.age_label(movie.get("ageRating"))
    source.language = source.language or str(movie.get("language") or "")
    source.runtime = source.runtime or runtime_label(movie.get("runtime"))
    source.overview = source.overview or clean_htmlish(str(movie.get("overview") or ""))
    source.short_description = source.short_description or clean_ingresses(movie.get("ingresses"))
    for genre in movie.get("genres") or []:
      genre = str(genre)
      if genre and genre not in source.genres:
        source.genres.append(genre)


def generate_summary(source: MovieSource, model: str) -> dict:
  payload = {
    "model": model,
    "temperature": 0.2,
    "messages": [
      {
        "role": "system",
        "content": (
          "Du skriver korte filmomtaler på enkel norsk for foreldre som skal "
          "velge barne- eller ungdomsfilm på kino. Bruk bare informasjonen du får. "
          "Ikke finn på handling eller vurderinger som ikke står i kildeteksten. "
          "Når du nevner språk eller teksting, må du bruke aktuelle_visningsspråk."
        ),
      },
      {
        "role": "user",
        "content": build_prompt(source),
      },
    ],
    "response_format": {"type": "json_object"},
  }
  data = openai_request(payload)
  content = data["choices"][0]["message"]["content"]
  parsed = json.loads(content)
  return {
    "kort_omtale": clean_generated(parsed.get("kort_omtale", "")),
    "passer_for": clean_generated(parsed.get("passer_for", "")),
    "foreldre_merknad": clean_generated(parsed.get("foreldre_merknad", "")),
    "kilder": sorted(source.source_urls),
  }


def build_prompt(source: MovieSource) -> str:
  return json.dumps(
    {
      "oppgave": (
        "Returner JSON med nøklene kort_omtale, passer_for og foreldre_merknad. "
        "kort_omtale skal være maks 45 ord. passer_for maks 18 ord. "
        "foreldre_merknad maks 22 ord og skal nevne alder/språk/tekst bare hvis relevant."
      ),
      "film": source.title,
      "aldersgrense": source.age,
      "sjangre": source.genres,
      "språk": source.language,
      "aktuelle_visningsspråk": sorted(source.showing_notes),
      "lengde": source.runtime,
      "korttekst": source.short_description,
      "omtale": source.overview,
    },
    ensure_ascii=False,
  )


def openai_request(payload: dict) -> dict:
  body = json.dumps(payload).encode("utf-8")
  request = urllib.request.Request(
    OPENAI_CHAT_COMPLETIONS_URL,
    data=body,
    headers={
      "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
      "Content-Type": "application/json",
    },
    method="POST",
  )
  try:
    with urllib.request.urlopen(request, timeout=60) as response:
      return json.loads(response.read().decode("utf-8"))
  except urllib.error.HTTPError as error:
    error_body = error.read().decode("utf-8", errors="replace")
    raise RuntimeError(f"OpenAI-kall feilet med HTTP {error.code}: {error_body}") from error


def safe_read_url(url: str) -> str:
  try:
    return kino_barn_csv.read_html(None, url)
  except Exception as error:
    print(f"Advarsel: kunne ikke hente {url}: {error}", file=sys.stderr)
    return ""


def first_url(source: str, pattern: str) -> str:
  match = re.search(pattern, source, flags=re.S | re.I)
  return html.unescape(match.group(1)) if match else ""


def extract_nfkino_field(source: str, field_name: str) -> str:
  pattern = (
    r'<div class="field field--name-' + re.escape(field_name) +
    r'\b[^"]*"[^>]*>.*?<div class="field__item">(.*?)</div>'
  )
  return clean_htmlish(kino_barn_csv.first_text(source, pattern))


def extract_nfkino_genres(source: str) -> list[str]:
  match = re.search(
    r'<div class="field field--name-field-genre\b.*?</div>\s*</div>',
    source,
    flags=re.S | re.I,
  )
  if not match:
    return []
  text = clean_htmlish(match.group(0))
  text = re.sub(r"^Sjanger\s*", "", text, flags=re.I)
  return [item.strip() for item in re.split(r",|\s{2,}", text) if item.strip()]


def clean_ingresses(value: object) -> str:
  if isinstance(value, dict):
    parts = [clean_htmlish(str(item)) for item in value.values() if item]
    return " ".join(part for part in parts if part)
  return clean_htmlish(str(value or ""))


def clean_htmlish(value: str) -> str:
  value = html.unescape(value)
  value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
  value = re.sub(r"<[^>]+>", " ", value)
  return re.sub(r"\s+", " ", value).strip()


def clean_generated(value: object) -> str:
  return re.sub(r"\s+", " ", str(value or "")).strip()


def runtime_label(value: object) -> str:
  try:
    minutes = int(value)
  except (TypeError, ValueError):
    return ""
  hours, mins = divmod(minutes, 60)
  if hours and mins:
    return f"{hours} t {mins} min"
  if hours:
    return f"{hours} t"
  return f"{mins} min"


if __name__ == "__main__":
  sys.exit(main())


# Local Variables:
# mode: python
# python-indent-offset: 2
# End:
