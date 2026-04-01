from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.http import request


class UfsalesWebsiteSale(WebsiteSale):
    def _get_additional_shop_values(self, values, **kwargs):
        additional_values = super()._get_additional_shop_values(values, **kwargs)
        category = values.get("category")
        search = values.get("search") or kwargs.get("search") or ""
        additional_values.update(
            {
                "ufs_shop_categories": request.website._ufs_catalog_browse_categories(
                    category=category,
                    search=search,
                ),
            }
        )
        return additional_values
