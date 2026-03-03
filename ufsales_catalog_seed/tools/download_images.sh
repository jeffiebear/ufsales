#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CAT_DIR="${MODULE_ROOT}/static/src/img/categories"
PROD_DIR="${MODULE_ROOT}/static/src/img/products"

mkdir -p "${CAT_DIR}" "${PROD_DIR}"

download() {
  local url="$1"
  local output="$2"
  local tmp_file="${output}.tmp"
  echo "Downloading ${output}"
  curl -L "${url}" -o "${tmp_file}"
  local mime_type
  mime_type="$(file --brief --mime-type "${tmp_file}" || true)"
  if [[ "${mime_type}" != image/* ]]; then
    echo "Download did not return an image for: ${url}" >&2
    echo "Saved content type: ${mime_type}" >&2
    rm -f "${tmp_file}"
    exit 1
  fi
  mv "${tmp_file}" "${output}"
}

# Category images
download "https://unsplash.com/photos/dBBgsCGNfDA/download?force=true" "${CAT_DIR}/janitorial.jpg"
download "https://unsplash.com/photos/5qsEhKp_R5w/download?force=true" "${CAT_DIR}/soaps.jpg"
download "https://unsplash.com/photos/WhrZscWpvzk/download?force=true" "${CAT_DIR}/food_service.jpg"
download "https://unsplash.com/photos/f2kBV-2Wj0U/download?force=true" "${CAT_DIR}/gloves_safety.jpg"
download "https://unsplash.com/photos/Ys-DBJeX0nE/download?force=true" "${CAT_DIR}/packaging.jpg"

# Product images
download "https://unsplash.com/photos/a-uAE0SX91c/download?force=true" "${PROD_DIR}/spray_bottle.jpg"
download "https://unsplash.com/photos/Gnd_Xd7Go0w/download?force=true" "${PROD_DIR}/cleaning_bottle.jpg"
download "https://unsplash.com/photos/5rA4DRrEXU4/download?force=true" "${PROD_DIR}/paper_towels.jpg"
download "https://unsplash.com/photos/P6uXw3IWmxc/download?force=true" "${PROD_DIR}/bubble_wrap.jpg"
download "https://unsplash.com/photos/Oiagtt4idqU/download?force=true" "${PROD_DIR}/trash_bag.jpg"
download "https://unsplash.com/photos/O_g9VmqjWCI/download?force=true" "${PROD_DIR}/paper_cups.jpg"

echo "Done. Images saved in:"
echo "  ${CAT_DIR}"
echo "  ${PROD_DIR}"
