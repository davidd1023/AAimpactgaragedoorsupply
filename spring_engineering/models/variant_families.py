"""WHICH OLD PRODUCTS BECOME WHICH VARIANT OF WHICH PRODUCT.

This table is the whole decision. It was GENERATED from the owner's own
catalogue export (211 products, 2026-10-21) and then checked three ways
before it was written here:

  * every name in it exists in that export, spelled exactly as the catalogue
    spells it - double spaces, "( Pair )" and all - because the merge matches
    on the name and a near miss is a product left behind;
  * no name is claimed by two families;
  * every family is a FULL matrix. 7 hinge sizes x 3 colours is 21 rows and
    the catalogue has 21. If a family were missing a combination, Odoo would
    still create that variant and the store would offer a part the owner has
    never stocked - so the merge refuses a family that does not square.

WHAT THE OWNER DECIDED (2026-10-21, all three in his words):

  * "ebp, hinges, rollers, shafts, angles, trims, and brackets should be one
    product on the store, but in the individual product page people will be
    able to then choose the other sizes or color."
  * "types of these products will still be separate, for example spring
    anchor bracket and top brackets will remain different products" - which is
    why there are fifteen families here and not one.
  * "hands should be on the same product, so another choice for rh or lh on
    the individual product" - so LH and RH collapse too, on the one product
    that has them.

Tracks, drums, cables and cones are deliberately NOT here. They have the same
colour-split shape and the owner left them out: tracks especially are read by
name all over the shop floor code and are their own job.

THE BASE IS THE PRODUCT THAT SURVIVES. Its record keeps the page, the images,
the website category and whatever history it carries, and the other rows of
the family are folded into it as variants and archived. The best-stocked black
row of each family was chosen, because that is the row most likely to be the
one people have been buying.
"""

# Attribute XML IDs, with the values each one offers IN THE ORDER THE PAGE
# SHOULD SHOW THEM. Numeric sizes have to be listed, not sorted: "#10" before
# "#16" is wrong alphabetically and right on a page, and 8'6" sorts before
# 10'6" only if a human says so.
ATTRIBUTE_VALUES = {
    "attribute_finish_colour": ("Black", "White", "Bronze", "Galvanized"),
    "attribute_hand": ("LH", "RH"),
    "attribute_hinge_size": ("#1", "#2", "#3", "#4", "#5", "#6", "#7"),
    "attribute_jamb_bracket_size": ("#10", "#12", "#14", "#16"),
    "attribute_bearing_plate_size": ('3 3/8"', '4 3/8"', '6"'),
    "attribute_flag_angle_size": ('5.9"', '6-3/8"'),
    "attribute_roller_stem": ('7"', '9"'),
    "attribute_shaft_length": ("8'6\"", "9'6\"", "10'6\""),
}

# survivor: the name the merged product ends up with.
# base:     the old product whose record survives and becomes it.
# attributes: in page order - the first choice a customer makes comes first.
# products: old product name -> the combination it becomes.
FAMILIES = (
    {
        "survivor": 'Spring Anchor Bracket',
        "base": 'Spring Anchor Bracket RH Black',
        "attributes": ('attribute_hand', 'attribute_finish_colour'),
        "products": {
            'Spring Anchor Bracket LH Black': {'attribute_finish_colour': 'Black', 'attribute_hand': 'LH'},
            'Spring Anchor Bracket LH White': {'attribute_finish_colour': 'White', 'attribute_hand': 'LH'},
            'Spring Anchor Bracket RH Black': {'attribute_finish_colour': 'Black', 'attribute_hand': 'RH'},
            'Spring Anchor Bracket RH White': {'attribute_finish_colour': 'White', 'attribute_hand': 'RH'},
        },
    },
    {
        "survivor": 'Top Bracket',
        "base": 'Top Bracket Black',
        "attributes": ('attribute_finish_colour',),
        "products": {
            'Top Bracket Black': {'attribute_finish_colour': 'Black'},
            'Top Bracket White': {'attribute_finish_colour': 'White'},
        },
    },
    {
        "survivor": 'Bottom Bracket ( Pair )',
        "base": 'Bottom Bracket Black ( Pair )',
        "attributes": ('attribute_finish_colour',),
        "products": {
            'Bottom Bracket Black ( Pair )': {'attribute_finish_colour': 'Black'},
            'Bottom Bracket White ( Pair )': {'attribute_finish_colour': 'White'},
        },
    },
    {
        "survivor": 'Center Hinge',
        "base": 'Center Hinge Black',
        "attributes": ('attribute_finish_colour',),
        "products": {
            'Center Hinge Black': {'attribute_finish_colour': 'Black'},
            'Center Hinge White': {'attribute_finish_colour': 'White'},
        },
    },
    {
        "survivor": 'Perforated Angles 10ft',
        "base": 'Perforated Angles 10ft Black',
        "attributes": ('attribute_finish_colour',),
        "products": {
            'Perforated Angles 10ft Black': {'attribute_finish_colour': 'Black'},
            'Perforated Angles 10ft White': {'attribute_finish_colour': 'White'},
        },
    },
    {
        "survivor": 'Trims',
        "base": 'Black Trims',
        "attributes": ('attribute_finish_colour',),
        "products": {
            'Black Trims': {'attribute_finish_colour': 'Black'},
            'Bronze Trims': {'attribute_finish_colour': 'Bronze'},
            'White Trims': {'attribute_finish_colour': 'White'},
        },
    },
    {
        "survivor": '3" Lock',
        "base": '3" Lock Black',
        "attributes": ('attribute_finish_colour',),
        "products": {
            '3" Lock Black': {'attribute_finish_colour': 'Black'},
            '3" Lock White': {'attribute_finish_colour': 'White'},
        },
    },
    {
        "survivor": 'Jamb Bracket',
        "base": 'Jamb Bracket # 10 Black',
        "attributes": ('attribute_jamb_bracket_size', 'attribute_finish_colour'),
        "products": {
            'Jamb Bracket # 10 Black': {'attribute_jamb_bracket_size': '#10', 'attribute_finish_colour': 'Black'},
            'Jamb Bracket # 10 White': {'attribute_jamb_bracket_size': '#10', 'attribute_finish_colour': 'White'},
            'Jamb Bracket # 12 Black': {'attribute_jamb_bracket_size': '#12', 'attribute_finish_colour': 'Black'},
            'Jamb Bracket # 12 White': {'attribute_jamb_bracket_size': '#12', 'attribute_finish_colour': 'White'},
            'Jamb Bracket # 14 Black': {'attribute_jamb_bracket_size': '#14', 'attribute_finish_colour': 'Black'},
            'Jamb Bracket # 14 White': {'attribute_jamb_bracket_size': '#14', 'attribute_finish_colour': 'White'},
            'Jamb Bracket # 16 Black': {'attribute_jamb_bracket_size': '#16', 'attribute_finish_colour': 'Black'},
            'Jamb Bracket # 16 White': {'attribute_jamb_bracket_size': '#16', 'attribute_finish_colour': 'White'},
        },
    },
    {
        "survivor": 'End Bearing Plate ( Pair )',
        "base": 'End Bearing Plate 3 3/8 Black ( Pair )',
        "attributes": ('attribute_bearing_plate_size', 'attribute_finish_colour'),
        "products": {
            'End Bearing Plate 3 3/8 Black ( Pair )': {'attribute_bearing_plate_size': '3 3/8"', 'attribute_finish_colour': 'Black'},
            'End Bearing Plate 3 3/8 White ( Pair )': {'attribute_bearing_plate_size': '3 3/8"', 'attribute_finish_colour': 'White'},
            'End Bearing Plate 4 3/8 Black ( Pair )': {'attribute_bearing_plate_size': '4 3/8"', 'attribute_finish_colour': 'Black'},
            'End Bearing Plate 4 3/8 White ( Pair )': {'attribute_bearing_plate_size': '4 3/8"', 'attribute_finish_colour': 'White'},
            'End Bearing Plate 6" Black ( Pair )': {'attribute_bearing_plate_size': '6"', 'attribute_finish_colour': 'Black'},
            'End Bearing Plate 6" White ( Pair )': {'attribute_bearing_plate_size': '6"', 'attribute_finish_colour': 'White'},
        },
    },
    {
        "survivor": 'Hinge',
        "base": 'Hinge # 1 Black',
        "attributes": ('attribute_hinge_size', 'attribute_finish_colour'),
        "products": {
            'Hinge # 1 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#1'},
            'Hinge # 1 Galvanized': {'attribute_finish_colour': 'Galvanized', 'attribute_hinge_size': '#1'},
            'Hinge # 1 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#1'},
            'Hinge # 2 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#2'},
            'Hinge # 2 Galvanized': {'attribute_finish_colour': 'Galvanized', 'attribute_hinge_size': '#2'},
            'Hinge # 2 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#2'},
            'Hinge # 3 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#3'},
            'Hinge # 3 Galvanized': {'attribute_finish_colour': 'Galvanized', 'attribute_hinge_size': '#3'},
            'Hinge # 3 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#3'},
            'Hinge # 4 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#4'},
            'Hinge # 4 Galvanized': {'attribute_finish_colour': 'Galvanized', 'attribute_hinge_size': '#4'},
            'Hinge # 4 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#4'},
            'Hinge # 5 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#5'},
            'Hinge # 5 Galvanized': {'attribute_finish_colour': 'Galvanized', 'attribute_hinge_size': '#5'},
            'Hinge # 5 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#5'},
            'Hinge # 6 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#6'},
            'Hinge # 6 Galvanized': {'attribute_finish_colour': 'Galvanized', 'attribute_hinge_size': '#6'},
            'Hinge # 6 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#6'},
            'Hinge # 7 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#7'},
            'Hinge # 7 Galvanized': {'attribute_finish_colour': 'Galvanized', 'attribute_hinge_size': '#7'},
            'Hinge # 7 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#7'},
        },
    },
    {
        "survivor": 'Cut Down Hinge',
        "base": 'Cut Down Hinge # 1 Black',
        "attributes": ('attribute_hinge_size', 'attribute_finish_colour'),
        "products": {
            'Cut Down Hinge # 1 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#1'},
            'Cut Down Hinge # 1 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#1'},
            'Cut Down Hinge # 2 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#2'},
            'Cut Down Hinge # 2 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#2'},
            'Cut Down Hinge # 3 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#3'},
            'Cut Down Hinge # 3 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#3'},
            'Cut Down Hinge # 4 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#4'},
            'Cut Down Hinge # 4 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#4'},
            'Cut Down Hinge # 5 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#5'},
            'Cut Down Hinge # 5 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#5'},
            'Cut Down Hinge # 6 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#6'},
            'Cut Down Hinge # 6 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#6'},
            'Cut Down Hinge # 7 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#7'},
            'Cut Down Hinge # 7 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#7'},
        },
    },
    {
        "survivor": 'Flag Angle',
        "base": 'Flag Angle 6-3/8" Black',
        "attributes": ('attribute_flag_angle_size', 'attribute_finish_colour'),
        "products": {
            'Flag Angle 5.9" Black': {'attribute_finish_colour': 'Black', 'attribute_flag_angle_size': '5.9"'},
            'Flag Angle 5.9" White': {'attribute_finish_colour': 'White', 'attribute_flag_angle_size': '5.9"'},
            'Flag Angle 6-3/8" Black': {'attribute_finish_colour': 'Black', 'attribute_flag_angle_size': '6-3/8"'},
            'Flag Angle 6-3/8" White': {'attribute_finish_colour': 'White', 'attribute_flag_angle_size': '6-3/8"'},
        },
    },
    {
        "survivor": 'Roller 2"',
        "base": 'Roller 2-9 Black',
        "attributes": ('attribute_roller_stem', 'attribute_finish_colour'),
        "products": {
            'Roller 2-7 Black': {'attribute_finish_colour': 'Black', 'attribute_roller_stem': '7"'},
            'Roller 2-7 White': {'attribute_finish_colour': 'White', 'attribute_roller_stem': '7"'},
            'Roller 2-9 Black': {'attribute_finish_colour': 'Black', 'attribute_roller_stem': '9"'},
            'Roller 2-9 White': {'attribute_finish_colour': 'White', 'attribute_roller_stem': '9"'},
        },
    },
    {
        "survivor": 'Roller 3"',
        "base": 'Roller 3-9 Black',
        "attributes": ('attribute_roller_stem', 'attribute_finish_colour'),
        "products": {
            'Roller 3-7 Black': {'attribute_finish_colour': 'Black', 'attribute_roller_stem': '7"'},
            'Roller 3-7 White': {'attribute_finish_colour': 'White', 'attribute_roller_stem': '7"'},
            'Roller 3-9 Black': {'attribute_finish_colour': 'Black', 'attribute_roller_stem': '9"'},
            'Roller 3-9 White': {'attribute_finish_colour': 'White', 'attribute_roller_stem': '9"'},
        },
    },
    {
        "survivor": 'Torsion Solid Shaft',
        "base": 'Torsion Solid Shaft 8\'6"',
        "attributes": ('attribute_shaft_length',),
        "products": {
            'Torsion Solid Shaft 10\'6"': {'attribute_shaft_length': '10\'6"'},
            'Torsion Solid Shaft 8\'6"': {'attribute_shaft_length': '8\'6"'},
            'Torsion Solid Shaft 9\'6"': {'attribute_shaft_length': '9\'6"'},
        },
    },
)
