# -*- coding: utf-8 -*-
import base64
import csv
import io
import logging
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..models.ufs_price_rule import parse_step1_price_opt

_logger = logging.getLogger(__name__)


# STEP1 CPPriceOpt → internal rule_type. CPPriceOpt is the authoritative
# type letter on the CustomerPriceRule row; the magnitude is stored in
# CPPricePct (P/M), CPPriceBrkt (B), or CPSpecialPrice (S). The legacy
# PriceOpt column is unreliable — some rows carry a raw numeric price.
_CP_TYPE_MAP = {
    'S': 'special',
    'P': 'margin',
    'M': 'markup',
    'B': 'bracket',
}


def _resolve_rule_from_cp(cp_price_opt, cp_pct, cp_brkt, cp_special, price_opt):
    """Return (rule_type, pct, brkt, special) from the CP-* columns.

    Falls back to parse_step1_price_opt(price_opt) only when CPPriceOpt
    is empty or unrecognised."""
    letter = (cp_price_opt or '').strip().upper()[:1]
    rt = _CP_TYPE_MAP.get(letter)
    if rt == 'special':
        return ('special', 0.0, 0, cp_special)
    if rt == 'margin':
        return ('margin', cp_pct, 0, 0.0)
    if rt == 'markup':
        return ('markup', cp_pct, 0, 0.0)
    if rt == 'bracket':
        return ('bracket', 0.0, int(cp_brkt or 0), 0.0)
    # CPPriceOpt blank/unknown — fall back to the PriceOpt code if any.
    fb_type, fb_num = parse_step1_price_opt(price_opt)
    return (
        fb_type,
        fb_num if fb_type in ('margin', 'markup') else 0.0,
        int(fb_num) if fb_type == 'bracket' and fb_num else 0,
        0.0,
    )


def _to_date(s):
    s = (s or '').strip()
    if not s:
        return False
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return False


def _to_float(s):
    s = (s or '').strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _yesno(s):
    return (s or '').strip().upper() in ('Y', 'YES', 'TRUE', '1')


class UfsPriceRuleImport(models.TransientModel):
    _name = 'ufs.price.rule.import'
    _description = 'Import STEP1 Customer Price Rules'

    csv_file = fields.Binary(string='STEP1 Export CSV', required=True)
    csv_filename = fields.Char(string='File Name')
    create_missing_customers = fields.Boolean(
        string='Create Missing Customers', default=False,
        help="If a CustAcct in the file isn't found, create a stub customer. "
             "Otherwise the row is skipped and reported.",
    )
    create_missing_products = fields.Boolean(
        string='Create Missing Products', default=False,
        help="If an ItemCode in the file isn't found, create a stub product. "
             "Otherwise the row is skipped and reported.",
    )
    delete_existing = fields.Boolean(
        string='Replace Existing Imported Rules', default=False,
        help="Before importing, delete all rules previously imported from "
             "STEP1 (step1_imported = True). Use for clean re-imports.",
    )

    log = fields.Text(string='Import Log', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
    ], default='draft')

    # ---- Action ---------------------------------------------------------
    def action_import(self):
        self.ensure_one()
        if not self.csv_file:
            raise UserError(_("Please attach the STEP1 export CSV first."))

        raw = base64.b64decode(self.csv_file)
        # Many STEP1 exports come back as cp1252 / latin-1
        for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise UserError(_("Could not decode the CSV file."))

        reader = csv.DictReader(io.StringIO(text))
        if 'CustAcct' not in (reader.fieldnames or []):
            raise UserError(_(
                "This doesn't look like a STEP1 CustomerPriceRules export "
                "(no CustAcct column found)."
            ))

        if self.delete_existing:
            self.env['ufs.price.rule'].search([
                ('step1_imported', '=', True),
            ]).unlink()

        Partner = self.env['res.partner']
        Product = self.env['product.product']
        Rule = self.env['ufs.price.rule']

        # Pre-cache lookups
        partner_by_acct = {
            p.ufs_step1_cust_acct: p for p in Partner.search([
                ('ufs_step1_cust_acct', '!=', False)
            ])
        }
        product_by_code = {
            p.product_tmpl_id.ufs_step1_item_code: p for p in Product.search([
                ('product_tmpl_id.ufs_step1_item_code', '!=', False)
            ])
        }

        created = updated = skipped_cust = skipped_prod = errors = 0
        msgs = []

        for line_no, row in enumerate(reader, start=2):  # 1 = header
            try:
                acct = (row.get('CustAcct') or '').strip()
                # STEP1 prefixes inactive/flagged accounts with '*'.
                # Lookup first by the raw value, then fall back to the
                # unstarred version so those rows aren't lost.
                code = (row.get('ItemCode') or '').strip()
                if not acct or not code:
                    continue

                partner = partner_by_acct.get(acct)
                if not partner and acct.startswith('*'):
                    partner = partner_by_acct.get(acct.lstrip('*'))
                if not partner:
                    if self.create_missing_customers:
                        partner = Partner.create({
                            'name': (row.get('CustomerName') or acct).strip(),
                            'ufs_step1_cust_acct': acct,
                            'customer_rank': 1,
                            'company_type': 'company',
                        })
                        partner_by_acct[acct] = partner
                    else:
                        skipped_cust += 1
                        continue

                product = product_by_code.get(code)
                if not product:
                    if self.create_missing_products:
                        tmpl = self.env['product.template'].create({
                            'name': (row.get('ItemDescription') or code).strip(),
                            'ufs_step1_item_code': code,
                            'list_price': _to_float(row.get('ListPrice')),
                            'standard_price': _to_float(row.get('CurRebateCost')),
                            'type': 'consu',
                        })
                        product = tmpl.product_variant_id
                        product_by_code[code] = product
                    else:
                        skipped_prod += 1
                        continue

                # Pricing scheme: CPPriceOpt is authoritative for the type;
                # magnitude comes from CPPricePct / CPPriceBrkt /
                # CPSpecialPrice depending on the type. The legacy PriceOpt
                # column is used only as a fallback when CPPriceOpt is blank.
                price_opt_raw = (row.get('PriceOpt') or '').strip()
                cp_price_opt = (row.get('CPPriceOpt') or '').strip()
                rule_type, pct, brkt, special = _resolve_rule_from_cp(
                    cp_price_opt,
                    _to_float(row.get('CPPricePct')),
                    _to_float(row.get('CPPriceBrkt')),
                    _to_float(row.get('CPSpecialPrice')),
                    price_opt_raw,
                )

                vals = {
                    'partner_id': partner.id,
                    'product_id': product.id,
                    'rule_type': rule_type,
                    'special_price': special,
                    'margin_pct': pct if rule_type == 'margin' else 0.0,
                    'markup_pct': pct if rule_type == 'markup' else 0.0,
                    'bracket_no': brkt,
                    'step1_price_opt': price_opt_raw,
                    'step1_cp_price_opt': cp_price_opt,
                    'step1_imported': True,
                    'list_price_at_import': _to_float(row.get('ListPrice')),
                    'current_price_at_import': _to_float(row.get('CurrentPrice')),
                    'last_price_paid': _to_float(row.get('LastPricePaid')),
                    'last_qty_ordered': _to_float(row.get('LastQtyOrdered')),
                    'first_sale_date': _to_date(row.get('FirstSaleDate')),
                    'last_sale_date': _to_date(row.get('LastSaleDate')),
                    'next_sale_date': _to_date(row.get('NextSaleDate')),
                    'notes_date': _to_date(row.get('CPNotesDate')),
                    'note1': (row.get('CPNotes1') or '').strip() or False,
                    'note2': (row.get('CPNotes2') or '').strip() or False,
                    'note3': (row.get('CPNotes3') or '').strip() or False,
                    'notes_add_to_order': _yesno(row.get('CPNotesAddToOrder')),
                    'print_on_order_form': _yesno(row.get('CPPrintOnOrderForm')),
                    'customer_part_num': (row.get('CustomerPartNum') or '').strip() or False,
                    'sales_class': (row.get('SalesClass') or '').strip() or False,
                    'tax_flag': _yesno(row.get('CPTaxFlag')),
                    'commission_flag': _yesno(row.get('CPComFlag')),
                }

                # Upsert by (partner, product)
                existing = Rule.search([
                    ('partner_id', '=', partner.id),
                    ('product_id', '=', product.id),
                ], limit=1)
                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    Rule.create(vals)
                    created += 1
            except Exception as e:
                errors += 1
                msgs.append("Row %d: %s" % (line_no, e))
                _logger.exception("UFS price rule import error on row %d", line_no)

        log = [
            _("Created: %d") % created,
            _("Updated: %d") % updated,
            _("Skipped (customer not found): %d") % skipped_cust,
            _("Skipped (product not found): %d") % skipped_prod,
            _("Errors: %d") % errors,
        ]
        if msgs:
            log.append("")
            log.append(_("First 50 error rows:"))
            log.extend(msgs[:50])
        self.write({'log': "\n".join(log), 'state': 'done'})

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
