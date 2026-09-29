# -*- coding: utf-8 -*-
"""
Re-point the BofA credit-card journal (BNK2) onto the credit-card LIABILITY
account, off the asset_cash account it was mistakenly set up on.

A credit card is a liability, not an asset. BNK2 stays type='bank' (Odoo 19
allows a bank journal to post to a liability_credit_card account - verified on
staging), only its default account changes: 101405 (asset_cash) -> 212400
"Bank of America Credit Card" (liability_credit_card, created by this module's
account_cutover_chart_data.xml).

Only the DEFAULT account changes here; existing postings are NOT restated. The
historical balance stranded on the old 101405 account is cleaned up at the
July-1 cutover opening (the same way the duplicate checking GL is), not here.

Resolved by CODE (not id) so it is portable across the staging and production
databases. Idempotent: safe to run more than once.

Author: Parameter (https://parameterllc.com/)
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    journal = env['account.journal'].search([('code', '=', 'BNK2')], limit=1)
    if not journal:
        _logger.info("ufs_customizations: BNK2 journal not found; skipping card re-point.")
        return
    target = env['account.account'].search([('code', '=', '212400')], limit=1)
    if not target:
        _logger.warning(
            "ufs_customizations: 212400 credit-card liability account not found; "
            "skipping BNK2 re-point (chart data may not have loaded)."
        )
        return
    if journal.default_account_id == target:
        _logger.info("ufs_customizations: BNK2 already points at 212400; nothing to do.")
        return
    old_code = journal.default_account_id.code
    journal.default_account_id = target.id
    _logger.info(
        "ufs_customizations: re-pointed BNK2 default account %s -> 212400 "
        "(BofA Credit Card liability).", old_code,
    )
