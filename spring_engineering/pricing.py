"""What the materials cost us. Server side, and deliberately not in the bundle.

THESE USED TO LIVE IN static/src/js/spring_engineering.js, where the controller
parsed them out of the source. The reasoning was that one file should be the
single place the costs are written down - which was right about the principle and
wrong about the file, because everything under static/ is served to anybody who
opens the page. A visitor could read

    STEEL_PRICE_PER_LB=1.46
    CONE_PRICES={2.625:4.99,3.75:11.55,5.25:19.43,6:19.43,}

straight out of the frontend bundle. That is worse than it first looks. The
markup percentage is kept off the wire on purpose - /spring-calculator/rates
sends the rates with it already applied and never the figure itself - but
publishing the costs makes the markup a division away from any quote on the page.
The care taken over the percentage was worth nothing while these were public.

The page does not need them and never did: it prices from the rates the server
sends it. Both constants were dead code in the browser, shipped to every visitor.

STEEL_DENSITY stays in the JavaScript because the page genuinely uses it, to show
spring weights, and the controller still reads it from there so there is one copy
of it. A density is physics and tells a competitor nothing.
"""

# Per pound of FINISHED spring, counting every spring in the assembly.
STEEL_PRICE_PER_LB = 1.46

# Per SPRING, chosen by inside diameter. A Duplex spring is two springs nested on
# one shaft position, so it carries a set for the inner diameter and a set for the
# outer, and the two are added.
#
# 6" is not a size of its own: it takes the 5 1/4" price. The three Single
# diameters are the three that were quoted to us, and 6" appears only as the outer
# half of a Duplex pair.
#
# UNINSTALLED prices, quoted 2026-10-05. They replace an earlier set (6.04, 12.00,
# 20.00) which was a little higher at every size.
CONE_PRICES = {
    2.625: 4.99,
    3.75: 11.55,
    5.25: 19.43,
    6.0: 19.43,
}
