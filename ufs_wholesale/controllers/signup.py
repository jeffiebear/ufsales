# -*- coding: utf-8 -*-

import base64
import logging

import werkzeug
from markupsafe import Markup

from odoo import _, http
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.auth_signup.models.res_users import SignupError
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)
_logger = logging.getLogger(__name__)


class UfsWholesaleSignup(AuthSignupHome):
    _extra_signup_fields = (
        "company_name",
        "street",
        "street2",
        "city",
        "state_name",
        "zip",
        "country_name",
        "phone",
        "fein_taxid",
    )

    def _prepare_wholesale_partner_values(self, kw):
        def _required(key, label):
            value = (kw.get(key) or "").strip()
            if not value:
                raise UserError(_("Please complete the required field: %s") % label)
            return value

        company_name = _required("company_name", _("Company Name"))
        street = _required("street", _("Street Address"))
        city = _required("city", _("City"))
        state_name = _required("state_name", _("State / Region"))
        zip_code = _required("zip", _("ZIP / Postal Code"))
        country_name = _required("country_name", _("Country"))
        fein_taxid = _required("fein_taxid", _("FEIN / Tax ID"))
        certificate = request.httprequest.files.get("resale_certificate")
        if not certificate or not certificate.filename:
            raise UserError(_("Please upload your Tax Resale Certificate."))

        certificate_content = certificate.read()
        if not certificate_content:
            raise UserError(_("The uploaded Tax Resale Certificate file is empty."))
        if len(certificate_content) > 10 * 1024 * 1024:
            raise UserError(_("The uploaded Tax Resale Certificate must be under 10 MB."))

        partner_fields = request.env["res.partner"]._fields
        vals = {
            "street": street,
            "street2": (kw.get("street2") or "").strip(),
            "city": city,
            "zip": zip_code,
            "phone": (kw.get("phone") or "").strip(),
            "vat": fein_taxid,
            "ufs_company_name": company_name,
            "ufs_fein_taxid": fein_taxid,
            "ufs_state_text": state_name,
            "ufs_country_text": country_name,
            "ufs_resale_certificate": base64.b64encode(certificate_content),
            "ufs_resale_certificate_filename": certificate.filename,
        }
        if "company_name" in partner_fields:
            vals["company_name"] = company_name
        return vals

    @http.route(
        "/web/signup",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
        captcha="signup",
        list_as_website_content=_lt("Sign Up"),
    )
    def web_auth_signup(self, *args, **kw):
        qcontext = self.get_auth_signup_qcontext()

        if not qcontext.get("token") and not qcontext.get("signup_enabled"):
            raise werkzeug.exceptions.NotFound()

        for field_name in self._extra_signup_fields:
            qcontext.setdefault(field_name, kw.get(field_name))

        if "error" not in qcontext and request.httprequest.method == "POST":
            try:
                partner_vals = self._prepare_wholesale_partner_values(kw)
                self.do_signup(qcontext, do_login=False)

                User = request.env["res.users"]
                user_sudo = User.sudo().search(
                    User._get_login_domain(qcontext.get("login")),
                    order=User._get_login_order(),
                    limit=1,
                )
                if not user_sudo:
                    raise UserError(_("We could not locate the newly created account. Please contact us."))

                user_sudo.partner_id.sudo().write(partner_vals)
                user_sudo.sudo().action_ufs_set_wholesale_pending()
                user_sudo.sudo().action_ufs_send_registration_acknowledgement()

                public_user = request.env.ref("base.public_user")
                request.update_env(user=public_user)
                return request.render(
                    "ufs_wholesale.signup_pending",
                    {"login": qcontext.get("login")},
                )
            except UserError as e:
                qcontext["error"] = e.args[0]
            except (SignupError, AssertionError) as e:
                User = request.env["res.users"]
                if User.sudo().with_context(active_test=False).search_count(
                    User._get_login_domain(qcontext.get("login")), limit=1
                ):
                    qcontext["error"] = _("Another user is already registered using this email address.")
                else:
                    _logger.warning("%s", e)
                    qcontext["error"] = _("Could not create a new account.") + Markup("<br/>") + str(e)

        response = request.render("auth_signup.signup", qcontext)
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
        return response

