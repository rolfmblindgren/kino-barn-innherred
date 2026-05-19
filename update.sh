#!/bin/sh
set -eu

cd /srv/shiny-server/kino-barn

./kino_barn_csv.py
./generate_film_omtaler.py
