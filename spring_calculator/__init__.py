# GENERATED FROM spring_engineering BY tools/build_spring_calculator.py. DO NOT EDIT BY HAND - change the original and re-run the script.
from odoo.exceptions import UserError

from . import controllers
from . import models


def _refuse_beside_the_original(env):
    """Refuse to install where `spring_engineering` already lives.

    Both modules claim /spring-calculator and /custom-torsion-spring, and
    this one wins them - so installing it on the database that runs the shop
    would silently replace the live calculator with a copy that has none of
    the shop's products behind it.
    """
    original = env["ir.module.module"].sudo().search(
        [("name", "=", "spring_engineering"),
         ("state", "in", ("installed", "to upgrade", "to install"))], limit=1)

    if original:
        raise UserError(
            "Spring Calculator cannot be installed on this database.\n\n"
            "The Spring Engineering module is already installed here, and the"
            " two claim the same pages (/spring-calculator and"
            " /custom-torsion-spring). This one would take them over, so the"
            " calculator would stop showing the shop's own products.\n\n"
            "This module is the copy kept for the separate calculator-only"
            " project. Nothing needs to be installed here."
        )
