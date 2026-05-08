# Reparent existing top-level product categories to match the legacy
# ufsales.com/Catalog/ reference tree.
#
# Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/reparent_categories.py').read())
#
# Or paste the body directly into the shell. Idempotent: re-running is a no-op.

REFERENCE_TREE = {
    "Chemicals": "Janitorial Supplies",
    "Cleaning Supplies": "Janitorial Supplies",
    "Liners": "Janitorial Supplies",
    "Paper": "Janitorial Supplies",
    "Receptacles / Trash": "Janitorial Supplies",
    "Safety": "Gloves and Safety",
    "Industrial Packaging": "Packaging",
    "Retail Packaging": "Packaging",
}


def _reparent(env, model_name):
    Cat = env[model_name].with_context(active_test=False).sudo()
    fields_map = Cat._fields
    has_source_path = "ufsales_source_path" in fields_map
    has_imported = "ufsales_imported" in fields_map
    has_publish = "website_published" in fields_map or "is_published" in fields_map
    moved = wrappers_created = wrappers_existing = 0

    for child_name, wrapper_name in REFERENCE_TREE.items():
        wrapper = Cat.search(
            [("name", "=", wrapper_name), ("parent_id", "=", False)], limit=1
        )
        if not wrapper:
            wvals = {"name": wrapper_name}
            if has_imported:
                wvals["ufsales_imported"] = True
            if has_source_path:
                wvals["ufsales_source_path"] = wrapper_name
            if "website_published" in fields_map:
                wvals["website_published"] = True
            elif "is_published" in fields_map:
                wvals["is_published"] = True
            wrapper = Cat.create(wvals)
            wrappers_created += 1
        else:
            wrappers_existing += 1
            wvals = {}
            if has_imported and not wrapper.ufsales_imported:
                wvals["ufsales_imported"] = True
            if has_source_path and not wrapper.ufsales_source_path:
                wvals["ufsales_source_path"] = wrapper_name
            if wvals:
                wrapper.write(wvals)

        children = Cat.search(
            [("name", "=", child_name), ("parent_id", "=", False)]
        ).filtered(lambda c: c.id != wrapper.id)

        for child in children:
            cvals = {"parent_id": wrapper.id}
            if has_source_path:
                cvals["ufsales_source_path"] = "%s / %s" % (wrapper_name, child_name)
            child.write(cvals)
            moved += 1
            print("  moved %s id=%s -> parent=%s" % (model_name, child.id, wrapper_name))

    return {
        "model": model_name,
        "moved": moved,
        "wrappers_created": wrappers_created,
        "wrappers_existing": wrappers_existing,
    }


print(_reparent(env, "product.public.category"))
print(_reparent(env, "product.category"))
env.cr.commit()
print("done.")
