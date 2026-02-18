#!/usr/bin/env bash
set -euo pipefail

MODULE_NAME="fevm-ip3-fancontrol"
MODULE_VERSION="0.1.0"
KERNEL_VERSION="$(uname -r)"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'USAGE'
Usage: ./scripts/install_dkms.sh [module_version]

Example:
  ./scripts/install_dkms.sh
  ./scripts/install_dkms.sh 0.1.0
USAGE
  exit 0
fi

if [[ $# -ge 1 ]]; then
  MODULE_VERSION="$1"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
KERNEL_DIR="${REPO_ROOT}/kernel"
SRC_DIR="/usr/src/${MODULE_NAME}-${MODULE_VERSION}"

SUDO=""
if [[ "${EUID}" -ne 0 ]]; then
  SUDO="sudo"
fi

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing command: $1" >&2
    exit 1
  fi
}

need_file() {
  if [[ ! -f "$1" ]]; then
    echo "Missing required file: $1" >&2
    exit 1
  fi
}

need_cmd dkms
need_cmd make
need_cmd modprobe
need_cmd uname

if [[ ! -d "/lib/modules/${KERNEL_VERSION}/build" ]]; then
  echo "Kernel headers not found for ${KERNEL_VERSION}" >&2
  echo "Please install matching headers first." >&2
  exit 1
fi

need_file "${KERNEL_DIR}/fevm_ip3_wmi_fan.c"
need_file "${KERNEL_DIR}/Makefile"
need_file "${KERNEL_DIR}/dkms.conf"
need_file "${KERNEL_DIR}/Kconfig"

echo "[1/6] Copy source to ${SRC_DIR}"
${SUDO} rm -rf "${SRC_DIR}"
${SUDO} install -d "${SRC_DIR}"
${SUDO} install -m 0644 "${KERNEL_DIR}/fevm_ip3_wmi_fan.c" "${SRC_DIR}/"
${SUDO} install -m 0644 "${KERNEL_DIR}/Makefile" "${SRC_DIR}/"
${SUDO} install -m 0644 "${KERNEL_DIR}/dkms.conf" "${SRC_DIR}/"
${SUDO} install -m 0644 "${KERNEL_DIR}/Kconfig" "${SRC_DIR}/"

echo "[2/6] Remove old DKMS entry (if exists)"
${SUDO} dkms remove -m "${MODULE_NAME}" -v "${MODULE_VERSION}" --all >/dev/null 2>&1 || true

echo "[3/6] Add DKMS module"
${SUDO} dkms add -m "${MODULE_NAME}" -v "${MODULE_VERSION}"

echo "[4/6] Build for kernel ${KERNEL_VERSION}"
${SUDO} dkms build -m "${MODULE_NAME}" -v "${MODULE_VERSION}" -k "${KERNEL_VERSION}"

echo "[5/6] Install for kernel ${KERNEL_VERSION}"
${SUDO} dkms install -m "${MODULE_NAME}" -v "${MODULE_VERSION}" -k "${KERNEL_VERSION}"

echo "[6/6] Load module"
${SUDO} modprobe fevm_ip3_wmi_fan

echo
echo "DKMS status:"
dkms status | rg -n "${MODULE_NAME}" || true
echo

if [[ -e /sys/devices/platform/fevm-ip3-wmi/fan1_duty ]]; then
  echo "OK: /sys/devices/platform/fevm-ip3-wmi/fan1_duty is available"
  echo "Test command:"
  echo "  echo 60 | sudo tee /sys/devices/platform/fevm-ip3-wmi/fan1_duty"
else
  echo "Module loaded, but fan sysfs node not found yet." >&2
  echo "Check logs with:" >&2
  echo "  sudo dmesg | tail -n 100" >&2
fi
