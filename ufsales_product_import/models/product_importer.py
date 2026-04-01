import base64
import html
import json
import logging
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.modules.module import get_module_path
from odoo.tools import config, html2plaintext

_logger = logging.getLogger(__name__)

_DEFAULT_IMAGE_MARKERS = ("default_product.jpg",)
_DEFAULT_JSON_PATH = "/Applications/MAMP/htdocs/UFS/UFS/ufsales/ufsales_products.json"
_UOM_LABELS = {
    "BG": "Bag",
    "BN": "Bundle",
    "BX": "Box",
    "CASE": "Case",
    "CN": "Can",
    "CS": "Case",
    "CTN": "Carton",
    "DOZ": "Dozen",
    "DZ": "Dozen",
    "EA": "Each",
    "EACH": "Each",
    "PAIL": "Pail",
    "PK": "Pack",
    "QT": "Quart",
    "RL": "Roll",
    "ROLL": "Roll",
}


class ProductCategory(models.Model):
    _inherit = "product.category"

    ufsales_imported = fields.Boolean(copy=False, index=True)
    ufsales_source_path = fields.Char(copy=False, index=True)


class ProductPublicCategory(models.Model):
    _inherit = "product.public.category"

    ufsales_imported = fields.Boolean(copy=False, index=True)
    ufsales_source_path = fields.Char(copy=False, index=True)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    ufsales_imported = fields.Boolean(copy=False, index=True)
    ufsales_item_attributes = fields.Char(copy=False)
    ufsales_manufacturer_item_no = fields.Char(copy=False)
    ufsales_raw_price = fields.Char(copy=False)
    ufsales_resource_payload = fields.Text(copy=False)
    ufsales_source_description_html = fields.Html(copy=False, sanitize=False)
    ufsales_source_highlights_html = fields.Html(copy=False, sanitize=False)
    ufsales_source_uom_code = fields.Char(copy=False)
    ufsales_source_url = fields.Char(copy=False)


class ProductImage(models.Model):
    _inherit = "product.image"

    ufsales_imported = fields.Boolean(copy=False, index=True)
    ufsales_source_url = fields.Char(copy=False, index=True)
    ufsales_source_zoom_url = fields.Char(copy=False)


class UfsalesProductImporter(models.AbstractModel):
    _name = "ufsales.product.importer"
    _description = "UF Sales Product Importer"

    @api.model
    def _candidate_json_paths(self):
        filename = "ufsales_products.json"
        configured_path = self.env["ir.config_parameter"].sudo().get_param("ufsales_product_import.json_path")
        candidate_paths = []

        if configured_path:
            candidate_paths.append(Path(configured_path).expanduser())

        module_path = get_module_path("ufsales_product_import", display_warning=False)
        search_roots = []
        if module_path:
            module_dir = Path(module_path).resolve()
            candidate_paths.append(module_dir / "data" / filename)
            candidate_paths.append(module_dir / filename)
            search_roots.extend([module_dir, *module_dir.parents[:4]])

        cwd = os.getcwd()
        if cwd:
            search_roots.append(Path(cwd).resolve())

        addons_path = config.get("addons_path") or []
        if isinstance(addons_path, str):
            addons_paths = addons_path.split(",")
        elif isinstance(addons_path, (list, tuple, set)):
            addons_paths = addons_path
        else:
            addons_paths = [addons_path]

        for raw_path in addons_paths:
            raw_path = str(raw_path)
            raw_path = raw_path.strip()
            if not raw_path:
                continue
            addons_dir = Path(raw_path).expanduser().resolve()
            search_roots.extend([addons_dir, addons_dir.parent])

        search_roots.append(Path(_DEFAULT_JSON_PATH).parent)

        seen = set()
        for root in search_roots:
            if not root:
                continue
            for candidate in (root / filename, root / "ufsales" / filename):
                try:
                    resolved = candidate.resolve()
                except FileNotFoundError:
                    resolved = candidate
                key = str(resolved)
                if key in seen:
                    continue
                seen.add(key)
                candidate_paths.append(resolved)

        candidate_paths.append(Path(_DEFAULT_JSON_PATH))
        return candidate_paths

    @api.model
    def _get_json_path(self):
        candidate_paths = self._candidate_json_paths()
        for candidate in candidate_paths:
            if candidate and candidate.exists():
                return candidate
        searched = "\n".join("- %s" % path for path in candidate_paths if path)
        raise UserError(
            "UF Sales source JSON was not found. Set the system parameter "
            "'ufsales_product_import.json_path' or place ufsales_products.json "
            "next to the custom addons.\nSearched:\n%s" % searched
        )

    @api.model
    def _load_source_rows(self):
        json_path = self._get_json_path()
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise UserError("UF Sales source JSON is invalid: %s" % exc) from exc
        if not isinstance(payload, list):
            raise UserError("UF Sales source JSON must contain a list of product records.")
        return payload

    @api.model
    def _category_source_key(self, segments):
        return " / ".join(segment for segment in segments if segment)

    @api.model
    def _set_publish_flag(self, fields_map, vals):
        if "website_published" in fields_map:
            vals["website_published"] = True
        elif "is_published" in fields_map:
            vals["is_published"] = True
        return vals

    @api.model
    def _set_website_description(self, product_fields, vals, html_body):
        if not html_body:
            return vals
        if "description_ecommerce" in product_fields:
            vals["description_ecommerce"] = html_body
        elif "website_description" in product_fields:
            vals["website_description"] = html_body
        return vals

    @api.model
    def _set_product_type(self, product_fields, vals):
        if "detailed_type" in product_fields:
            vals["detailed_type"] = "consu"
        elif "type" in product_fields:
            vals["type"] = "consu"
        return vals

    @api.model
    def _set_uom_fields(self, product_fields, vals, uom):
        if "uom_id" in product_fields:
            vals["uom_id"] = uom.id
        if "uom_po_id" in product_fields:
            vals["uom_po_id"] = uom.id
        elif "purchase_uom_id" in product_fields:
            vals["purchase_uom_id"] = uom.id
        return vals

    @api.model
    def _ensure_uom(self, source_code, stats):
        code = (source_code or "EACH").strip().upper()
        Uom = self.env["uom.uom"].sudo().with_context(active_test=False)

        reference_uom = self.env.ref("uom.product_uom_unit", raise_if_not_found=False)
        if not reference_uom:
            reference_uom = Uom.search(
                [
                    ("relative_uom_id", "=", False),
                    ("name", "in", ["Units", "Unit", "Each"]),
                ],
                order="id",
                limit=1,
            )
        if not reference_uom:
            reference_uom = Uom.create(
                {
                    "name": "Each",
                    "relative_factor": 1.0,
                }
            )
            stats["uoms_created"] += 1

        if code in ("EA", "EACH", ""):
            return reference_uom

        uom_name = _UOM_LABELS.get(code, code)
        uom = Uom.search(
            [
                ("name", "=", uom_name),
                ("relative_uom_id", "=", reference_uom.id),
            ],
            limit=1,
        )
        if uom:
            return uom

        uom = Uom.create(
            {
                "name": uom_name,
                "relative_uom_id": reference_uom.id,
                "relative_factor": 1.0,
            }
        )
        stats["uoms_created"] += 1
        return uom

    @api.model
    def _ensure_category_path(self, model_name, category_path, cache, stats):
        Category = self.env[model_name].sudo().with_context(active_test=False)
        category_fields = Category._fields
        path_nodes = Category.browse()
        parent = Category.browse()
        current_segments = []

        for raw_name in category_path or []:
            category_name = (raw_name or "").strip()
            if not category_name:
                continue

            current_segments.append(category_name)
            source_key = self._category_source_key(current_segments)
            category = cache.get(source_key)
            if category:
                parent = category
                path_nodes |= category
                continue

            category = Category.search([("ufsales_source_path", "=", source_key)], limit=1)
            if not category:
                category = Category.search(
                    [
                        ("name", "=", category_name),
                        ("parent_id", "=", parent.id or False),
                    ],
                    limit=1,
                )

            vals = {
                "name": category_name,
                "ufsales_imported": True,
                "ufsales_source_path": source_key,
            }
            if "active" in category_fields:
                vals["active"] = True
            if "parent_id" in category_fields and parent:
                vals["parent_id"] = parent.id
            vals = self._set_publish_flag(category_fields, vals)

            if category:
                category.write(vals)
                stats["categories_updated"] += 1
            else:
                category = Category.create(vals)
                stats["categories_created"] += 1

            cache[source_key] = category
            parent = category
            path_nodes |= category

        return path_nodes

    @api.model
    def _build_description_html(self, row):
        parts = []
        highlights_html = row.get("highlights_html")
        description_html = row.get("description_html")
        resources = row.get("resources") or []

        if highlights_html:
            parts.append("<section><h2>Highlights</h2>%s</section>" % highlights_html)
        if description_html:
            parts.append("<section><h2>Description</h2>%s</section>" % description_html)
        if resources:
            links = []
            for resource in resources:
                url = (resource or {}).get("url")
                if not url:
                    continue
                label = (resource or {}).get("label") or url
                links.append(
                    '<li><a href="%s" target="_blank" rel="noopener noreferrer">%s</a></li>'
                    % (html.escape(url, quote=True), html.escape(label))
                )
            if links:
                parts.append("<section><h2>Resources</h2><ul>%s</ul></section>" % "".join(links))
        return "".join(parts)

    @api.model
    def _fetch_image(self, url):
        if not url or any(marker in url for marker in _DEFAULT_IMAGE_MARKERS):
            return False
        request = Request(url, headers={"User-Agent": "UF Sales Odoo Importer/1.0"})
        try:
            with urlopen(request, timeout=20) as response:
                return base64.b64encode(response.read())
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            _logger.warning("UF Sales image fetch failed for %s: %s", url, exc)
        return False

    @api.model
    def _sync_product_images(self, template, images):
        ProductImage = self.env["product.image"].sudo().with_context(active_test=False)
        image_fields = ProductImage._fields
        binary_field = "image_1920" if "image_1920" in image_fields else "image"
        product_field = "product_tmpl_id" if "product_tmpl_id" in image_fields else "product_template_id"

        usable_images = [img for img in images or [] if (img or {}).get("image_url")]
        usable_images = [
            img
            for img in usable_images
            if not any(marker in img.get("image_url", "") for marker in _DEFAULT_IMAGE_MARKERS)
        ]

        primary_image = usable_images[:1]
        if primary_image:
            primary_payload = self._fetch_image(primary_image[0].get("zoom_url") or primary_image[0].get("image_url"))
            if primary_payload:
                template.write({"image_1920": primary_payload})

        existing_images = ProductImage.search(
            [
                (product_field, "=", template.id),
                ("ufsales_imported", "=", True),
            ]
        )
        existing_by_url = {image.ufsales_source_url: image for image in existing_images if image.ufsales_source_url}
        keep_images = ProductImage.browse()

        for index, image_entry in enumerate(usable_images[1:], start=2):
            source_url = image_entry.get("image_url")
            zoom_url = image_entry.get("zoom_url")
            image_payload = self._fetch_image(zoom_url or source_url)
            existing_image = existing_by_url.get(source_url)

            vals = {
                "name": "%s Image %s" % (template.name, index),
                product_field: template.id,
                "ufsales_imported": True,
                "ufsales_source_url": source_url,
                "ufsales_source_zoom_url": zoom_url,
            }
            if image_payload:
                vals[binary_field] = image_payload

            if existing_image:
                existing_image.write(vals)
                keep_images |= existing_image
            elif image_payload:
                keep_images |= ProductImage.create(vals)

        stale_images = existing_images - keep_images
        if stale_images:
            stale_images.unlink()

    @api.model
    def _upsert_product(self, row, internal_categories, public_categories, sequence, stats):
        ProductTemplate = self.env["product.template"].sudo().with_context(active_test=False)
        product_fields = ProductTemplate._fields
        sku = (row.get("item_number") or "").strip()
        if not sku:
            _logger.warning("Skipping product without item_number: %s", row.get("name"))
            return

        description_html = self._build_description_html(row)
        description_plain = html2plaintext(description_html).strip() if description_html else False
        uom = self._ensure_uom(row.get("uom"), stats)

        vals = {
            "name": (row.get("name") or sku).strip(),
            "default_code": sku,
            "list_price": float(row.get("price") or 0.0),
            "sale_ok": True,
            "purchase_ok": True,
            "ufsales_imported": True,
            "ufsales_item_attributes": row.get("item_attributes") or False,
            "ufsales_manufacturer_item_no": row.get("manufacturer_item_no") or False,
            "ufsales_raw_price": row.get("raw_price") or False,
            "ufsales_resource_payload": json.dumps(row.get("resources") or [], ensure_ascii=False, indent=2),
            "ufsales_source_description_html": row.get("description_html") or False,
            "ufsales_source_highlights_html": row.get("highlights_html") or False,
            "ufsales_source_uom_code": row.get("uom") or False,
            "ufsales_source_url": row.get("source_url") or False,
        }
        if internal_categories:
            vals["categ_id"] = internal_categories[-1].id
        if public_categories:
            vals["public_categ_ids"] = [(6, 0, public_categories.ids)]
        if "description_sale" in product_fields and description_plain:
            vals["description_sale"] = description_plain
        if "website_sequence" in product_fields:
            vals["website_sequence"] = sequence

        vals = self._set_product_type(product_fields, vals)
        vals = self._set_uom_fields(product_fields, vals, uom)
        vals = self._set_publish_flag(product_fields, vals)
        vals = self._set_website_description(product_fields, vals, description_html)

        template = ProductTemplate.search([("default_code", "=", sku)], limit=1)
        if template:
            template.write(vals)
            stats["products_updated"] += 1
        else:
            template = ProductTemplate.create(vals)
            stats["products_created"] += 1

        self._sync_product_images(template, row.get("images") or [])

    @api.model
    def run_import(self):
        rows = self._load_source_rows()
        stats = {
            "categories_created": 0,
            "categories_updated": 0,
            "products_created": 0,
            "products_updated": 0,
            "uoms_created": 0,
        }
        internal_cache = {}
        public_cache = {}

        for sequence, row in enumerate(rows, start=1):
            category_path = row.get("category_path") or []
            internal_categories = self._ensure_category_path(
                "product.category",
                category_path,
                internal_cache,
                stats,
            )
            public_categories = self._ensure_category_path(
                "product.public.category",
                category_path,
                public_cache,
                stats,
            )
            self._upsert_product(
                row=row,
                internal_categories=internal_categories,
                public_categories=public_categories,
                sequence=sequence,
                stats=stats,
            )

        _logger.info(
            "UF Sales import finished: %s created / %s updated products, "
            "%s created / %s updated categories, %s UoMs created.",
            stats["products_created"],
            stats["products_updated"],
            stats["categories_created"],
            stats["categories_updated"],
            stats["uoms_created"],
        )
        return stats
