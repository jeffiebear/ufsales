# -*- coding: utf-8 -*-

import base64
from pathlib import Path

from odoo import api, models


class UfsalesCatalogSeedHelper(models.AbstractModel):
    _name = "ufsales.catalog.seed.helper"
    _description = "UF Sales Catalog Seed Helper"

    @api.model
    def _normalize_menu(self, menu, website, menu_fields):
        vals = {}
        if "is_visible" in menu_fields:
            vals["is_visible"] = True
        if "active" in menu_fields:
            vals["active"] = True
        if "website_id" in menu_fields:
            vals["website_id"] = website.id
        if vals:
            menu.write(vals)
        for group_field in ("group_ids", "groups_id", "visible_group_ids"):
            if group_field in menu_fields:
                menu.write({group_field: [(5, 0, 0)]})

    @api.model
    def _get_or_create_main_root_menu(self, website, menu_fields):
        Menu = self.env["website.menu"]
        domain = [("parent_id", "=", False), ("name", "=", "Main")]
        if "website_id" in menu_fields:
            domain.append(("website_id", "=", website.id))
        root_menu = Menu.search(domain, limit=1)
        if not root_menu:
            root_menu = website.menu_id
        if not root_menu:
            create_vals = {
                "name": "Main",
                "url": "#",
                "sequence": 60,
            }
            if "is_visible" in menu_fields:
                create_vals["is_visible"] = True
            if "website_id" in menu_fields:
                create_vals["website_id"] = website.id
            root_menu = Menu.create(create_vals)

        self._normalize_menu(root_menu, website, menu_fields)
        if website.menu_id != root_menu:
            website.menu_id = root_menu
        return root_menu

    @api.model
    def _ensure_core_menus(self):
        """Ensure each website has the requested top-level navigation entries."""
        websites = self.env["website"].search([])
        Menu = self.env["website.menu"]
        menu_fields = Menu._fields
        desired_entries = [
            ("Home", "/", 10),
            ("Shop", "/shop", 20),
            ("Tips & Trends", "/blog", 30),
            ("About Us", "/about-us", 40),
            ("Contact Us", "/contactus", 50),
            ("Thanks (Contact us)", "/contactus-thank-you", 60),
            ("Privacy Policy", "/privacy", 70),
        ]

        for website in websites:
            root_menu = self._get_or_create_main_root_menu(website, menu_fields)

            for name, url, sequence in desired_entries:
                matches = Menu.search([("parent_id", "=", root_menu.id), ("url", "=", url)])
                menu = matches[:1]
                if len(matches) > 1:
                    (matches - menu).unlink()

                if not menu:
                    create_vals = {
                        "name": name,
                        "parent_id": root_menu.id,
                        "url": url,
                        "sequence": sequence,
                    }
                    if "is_visible" in menu_fields:
                        create_vals["is_visible"] = True
                    if "website_id" in menu_fields:
                        create_vals["website_id"] = website.id
                    menu = Menu.create(create_vals)
                else:
                    menu.write({"name": name, "sequence": sequence})

                self._normalize_menu(menu, website, menu_fields)
        return True

    @api.model
    def cleanup_legacy_menus(self):
        """Remove previously seeded website menus from older module revisions."""
        imd = self.env["ir.model.data"].search(
            [
                ("module", "=", "ufsales_catalog_seed"),
                ("model", "=", "website.menu"),
                ("name", "like", "menu_uf_%"),
            ]
        )
        if imd:
            menus = self.env["website.menu"].browse(imd.mapped("res_id")).exists()
            if menus:
                menus.unlink()
            imd.unlink()

        # Defensive cleanup for previously created menu entries even if XMLIDs changed.
        legacy_names = [
            "Janitorial Supplies",
            "Soaps and Sanitizers",
            "Food Service",
            "Gloves and Safety",
            "Packaging",
            "Chemicals",
            "Cleaning Tools",
            "Paper Products",
            "Hand Soaps",
            "Sanitizers",
            "Dispensers",
            "Cups and Lids",
            "Takeout Containers",
            "Cutlery and Napkins",
            "Disposable Gloves",
            "Safety Gear",
            "Facility Safety",
            "Boxes",
            "Protective Wrap",
            "Mailers and Tape",
            "Bleach",
            "Degreasers",
            "Mops and Buckets",
            "Spray Bottles",
            "Trash Bags",
            "Paper Towels",
            "Toilet Tissue",
            "Foaming Soap",
            "Liquid Soap",
            "Gel Sanitizer",
            "Spray Sanitizer",
            "Wall Mounted",
            "Countertop",
            "Paper Cups",
            "Plastic Lids",
            "Clamshells",
            "Soup Containers",
            "Disposable Cutlery",
            "Dinner Napkins",
            "Nitrile Gloves",
            "Vinyl Gloves",
            "Safety Glasses",
            "Face Masks",
            "Wet Floor Signs",
            "First Aid",
            "Shipping Boxes",
            "Moving Boxes",
            "Bubble Wrap",
            "Stretch Film",
            "Poly Mailers",
            "Packing Tape",
        ]
        legacy_menus = self.env["website.menu"].search(
            [
                ("name", "in", legacy_names),
                ("url", "like", "/shop/category/%"),
            ]
        )
        if legacy_menus:
            legacy_menus.unlink()
        self._ensure_core_menus()
        return True

    @api.model
    def _load_module_image(self, relative_path):
        module_root = Path(__file__).resolve().parents[1]
        image_path = module_root / relative_path
        if not image_path.exists():
            return False
        with image_path.open("rb") as img_file:
            return base64.b64encode(img_file.read())

    @api.model
    def _set_product_publish_flag(self, vals):
        product_fields = self.env["product.template"]._fields
        if "website_published" in product_fields:
            vals["website_published"] = True
        elif "is_published" in product_fields:
            vals["is_published"] = True
        return vals

    @api.model
    def _upsert_template(self, product_data):
        ProductTemplate = self.env["product.template"].with_context(active_test=False)
        categ_ids = [self.env.ref(xmlid).id for xmlid in product_data["public_categ_xmlids"]]
        vals = {
            "name": product_data["name"],
            "default_code": product_data["default_code"],
            "list_price": product_data["list_price"],
            "sale_ok": True,
            "purchase_ok": True,
            "public_categ_ids": [(6, 0, categ_ids)],
            "image_1920": self._load_module_image(product_data["image"]),
        }
        vals = self._set_product_publish_flag(vals)

        template = ProductTemplate.search([("default_code", "=", product_data["default_code"])], limit=1)
        if template:
            template.write(vals)
        else:
            template = ProductTemplate.create(vals)
        return template

    @api.model
    def _ensure_attribute_line(self, template, attribute_xmlid, value_xmlids):
        attribute = self.env.ref(attribute_xmlid)
        value_ids = [self.env.ref(xmlid).id for xmlid in value_xmlids]
        line = template.attribute_line_ids.filtered(lambda l: l.attribute_id == attribute)
        if line:
            line.write({"value_ids": [(6, 0, value_ids)]})
        else:
            self.env["product.template.attribute.line"].create(
                {
                    "product_tmpl_id": template.id,
                    "attribute_id": attribute.id,
                    "value_ids": [(6, 0, value_ids)],
                }
            )

    @api.model
    def seed_sample_products(self):
        products = [
            {
                "name": "Spray Bottle 32 oz",
                "default_code": "UFS-SPRAY-32",
                "list_price": 4.99,
                "image": "static/src/img/products/spray_bottle.jpg",
                "public_categ_xmlids": ["ufsales_catalog_seed.ppc_janitorial_cleaning_tools_spray_bottles"],
            },
            {
                "name": "Multi-Surface Cleaner 1L",
                "default_code": "UFS-CLEAN-1L",
                "list_price": 8.49,
                "image": "static/src/img/products/cleaning_bottle.jpg",
                "public_categ_xmlids": ["ufsales_catalog_seed.ppc_janitorial_chemicals_degreasers"],
            },
            {
                "name": "Paper Towels - 24 Roll Case",
                "default_code": "UFS-PTOWL-24",
                "list_price": 29.99,
                "image": "static/src/img/products/paper_towels.jpg",
                "public_categ_xmlids": ["ufsales_catalog_seed.ppc_janitorial_paper_products_paper_towels"],
            },
            {
                "name": "Bubble Wrap Roll 12 in x 175 ft",
                "default_code": "UFS-BWRAP-12175",
                "list_price": 21.95,
                "image": "static/src/img/products/bubble_wrap.jpg",
                "public_categ_xmlids": ["ufsales_catalog_seed.ppc_packaging_protective_wrap_bubble_wrap"],
            },
            {
                "name": "Heavy Duty Trash Bags 55 gal (50 ct)",
                "default_code": "UFS-TRASH-55",
                "list_price": 32.50,
                "image": "static/src/img/products/trash_bag.jpg",
                "public_categ_xmlids": ["ufsales_catalog_seed.ppc_janitorial_cleaning_tools_trash_bags"],
            },
            {
                "name": "Paper Cups 12 oz (100 ct)",
                "default_code": "UFS-PCUP-12-100",
                "list_price": 10.99,
                "image": "static/src/img/products/paper_cups.jpg",
                "public_categ_xmlids": ["ufsales_catalog_seed.ppc_food_service_cups_lids_paper_cups"],
            },
            {
                "name": "Nitrile Gloves Powder-Free",
                "default_code": "UFS-NGLOVE",
                "list_price": 15.75,
                "image": "static/src/img/products/cleaning_bottle.jpg",
                "public_categ_xmlids": ["ufsales_catalog_seed.ppc_gloves_safety_disposable_gloves_nitrile_gloves"],
            },
            {
                "name": "Shipping Box 16 x 12 x 10 in",
                "default_code": "UFS-BOX-161210",
                "list_price": 3.75,
                "image": "static/src/img/products/bubble_wrap.jpg",
                "public_categ_xmlids": ["ufsales_catalog_seed.ppc_packaging_boxes_shipping_boxes"],
            },
            {
                "name": "Foaming Hand Soap 1 Gallon",
                "default_code": "UFS-FSOAP-1G",
                "list_price": 13.40,
                "image": "static/src/img/products/cleaning_bottle.jpg",
                "public_categ_xmlids": ["ufsales_catalog_seed.ppc_soaps_hand_soaps_foaming"],
            },
            {
                "name": "Packing Tape Clear 2 in x 110 yd",
                "default_code": "UFS-TAPE-2110",
                "list_price": 2.25,
                "image": "static/src/img/products/bubble_wrap.jpg",
                "public_categ_xmlids": ["ufsales_catalog_seed.ppc_packaging_mailers_tape_packing_tape"],
            },
        ]

        templates = {}
        for product_data in products:
            templates[product_data["default_code"]] = self._upsert_template(product_data)

        self._ensure_attribute_line(
            templates["UFS-NGLOVE"],
            "ufsales_catalog_seed.attr_size",
            [
                "ufsales_catalog_seed.attr_size_s",
                "ufsales_catalog_seed.attr_size_m",
                "ufsales_catalog_seed.attr_size_l",
                "ufsales_catalog_seed.attr_size_xl",
            ],
        )
        self._ensure_attribute_line(
            templates["UFS-BOX-161210"],
            "ufsales_catalog_seed.attr_pack",
            [
                "ufsales_catalog_seed.attr_pack_single",
                "ufsales_catalog_seed.attr_pack_case_25",
            ],
        )
        return True
