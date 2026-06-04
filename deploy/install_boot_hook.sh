#!/usr/bin/env bash
# Add a fail-safe boot hook to /entrypoint.sh so the watchdog starts on container
# restart. The hook is inserted AFTER sshd starts and is wrapped so it can never
# fail the entrypoint (set -e safe): a backgrounded subshell with `|| true`.
#
# Caveat: survives a container *restart* (fs persists), NOT a *recreate* from the
# image. For recreate-survival, bake this into the image/Jenkins instead.
#
# Run once, on the server. Keeps a backup at /entrypoint.sh.bak.
set -euo pipefail

ENTRY=/entrypoint.sh
WATCHDOG=/root/data/workspace/app1/deploy/watchdog.sh
MARK="app1-autostart-hook"
HOOK="( setsid bash $WATCHDOG >/dev/null 2>&1 & ) || true   # $MARK"

if grep -q "$MARK" "$ENTRY"; then
  echo "boot hook already present"
  exit 0
fi

cp "$ENTRY" "$ENTRY.bak"
# Insert the hook right before the 'Execute original entrypoint' banner, which is
# after sshd has started -- so even if the hook were to error, SSH is already up.
awk -v hook="$HOOK" '
  /^# ==+/ && !inserted { print hook; inserted=1 }
  { print }
' "$ENTRY.bak" > "$ENTRY"

if grep -q "$MARK" "$ENTRY"; then
  echo "boot hook added to $ENTRY (backup: $ENTRY.bak)"
else
  echo "FAILED to add hook; restoring backup"
  cp "$ENTRY.bak" "$ENTRY"
  exit 1
fi
