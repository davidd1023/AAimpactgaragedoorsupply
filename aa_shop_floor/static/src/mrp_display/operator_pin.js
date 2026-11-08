/** @odoo-module **/
// CHANGE PIN, from the Shop Floor's own menu (owner, 2026-10-28): "as admin I
// should have the option to change Jorge's and Michel's work-station PIN".
//
// ADMINS ONLY. The entry is hidden for everybody else and the server refuses
// as well - hiding a button is not a lock. No PIN ever comes back from the
// server, only whether one is set.

import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { MrpDisplay } from "@mrp_workorder/mrp_display/mrp_display";

export class AaOperatorPinDialog extends Component {
    static template = "aa_shop_floor.OperatorPinDialog";
    static components = { Dialog };
    static props = { close: Function };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ loading: true, operators: [], typed: {}, saving: false });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.operators = await this.orm.call("hr.employee", "aa_shop_floor_pins", []);
        this.state.loading = false;
    }

    onInput(operator, ev) {
        // Digits only, as the PIN pad on the station takes nothing else.
        const digits = ev.target.value.replace(/\D/g, "");
        ev.target.value = digits;
        this.state.typed[operator.id] = digits;
    }

    async save(operator) {
        const pin = this.state.typed[operator.id] || "";
        if (pin.length < 4) {
            this.notification.add("The PIN must be at least 4 digits.", { type: "danger" });
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call("hr.employee", "aa_set_shop_floor_pin", [operator.id, pin]);
            this.notification.add(`${operator.name}'s PIN is changed.`, { type: "success" });
            this.state.typed[operator.id] = "";
            await this.load();
        } finally {
            this.state.saving = false;
        }
    }
}

patch(MrpDisplay.prototype, {
    setup() {
        super.setup();
        this.aaPinDialog = useService("dialog");
        this.aaIsAdmin = user.isSystem;
    },

    aaOpenOperatorPins() {
        this.aaPinDialog.add(AaOperatorPinDialog, {});
    },
});
