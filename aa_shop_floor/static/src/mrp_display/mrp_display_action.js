import { patch } from "@web/core/utils/patch";
import { MrpDisplayAction } from "@mrp_workorder/mrp_display/mrp_display_action";

// Load the shop floor instructions with the cards.
patch(MrpDisplayAction.prototype, {
    get fieldsStructure() {
        const structure = super.fieldsStructure;
        structure["mrp.production"].push("aa_shop_spec");
        structure["mrp.workorder"].push("aa_shop_spec");
        return structure;
    },
});
