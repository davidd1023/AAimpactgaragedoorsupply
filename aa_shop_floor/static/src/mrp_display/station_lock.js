import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { user } from "@web/core/user";
import { MrpDisplay } from "@mrp_workorder/mrp_display/mrp_display";

// EACH WORKER SEES ONLY HIS OWN STATIONS (owner, 2026-11-26): Jorge opens
// straight on Track Prep; Michel gets Hardware and Springs and picks one. No
// Overview, no "My WO", no other station, no button to add one. Which stations
// are his comes from the server (station_lock.py: the work centers' Allowed
// Employees); an admin, or anybody not in "Shop Floor only", gets `false` and
// none of this applies.
//
// The Shop Floor reads its station tabs from localStorage during setup, so the
// list is written there BEFORE setup runs - whatever the tablet had saved is
// replaced each time it opens.

function lockedStations() {
    const stations = session.aa_shop_floor_stations;
    return Array.isArray(stations) && stations.length ? stations : null;
}

patch(MrpDisplay.prototype, {
    setup() {
        const stations = lockedStations();
        if (stations) {
            const key = `mrp_workorder.db_${session.db}.user_${user.userId}`;
            try {
                window.localStorage.setItem(key, JSON.stringify(stations));
                const active = Number(JSON.parse(window.localStorage.getItem(`${key}.activeWC`)));
                if (!stations.some((wc) => wc.id === active)) {
                    window.localStorage.setItem(`${key}.activeWC`, String(stations[0].id));
                }
            } catch {
                // A tablet that keeps nothing: _loadActiveWorkcenter below
                // still lands him on his first station.
            }
        }
        super.setup(...arguments);
        this.aaLockedStations = stations;
        if (stations) {
            // Only his stations as tabs: Overview (0) and My WO (-1) go.
            this.state.workcenters = [...stations];
        }
    },

    aaStationAllowed(workcenterId) {
        return (this.aaLockedStations || []).some((wc) => wc.id === Number(workcenterId));
    },

    _loadActiveWorkcenter() {
        const active = super._loadActiveWorkcenter(...arguments);
        const stations = lockedStations();
        if (stations && !stations.some((wc) => wc.id === Number(active))) {
            return stations[0].id;
        }
        return active;
    },

    get shouldHideNewWorkcenterButton() {
        return this.aaLockedStations ? true : super.shouldHideNewWorkcenterButton;
    },

    toggleWorkcenterDialog() {
        if (this.aaLockedStations) {
            return;
        }
        return super.toggleWorkcenterDialog(...arguments);
    },

    async toggleWorkcenter(workcenters) {
        if (this.aaLockedStations) {
            this.state.workcenters = [...this.aaLockedStations];
            return;
        }
        return super.toggleWorkcenter(...arguments);
    },

    async selectWorkcenter(workcenterId) {
        if (this.aaLockedStations && !this.aaStationAllowed(workcenterId)) {
            return;
        }
        return super.selectWorkcenter(...arguments);
    },
});
