# GENERATED FROM spring_engineering BY tools/build_spring_calculator.py. DO NOT EDIT BY HAND - change the original and re-run the script.
{
    "name": "Spring Calculator",
    # NO SERIES IN THE VERSION, ON PURPOSE (owner, 2026-11-02: his second
    # project turned out to run Odoo 20, and the module showed up in Apps as
    # "Uninstallable" with no reason given).
    #
    # Odoo's loader does this, in odoo/modules/module.py:
    #
    #     if manifest['installable'] and not check_version(version, ...):
    #         manifest['installable'] = False
    #
    # and `check_version` passes only when the version STARTS WITH the
    # running series. A five-part "19.0.1.0.0" is returned unchanged by
    # `adapt_version`, so it fails on 20.0 - silently, as a greyed-out
    # button. A THREE-part version is PREFIXED with whatever series is
    # running ("1.0.0" -> "20.0.1.0.0"), so the module is offered on any of
    # them.
    #
    # THE TRADE, WRITTEN DOWN: Odoo will no longer refuse this module on a
    # series it was not written for. That refusal was worth something - but
    # not much, since it names no reason - and it is worth less than being
    # able to install the thing and read a real traceback.
    "version": "1.0.0",
    "category": "Engineering",
    "summary": "Torsion spring calculator, quote and cart",
    "author": "AA Impact Garage Door Supply",
    "license": "LGPL-3",
    # ONLY WHAT THE CALCULATOR ITSELF NEEDS. The original also pulls in
    # `website_sale_wishlist` (for the heart toggle) and `auth_signup` (for
    # the address check); neither is any part of the calculator, and both are
    # left behind with the features that wanted them.
    "depends": ["sale_management", "website", "website_sale"],
    "data": [
        "views/spring_calculator_settings.xml",
        "views/spring_calculator_product.xml",
        "views/spring_calculator_templates.xml",
        "views/custom_torsion_spring_templates.xml",
        "views/spring_calculator_views.xml",
        "views/spring_calculator_config_settings.xml",
    ],
    # THE SAME THREE FILES IN BOTH BUNDLES, as in the original: the backend
    # action and the public page mount one component from one source.
    "assets": {
        "web.assets_backend": [
            "spring_calculator/static/src/js/spring_calculator.js",
            "spring_calculator/static/src/xml/spring_calculator.xml",
            "spring_calculator/static/src/css/spring_calculator.css",
        ],
        "web.assets_frontend": [
            "spring_calculator/static/src/js/spring_calculator.js",
            "spring_calculator/static/src/xml/spring_calculator.xml",
            "spring_calculator/static/src/css/spring_calculator.css",
            "spring_calculator/static/src/css/spring_calculator_site.css",
        ],
    },
    "installable": True,
    "application": True,
}
