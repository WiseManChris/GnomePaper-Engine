#!/usr/bin/env bash
# GnomePaper Engine — one-command install for any GNOME Linux desktop
set -euo pipefail

APP_ID="io.github.gnomepaper.Engine"
APP_NAME="GnomePaper Engine"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_DIR="${HOME}/.local/bin"
PREFIX="${DATA_HOME}/gnomepaper-engine"
VENV="${PREFIX}/venv"
DESKTOP_SRC="${REPO_ROOT}/data/${APP_ID}.desktop"
DESKTOP_DST="${DATA_HOME}/applications/${APP_ID}.desktop"

red()  { printf '\033[1;31m%s\033[0m\n' "$*"; }
green(){ printf '\033[1;32m%s\033[0m\n' "$*"; }
bold() { printf '\033[1m%s\033[0m\n' "$*"; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { red "Missing command: $1"; exit 1; }
}

detect_pm() {
  if command -v apt-get >/dev/null 2>&1; then echo apt
  elif command -v dnf >/dev/null 2>&1; then echo dnf
  elif command -v pacman >/dev/null 2>&1; then echo pacman
  elif command -v zypper >/dev/null 2>&1; then echo zypper
  else echo unknown
  fi
}

install_system_deps() {
  local pm
  pm="$(detect_pm)"
  bold "==> Installing system packages ($pm)…"

  case "$pm" in
    apt)
      sudo apt-get update -y
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
        python3 python3-pip python3-venv python3-gi python3-gi-cairo \
        gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gtk-3.0 \
        libgtk-4-1 libadwaita-1-0 \
        gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad gstreamer1.0-libav \
        x11-utils wmctrl xdotool ffmpeg curl tar \
        gir1.2-ayatanaappindicator3-0.1 || true
      ;;
    dnf)
      sudo dnf install -y --skip-broken \
        python3 python3-pip python3-gobject \
        gtk4 libadwaita gtk3 \
        gstreamer1-plugins-base gstreamer1-plugins-good \
        gstreamer1-plugins-bad-free \
        xprop wmctrl xdotool ffmpeg curl tar \
        libayatana-appindicator-gtk3 || true
      ;;
    pacman)
      sudo pacman -Sy --needed --noconfirm \
        python python-pip python-gobject \
        gtk4 libadwaita gtk3 \
        gst-plugins-base gst-plugins-good gst-plugins-bad \
        xorg-xprop wmctrl xdotool ffmpeg curl tar \
        libayatana-appindicator || true
      ;;
    zypper)
      sudo zypper --non-interactive install \
        python3 python3-pip python3-gobject \
        gtk4 libadwaita-1-0 typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 \
        gstreamer-plugins-base gstreamer-plugins-good \
        xprop wmctrl xdotool ffmpeg curl tar || true
      ;;
    *)
      red "Unknown package manager. Install these, then re-run this script:"
      echo "  Python 3.11+, PyGObject, GTK4, libadwaita, GStreamer,"
      echo "  xprop, wmctrl, xdotool, ffmpeg, curl, tar"
      exit 1
      ;;
  esac
}

verify_python_gi() {
  bold "==> Checking GTK / PyGObject…"
  python3 - <<'PY'
import sys
try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Adw
except Exception as e:
    print("ERROR: GTK4/libadwaita Python bindings missing:", e, file=sys.stderr)
    sys.exit(1)
print("GTK", Gtk.get_major_version(), Gtk.get_minor_version(), "+ Adwaita OK")
PY
}

install_app() {
  bold "==> Installing GnomePaper Engine into ${PREFIX}…"
  need_cmd python3
  mkdir -p "${PREFIX}" "${BIN_DIR}" "${DATA_HOME}/applications"

  # --system-site-packages: use distro PyGObject/GTK (not available from pip)
  if [[ ! -f "${VENV}/bin/python" ]]; then
    python3 -m venv --system-site-packages "${VENV}"
  elif ! "${VENV}/bin/python" -c "import gi" 2>/dev/null; then
    bold "==> Recreating venv with system packages (for GTK)…"
    rm -rf "${VENV}"
    python3 -m venv --system-site-packages "${VENV}"
  fi
  # shellcheck disable=SC1091
  source "${VENV}/bin/activate"
  pip install --upgrade pip setuptools wheel >/dev/null
  pip install --force-reinstall "${REPO_ROOT}"

  # Stable launcher on PATH (always points at venv)
  cat > "${BIN_DIR}/gnomepaper-engine" <<EOF
#!/usr/bin/env bash
exec "${VENV}/bin/gnomepaper-engine" "\$@"
EOF
  chmod +x "${BIN_DIR}/gnomepaper-engine"

  # Desktop entry with absolute Exec (works even if PATH is incomplete)
  if [[ -f "${DESKTOP_SRC}" ]]; then
    sed "s|^Exec=.*|Exec=${BIN_DIR}/gnomepaper-engine|" "${DESKTOP_SRC}" \
      > "${DESKTOP_DST}"
  else
    cat > "${DESKTOP_DST}" <<EOF
[Desktop Entry]
Name=${APP_NAME}
Comment=Steam Wallpaper Engine wallpapers on GNOME
Exec=${BIN_DIR}/gnomepaper-engine
Icon=preferences-desktop-wallpaper
Terminal=false
Type=Application
Categories=Utility;GTK;GNOME;
Keywords=wallpaper;steam;desktop;background;
StartupNotify=true
EOF
  fi

  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${DATA_HOME}/applications" 2>/dev/null || true
  fi

  # Remember install root for uninstall
  echo "${REPO_ROOT}" > "${PREFIX}/source_path" 2>/dev/null || true
  echo "${VENV}" > "${PREFIX}/venv_path"
}

ensure_path_hint() {
  case ":${PATH}:" in
    *":${BIN_DIR}:"*) ;;
    *)
      echo
      bold "Note: add ~/.local/bin to your PATH if the command is not found:"
      echo '  echo '\''export PATH="$HOME/.local/bin:$PATH"'\'' >> ~/.bashrc && source ~/.bashrc'
      ;;
  esac
}

print_next_steps() {
  echo
  green "✓ ${APP_NAME} installed"
  echo
  bold "Run it:"
  echo "  gnomepaper-engine"
  echo "  # or open “GnomePaper Engine” from your app menu"
  echo
  bold "You also need:"
  echo "  1. Steam installed and logged in"
  echo "  2. Wallpaper Engine owned & installed on Steam"
  echo "  3. (Optional, for scene wallpapers)"
  echo "       ${REPO_ROOT}/scripts/install_linux_wallpaperengine.sh"
  echo
  bold "Uninstall later:"
  echo "  ${REPO_ROOT}/uninstall.sh"
  echo
}

main() {
  bold "=== ${APP_NAME} installer ==="
  echo "Works on any GNOME desktop (Ubuntu, Fedora, Arch, openSUSE, …)"
  echo

  if [[ "$(id -u)" -eq 0 ]]; then
    red "Do not run as root. Run as your normal user (sudo is used only for packages)."
    exit 1
  fi

  need_cmd python3
  need_cmd curl

  install_system_deps
  verify_python_gi
  install_app
  ensure_path_hint
  print_next_steps
}

main "$@"
