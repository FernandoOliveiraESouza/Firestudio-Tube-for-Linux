#!/bin/sh
# Installs the FireStudio Tube setup for the current user (no sudo needed).
set -eu

here=$(cd "$(dirname "$0")" && pwd)

# Dependencies built from source (Ubuntu/Mint packages needed first:
# meson ninja-build libudev-dev gobject-introspection libgirepository1.0-dev
# libhinawa-dev libhitaki-dev libasound2-dev, plus Rust from rustup.rs).
ALSA_GOBJECT_TAG=v0.3.1
CTL_SERVICES_REV=7654d40cb0e62426e460c0b94605e2a4b506d6bb
libdir="$HOME/.local/lib/x86_64-linux-gnu"

if [ ! -f "$libdir/pkgconfig/alsactl.pc" ]; then
    [ -d "$here/src/alsa-gobject" ] || \
        git clone --branch "$ALSA_GOBJECT_TAG" https://github.com/alsa-project/alsa-gobject "$here/src/alsa-gobject"
    meson setup "$here/src/alsa-gobject/build" "$here/src/alsa-gobject" --prefix="$HOME/.local" -Ddoc=false
    ninja -C "$here/src/alsa-gobject/build" install
fi

service="$here/src/snd-firewire-ctl-services/target/release/snd-dice-ctl-service"
if [ ! -x "$service" ]; then
    if [ ! -d "$here/src/snd-firewire-ctl-services" ]; then
        git clone https://github.com/alsa-project/snd-firewire-ctl-services "$here/src/snd-firewire-ctl-services"
        git -C "$here/src/snd-firewire-ctl-services" checkout "$CTL_SERVICES_REV"
    fi
    (cd "$here/src/snd-firewire-ctl-services" &&
        PKG_CONFIG_PATH="$libdir/pkgconfig" cargo build --release --bin snd-dice-ctl-service)
fi

chmod +x "$here/bin/firestudio-ctl-service" "$here/firestudio-control"

mkdir -p ~/.config/pipewire/pipewire.conf.d ~/.config/wireplumber/main.lua.d ~/.local/share/icons/hicolor/scalable/apps \
         ~/.config/systemd/user ~/.local/share/applications ~/.local/bin
ln -sf "$here/config/pipewire/firestudio-tube.conf" ~/.config/pipewire/pipewire.conf.d/
ln -sf "$here/config/wireplumber/51-firestudio-tube.lua" ~/.config/wireplumber/main.lua.d/
ln -sf "$here/systemd/firestudio-tube-ctl.service" ~/.config/systemd/user/
ln -sf "$here/firestudio-control" ~/.local/bin/firestudio-control
ln -sf "$here/assets/firestudio-tube.svg" ~/.local/share/icons/hicolor/scalable/apps/firestudio-tube.svg

cat > ~/.local/share/applications/firestudio-control.desktop <<EOF
[Desktop Entry]
Type=Application
Name=FireStudio Tube
Comment=Mixer e roteamento da PreSonus FireStudio Tube
Exec=$here/firestudio-control
Icon=firestudio-tube
Categories=AudioVideo;Audio;Mixer;
EOF

systemctl --user daemon-reload
systemctl --user enable --now firestudio-tube-ctl.service
systemctl --user restart wireplumber pipewire pipewire-pulse

echo "Instalado. Abra \"FireStudio Tube\" no menu ou rode: firestudio-control"
