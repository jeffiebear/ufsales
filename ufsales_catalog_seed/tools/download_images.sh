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

# Category images (royalty-free demo photos)
download "https://picsum.photos/seed/uf-category-janitorial/1600/1000" "${CAT_DIR}/janitorial.jpg"
download "https://picsum.photos/seed/uf-category-soaps/1600/1000" "${CAT_DIR}/soaps.jpg"
download "https://picsum.photos/seed/uf-category-food-service/1600/1000" "${CAT_DIR}/food_service.jpg"
download "https://picsum.photos/seed/uf-category-gloves-safety/1600/1000" "${CAT_DIR}/gloves_safety.jpg"
download "https://picsum.photos/seed/uf-category-packaging/1600/1000" "${CAT_DIR}/packaging.jpg"

# Product images (royalty-free demo photos)
download "https://picsum.photos/seed/uf-product-spray-bottle/1200/900" "${PROD_DIR}/spray_bottle.jpg"
download "https://picsum.photos/seed/uf-product-cleaning-bottle/1200/900" "${PROD_DIR}/cleaning_bottle.jpg"
download "https://picsum.photos/seed/uf-product-paper-towels/1200/900" "${PROD_DIR}/paper_towels.jpg"
download "https://picsum.photos/seed/uf-product-bubble-wrap/1200/900" "${PROD_DIR}/bubble_wrap.jpg"
download "https://picsum.photos/seed/uf-product-trash-bag/1200/900" "${PROD_DIR}/trash_bag.jpg"
download "https://picsum.photos/seed/uf-product-paper-cups/1200/900" "${PROD_DIR}/paper_cups.jpg"

echo "Done. Images saved in:"
echo "  ${CAT_DIR}"
echo "  ${PROD_DIR}"
