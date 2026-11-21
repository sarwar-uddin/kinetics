#!/usr/bin/env bash
# Install Kinetics for the current user. No root required.
#
#   ./install.sh            run from this directory (a launcher points here)
#   ./install.sh --pipx     install properly into an isolated venv via pipx
#
set -euo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
APP=com.github.sarwaruddin.kinetics

mkdir -p ~/.local/bin \
         ~/.local/share/applications \
         ~/.local/share/icons/hicolor/scalable/apps \
         ~/.local/share/metainfo

if [[ "${1:-}" == "--pipx" ]]; then
    pipx install --force "$REPO"
else
    cat > ~/.local/bin/kinetics <<SH
#!/usr/bin/env bash
cd "$REPO" && exec python3 -m kinetics "\$@"
SH
    chmod +x ~/.local/bin/kinetics
fi

# Absolute Exec: ~/.local/bin is on the shell's PATH but not the Plasma session's.
sed "s|^Exec=kinetics|Exec=$HOME/.local/bin/kinetics|" "$REPO/data/$APP.desktop" \
    > ~/.local/share/applications/$APP.desktop
install -m644 "$REPO/data/icons/$APP.svg" ~/.local/share/icons/hicolor/scalable/apps/
install -m644 "$REPO/data/$APP.metainfo.xml" ~/.local/share/metainfo/

update-desktop-database ~/.local/share/applications 2>/dev/null || true
gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor 2>/dev/null || true
kbuildsycoca6 --noincremental >/dev/null 2>&1 || true

echo "Installed. Launch with 'kinetics' or from the menu under Education."
