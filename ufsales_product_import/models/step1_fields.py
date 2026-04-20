# -*- coding: utf-8 -*-
"""Field extensions that carry STEP1 legacy identifiers.

Kept small and free of business logic — the actual importers live in
`step1_csv_importer.py`.
"""
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    ufs_step1_vendor_acct = fields.Char(
        string="STEP1 Vendor Acct", index=True, copy=False,
        help="Legacy STEP1 VendorAcct. Used as the import key for vendors.",
    )
    ufs_step1_vendor_id = fields.Char(
        string="STEP1 Vendor ID", index=True, copy=False,
    )
    ufs_vendor_group_code = fields.Char(
        string="Vendor Group Code", copy=False,
    )
    ufs_carrier = fields.Char(string="Default Carrier", copy=False)

    # Customer-side STEP1 identifiers (paired with ufs_customer_pricing's
    # ufs_step1_cust_acct / ufs_default_price_opt).
    ufs_step1_cust_id = fields.Char(string="STEP1 CustID", index=True, copy=False)
    ufs_cust_status = fields.Char(string="STEP1 CustStatus", copy=False)
    ufs_sman_code = fields.Char(string="Salesman Code", copy=False, index=True)
    ufs_sman_name = fields.Char(string="Salesman Name", copy=False)
    ufs_branch_code = fields.Char(string="Branch Code", copy=False)
    ufs_market_group = fields.Char(string="Market Group", copy=False)
    ufs_pricing_class = fields.Char(string="Pricing Class", copy=False, index=True)
    ufs_sales_class = fields.Char(string="Customer Sales Class", copy=False)
    ufs_fob = fields.Char(string="FOB", copy=False)
    ufs_frt_ppd_collect = fields.Char(string="Freight Prepaid/Collect", copy=False)
    ufs_warehouse_code = fields.Char(string="Preferred WHCode", copy=False)
    ufs_resale_tax_num = fields.Char(string="Resale Tax Number", copy=False)
    ufs_po_required = fields.Boolean(string="PO Required", copy=False)
    ufs_blanket_po = fields.Char(string="Blanket PO", copy=False)
    ufs_key_customer = fields.Boolean(string="Key Customer", copy=False)
    ufs_terms_text = fields.Char(string="Payment Terms (legacy)", copy=False)
    ufs_comments = fields.Text(string="STEP1 Customer Comments", copy=False)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    ufs_step1_item_id = fields.Char(
        string="STEP1 ItemID", index=True, copy=False,
    )
    ufs_bin_number = fields.Char(string="Bin Number", copy=False)
    ufs_stock_class = fields.Char(string="Stock Class", copy=False, index=True)
    ufs_sales_class_code = fields.Char(
        string="Sales Class (Item)", copy=False, index=True,
    )
    ufs_price_unit = fields.Char(string="Price Unit (legacy)", copy=False)
    ufs_stock_unit = fields.Char(string="Stock Unit (legacy)", copy=False)
    ufs_purch_unit = fields.Char(string="Purchase Unit (legacy)", copy=False)
    ufs_msds_code = fields.Char(string="MSDS Code", copy=False)
    ufs_hazmat_code = fields.Char(string="HazMat Code", copy=False)
    ufs_hazmat = fields.Boolean(string="Hazardous Material", copy=False)
    ufs_is_obsolete = fields.Boolean(string="STEP1 Obsolete", copy=False)


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    ufs_step1_wh_code = fields.Char(
        string="STEP1 WH Code", index=True, copy=False,
    )
