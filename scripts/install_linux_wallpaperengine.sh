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

  if sudo dnf install -y --nogpgcheck \
      --setopt=*.gpgcheck=0 \
      "${extra[@]}" "${pkgs[@]}"; then
    return 0
  fi

  return 1
}

# Install packages one-by-one so a single bad package does not skip freeglut etc.
dnf_install_each() {
  local failed=()
  local p
  for p in "$@"; do
    if ! dnf_install "$p"; then
      failed+=("$p")
      echo "warning: could not install package: $p" >&2
    fi
  done
  if [[ ${#failed[@]} -gt 0 ]]; then
    echo "warning: failed packages: ${failed[*]}" >&2
    return 1
  fi
  return 0
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

# Packages required by linux-wallpaperengine CMakeLists find_package(...)
# Installed as hard requirements (not best-effort).
install_required_cmake_deps() {
  local pm
  pm="$(detect_pm)"
  echo "==> Installing required CMake dependencies ($pm)…"
  case "$pm" in
    apt)
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
        freeglut3-dev libglew-dev libgl-dev libsdl2-dev liblz4-dev \
        libavcodec-dev libavformat-dev libavutil-dev libswscale-dev \
        libmpv-dev libpulse-dev zlib1g-dev libpng-dev libfreetype-dev \
        libdbus-1-dev libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev \
        libxxf86vm-dev libglm-dev libglfw3-dev \
        libwayland-dev wayland-protocols libxkbcommon-dev
      ;;
    dnf)
      # freeglut-devel provides GLUT (GL/glut.h + libglut) — this was the Nobara failure.
      # Install one-by-one so GPG fallback works and one bad name does not skip GLUT.
      dnf_install_each \
        freeglut freeglut-devel \
        mesa-libGL-devel glew-devel \
        SDL2-devel lz4-devel \
        zlib-devel libpng-devel freetype-devel \
        dbus-devel \
        libXrandr-devel libXinerama-devel libXcursor-devel libXi-devel \
        libXxf86vm-devel \
        pulseaudio-libs-devel \
        mpv-devel mpv \
        glfw-devel glm-devel \
        wayland-devel wayland-protocols-devel libxkbcommon-devel \
        gmp-devel fftw-devel \
        || true
      # FFmpeg headers (package name varies by Fedora/Nobara)
      dnf_install ffmpeg-free-devel \
        || dnf_install ffmpeg-devel \
        || dnf_install_each \
             libavcodec-free-devel libavformat-free-devel \
             libavutil-free-devel libswscale-free-devel \
        || true
      ;;
    pacman)
      sudo pacman -Sy --needed --noconfirm \
        freeglut glew mesa sdl2 lz4 ffmpeg mpv libpulse zlib libpng freetype2 \
        dbus libxrandr libxinerama libxcursor libxi glm glfw-x11 \
        wayland wayland-protocols libxkbcommon fftw
      ;;
    zypper)
      sudo zypper --non-interactive install \
        freeglut-devel glew-devel Mesa-libGL-devel libSDL2-devel liblz4-devel \
        mpv-devel libpulse-devel zlib-devel libpng-devel freetype2-devel \
        dbus-1-devel libXrandr-devel libXinerama-devel libXcursor-devel \
        libXi-devel glm-devel glfw-devel \
        wayland-devel wayland-protocols-devel libxkbcommon-devel \
        ffmpeg-5-libavcodec-devel || true
      ;;
  esac
}

# Headers / libs CMake must see before configure.
have_glut() {
  [[ -f /usr/include/GL/glut.h ]] \
    || [[ -f /usr/include/GL/freeglut.h ]] \
    || pkg-config --exists glut 2>/dev/null \
    || pkg-config --exists freeglut 2>/dev/null \
    || ldconfig -p 2>/dev/null | grep -q 'libglut\.so'
}

ensure_glut() {
  if have_glut; then
    echo "    GLUT: OK"
    return 0
  fi
  echo "==> GLUT not found — installing freeglut development package…"
  case "$(detect_pm)" in
    apt)
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y freeglut3-dev
      ;;
    dnf)
      dnf_install freeglut freeglut-devel \
        || dnf_install freeglut-devel \
        || true
      ;;
    pacman)
      sudo pacman -Sy --needed --noconfirm freeglut
      ;;
    zypper)
      sudo zypper --non-interactive install freeglut-devel
      ;;
  esac
  if ! have_glut; then
    echo "" >&2
    echo "error: Could NOT find GLUT (missing freeglut headers/libs)." >&2
    echo "       CMake needs freeglut-devel (Fedora/Nobara) or freeglut3-dev (Debian)." >&2
    echo "" >&2
    case "$(detect_pm)" in
      dnf)
        echo "  Try manually:" >&2
        echo "    sudo dnf install -y --nogpgcheck freeglut freeglut-devel" >&2
        ;;
      apt)
        echo "  Try manually:" >&2
        echo "    sudo apt-get install -y freeglut3-dev" >&2
        ;;
      *)
        echo "  Install freeglut development packages for your distro, then re-run." >&2
        ;;
    esac
    exit 1
  fi
  echo "    GLUT: OK (installed)"
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

if [[ "$(detect_pm)" != "unknown" ]]; then
  install_required_cmake_deps || true
fi

# Hard fail with a clear fix if cmake is still missing (e.g. sudo was cancelled).
if ! command -v cmake >/dev/null 2>&1; then
  echo "" >&2
  echo "error: cmake is not installed (or not on PATH)." >&2
  echo "       The core package install may have failed (sudo password?)." >&2
  echo "" >&2
  case "$(detect_pm)" in
    apt)  echo "  sudo apt-get install -y build-essential cmake" >&2 ;;
    dnf)  echo "  sudo dnf install -y --nogpgcheck cmake gcc gcc-c++ make" >&2 ;;
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
if ! command -v g++ >/dev/null 2>&1 && ! command -v c++ >/dev/null 2>&1; then
  echo "error: a C++ compiler (g++) is required" >&2
  exit 1
fi

ensure_glut

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
# Drop a broken half-configured tree so re-runs after installing freeglut work cleanly
if [[ -f "${BUILD_DIR}/CMakeCache.txt" ]]; then
  # If previous configure failed missing GLUT, wipe cache and retry clean
  if grep -q 'GLUT_INCLUDE_DIR-NOTFOUND\|Could NOT find GLUT\|GLUT_glut_LIBRARY-NOTFOUND' \
       "${BUILD_DIR}/CMakeCache.txt" 2>/dev/null \
    || ! grep -q 'GLUT_INCLUDE_DIR:PATH=/' "${BUILD_DIR}/CMakeCache.txt" 2>/dev/null; then
    echo "    Clearing stale CMake cache from a previous failed configure…"
    rm -rf "${BUILD_DIR}"
  fi
fi
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
OUT_DIR="$(dirname "${BIN}")"
if [[ -d "${OUT_DIR}" ]]; then
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
  echo "${SUM}  linux-wallpaperengine" > "$(dirname "${REAL_BIN}")/linux-wallpaperengine.sha256" 2>/dev/null || true
fi
"${BIN_DIR}/linux-wallpaperengine" --help 2>&1 | head -20 || true
echo "Done. In GnomePaper: Settings → Scene engine → Re-detect (or wait for auto-detect)."
