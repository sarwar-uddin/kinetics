# AUR package

`PKGBUILD` and `.SRCINFO` for the Arch User Repository.

Built and tested with `makepkg -sf`, which runs the full test suite in
`check()` before packaging.

## Publishing or updating

The AUR repo is separate from this one. First time:

```bash
# 1. Create an account at https://aur.archlinux.org and add your SSH public key
#    (Settings -> SSH Public Key). Yours is ~/.ssh/id_ed25519.pub
# 2. Clone the (empty) AUR repo and copy these two files in:
git clone ssh://aur@aur.archlinux.org/kinetics.git /tmp/aur-kinetics
cp PKGBUILD .SRCINFO /tmp/aur-kinetics/
cd /tmp/aur-kinetics
git add PKGBUILD .SRCINFO
git commit -m "Initial import: kinetics 0.2.1"
git push
```

For a new version, bump `pkgver` in `PKGBUILD`, reset `pkgrel=1`, then:

```bash
updpkgsums                      # refresh sha256sums from the new tag
makepkg --printsrcinfo > .SRCINFO
makepkg -sf                     # verify it still builds and tests pass
```

`.SRCINFO` must be regenerated and committed alongside every `PKGBUILD`
change — the AUR rejects pushes where the two disagree.
