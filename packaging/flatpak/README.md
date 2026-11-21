# Flatpak

A self-hosted Flatpak build. **This is not a Flathub submission** — Flathub
requires its own hand-written manifest and review process.

## Why the Qt version is pinned

Kirigami comes from the KDE runtime and its QML plugin is compiled against that
runtime's Qt. PySide6 wheels ship their own copy of Qt, and two different Qt
builds will not load each other's QML plugins. So this build:

1. pins PySide6 to **exactly** the runtime's Qt version (6.11.3), and
2. deletes the Qt bundled inside the PySide6 wheel, so everything shares the
   runtime's Qt.

That also drops 179 MB and sidesteps the bundled `libQt6Network`, which links
`libgssapi_krb5` — a library the KDE runtime does not ship.

When bumping `runtime-version`, check the runtime's Qt version and repin
PySide6 and shiboken6 to match:

```bash
flatpak run --command=sh org.kde.Sdk//<ver> -c \
  'ls /usr/lib/x86_64-linux-gnu/libQt6Core.so.6.*'
```

## Build

```bash
flatpak install --user flathub org.flatpak.Builder org.kde.Platform//6.11 org.kde.Sdk//6.11
cd packaging/flatpak
flatpak run org.flatpak.Builder --force-clean --user --install-deps-from=flathub \
    --repo=/tmp/kinetics-repo /tmp/kinetics-build \
    io.github.sarwar_uddin.Kinetics.yml
```

Note that `flatpak-builder` runs sandboxed and gets its own `/tmp`, so build
and repo paths under the host's `/tmp` will not be visible afterwards. Use a
path under `$HOME`.

## Install and run

```bash
flatpak build-bundle /tmp/kinetics-repo kinetics.flatpak io.github.sarwar_uddin.Kinetics
flatpak install --user kinetics.flatpak
flatpak run io.github.sarwar_uddin.Kinetics
```

The app only writes one small profile file, and `XDG_CONFIG_HOME` inside the
sandbox already points at its own directory, so no host filesystem permission
is requested.
