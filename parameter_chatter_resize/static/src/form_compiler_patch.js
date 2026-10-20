/*
 * Chatter Workspace: record identity on the chatter panel (Odoo 19/20 adapter).
 * Copyright 2026 Parameter (https://parameterllc.com/)
 * License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
 *
 * Adds data attributes to the form's chatter container at template compile
 * time, so Owl itself keeps them in sync with the record the panel belongs to.
 * Nothing is moved, cloned or re-mounted: the controller only reads them.
 * The compiled expressions (`__comp__.props.record`) are the ones mail's own
 * form compiler uses in both 19.0 and 20.0.
 */
import { patch } from "@web/core/utils/patch";
import { setAttributes } from "@web/core/utils/xml";
import { FormCompiler } from "@web/views/form/form_compiler";

patch(FormCompiler.prototype, {
    compile(node, params) {
        const res = super.compile(node, params);
        for (const hook of res.querySelectorAll(".o-mail-Form-chatter")) {
            setAttributes(hook, {
                "t-att-data-pcw-model": "__comp__.props.record.resModel",
                "t-att-data-pcw-res-id": "__comp__.props.record.resId or ''",
                "t-att-data-pcw-new": "__comp__.props.record.isNew ? '1' : '0'",
                "t-att-data-pcw-name": "__comp__.props.record.data.display_name or ''",
            });
        }
        return res;
    },
});
