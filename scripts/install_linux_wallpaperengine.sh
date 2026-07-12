#!/usr/bin/env bash
# Build and install Almamu/linux-wallpaperengine for GnomePaper scene support.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/third_party/linux-wallpaperengine"
PREFIX="${HOME}/.local"
BIN_DIR="${PREFIX}/bin"
BUILD_DIR="${SRC}/build"

echo "==> GnomePaper: install linux-wallpaperengine"
echo "    Source: ${SRC}"
echo "    Binary: ${BIN_DIR}/linux-wallpaperengine"

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "error: required command not found: $1" >&2
    echo "       Install it, then re-run this script." >&2
    exit 1
  fi
}

if ! command -v git >/dev/null 2>&1; then
  echo "error: git is required" >&2
  exit 1
fi

detect_pm() {
  if command -v apt-get >/dev/null 2>&1; then echo apt
  elif command -v dnf >/dev/null 2>&1; then echo dnf
  elif command -v pacman >/dev/null 2>&1; then echo pacman
  elif command -v zypper >/dev/null 2>&1; then echo zypper
  else echo unknown
  fi
}

# dnf/dnf5 install with fallback for broken OpenPGP keys (common on Nobara/custom repos).
# Usage: dnf_install [--skip-broken] pkg1 pkg2 ...
dnf_install() {
  local extra=()
  while [[ $# -gt 0 && "$1" == --* ]]; do
    extra+=("$1")
    shift
  done
  local pkgs=("$@")
  if [[ ${#pkgs[@]} -eq 0 ]]; then
    return 0
  fi

  # 1) Normal install
  if sudo dnf install -y "${extra[@]}" "${pkgs[@]}"; then
    return 0
  fi

  echo "warning: dnf install failed — trying to refresh RPM keys…" >&2
  # Import any keys shipped on the system (Nobara/Fedora often need this after upgrades)
  if [[ -d /etc/pki/rpm-gpg ]]; then
    # shellcheck disable=SC2046
    sudo rpm --import $(find /etc/pki/rpm-gpg -type f 2>/dev/null | head -50) 2>/dev/null || true
  fi
  sudo dnf clean packages 2>/dev/null || true

  # 2) Retry after key import
  if sudo dnf install -y "${extra[@]}" "${pkgs[@]}"; then
    return 0
  fi

  # 3) OpenPGP / wrong-key fallback (Nobara repo keys often lag packages)
  echo "warning: OpenPGP check failed or install still blocked." >&2
  echo "         Retrying with GPG check disabled for this install only…" >&2
  if sudo dnf install -y --nogpgcheck \
      --setopt=gpgcheck=0 \
      --setopt=localpkg_gpgcheck=0 \
      "${extra[@]}" "${pkgs[@]}"; then
    return 0
  fi

  # dnf5 sometimes wants repo-wide setopt form
  if sudo dnf install -y --nogpgcheck \
      --setopt=*.gpgcheck=0 \
      "${extra[@]}" "${pkgs[@]}"; then
    return 0
  fi

  return 1
}

# Core toolchain only — must succeed (cmake, compilers, make, rsync).
install_core_build_tools() {
  local pm
  pm="$(detect_pm)"
  echo "==> Installing core build tools ($pm) — cmake, g++, make (needs sudo)…"
  case "$pm" in
    apt)
      sudo apt-get update -y
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
        build-essential cmake make g++ gcc git rsync pkg-config
      ;;
    dnf)
      # Prefer full set; fall back if optional pkg names differ (Fedora vs Nobara).
      if ! dnf_install cmake make gcc gcc-c++ git rsync pkgconf-pkg-config; then
        dnf_install cmake make gcc gcc-c++ git rsync pkgconfig \
          || dnf_install cmake make gcc gcc-c++ git rsync \
          || true
      fi
      ;;
    pacman)
      sudo pacman -Sy --needed --noconfirm \
        base-devel cmake make gcc git rsync pkgconf
      ;;
    zypper)
      sudo zypper --non-interactive install -t pattern devel_C_C++ || true
      sudo zypper --non-interactive install \
        cmake make gcc-c++ gcc git rsync pkg-config
      ;;
    *)
      echo "error: unknown package manager. Install at least: cmake g++ make git rsync" >&2
      exit 1
      ;;
  esac
}

# Optional / heavier scene-engine deps — best effort (do not hide core failures).
install_lwe_dev_libs() {
  local pm
  pm="$(detect_pm)"
  echo "==> Installing linux-wallpaperengine libraries ($pm)…"
  case "$pm" in
    apt)
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
        libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev \
        libgl-dev libglew-dev freeglut3-dev libsdl2-dev liblz4-dev \
        libavcodec-dev libavformat-dev libavutil-dev libswscale-dev \
        libxxf86vm-dev libglm-dev libglfw3-dev \
        libmpv-dev mpv libpulse-dev libfftw3-dev \
        zlib1g-dev libpng-dev libfreetype-dev \
        libwayland-dev wayland-protocols libxkbcommon-dev libdbus-1-dev \
        || echo "warning: some library packages failed; build may still work" >&2
      ;;
    dnf)
      dnf_install --skip-broken \
        libXrandr-devel libXinerama-devel libXcursor-devel libXi-devel \
        mesa-libGL-devel glew-devel freeglut-devel SDL2-devel lz4-devel \
        ffmpeg-free-devel libXxf86vm-devel glm-devel glfw-devel \
        mpv mpv-devel pulseaudio-libs-devel fftw-devel gmp-devel \
        zlib-devel libpng-devel freetype-devel wayland-devel \
        wayland-protocols-devel libxkbcommon-devel dbus-devel \
        || echo "warning: some library packages failed; build may still work" >&2
      ;;
    pacman)
      sudo pacman -Sy --needed --noconfirm \
        libxrandr libxinerama libxcursor libxi \
        mesa glew freeglut sdl2 lz4 ffmpeg glm glfw-x11 \
        mpv libpulse fftw zlib libpng freetype2 \
        wayland wayland-protocols libxkbcommon dbus \
        || echo "warning: some library packages failed; build may still work" >&2
      ;;
    zypper)
      sudo zypper --non-interactive install \
        libXrandr-devel libXinerama-devel libXcursor-devel libXi-devel \
        Mesa-libGL-devel glew-devel freeglut-devel libSDL2-devel liblz4-devel \
        ffmpeg-5-libavcodec-devel glm-devel glfw-devel \
        mpv-devel libpulse-devel fftw3-devel \
        zlib-devel libpng-devel freetype2-devel \
        wayland-devel wayland-protocols-devel libxkbcommon-devel dbus-1-devel \
        || echo "warning: some library packages failed; build may still work" >&2
      ;;
  esac
}

# Refresh PATH for tools just installed into /usr/bin (some shells keep a stale hash).
hash -r 2>/dev/null || true
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"

if ! command -v cmake >/dev/null 2>&1 \
  || ! command -v g++ >/dev/null 2>&1 \
  || ! command -v make >/dev/null 2>&1; then
  install_core_build_tools
  hash -r 2>/dev/null || true
fi

# Always try scene libs when we have a package manager (idempotent).
if [[ "$(detect_pm)" != "unknown" ]]; then
  install_lwe_dev_libs || true
fi

# Hard fail with a clear fix if cmake is still missing (e.g. sudo was cancelled).
if ! command -v cmake >/dev/null 2>&1; then
  echo "" >&2
  echo "error: cmake is not installed (or not on PATH)." >&2
  echo "       The core package install may have failed (sudo password?)." >&2
  echo "" >&2
  case "$(detect_pm)" in
    apt)  echo "  sudo apt-get install -y build-essential cmake" >&2 ;;
    dnf)  echo "  sudo dnf install -y cmake gcc gcc-c++ make" >&2 ;;
    pacman) echo "  sudo pacman -S --needed base-devel cmake" >&2 ;;
    zypper) echo "  sudo zypper install cmake gcc-c++ make" >&2 ;;
    *)    echo "  Install package 'cmake' for your distro, then re-run." >&2 ;;
  esac
  echo "" >&2
  echo "Then re-run:" >&2
  echo "  $0" >&2
  exit 1
fi

need_cmd cmake
need_cmd make
# g++ or c++
if ! command -v g++ >/dev/null 2>&1 && ! command -v c++ >/dev/null 2>&1; then
  echo "error: a C++ compiler (g++) is required" >&2
  exit 1
fi

echo "    cmake: $(command -v cmake) ($(cmake --version | head -1))"

if [[ ! -d "${SRC}/.git" ]]; then
  echo "==> Cloning linux-wallpaperengine…"
  mkdir -p "${ROOT}/third_party"
  git clone --depth 1 \
    https://github.com/Almamu/linux-wallpaperengine.git "${SRC}"
  git -C "${SRC}" submodule update --init --recursive --depth 1 || \
    git -C "${SRC}" submodule update --init --recursive
else
  echo "==> Updating existing clone…"
  git -C "${SRC}" pull --ff-only || true
  git -C "${SRC}" submodule update --init --recursive || true
fi

echo "==> Configuring CMake (Release)…"
mkdir -p "${BUILD_DIR}"
cmake -S "${SRC}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE=Release

echo "==> Building…"
cmake --build "${BUILD_DIR}" -j"$(nproc 2>/dev/null || echo 2)"

# Binary location varies by project version
CANDIDATES=(
  "${BUILD_DIR}/output/linux-wallpaperengine"
  "${BUILD_DIR}/linux-wallpaperengine"
  "${SRC}/output/linux-wallpaperengine"
  "${BUILD_DIR}/bin/linux-wallpaperengine"
)

BIN=""
for c in "${CANDIDATES[@]}"; do
  if [[ -x "${c}" ]]; then
    BIN="${c}"
    break
  fi
done

if [[ -z "${BIN}" ]]; then
  echo "Build finished but binary not found. Look under ${BUILD_DIR}" >&2
  find "${BUILD_DIR}" -name 'linux-wallpaperengine' -type f 2>/dev/null | head
  exit 1
fi

mkdir -p "${BIN_DIR}"
# Copy binary + neighboring runtime files if an output dir exists
OUT_DIR="$(dirname "${BIN}")"
if [[ -d "${OUT_DIR}" ]]; then
  # Prefer symlink of the whole output tree into share, binary into bin
  SHARE="${PREFIX}/share/linux-wallpaperengine"
  mkdir -p "${SHARE}"
  rsync -a --delete "${OUT_DIR}/" "${SHARE}/" 2>/dev/null \
    || cp -a "${OUT_DIR}/." "${SHARE}/"
  ln -sfn "${SHARE}/linux-wallpaperengine" "${BIN_DIR}/linux-wallpaperengine"
else
  install -m 755 "${BIN}" "${BIN_DIR}/linux-wallpaperengine"
fi

echo "==> Installed: ${BIN_DIR}/linux-wallpaperengine"
REAL_BIN="$(readlink -f "${BIN_DIR}/linux-wallpaperengine" 2>/dev/null || echo "${BIN_DIR}/linux-wallpaperengine")"
if command -v sha256sum >/dev/null 2>&1 && [[ -f "${REAL_BIN}" ]]; then
  SUM="$(sha256sum "${REAL_BIN}" | awk '{print $1}')"
  echo "    SHA-256: ${SUM}"
  # Side-car checksum for GnomePaper auto-detect / diagnostics
  echo "${SUM}  linux-wallpaperengine" > "$(dirname "${REAL_BIN}")/linux-wallpaperengine.sha256" 2>/dev/null || true
fi
"${BIN_DIR}/linux-wallpaperengine" --help 2>&1 | head -20 || true
echo "Done. In GnomePaper: Settings → Scene engine → Re-detect (or wait for auto-detect)."
