# GENERATED FROM spring_engineering BY tools/build_spring_calculator.py. DO NOT EDIT BY HAND - change the original and re-run the script.
{
    "name": "Spring Calculator",
    "version": "19.0.1.0.0",
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
