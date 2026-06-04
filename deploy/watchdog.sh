#!/usr/bin/env bash
# Keep app1 (+ model server) up while the container runs: run autostart.sh in a
# loop. Recovers from process crashes. Does NOT survive a container *recreate*
# on its own -- pair with the boot hook (see install_boot_hook.sh).
cd "$(dirname "$0")" || exit 1
while true; do
  bash ./autostart.sh
  sleep 30
done
