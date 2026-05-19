# Kino Barn CSV

Lite Python-script som henter offentlige kinoprogram fra Verdal kino og Steinkjer kino, plukker ut barne- og familiefilmer, og skriver en CSV-fil med dato, ukedag, klokkeslett og sal.

## Lag CSV

Kjør slik:

```sh
./kino_barn_csv.py
```

Da skrives `barnefilmer_kino.csv` i samme mappe som kommandoen kjøres fra.

CSV-en har disse kolonnene:

```csv
kino,film,dato,ukedag,klokkeslett,sal,aldersgrense,kategori,sprak_og_tekst,kilde
```

Scriptet bruker bare Python-standardbiblioteket. Det trenger altså ingen `pip install`.

For test med lagrede HTML-filer:

```sh
python3 kino_barn_csv.py --verdal-html /tmp/verdal.html --steinkjer-html /tmp/steinkjerkino.html
```

## Vis CSV i nettleser

Start en enkel lokal webserver:

```sh
python3 -m http.server 8765
```

Åpne så:

```text
http://127.0.0.1:8765/
```

Webappen leser `barnefilmer_kino.csv`, viser visningene i tabell og har filter for kino, dato og fritekst.

## Kjør som Shiny-app

Mappen har også en vanlig Shiny-app:

```sh
Rscript -e "shiny::runApp('.', port = 8766)"
```

På Shiny Server kan hele mappen kopieres til en app-mappe. Appen leser `barnefilmer_kino.csv` og `film_omtaler.json` fra samme mappe.

Appen bruker `shiny`, `jsonlite`, `grendelshiny` og `shinyseo`, så disse R-pakkene må finnes på serveren.

## Lag korte filmomtaler

Hvis `OPENAI_API_KEY` finnes i miljøet, kan du lage korte norske omtaler fra kinoenes filmtekster:

```sh
./generate_film_omtaler.py
```

Da skrives `film_omtaler.json`, som webappen viser under filmtitlene.

Merk: Dette er scraping av offentlige nettsider, ikke et offisielt API. Hvis kinoene endrer nettsidene sine, kan scriptet måtte justeres.

## Coda

From web-lit screens it gathers days with care  
It sorts the films that children want to see  
And lays the times in rows both clean and fair  
A modest tool that keeps the morning free  
