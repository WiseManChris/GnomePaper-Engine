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

if ! command -v git >/dev/null; then
  echo "git is required" >&2
  exit 1
fi

echo "==> Installing build dependencies (sudo)…"
if command -v dnf >/dev/null; then
  sudo dnf install -y \
    gcc gcc-c++ cmake make git rsync \
    libXrandr-devel libXinerama-devel libXcursor-devel libXi-devel \
    mesa-libGL-devel glew-devel freeglut-devel SDL2-devel lz4-devel \
    ffmpeg-free-devel libXxf86vm-devel glm-devel glfw-devel \
    mpv mpv-devel pulseaudio-libs-devel fftw-devel gmp-devel \
    zlib-devel libpng-devel freetype-devel wayland-devel \
    wayland-protocols-devel libxkbcommon-devel dbus-devel || true
elif command -v apt-get >/dev/null; then
  sudo apt-get update -y
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    build-essential cmake git rsync \
    libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev \
    libgl-dev libglew-dev freeglut3-dev libsdl2-dev liblz4-dev \
    libavcodec-dev libavformat-dev libavutil-dev libswscale-dev \
    libxxf86vm-dev libglm-dev libglfw3-dev \
    libmpv-dev mpv libpulse-dev libfftw3-dev \
    zlib1g-dev libpng-dev libfreetype-dev \
    libwayland-dev wayland-protocols libxkbcommon-dev libdbus-1-dev || true
elif command -v pacman >/dev/null; then
  sudo pacman -Sy --needed --noconfirm \
    base-devel cmake git rsync \
    libxrandr libxinerama libxcursor libxi \
    mesa glew freeglut sdl2 lz4 ffmpeg glm glfw-x11 \
    mpv libpulse fftw zlib libpng freetype2 \
    wayland wayland-protocols libxkbcommon dbus || true
elif command -v zypper >/dev/null; then
  sudo zypper --non-interactive install -t pattern devel_C_C++ || true
  sudo zypper --non-interactive install \
    cmake git rsync gcc-c++ \
    libXrandr-devel libXinerama-devel libXcursor-devel libXi-devel \
    Mesa-libGL-devel glew-devel freeglut-devel libSDL2-devel liblz4-devel \
    ffmpeg-5-libavcodec-devel glm-devel glfw-devel \
    mpv-devel libpulse-devel fftw3-devel \
    zlib-devel libpng-devel freetype2-devel \
    wayland-devel wayland-protocols-devel libxkbcommon-devel dbus-1-devel || true
else
  echo "Install build tools + OpenGL/FFmpeg/mpv/Wayland dev packages for your distro, then re-run." >&2
fi

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
cmake --build "${BUILD_DIR}" -j"$(nproc)"

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
"${BIN_DIR}/linux-wallpaperengine" --help 2>&1 | head -20 || true
echo "Done. Restart GnomePaper Engine and apply a scene wallpaper."
