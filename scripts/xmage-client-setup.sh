#!/usr/bin/env bash
# Set up the XMage client on a Fedora desktop so that it stays in sync with the homelab server.
#
#   scripts/xmage-client-setup.sh [--list-old] [--copy-images-from SRC] [--no-launch]
#
# The server (role `xmage`) follows the newest beta build every night, and client and server must
# run the same build. So the client is installed once from the full package and then updated in
# place by the XMage Launcher; the card images (~19 GB) live outside the install and are never
# downloaded twice.
#
#   --copy-images-from SRC  seed the image folder from another copy instead of downloading it from
#                           Scryfall: a local path, or user@host:/path for rsync over SSH
#                           (the old PC keeps them in <install>/xmage/mage-client/plugins/images)
#   --no-launch             only install, do not start the launcher
#   --list-old              only list what is left of older XMage setups (installs, packages, image
#                           folders with their size) and exit: it never deletes or changes anything
#
# Nothing needs root: the client always runs on Java 17; Temurin 17 is unpacked in the user's home
# when the system has no Java 17. The `xmage` command (~/.local/bin) starts the launcher with it
# (the launcher then runs the client on the Java 8 bundled in the package).
# Safe to run again: an existing install is kept, only the missing pieces are recreated.
#
# Everything lives in $XMAGE_HOME (default ~/.local/share/xmage):
#   app/      the XMage package (launcher + client), updated by the launcher
#   images/   card images, linked into app/xmage/mage-client/plugins/images
#   jdk/      Java, only when the system has none
set -euo pipefail

XMAGE_HOME=${XMAGE_HOME:-$HOME/.local/share/xmage}
SITE=https://xmage.today
SERVER=192.168.1.250
APP=$XMAGE_HOME/app
IMAGES=$XMAGE_HOME/images
BIN=$HOME/.local/bin
LINK=$APP/xmage/mage-client/plugins/images

copy_from= launch=1 list_old=0
while [ $# -gt 0 ]; do
  case $1 in
    --copy-images-from) copy_from=${2:?missing source}; shift 2 ;;
    --no-launch) launch=0; shift ;;
    --list-old) list_old=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

if [ "$list_old" = 1 ]; then
  echo "Older XMage setups under $HOME (nothing is deleted):"
  found=0
  # Folders that hold a client or the card images, and packages left in Downloads.
  while IFS= read -r d; do
    case $d in "$XMAGE_HOME"|"$XMAGE_HOME"/*) continue ;; esac
    found=1; printf '  %-8s %s\n' "$(du -shL "$d" 2>/dev/null | cut -f1)" "$d"
  done < <(find "$HOME" -maxdepth 5 \( -path "$XMAGE_HOME" -o -path '*/.cache' -o -path '*/.var' -o -path "$HOME/repos" \) -prune -o \
    \( -type d \( -name 'mage-full_*' -o -name mage-client -o -name 'xmage*' \) -o -type f -name 'mage-full_*.zip' -o -type f -name 'XMageLauncher*.jar' \) -print 2>/dev/null | sort)
  echo
  echo "Image folders (<install>/xmage/mage-client/plugins/images): move the biggest one to $IMAGES"
  echo "with mv before deleting anything else; the setup script then links it into the new install."
  [ -L "$LINK" ] && echo "This PC already uses $IMAGES ($(du -shL "$IMAGES" 2>/dev/null | cut -f1))."
  [ "$found" = 1 ] || echo "  (no old setup found)"
  echo "Client settings (user name, server list) are in ~/.java/.userPrefs/mage: keep them."
  exit 0
fi

say() { printf '== %s\n' "$*"; }
need() { command -v "$1" >/dev/null || { echo "missing command: $1 (sudo dnf install $1)" >&2; exit 1; }; }
for c in curl unzip tar; do need "$c"; done
if [ -n "$copy_from" ]; then need rsync; fi
mkdir -p "$XMAGE_HOME" "$BIN" "$IMAGES"

# --- Java -----------------------------------------------------------------------------------
java_major() { "$1" -version 2>&1 | sed -n 's/^.* version "\([0-9]*\)[."].*/\1/p' | head -1; }
JAVA=
if command -v java >/dev/null && [ "$(java_major java)" = 17 ]; then
  JAVA=$(command -v java)
elif [ -x "$XMAGE_HOME/jdk/bin/java" ]; then
  JAVA=$XMAGE_HOME/jdk/bin/java
else
  say "Java 17 not found: unpacking Temurin 17 in $XMAGE_HOME/jdk"
  case $(uname -m) in x86_64) arch=x64 ;; aarch64) arch=aarch64 ;; *) echo "unsupported CPU: $(uname -m)" >&2; exit 1 ;; esac
  tmp=$(mktemp -d)
  curl -fL --progress-bar "https://api.adoptium.net/v3/binary/latest/17/ga/linux/$arch/jdk/hotspot/normal/eclipse" -o "$tmp/jdk.tar.gz"
  mkdir -p "$XMAGE_HOME/jdk"
  tar -xzf "$tmp/jdk.tar.gz" -C "$XMAGE_HOME/jdk" --strip-components=1
  rm -rf "$tmp"
  JAVA=$XMAGE_HOME/jdk/bin/java
fi
say "Java: $JAVA (version $(java_major "$JAVA"))"

# --- XMage package --------------------------------------------------------------------------
if ! ls "$APP"/XMageLauncher-*.jar >/dev/null 2>&1; then
  zip=$(curl -fsSL "$SITE/" | grep -oE 'files/mage-full_[^"]+\.zip' | head -1)
  [ -n "$zip" ] || { echo "cannot find the full package on $SITE" >&2; exit 1; }
  say "Downloading $zip"
  tmp=$(mktemp -d)
  curl -fL --progress-bar "$SITE/$zip" -o "$tmp/xmage.zip"
  mkdir -p "$APP"
  # Exit 1 only warns about file names with non-ASCII characters (sample decks): the files are fine.
  unzip -qq "$tmp/xmage.zip" -d "$APP" >/dev/null 2>&1 || [ $? -eq 1 ]
  rm -rf "$tmp"
  # Some packages unpack into one extra folder: flatten it.
  if ! ls "$APP"/XMageLauncher-*.jar >/dev/null 2>&1; then
    inner=$(dirname "$(ls "$APP"/*/XMageLauncher-*.jar | head -1)")
    shopt -s dotglob; mv "$inner"/* "$APP"/; shopt -u dotglob; rmdir "$inner"
  fi
else
  say "XMage already installed in $APP (the launcher keeps it updated)"
fi
LAUNCHER=$(ls "$APP"/XMageLauncher-*.jar | head -1)

# The launcher reads its home and Java options from here. Keep the file if it already exists.
if [ ! -f "$APP/installed.properties" ]; then
  cat >"$APP/installed.properties" <<EOF
#---XMage Properties---
xmage.home=$SITE/
xmage.client.javaopts=-Xmx2000m
xmage.client.console=true
xmage.server.console=true
xmage.torrent.use=false
EOF
fi

# --- Card images, outside the install -------------------------------------------------------
mkdir -p "$(dirname "$LINK")"
if [ -d "$LINK" ] && [ ! -L "$LINK" ]; then
  say "Moving the images found in the install to $IMAGES"
  cp -an "$LINK"/. "$IMAGES"/ && rm -rf "$LINK"
fi
ln -sfn "$IMAGES" "$LINK"
if [ -n "$copy_from" ]; then
  say "Copying images from $copy_from (can take a while)"
  rsync -a --info=progress2 "${copy_from%/}/" "$IMAGES"/
fi

# --- Commands and menu entry ----------------------------------------------------------------
cat >"$BIN/xmage" <<EOF
#!/usr/bin/env bash
# XMage launcher: it updates the client to the build the homelab server runs, then starts it.
# The launcher starts the client with the Java 8 bundled in the package, which rejects the
# --add-opens flags that other tools may leave in JAVA_TOOL_OPTIONS: start from a clean environment.
unset JAVA_TOOL_OPTIONS JDK_JAVA_OPTIONS _JAVA_OPTIONS
cd "$APP" && exec "$JAVA" -Djava.net.preferIPv4Stack=true -jar "$(basename "$LAUNCHER")"
EOF
cat >"$BIN/xmage-client" <<EOF
#!/usr/bin/env bash
# Starts another client window straight away (no update check): use it for the second player.
unset JAVA_TOOL_OPTIONS JDK_JAVA_OPTIONS _JAVA_OPTIONS
cd "$APP/xmage/mage-client" && exec "$JAVA" -Xmx2000m -Djava.net.preferIPv4Stack=true -jar "\$(ls lib/mage-client-*.jar | head -1)" "\$@"
EOF
chmod +x "$BIN/xmage" "$BIN/xmage-client"
mkdir -p "$HOME/.local/share/applications"
cat >"$HOME/.local/share/applications/xmage.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=XMage
Comment=Magic: The Gathering client (updates itself from the launcher)
Exec=$BIN/xmage
Terminal=false
Categories=Game;CardGame;
EOF

cat <<EOF

Done. Start it from the application menu ("XMage") or with: xmage
  - Always start through the launcher and accept its updates: the server moves to the newest build every night.
  - In the client: server $SERVER, port 17171, any user name, empty password.
  - A second player on this PC: run xmage-client again (different user name).
  - Card images are in $IMAGES; the client downloads the missing ones from its Preferences/Download images menu.
EOF
[ "$launch" = 1 ] && exec "$BIN/xmage"
