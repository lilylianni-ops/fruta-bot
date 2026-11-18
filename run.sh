#!/usr/bin/env bash
cd "$(dirname "$0")"
while true; do
  python3 bot.py
  echo "El bot se cayó, reiniciando en 5 segundos..."
  sleep 5
done
