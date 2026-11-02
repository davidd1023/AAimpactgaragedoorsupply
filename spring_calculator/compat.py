# GENERATED FROM spring_engineering BY tools/build_spring_calculator.py. DO NOT EDIT BY HAND - change the original and re-run the script.
"""ONE FILE SET, TWO ODOO SERIES.

**Odoo 20 removed `ir.config_parameter.get_param` and `set_param`** and put
typed accessors in their place - `get_str`, `get_float`, `get_int`,
`get_bool` and matching setters. The module died on install with

    AttributeError: 'ir.config_parameter' object has no attribute 'get_param'

WHY A SHIM RATHER THAN JUST MOVING TO THE NEW API: the tests that prove this
carve correct - the ones that run eight specifications through BOTH engines
and compare the quotes - can only run where `spring_engineering` is, which is
Odoo 19. A module that only installs on 20 is a module whose maths nothing
checks.

**READ IT THE WAY IT IS WRITTEN.** Both parameters back `Float` fields on
res.config.settings, and on Odoo 20 Odoo's own settings page writes them with
`set_float`. Reading a float row back with `get_str` returns INVALID_VALUE,
which `get_str` turns into the default - indistinguishable from a deleted
parameter, which the engine turns into "call us". So these use the FLOAT
accessors on 20, matching what the settings page does.
"""


def config_rate(env, key):
    """The stored rate, or None/False when there is no row.

    The caller tells a missing parameter from a zero and refuses to quote on
    the first - which is the whole point of it, so neither series may answer
    "0.0" for "absent".
    """
    params = env["ir.config_parameter"].sudo()

    if hasattr(params, "get_float"):        # Odoo 20 and later
        return params.get_float(key, None)

    return params.get_param(key)            # Odoo 19 and earlier


def set_config_rate(env, key, value):
    """Store a rate so that ZERO survives.

    On Odoo 19 `set_param` DELETES the row when handed a falsy value, so the
    figure goes in as a string - a deliberate 0 would otherwise read back as
    a deleted parameter and turn every quote into "call us". Odoo 20 does not
    have that fault (`0.0 is False` is False, so the float is stored), and
    takes the float.
    """
    params = env["ir.config_parameter"].sudo()

    if hasattr(params, "set_float"):        # Odoo 20 and later
        params.set_float(key, float(value))
    else:
        params.set_param(key, str(value))   # Odoo 19 and earlier
