# Copyright 2026 Parameter (https://parameterllc.com/)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
"""Version adapters for APIs that differ between Odoo 19.0 and 20.0."""


def get_param(params, key):
    """Read a raw ir.config_parameter value (False when unset)."""
    getter = getattr(params, "get_str", None)  # 20.0: typed accessors
    if getter is not None:
        return getter(key, False)
    return params.get_param(key)  # 19.0


def set_param(params, key, value):
    setter = getattr(params, "set_str", None)  # 20.0
    if setter is not None:
        return setter(key, value)
    return params.set_param(key, value)  # 19.0
