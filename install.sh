#!/usr/bin/env bash
# Installs the launcher + menu entry for the current user (no root needed).
set -euo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
mkdir -p ~/.local/bin ~/.local/share/applications
cat > ~/.local/bin/kinetics <<SH
#!/usr/bin/env bash
cd "$REPO" && exec python3 -m kinetics "\$@"
SH
chmod +x ~/.local/bin/kinetics
# absolute Exec: ~/.local/bin isn't on the Plasma session's PATH, only the shell's
sed "s|^Exec=kinetics|Exec=$HOME/.local/bin/kinetics|" \
  "$REPO/data/com.github.sarwaruddin.kinetics.desktop" \
  > ~/.local/share/applications/com.github.sarwaruddin.kinetics.desktop
update-desktop-database ~/.local/share/applications 2>/dev/null || true
kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
echo "installed: ~/.local/bin/kinetics + menu entry (Education > Science)"
