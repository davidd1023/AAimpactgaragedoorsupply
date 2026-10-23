"""WHICH OLD PRODUCTS BECOME WHICH VARIANT OF WHICH PRODUCT.

This table is the whole decision. It was GENERATED from the owner's own
catalogue export (211 products, 2026-10-21) and then checked three ways
before it was written here:

  * every name in it exists in that export, spelled exactly as the catalogue
    spells it - double spaces, "( Pair )" and all - because the merge matches
    on the name and a near miss is a product left behind;
  * no name is claimed by two families;
  * a family NEED NOT be a full matrix, and the hinges are not: they run #1
    to #9 while the Galvanized ones stop at #7, so nine sizes by three colours
    is 27 combinations over 25 products. Odoo builds a variant per combination
    regardless, so the two the owner has never stocked are ARCHIVED by the
    merge, which Odoo reads as "this combination does not exist". An earlier
    draft refused a family like that outright - which would have left four
    hinge sizes as separate products, the very thing this change exists to
    stop.

HIS CATALOGUE MOVED UNDER THIS TABLE ALREADY. Hinge #8 and #9 and Cut Down
Hinge #8 and #9 were not in the export it was generated from, and the first
rehearsal on his database named them as strays it had left alone. They are in
here now, on the assumption that a "Hinge # 8" belongs with "Hinge # 7" - the
part numbers continue the same CH1411 series - and if that is ever wrong, the
four lines to delete are obvious.

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

THE DRUMS WERE ADDED ON 2026-10-23, by colour ONLY: "only merge them by color,
so we will have each drum separate like d400-96, d400-144, and d575-120hl will
all still be seperate". That is the safe half of the job he first asked for.
Folding the MODELS together as well would have broken the high-lift kits -
aa_dealer_orders/kit_setup.py finds a drum with `name ilike 'D525-54'` and
swaps it into a kit's BoM - because the model would have left the name and
moved into a variant value. Keeping one product per model keeps the model in
the name, so none of that machinery notices. D800-120 HL has no colour and so
nothing to merge.

Tracks, cables and cones are still deliberately NOT here. Tracks especially are
read by name all over the shop floor code and are their own job.

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
    "attribute_hinge_size": ("#1", "#2", "#3", "#4", "#5", "#6", "#7", "#8",
                            "#9"),
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
            'Hinge # 8 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#8'},
            'Hinge # 8 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#8'},
            'Hinge # 9 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#9'},
            'Hinge # 9 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#9'},
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
            'Cut Down Hinge # 8 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#8'},
            'Cut Down Hinge # 8 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#8'},
            'Cut Down Hinge # 9 Black': {'attribute_finish_colour': 'Black', 'attribute_hinge_size': '#9'},
            'Cut Down Hinge # 9 White': {'attribute_finish_colour': 'White', 'attribute_hinge_size': '#9'},
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
    {
        "survivor": 'Canimex D400-96',
        "base": 'Canimex D400-96 Black',
        "attributes": ('attribute_finish_colour',),
        "products": {
            'Canimex D400-96 Black': {'attribute_finish_colour': 'Black'},
            'Canimex D400-96 White': {'attribute_finish_colour': 'White'},
        },
    },
    {
        "survivor": 'Canimex D400-144',
        "base": 'Canimex D400-144 Black',
        "attributes": ('attribute_finish_colour',),
        "products": {
            'Canimex D400-144 Black': {'attribute_finish_colour': 'Black'},
            'Canimex D400-144 White': {'attribute_finish_colour': 'White'},
        },
    },
    {
        "survivor": 'Canimex D525-216',
        "base": 'Canimex D525-216 Black',
        "attributes": ('attribute_finish_colour',),
        "products": {
            'Canimex D525-216 Black': {'attribute_finish_colour': 'Black'},
            'Canimex D525-216 White': {'attribute_finish_colour': 'White'},
        },
    },
    {
        "survivor": 'Canimex D525-54 HL',
        "base": 'Canimex D525-54 HL Black',
        "attributes": ('attribute_finish_colour',),
        "products": {
            'Canimex D525-54 HL Black': {'attribute_finish_colour': 'Black'},
            'Canimex D525-54 HL White': {'attribute_finish_colour': 'White'},
        },
    },
    {
        "survivor": 'Canimex D575-120 HL',
        "base": 'Canimex D575-120 HL Black',
        "attributes": ('attribute_finish_colour',),
        "products": {
            'Canimex D575-120 HL Black': {'attribute_finish_colour': 'Black'},
            'Canimex D575-120 HL White': {'attribute_finish_colour': 'White'},
        },
    },
)
