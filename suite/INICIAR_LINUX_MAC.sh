#!/bin/sh
cd "$(dirname "$0")" || exit 1
exec python3 skills/oficina-inteligente-cuba/scripts/oficina.py serve --open
