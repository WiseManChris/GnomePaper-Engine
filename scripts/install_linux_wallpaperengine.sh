#!/usr/bin/env bash
# =============================================================================
# GnomePaper — seamless linux-wallpaperengine installer
#
# Detects the distro, installs every build dependency (with GPG fallbacks for
# Nobara/Fedora), verifies headers/libs exist, then builds and installs LWE to:
#   ~/.local/share/linux-wallpaperengine/
#   ~/.local/bin/linux-wallpaperengine
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/third_party/linux-wallpaperengine"
PREFIX="${HOME}/.local"
BIN_DIR="${PREFIX}/bin"
SHARE="${PREFIX}/share/linux-wallpaperengine"
BUILD_DIR="${SRC}/build"

# ── UI ──────────────────────────────────────────────────────────────────────
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
ok()    { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn()  { printf '  \033[33m!\033[0m %s\n' "$*" >&2; }
fail()  { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; }
die()   { fail "$*"; exit 1; }
step()  { echo; bold "==> $*"; }

# ── Distro detection ────────────────────────────────────────────────────────
OS_ID=""
OS_LIKE=""
OS_NAME=""
PM=""          # apt | dnf | pacman | zypper
IS_NOBARA=0

detect_os() {
  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    OS_ID="${ID:-unknown}"
    OS_LIKE="${ID_LIKE:-}"
    OS_NAME="${PRETTY_NAME:-$OS_ID}"
  else
    OS_ID="unknown"
    OS_NAME="unknown"
  fi

  case "${OS_ID}" in
    nobara) IS_NOBARA=1 ;;
  esac
  [[ " ${OS_LIKE} " == *" nobara "* ]] && IS_NOBARA=1

  if command -v apt-get >/dev/null 2>&1; then
    PM=apt
  elif command -v dnf >/dev/null 2>&1; then
    PM=dnf
  elif command -v pacman >/dev/null 2>&1; then
    PM=pacman
  elif command -v zypper >/dev/null 2>&1; then
    PM=zypper
  else
    PM=unknown
  fi
}

# ── Sudo ────────────────────────────────────────────────────────────────────
ensure_sudo() {
  if [[ "${EUID}" -eq 0 ]]; then
    return 0
  fi
  if ! command -v sudo >/dev/null 2>&1; then
    die "sudo is required to install packages. Install sudo or re-run as root."
  fi
  step "Requesting administrator access (sudo)"
  if ! sudo -v; then
    die "sudo authentication failed. Re-run and enter your password."
  fi
  # Keep sudo alive during long builds
  (
    while true; do
      sudo -n true 2>/dev/null || exit 0
      sleep 50
    done
  ) &
  SUDO_KEEPALIVE_PID=$!
  trap 'kill "${SUDO_KEEPALIVE_PID}" 2>/dev/null || true' EXIT
}

run_root() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

# ── Package install (dnf/apt/pacman/zypper) ─────────────────────────────────
# Nobara often has broken OpenPGP keys for its repos. Prefer normal install,
# then retry with GPG disabled so users are never stuck on "wrong key".

dnf_try_install() {
  # $@ = packages
  local -a pkgs=("$@")
  [[ ${#pkgs[@]} -eq 0 ]] && return 0

  # Normal
  if run_root dnf install -y "${pkgs[@]}"; then
    return 0
  fi

  warn "dnf install failed — refreshing RPM keys…"
  if [[ -d /etc/pki/rpm-gpg ]]; then
    # shellcheck disable=SC2046
    run_root rpm --import $(find /etc/pki/rpm-gpg -type f 2>/dev/null | head -80) 2>/dev/null || true
  fi
  run_root dnf clean packages 2>/dev/null || true

  if run_root dnf install -y "${pkgs[@]}"; then
    return 0
  fi

  warn "OpenPGP / repo key issue — installing with GPG check disabled (this session only)…"
  # Cover dnf4 + dnf5 option names
  if run_root dnf install -y --nogpgcheck \
      --setopt=gpgcheck=0 \
      --setopt=localpkg_gpgcheck=0 \
      --setopt=repo_gpgcheck=0 \
      "${pkgs[@]}"; then
    return 0
  fi
  if run_root dnf install -y --nogpgcheck --setopt=*.gpgcheck=0 "${pkgs[@]}"; then
    return 0
  fi
  return 1
}

# On Nobara, skip GPG on the first try — their keys break constantly for users.
dnf_install_packages() {
  local -a pkgs=("$@")
  [[ ${#pkgs[@]} -eq 0 ]] && return 0

  if [[ "${IS_NOBARA}" -eq 1 ]]; then
    step "Installing packages (Nobara: GPG-relaxed mode)"
    if run_root dnf install -y --nogpgcheck \
        --setopt=gpgcheck=0 \
        --setopt=localpkg_gpgcheck=0 \
        --setopt=repo_gpgcheck=0 \
        "${pkgs[@]}"; then
      return 0
    fi
    # Still try normal path + full fallback
  fi

  step "Installing packages via dnf"
  if dnf_try_install "${pkgs[@]}"; then
    return 0
  fi

  # Last resort: one package at a time so freeglut cannot be skipped by a sibling failure
  warn "Bulk install failed — installing packages one at a time…"
  local p failed=0
  for p in "${pkgs[@]}"; do
    if dnf_try_install "$p"; then
      ok "$p"
    else
      warn "failed: $p"
      failed=1
    fi
  done
  return "$failed"
}

apt_install_packages() {
  step "Installing packages via apt"
  run_root apt-get update -y
  run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"
}

pacman_install_packages() {
  step "Installing packages via pacman"
  run_root pacman -Sy --needed --noconfirm "$@"
}

zypper_install_packages() {
  step "Installing packages via zypper"
  run_root zypper --non-interactive install "$@" || \
    run_root zypper --non-interactive install --force "$@"
}

# ── Full dependency lists (from Almamu README + extras LWE needs) ───────────
install_all_deps() {
  case "${PM}" in
    apt)
      # Ubuntu 22.04 / 24.04 + Debian; include dbus which CMake needs
      apt_install_packages \
        build-essential cmake git rsync pkg-config \
        libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev \
        libgl-dev libglew-dev freeglut3-dev \
        libsdl2-dev liblz4-dev \
        libavcodec-dev libavformat-dev libavutil-dev libswscale-dev libswresample-dev \
        libxxf86vm-dev libglm-dev libglfw3-dev \
        libmpv-dev mpv \
        libpulse-dev libfftw3-dev \
        libfreetype-dev zlib1g-dev libpng-dev \
        libdbus-1-dev \
        libwayland-dev wayland-protocols libxkbcommon-dev
      ;;
    dnf)
      # Fedora / Nobara / RHEL-like — freeglut-devel is REQUIRED (GLUT)
      # Official Fedora 42 list + zlib/png/freetype/dbus/wayland
      dnf_install_packages \
        gcc gcc-c++ cmake make git rsync pkgconf-pkg-config \
        freeglut freeglut-devel \
        glew-devel mesa-libGL-devel \
        libXrandr-devel libXinerama-devel libXcursor-devel libXi-devel \
        libXxf86vm-devel \
        SDL2-devel lz4-devel \
        ffmpeg ffmpeg-free-devel \
        glm-devel glfw-devel \
        mpv mpv-devel \
        pulseaudio-libs-devel fftw-devel gmp-devel \
        zlib-devel libpng-devel freetype-devel \
        dbus-devel \
        wayland-devel wayland-protocols-devel libxkbcommon-devel \
        || true

      # Alternate FFmpeg package names if ffmpeg-free-devel missing
      if ! rpm -q ffmpeg-free-devel >/dev/null 2>&1 && ! rpm -q ffmpeg-devel >/dev/null 2>&1; then
        dnf_install_packages ffmpeg-devel \
          || dnf_install_packages \
               libavcodec-free-devel libavformat-free-devel \
               libavutil-free-devel libswscale-free-devel \
          || true
      fi
      # pkgconf name varies
      dnf_install_packages pkgconfig 2>/dev/null || true
      ;;
    pacman)
      pacman_install_packages \
        base-devel cmake git rsync pkgconf \
        freeglut glew mesa \
        libxrandr libxinerama libxcursor libxi \
        sdl2 lz4 ffmpeg glm glfw-x11 \
        mpv libpulse fftw \
        zlib libpng freetype2 dbus \
        wayland wayland-protocols libxkbcommon
      ;;
    zypper)
      run_root zypper --non-interactive install -t pattern devel_C_C++ || true
      zypper_install_packages \
        cmake git rsync gcc-c++ pkg-config \
        freeglut-devel glew-devel Mesa-libGL-devel \
        libXrandr-devel libXinerama-devel libXcursor-devel libXi-devel \
        libSDL2-devel liblz4-devel \
        glm-devel glfw-devel \
        mpv-devel libpulse-devel fftw3-devel \
        zlib-devel libpng-devel freetype2-devel dbus-1-devel \
        wayland-devel wayland-protocols-devel libxkbcommon-devel \
        || true
      zypper_install_packages ffmpeg-5-libavcodec-devel || true
      ;;
    *)
      die "Unsupported package manager. Install cmake, g++, freeglut-devel (GLUT), glew, SDL2, ffmpeg, mpv, etc., then re-run."
      ;;
  esac
}

# ── Verify deps actually present (not just “dnf said ok”) ───────────────────
# Each entry: "label|test command"
verify_one() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    ok "$label"
    return 0
  fi
  fail "$label"
  return 1
}

file_exists() { [[ -f "$1" || -e "$1" ]]; }

find_header() {
  # find_header name path1 path2 ...
  local p
  for p in "$@"; do
    [[ -f "$p" ]] && return 0
  done
  return 1
}

find_lib() {
  # libglut, libGLEW, etc.
  local name="$1"
  ldconfig -p 2>/dev/null | grep -q "${name}\\.so" && return 0
  [[ -e "/usr/lib64/${name}.so" || -e "/usr/lib/${name}.so" \
    || -e "/usr/lib/x86_64-linux-gnu/${name}.so" ]] && return 0
  return 1
}

verify_and_fix() {
  step "Verifying build dependencies"
  local missing=0

  command -v cmake >/dev/null 2>&1 && ok "cmake ($(cmake --version | head -1))" || { fail "cmake"; missing=1; }
  command -v g++   >/dev/null 2>&1 && ok "g++ ($(g++ --version | head -1))"     || { fail "g++"; missing=1; }
  command -v make  >/dev/null 2>&1 && ok "make"                                  || { fail "make"; missing=1; }
  command -v git   >/dev/null 2>&1 && ok "git"                                   || { fail "git"; missing=1; }

  # GLUT — the one that kept failing for users
  if find_header \
       /usr/include/GL/glut.h \
       /usr/include/GL/freeglut.h \
       /usr/local/include/GL/glut.h \
    && find_lib libglut; then
    ok "GLUT (freeglut) — /usr/include/GL/glut.h + libglut"
  else
    fail "GLUT (freeglut) headers or library"
    missing=1
  fi

  find_header /usr/include/GL/glew.h /usr/include/glew.h && find_lib libGLEW \
    && ok "GLEW" || { fail "GLEW"; missing=1; }

  find_header /usr/include/GL/gl.h && ok "OpenGL headers" || { fail "OpenGL headers"; missing=1; }

  if pkg-config --exists sdl2 2>/dev/null || find_header /usr/include/SDL2/SDL.h; then
    ok "SDL2"
  else
    fail "SDL2"; missing=1
  fi

  find_header /usr/include/lz4.h /usr/include/lz4/lz4.h && ok "LZ4" || { fail "LZ4"; missing=1; }
  find_header /usr/include/zlib.h && ok "zlib" || { fail "zlib"; missing=1; }
  find_header /usr/include/ft2build.h /usr/include/freetype2/ft2build.h && ok "Freetype" || { fail "Freetype"; missing=1; }

  if pkg-config --exists dbus-1 2>/dev/null \
    || find_header /usr/include/dbus-1.0/dbus/dbus.h; then
    ok "DBus"
  else
    fail "DBus"; missing=1
  fi

  if pkg-config --exists mpv 2>/dev/null \
    || find_header /usr/include/mpv/client.h; then
    ok "MPV"
  else
    fail "MPV"; missing=1
  fi

  if pkg-config --exists libpulse 2>/dev/null \
    || find_header /usr/include/pulse/pulseaudio.h; then
    ok "PulseAudio"
  else
    fail "PulseAudio"; missing=1
  fi

  # FFmpeg (any of the core libs)
  if pkg-config --exists libavcodec 2>/dev/null \
    || find_header /usr/include/libavcodec/avcodec.h \
                   /usr/include/ffmpeg/libavcodec/avcodec.h; then
    ok "FFmpeg"
  else
    warn "FFmpeg headers not detected (build may still find them)"
  fi

  return "$missing"
}

# Force-install anything still missing after the big install.
repair_missing_deps() {
  step "Repairing any missing packages"
  case "${PM}" in
    dnf)
      # Always force freeglut first — this is the #1 user failure
      if ! find_header /usr/include/GL/glut.h || ! find_lib libglut; then
        bold "    Installing freeglut + freeglut-devel (required for GLUT)…"
        dnf_install_packages freeglut freeglut-devel || true
        # Absolute last resort: download RPM and rpm -Uvh --nodeps
        if ! find_header /usr/include/GL/glut.h; then
          warn "Trying direct RPM install for freeglut-devel…"
          local tmp
          tmp="$(mktemp -d)"
          (
            cd "$tmp"
            run_root dnf download --nogpgcheck freeglut freeglut-devel 2>/dev/null \
              || dnf download --nogpgcheck freeglut freeglut-devel 2>/dev/null \
              || true
            shopt -s nullglob
            local rpms=( ./*.rpm )
            if [[ ${#rpms[@]} -gt 0 ]]; then
              run_root rpm -Uvh --force --nodeps "${rpms[@]}" || true
            fi
          )
          rm -rf "$tmp"
        fi
      fi
      command -v cmake >/dev/null || dnf_install_packages cmake || true
      command -v g++   >/dev/null || dnf_install_packages gcc-c++ || true
      find_header /usr/include/GL/glew.h || dnf_install_packages glew-devel || true
      find_header /usr/include/GL/gl.h   || dnf_install_packages mesa-libGL-devel || true
      pkg-config --exists sdl2 2>/dev/null || find_header /usr/include/SDL2/SDL.h \
        || dnf_install_packages SDL2-devel || true
      find_header /usr/include/lz4.h || dnf_install_packages lz4-devel || true
      find_header /usr/include/zlib.h || dnf_install_packages zlib-devel || true
      find_header /usr/include/mpv/client.h || dnf_install_packages mpv-devel || true
      pkg-config --exists dbus-1 2>/dev/null || dnf_install_packages dbus-devel || true
      pkg-config --exists libpulse 2>/dev/null || dnf_install_packages pulseaudio-libs-devel || true
      find_header /usr/include/ft2build.h /usr/include/freetype2/ft2build.h \
        || dnf_install_packages freetype-devel || true
      ;;
    apt)
      if ! find_header /usr/include/GL/glut.h; then
        apt_install_packages freeglut3-dev || true
      fi
      command -v cmake >/dev/null || apt_install_packages cmake build-essential || true
      find_header /usr/include/GL/glew.h || apt_install_packages libglew-dev || true
      pkg-config --exists sdl2 2>/dev/null || apt_install_packages libsdl2-dev || true
      find_header /usr/include/mpv/client.h || apt_install_packages libmpv-dev || true
      pkg-config --exists dbus-1 2>/dev/null || apt_install_packages libdbus-1-dev || true
      ;;
    pacman)
      if ! find_header /usr/include/GL/glut.h; then
        pacman_install_packages freeglut || true
      fi
      ;;
    zypper)
      if ! find_header /usr/include/GL/glut.h; then
        zypper_install_packages freeglut-devel || true
      fi
      ;;
  esac
}

require_glut_or_die() {
  if find_header /usr/include/GL/glut.h /usr/include/GL/freeglut.h \
    && find_lib libglut; then
    ok "GLUT ready for CMake"
    return 0
  fi
  echo
  fail "GLUT is still missing after package install."
  echo
  echo "  CMake cannot build linux-wallpaperengine without freeglut."
  echo "  Try this manually, then re-run the installer:"
  echo
  case "${PM}" in
    dnf)
      echo "    sudo dnf install -y --nogpgcheck freeglut freeglut-devel"
      echo "    ls /usr/include/GL/glut.h /usr/lib64/libglut.so"
      ;;
    apt)
      echo "    sudo apt-get install -y freeglut3-dev"
      ;;
    pacman)
      echo "    sudo pacman -S freeglut"
      ;;
    zypper)
      echo "    sudo zypper install freeglut-devel"
      ;;
  esac
  echo
  exit 1
}

# ── Source + build ──────────────────────────────────────────────────────────
prepare_source() {
  step "Fetching linux-wallpaperengine source"
  if [[ ! -d "${SRC}/.git" ]]; then
    mkdir -p "${ROOT}/third_party"
    git clone --depth 1 \
      https://github.com/Almamu/linux-wallpaperengine.git "${SRC}"
  else
    git -C "${SRC}" pull --ff-only || warn "git pull skipped (local changes?)"
  fi
  git -C "${SRC}" submodule update --init --recursive --depth 1 2>/dev/null \
    || git -C "${SRC}" submodule update --init --recursive \
    || warn "submodule update had issues (continuing)"
  ok "Source: ${SRC}"
}

configure_and_build() {
  step "Configuring CMake (clean build tree)"
  # Always wipe build dir so stale GLUT-NOTFOUND caches cannot stick
  rm -rf "${BUILD_DIR}"
  mkdir -p "${BUILD_DIR}"

  # Help CMake find freeglut on multi-arch layouts
  export CMAKE_PREFIX_PATH="/usr:/usr/local${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"
  # Prefer lib64 on Fedora/Nobara
  local cmake_extra=()
  if [[ -d /usr/lib64 ]]; then
    cmake_extra+=(
      "-DCMAKE_LIBRARY_PATH=/usr/lib64;/usr/lib"
      "-DCMAKE_INCLUDE_PATH=/usr/include"
    )
  fi

  # Point GLUT explicitly when freeglut is installed in the usual place
  if [[ -f /usr/include/GL/glut.h ]]; then
    cmake_extra+=("-DGLUT_INCLUDE_DIR=/usr/include")
  fi
  for candidate in \
      /usr/lib64/libglut.so /usr/lib64/libglut.so.3 \
      /usr/lib/libglut.so /usr/lib/libglut.so.3 \
      /usr/lib/x86_64-linux-gnu/libglut.so \
      /usr/lib/x86_64-linux-gnu/libglut.so.3; do
    if [[ -e "$candidate" ]]; then
      cmake_extra+=("-DGLUT_glut_LIBRARY=${candidate}")
      ok "Hinting CMake: GLUT library = ${candidate}"
      break
    fi
  done

  echo "    cmake ${cmake_extra[*]:-}"
  if ! cmake -S "${SRC}" -B "${BUILD_DIR}" \
      -DCMAKE_BUILD_TYPE=Release \
      "${cmake_extra[@]}"; then
    fail "CMake configure failed."
    echo
    echo "  Last 40 lines of CMakeError.log (if any):"
    tail -40 "${BUILD_DIR}/CMakeFiles/CMakeError.log" 2>/dev/null || true
    tail -40 "${BUILD_DIR}/CMakeFiles/CMakeOutput.log" 2>/dev/null || true
    die "Fix the missing dependency above, then re-run: $0"
  fi
  ok "CMake configured"

  step "Building (this can take several minutes)"
  local jobs
  jobs="$(nproc 2>/dev/null || echo 2)"
  cmake --build "${BUILD_DIR}" -j"${jobs}"
  ok "Build finished"
}

install_binary() {
  step "Installing to ${PREFIX}"

  local candidates=(
    "${BUILD_DIR}/output/linux-wallpaperengine"
    "${BUILD_DIR}/linux-wallpaperengine"
    "${SRC}/output/linux-wallpaperengine"
    "${BUILD_DIR}/bin/linux-wallpaperengine"
  )
  local bin="" c
  for c in "${candidates[@]}"; do
    if [[ -x "$c" ]]; then
      bin="$c"
      break
    fi
  done
  if [[ -z "$bin" ]]; then
    bin="$(find "${BUILD_DIR}" -name 'linux-wallpaperengine' -type f -executable 2>/dev/null | head -1 || true)"
  fi
  [[ -n "$bin" && -x "$bin" ]] || die "Built binary not found under ${BUILD_DIR}"

  local out_dir
  out_dir="$(dirname "$bin")"
  mkdir -p "${SHARE}" "${BIN_DIR}"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "${out_dir}/" "${SHARE}/"
  else
    cp -a "${out_dir}/." "${SHARE}/"
  fi
  ln -sfn "${SHARE}/linux-wallpaperengine" "${BIN_DIR}/linux-wallpaperengine"
  chmod +x "${SHARE}/linux-wallpaperengine" 2>/dev/null || true

  local real
  real="$(readlink -f "${BIN_DIR}/linux-wallpaperengine" 2>/dev/null || echo "${BIN_DIR}/linux-wallpaperengine")"
  if command -v sha256sum >/dev/null 2>&1 && [[ -f "$real" ]]; then
    local sum
    sum="$(sha256sum "$real" | awk '{print $1}')"
    echo "${sum}  linux-wallpaperengine" > "${SHARE}/linux-wallpaperengine.sha256"
    ok "Installed: ${BIN_DIR}/linux-wallpaperengine"
    ok "SHA-256: ${sum}"
  else
    ok "Installed: ${BIN_DIR}/linux-wallpaperengine"
  fi

  # Smoke test
  if "${BIN_DIR}/linux-wallpaperengine" --help >/dev/null 2>&1; then
    ok "Binary runs (--help OK)"
  else
    warn "Binary installed but --help returned non-zero (may still work for wallpapers)"
    "${BIN_DIR}/linux-wallpaperengine" --help 2>&1 | head -15 || true
  fi
}

# ── Main ────────────────────────────────────────────────────────────────────
main() {
  bold "GnomePaper · linux-wallpaperengine installer"
  echo "  Install prefix: ${PREFIX}"
  echo "  Source tree:    ${SRC}"

  detect_os
  echo "  System:         ${OS_NAME}"
  echo "  Package mgr:    ${PM}"
  if [[ "${IS_NOBARA}" -eq 1 ]]; then
    echo "  Nobara:         yes (using GPG-relaxed package installs)"
  fi

  if ! command -v git >/dev/null 2>&1; then
    ensure_sudo
    case "${PM}" in
      apt) apt_install_packages git ;;
      dnf) dnf_install_packages git ;;
      pacman) pacman_install_packages git ;;
      zypper) zypper_install_packages git ;;
    esac
  fi
  command -v git >/dev/null 2>&1 || die "git is required"

  ensure_sudo

  # 1) Install everything the project needs
  install_all_deps

  # 2) Repair anything still missing (especially freeglut)
  repair_missing_deps

  # 3) Verify; if GLUT still missing, one more repair + die clearly
  if ! verify_and_fix; then
    warn "Some dependencies missing — running repair pass again…"
    repair_missing_deps
    verify_and_fix || true
  fi
  require_glut_or_die

  # 4) Build
  prepare_source
  configure_and_build
  install_binary

  echo
  bold "Done."
  echo "  Binary:  ${BIN_DIR}/linux-wallpaperengine"
  echo "  Next:    open GnomePaper → Settings → Scene engine → Re-detect"
  echo "           (or wait for auto-detect)"
  echo
}

main "$@"
