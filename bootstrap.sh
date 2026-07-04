#!/usr/bin/env bash
set -euo pipefail

TOOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10

if [ -t 1 ]; then
    B="\033[1m"; R="\033[0m"; G="\033[92m"; YL="\033[93m"; RD="\033[91m"; W="\033[97m"
else
    B=""; R=""; G=""; YL=""; RD=""; W=""
fi

banner() {
    clear 2>/dev/null || true
    echo -e "${W}${B}"
    echo '  ██╗  ██╗██╗██████╗ ███████╗'
    echo '  ██║  ██║██║██╔══██╗██╔════╝'
    echo '  ███████║██║██║  ██║█████╗  '
    echo '  ██╔══██║██║██║  ██║██╔══╝  '
    echo '  ██║  ██║██║██████╔╝███████╗'
    echo '  ╚═╝  ╚═╝╚═╝╚═════╝ ╚══════╝'
    echo -e "${R}"
    echo -e "  ${W}made by plastral${R}"
    echo -e "  ──────────────────────────────────────────────"
    echo
}

step()  { echo -e "  ${W}${B}▸ $1${R}"; }
ok()    { echo -e "    ${G}✓${R} $1"; }
warn()  { echo -e "    ${YL}!${R} $1"; }
fail()  { echo -e "    ${RD}✗${R} $1"; }
info()  { echo -e "    ${W}·${R} $1"; }

OS=""
DISTRO=""
PKG=""

detect_os() {
    case "$(uname -s)" in
        Darwin)  OS="macos" ;;
        Linux)
            OS="linux"
            if   [ -f /etc/debian_version ];   then DISTRO="debian"; PKG="apt"
            elif [ -f /etc/fedora-release ];   then DISTRO="fedora"; PKG="dnf"
            elif [ -f /etc/arch-release ];     then DISTRO="arch";   PKG="pacman"
            elif [ -f /etc/opensuse-release ]; then DISTRO="suse";   PKG="zypper"
            else                                    DISTRO="unknown"; PKG="unknown"
            fi
            ;;
        MINGW*|MSYS*|CYGWIN*)
            fail "Windows detected — please run bootstrap.ps1 instead."
            echo "    Run in PowerShell:  .\\bootstrap.ps1"
            exit 1
            ;;
        *)
            fail "Unsupported OS: $(uname -s)"
            exit 1
            ;;
    esac
}

PYTHON=""

python_ok() {
    local py="$1"
    if ! command -v "$py" &>/dev/null; then return 1; fi
    local ver
    ver=$("$py" -c "import sys; print(sys.version_info[:2])" 2>/dev/null) || return 1
    python3 -c "
import sys
v = $ver
sys.exit(0 if v >= ($MIN_PYTHON_MAJOR,$MIN_PYTHON_MINOR) else 1)
" 2>/dev/null
}

find_python() {
    for candidate in python3.12 python3.11 python3.10 python3 python; do
        if python_ok "$candidate" 2>/dev/null; then
            PYTHON="$(command -v "$candidate")"
            return 0
        fi
    done
    return 1
}

install_python_macos() {
    info "Installing Homebrew (required for Python)..."
    if ! command -v brew &>/dev/null; then
        /bin/bash -c "$(curl -fsSL \
            https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
            </dev/null
        eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || true)"
        eval "$(/usr/local/bin/brew shellenv 2>/dev/null || true)"
    fi
    brew install python@3.12 2>/dev/null || brew install python3
    PYTHON="$(brew --prefix)/bin/python3"
}

install_python_linux() {
    case "$PKG" in
        apt)
            sudo apt-get update -qq
            sudo apt-get install -y -qq python3 python3-pip python3-venv
            ;;
        dnf)
            sudo dnf install -y -q python3 python3-pip
            ;;
        pacman)
            sudo pacman -S --noconfirm --needed python python-pip
            ;;
        zypper)
            sudo zypper install -y python3 python3-pip
            ;;
        *)
            fail "Cannot auto-install Python on this distribution."
            fail "Please install Python $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR+ manually."
            exit 1
            ;;
    esac
}

ensure_python() {
    step "Python $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR+"
    if find_python; then
        ok "Found: $PYTHON  ($($PYTHON --version 2>&1))"
        return
    fi
    warn "Python $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR+ not found — installing..."
    case "$OS" in
        macos) install_python_macos ;;
        linux) install_python_linux ;;
    esac
    if ! find_python; then
        fail "Python installation failed. Please install Python $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR+ manually."
        exit 1
    fi
    ok "Python installed: $PYTHON"
}

ensure_sudo() {
    step "Privilege Check"
    if [ "$EUID" -eq 0 ]; then
        ok "Running as root"
        return
    fi
    if sudo -n true 2>/dev/null; then
        ok "sudo available"
        return
    fi
    info "This tool needs admin access to set up firewall rules and system daemons."
    sudo -v
    ok "sudo access confirmed"
}

run_hide() {
    step "Setting up environment"
    "$PYTHON" -m venv "$TOOL_DIR/.venv"
    "$TOOL_DIR/.venv/bin/pip" install --quiet -r "$TOOL_DIR/requirements.txt"
    PYTHON="$TOOL_DIR/.venv/bin/python3"
    ok "Environment ready"

    step "Launching HIDE"
    info "Starting installer via Python..."
    echo
    exec "$PYTHON" "$TOOL_DIR/hide.py"
}

main() {
    banner
    detect_os
    info "OS: $OS${DISTRO:+ ($DISTRO)}"
    echo
    ensure_sudo
    ensure_python
    run_hide
}

main "$@"
