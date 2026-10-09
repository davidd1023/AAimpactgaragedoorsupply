/** @odoo-module ignore **/
/* Shop hardware-kit page (AA-1200 / 1600 / 1800): when Springs, Tracks or Cables are
 * ticked or a trim colour is picked, ask for the door once and price those extras like
 * the dealer Quick Order. Trims need the height: up to 9' takes 2 trims, taller takes 3.
 * The server adds them to the cart next to the kit (see AAKitCart.add_to_cart). */
(function () {
    "use strict";

    const EXTRAS = ["Springs", "Tracks", "Cables"];
    const TRACK_TYPES = [["3-15R", '3" 15R'], ["2-15R", '2" 15R'], ["2-12R", '2" 12R'], ["3-LHR", '3" LHR'], ["2-LHR", '2" LHR']];
    const LIFT_TYPES = [["standard", "Standard"], ["highlift", "High Lift"]];

    function rpc(url, params) {
        return fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", params }),
        }).then((r) => r.json()).then((j) => {
            if (j.error) throw new Error((j.error.data && j.error.data.message) || "Server error");
            return j.result;
        });
    }

    function el(tag, attrs, children) {
        const n = document.createElement(tag);
        Object.entries(attrs || {}).forEach(([k, v]) => {
            if (k === "class") n.className = v;
            else if (k === "text") n.textContent = v;
            else if (v !== undefined && v !== null && v !== false) n.setAttribute(k, v);
        });
        (children || []).forEach((c) => c && n.appendChild(c));
        return n;
    }

    function init(root) {
        const kit = JSON.parse(root.dataset.kit || "{}");
        const symbol = root.dataset.currencySymbol || "$";
        const money = (v) => symbol + Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        const scope = root.closest("#product_details") || document;

        const num = (ph) => el("input", { type: "number", min: "0", step: "any", class: "form-control form-control-sm", placeholder: ph });
        const wFt = num("ft"), wIn = num("in"), hFt = num("ft"), hIn = num("in"), weight = num("lb"), hl = num("in");
        const track = el("select", { class: "form-select form-select-sm" },
            [el("option", { value: "", text: "Select..." })].concat(TRACK_TYPES.map(([v, t]) => el("option", { value: v, text: t }))));
        const lift = el("select", { class: "form-select form-select-sm" }, LIFT_TYPES.map(([v, t]) => el("option", { value: v, text: t })));
        const hlCol = el("div", { class: "col-6 d-none" }, [el("label", { class: "form-label small mb-1", text: "High lift (in)" }), hl]);
        const field = (label, input, cls) => el("div", { class: cls || "col-6" }, [el("label", { class: "form-label small mb-1", text: label }), input]);
        const pair = (label, a, b) => el("div", { class: "col-6" }, [el("label", { class: "form-label small mb-1", text: label }), el("div", { class: "d-flex gap-1" }, [a, b])]);
        const out = el("div", { class: "small mt-2" });
        root.appendChild(el("div", { class: "border rounded p-3" }, [
            el("div", { class: "fw-bold mb-1", text: "Your door" }),
            el("div", { class: "small text-muted mb-2", text: "Springs, tracks, cables and trims are sized and priced for this door." }),
            el("div", { class: "row g-2" }, [
                pair("Width", wFt, wIn), pair("Height", hFt, hIn),
                field("Door weight", weight), field("Track type", track), field("Lift type", lift), hlCol,
            ]),
            out,
        ]));

        const widthIn = () => (Number(wFt.value) || 0) * 12 + (Number(wIn.value) || 0);
        const heightIn = () => (Number(hFt.value) || 0) * 12 + (Number(hIn.value) || 0);

        function selectedPtavs() {
            const ids = [];
            scope.querySelectorAll("input.js_variant_change:checked").forEach((i) => ids.push(Number(i.value)));
            scope.querySelectorAll("select.js_variant_change").forEach((s) => s.value && ids.push(Number(s.value)));
            return ids;
        }
        function tickedExtras() {
            return [...scope.querySelectorAll("input.js_variant_change:checked")]
                .map((i) => i.getAttribute("title") || "")
                .filter((t) => EXTRAS.includes(t));
        }
        function trimsPicked() {
            const trims = (kit.trims || []).map(String);
            return [...scope.querySelectorAll("input.js_variant_change:checked")].some((i) => trims.includes(String(i.value)))
                || [...scope.querySelectorAll("select.js_variant_change")].some((s) => trims.includes(String(s.value)));
        }
        function drumCode(ids) {
            for (const id of ids) {
                if (kit.drums && kit.drums[String(id)]) return kit.drums[String(id)];
            }
            return "";
        }
        function seriesFor(w) {
            if (!w) return null;
            if (w <= 144) return "AA-1200";
            if (w <= 194) return "AA-1600";
            if (w <= 220) return "AA-1800";
            return "too-wide";
        }

        let seq = 0;
        let timer = null;
        function refresh() {
            clearTimeout(timer);
            timer = setTimeout(update, 250);
        }
        function update() {
            const ticked = tickedExtras();
            const wantsDoor = ticked.length > 0 || trimsPicked();
            root.classList.toggle("d-none", !wantsDoor);
            hlCol.classList.toggle("d-none", lift.value !== "highlift");
            if (!wantsDoor) return;
            const ids = selectedPtavs();
            const drum = drumCode(ids);
            const door = {
                width: wFt.value || wIn.value ? (wFt.value || 0) + "' " + (wIn.value || 0) + '"' : "",
                height: hFt.value || hIn.value ? (hFt.value || 0) + "' " + (hIn.value || 0) + '"' : "",
                width_in: widthIn(), height_in: heightIn(), weight: weight.value,
                track_type: track.value, lift_type: lift.value,
                high_lift: lift.value === "highlift" ? hl.value : "", drum,
                spring_spec: null, spring_warnings: [],
            };
            const warn = [];
            const s = seriesFor(widthIn());
            if (s === "too-wide") warn.push("Doors wider than 18' 4\" need a special order - please call us.");
            else if (s && kit.name && !kit.name.startsWith(s)) warn.push("A door this wide takes the " + s + " kit.");
            if (ticked.includes("Springs") && typeof window.aaPickSprings === "function" && Number(weight.value) > 0 && heightIn() > 0) {
                try {
                    const r = window.aaPickSprings({
                        liftType: lift.value, highLift: Number(hl.value) || 0, trackType: track.value,
                        drum, widthIn: widthIn(), heightIn: heightIn(), weight: Number(weight.value) || 0,
                    });
                    if (!r.error) {
                        door.spring_spec = r.spec;
                        door.spring_warnings = r.warnings.filter((w) => w.severity === "red").map((w) => w.message);
                    } else {
                        warn.push(r.error);
                    }
                } catch (e) {
                    warn.push("Could not calculate the springs.");
                }
            }
            const qtyInput = scope.querySelector("input[name='add_qty']");
            const my = ++seq;
            rpc("/aa/kit/extras", { template_id: Number(root.dataset.templateId), ptav_ids: ids, door, qty: Number(qtyInput && qtyInput.value) || 1 })
                .then((r) => {
                    if (my !== seq) return;
                    out.innerHTML = "";
                    if (r.error) { out.appendChild(el("div", { class: "text-danger", text: r.error })); return; }
                    out.appendChild(el("div", { text: "Kit: " + money(r.kit_price) }));
                    r.extras.forEach((x) => out.appendChild(el("div", { text: x.label + ": " + x.name + " - " + money(x.unit_price * x.qty) })));
                    r.notes.concat(warn).forEach((n) => out.appendChild(el("div", { class: "text-warning-emphasis", text: n })));
                    door.spring_warnings.forEach((n) => out.appendChild(el("div", { class: "text-danger", text: "⚠ " + n })));
                    out.appendChild(el("div", { class: "fw-bold mt-1", text: "Kit + extras: " + money(r.unit_price) + " each" }));
                })
                .catch((e) => { if (my === seq) out.textContent = e.message; });
        }

        [wFt, wIn, hFt, hIn, weight, hl, track, lift].forEach((i) => i.addEventListener("change", refresh));
        scope.addEventListener("change", (ev) => { if (!root.contains(ev.target)) refresh(); });
        update();
    }

    function boot() {
        const root = document.getElementById("aa_kit_door");
        if (root && !root.dataset.aaReady) {
            root.dataset.aaReady = "1";
            init(root);
        }
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
    else boot();
})();
