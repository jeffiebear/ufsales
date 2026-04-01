from odoo import models


class Website(models.Model):
    _inherit = "website"

    def _ufs_public_category_domain(self, parent=None):
        Category = self.env["product.public.category"]
        category_fields = Category._fields
        domain = [("ufsales_imported", "=", True)]
        if parent:
            domain.append(("parent_id", "=", parent.id))
        else:
            domain.append(("parent_id", "=", False))
        if "website_published" in category_fields:
            domain.append(("website_published", "=", True))
        elif "is_published" in category_fields:
            domain.append(("is_published", "=", True))
        return domain

    def _ufs_public_categories(self, parent=None):
        Category = self.env["product.public.category"].sudo().with_context(active_test=False)
        return Category.search(self._ufs_public_category_domain(parent=parent), order="sequence, name, id")

    def _ufs_category_to_node(self, category, depth=2):
        children = self.env["product.public.category"].sudo()
        if depth > 0:
            children = self._ufs_public_categories(parent=category)
        return {
            "category": category,
            "children": [self._ufs_category_to_node(child, depth=depth - 1) for child in children],
        }

    def _ufs_catalog_menu_tree(self):
        self.ensure_one()
        return [self._ufs_category_to_node(category, depth=2) for category in self._ufs_public_categories(parent=None)]

    def _ufs_catalog_browse_categories(self, category=None, search=""):
        self.ensure_one()
        Category = self.env["product.public.category"].sudo()
        if search:
            return Category.browse()
        if category:
            if not getattr(category, "ufsales_imported", False):
                return Category.browse()
            return self._ufs_public_categories(parent=category)
        return self._ufs_public_categories(parent=None)
