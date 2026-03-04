# -*- coding: utf-8 -*-

from urllib.parse import quote

from odoo import _, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.addons.website_sale.controllers.cart import Cart as WebsiteSaleCart
from odoo.addons.website_sale.controllers.main import WebsiteSale as WebsiteSaleMain
from odoo.addons.website_sale.controllers.payment import PaymentPortal as WebsiteSalePaymentPortal


class UfsWholesaleAccessMixin:
    def _ufs_wholesale_can_buy(self):
        user = request.env.user
        return bool(user and not user._is_public() and user._ufs_has_wholesale_access())

    def _ufs_wholesale_block_message(self):
        return _("Pricing and checkout are available only to approved wholesale customers.")

    def _ufs_wholesale_redirect(self):
        if request.env.user._is_public():
            target = request.httprequest.path or "/shop"
            return request.redirect("/web/login?redirect=%s" % quote(target, safe=""))
        return request.redirect("/shop")

    def _ufs_wholesale_json_block(self):
        return {
            "cart_quantity": request.session.get("website_sale_cart_quantity", 0),
            "notification_info": {"warning": self._ufs_wholesale_block_message()},
            "quantity": 0,
            "tracking_info": [],
        }


class Cart(UfsWholesaleAccessMixin, WebsiteSaleCart):
    @http.route(route="/shop/cart", type="http", auth="public", website=True, sitemap=False)
    def cart(self, id=None, access_token=None, revive_method="", **post):
        if not self._ufs_wholesale_can_buy():
            return self._ufs_wholesale_redirect()
        return super().cart(id=id, access_token=access_token, revive_method=revive_method, **post)

    @http.route(
        route="/shop/cart/add",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        website=True,
        sitemap=False,
    )
    def add_to_cart(
        self,
        product_template_id,
        product_id,
        quantity=1.0,
        uom_id=None,
        product_custom_attribute_values=None,
        no_variant_attribute_value_ids=None,
        linked_products=None,
        **kwargs
    ):
        if not self._ufs_wholesale_can_buy():
            return self._ufs_wholesale_json_block()
        return super().add_to_cart(
            product_template_id=product_template_id,
            product_id=product_id,
            quantity=quantity,
            uom_id=uom_id,
            product_custom_attribute_values=product_custom_attribute_values,
            no_variant_attribute_value_ids=no_variant_attribute_value_ids,
            linked_products=linked_products,
            **kwargs
        )

    @http.route(
        route="/shop/cart/quick_add",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
        website=True,
    )
    def quick_add(self, product_template_id, product_id, quantity=1.0, **kwargs):
        if not self._ufs_wholesale_can_buy():
            return self._ufs_wholesale_json_block()
        return super().quick_add(product_template_id=product_template_id, product_id=product_id, quantity=quantity, **kwargs)

    @http.route(
        route="/shop/cart/update",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        website=True,
        sitemap=False,
    )
    def update_cart(self, line_id, quantity, product_id=None, **kwargs):
        if not self._ufs_wholesale_can_buy():
            raise UserError(self._ufs_wholesale_block_message())
        return super().update_cart(line_id=line_id, quantity=quantity, product_id=product_id, **kwargs)

    @http.route(route="/shop/cart/clear", type="jsonrpc", auth="public", website=True)
    def clear_cart(self):
        if not self._ufs_wholesale_can_buy():
            raise UserError(self._ufs_wholesale_block_message())
        return super().clear_cart()


class WebsiteSale(UfsWholesaleAccessMixin, WebsiteSaleMain):
    @http.route(
        ["/shop/product/is_add_to_cart_allowed"],
        type="jsonrpc",
        auth="public",
        website=True,
        readonly=True,
    )
    def is_add_to_cart_allowed(self, product_id, **kwargs):
        if not self._ufs_wholesale_can_buy():
            return False
        return super().is_add_to_cart_allowed(product_id, **kwargs)

    def _check_cart(self, order_sudo):
        if not self._ufs_wholesale_can_buy():
            return self._ufs_wholesale_redirect()
        return super()._check_cart(order_sudo)

    @http.route(
        WebsiteSaleMain._express_checkout_route,
        type="jsonrpc",
        methods=["POST"],
        auth="public",
        website=True,
        sitemap=False,
    )
    def process_express_checkout(self, billing_address, shipping_address=None, shipping_option=None, **kwargs):
        if not self._ufs_wholesale_can_buy():
            raise UserError(self._ufs_wholesale_block_message())
        return super().process_express_checkout(
            billing_address=billing_address,
            shipping_address=shipping_address,
            shipping_option=shipping_option,
            **kwargs
        )

    @http.route(
        WebsiteSaleMain._express_checkout_delivery_route + "/compute_taxes",
        type="jsonrpc",
        auth="public",
        website=True,
        sitemap=False,
    )
    def express_checkout_shipping_address_compute_taxes(self):
        if not self._ufs_wholesale_can_buy():
            raise UserError(self._ufs_wholesale_block_message())
        return super().express_checkout_shipping_address_compute_taxes()

    @http.route("/shop/update_address", type="jsonrpc", auth="public", website=True)
    def shop_update_address(self, partner_id, address_type="billing", **kw):
        if not self._ufs_wholesale_can_buy():
            raise UserError(self._ufs_wholesale_block_message())
        return super().shop_update_address(partner_id=partner_id, address_type=address_type, **kw)


class PaymentPortal(UfsWholesaleAccessMixin, WebsiteSalePaymentPortal):
    @http.route("/shop/payment/transaction/<int:order_id>", type="jsonrpc", auth="public", website=True)
    def shop_payment_transaction(self, order_id, access_token, **kwargs):
        if not self._ufs_wholesale_can_buy():
            raise ValidationError(self._ufs_wholesale_block_message())
        return super().shop_payment_transaction(order_id=order_id, access_token=access_token, **kwargs)

