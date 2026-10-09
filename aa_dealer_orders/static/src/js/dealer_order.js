/** @odoo-module ignore **/
/* AA Dealer Quick Order - plain JS, no framework. Runs only on /dealer/order.
 * Track / lift / drum / panel rules follow the AA Calculator. */
(function () {
    "use strict";

    function rpc(url, params) {
        return fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: params }),
        })
            .then((r) => r.json())
            .then((j) => {
                if (j.error) {
                    const msg = (j.error.data && j.error.data.message) || j.error.message || "Server error";
                    throw new Error(msg);
                }
                return j.result;
            });
    }

    function el(tag, attrs, children) {
        const node = document.createElement(tag);
        Object.entries(attrs || {}).forEach(([k, v]) => {
            if (k === "class") node.className = v;
            else if (k === "text") node.textContent = v;
            else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
            else if (v !== undefined && v !== null && v !== false) node.setAttribute(k, v);
        });
        (children || []).forEach((c) => c && node.appendChild(c));
        return node;
    }

    // ── AA Calculator rules ────────────────────────────────────────────────
    const TRACK_TYPES = [
        ["3-15R", '3" 15R'],
        ["2-15R", '2" 15R'],
        ["2-12R", '2" 12R'],
        ["3-LHR", '3" LHR'],
        ["2-LHR", '2" LHR'],
    ];
    const LIFT_TYPES = [
        ["standard", "Standard"],
        ["highlift", "High Lift"],
    ];
    const STD_DRUMS = ["D400-96", "D400-144", "D525-216"];
    const HL_DRUMS = ["D525-54", "D575-120", "D800-120"];

    // Door height in inches -> number of sections (AA Calculator getPanels).
    function panelsFor(h) {
        if (!h) return null;
        if (h <= 99.625) return 4;
        if (h <= 123.625) return 5;
        if (h <= 147.625) return 6;
        if (h <= 171.625) return 7;
        return 8;
    }
    // Drum the AA Calculator picks for this weight / lift.
    function drumFor(lift, weight, highLift) {
        if (lift === "highlift") {
            if (highLift <= 54 && weight <= 1000) return "D525-54";
            if (weight <= 1000) return "D575-120";
            return "D800-120";
        }
        if (weight <= 530) return "D400-96";
        if (weight <= 750) return "D400-144";
        return "D525-216";
    }

    // Door width in inches -> kit series (AA Calculator hwSeries).
    function seriesFor(w) {
        if (!w) return null;
        if (w <= 144) return "AA-1200";
        if (w <= 194) return "AA-1600";
        if (w <= 220) return "AA-1800";
        return "too-wide";
    }

    function splitInches(total) {
        const ft = Math.floor(total / 12);
        return [ft, Math.round((total - ft * 12) * 1000) / 1000];
    }

    function init(root) {
        const products = JSON.parse(root.dataset.products || "[]");
        const symbol = root.dataset.currencySymbol || "$";
        const linesBox = root.querySelector("#aa_lines");
        const totalEl = root.querySelector("#aa_total");
        const errorEl = root.querySelector("#aa_error");
        const submitBtn = root.querySelector("#aa_submit");
        const lines = [];
        const money = (v) => symbol + Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

        if (!products.length) {
            linesBox.appendChild(el("div", { class: "alert alert-warning", text: "No kits are set up for Quick Order yet. Please contact AA Impact." }));
            submitBtn.disabled = true;
            return;
        }

        function refreshTotal() {
            const total = lines.reduce((s, l) => s + (l.subtotal || 0), 0);
            totalEl.textContent = lines.some((l) => l.subtotal == null) ? money(total) + " *" : money(total);
        }

        function renumber() {
            lines.forEach((l, i) => (l.numEl.textContent = "Door " + (i + 1)));
        }

        function addLine(copyFrom) {
            const line = { subtotal: null, selects: {}, checks: {} };
            const kitSel = el("select", { class: "form-select" },
                products.map((p) => el("option", { value: p.id, text: p.name })));
            const attrsBox = el("div", { class: "row g-2" });
            const optsBox = el("div", { class: "aa-opts" });
            const tag = el("input", { type: "text", class: "form-control", maxlength: "80", placeholder: "e.g. Smith - 16x8" });
            const wFt = el("input", { type: "number", min: "0", class: "form-control", placeholder: "ft" });
            const wIn = el("input", { type: "number", min: "0", max: "11", step: "any", class: "form-control", placeholder: "in" });
            const hFt = el("input", { type: "number", min: "0", class: "form-control", placeholder: "ft" });
            const hIn = el("input", { type: "number", min: "0", max: "11", step: "any", class: "form-control", placeholder: "in" });
            const weight = el("input", { type: "number", min: "0", class: "form-control", placeholder: "lb" });
            const qty = el("input", { type: "number", min: "1", value: "1", class: "form-control" });
            const trackSel = el("select", { class: "form-select form-select-sm" },
                [el("option", { value: "", text: "Select..." })].concat(TRACK_TYPES.map(([v, t]) => el("option", { value: v, text: t }))));
            const liftSel = el("select", { class: "form-select form-select-sm" },
                LIFT_TYPES.map(([v, t]) => el("option", { value: v, text: t })));
            const hlInput = el("input", { type: "number", min: "1", step: "any", class: "form-control form-control-sm", placeholder: "e.g. 24" });
            const hlCol = el("div", { class: "col-6 col-md-3 d-none" }, [
                el("label", { class: "form-label small mb-1", text: "High lift (in)" }), hlInput,
            ]);
            const drumSel = el("select", { class: "form-select form-select-sm" });
            const drumHint = el("div", { class: "small text-muted mt-1" });
            const priceEl = el("div", { class: "aa-price", text: "-" });
            const breakdown = el("div", { class: "small text-muted mt-2 aa-breakdown" });
            // Springs: AA's spring calculator picks them (aaPickSprings); the dealer chooses nothing.
            const spResult = el("div", { class: "small mt-1" });
            const springBox = el("div", { class: "mt-1 d-none aa-springs" }, [
                el("div", { class: "small fw-bold", text: "Springs (calculated by AA's spring calculator)" }),
                spResult,
            ]);
            const kitLabel = el("div", { class: "form-control-plaintext fw-bold py-1", text: "Enter the door width" });
            const woBox = el("div", { class: "alert alert-info py-2 small mb-2 d-none aa-wo-note" });
            line.numEl = el("span", { class: "aa-line-num" });

            const dup = el("button", { type: "button", class: "btn btn-sm btn-outline-secondary", text: "Duplicate", onclick: () => addLine(line) });
            const del = el("button", {
                type: "button", class: "btn btn-sm btn-outline-danger", text: "Remove",
                onclick: () => {
                    if (lines.length === 1) return;
                    lines.splice(lines.indexOf(line), 1);
                    card.remove();
                    renumber();
                    refreshTotal();
                },
            });

            const field = (label, input, cls) =>
                el("div", { class: cls || "col-6 col-md-3" }, [el("label", { class: "form-label small mb-1", text: label }), input]);
            const dim = (label, a, b) =>
                el("div", { class: "col-6 col-md-2 aa-dim" }, [
                    el("label", { class: "form-label small mb-1", text: label }),
                    el("div", { class: "d-flex gap-1" }, [a, b]),
                ]);

            const card = el("div", { class: "card mb-3 aa-line" }, [
                el("div", { class: "card-body" }, [
                    el("div", { class: "d-flex justify-content-between align-items-center mb-2" }, [
                        line.numEl, el("div", { class: "d-flex gap-2" }, [dup, del]),
                    ]),
                    woBox,
                    el("div", { class: "row g-2 mb-2" }, [
                        el("div", { class: "d-none" }, [kitSel]),
                        field("Kit (from width)", kitLabel, "col-12 col-md-4"),
                        field("Door / job tag", tag, "col-12 col-md-4"),
                        field("Quantity", qty, "col-6 col-md-2"),
                        el("div", { class: "col-6 col-md-2 d-flex flex-column justify-content-end align-items-end" }, [
                            el("div", { class: "small text-muted", text: "Line total" }), priceEl,
                        ]),
                    ]),
                    el("div", { class: "row g-2 mb-2" }, [
                        dim("Width", wFt, wIn), dim("Height", hFt, hIn), field("Door weight", weight, "col-6 col-md-2"),
                        el("div", { class: "col-12 col-md-6 small text-muted d-flex align-items-end", text: "Height picks the panels; weight and lift pick the drum. You can still change both." }),
                    ]),
                    el("div", { class: "row g-2 mb-2" }, [
                        field("Track type", trackSel), field("Lift type", liftSel), hlCol,
                    ]),
                    attrsBox,
                    el("div", { class: "mt-2" }, [el("div", { class: "form-label small mb-1 fw-bold", text: "Add to your order" }), optsBox]),
                    springBox,
                    breakdown,
                ]),
            ]);

            function product() {
                return products.find((p) => p.id === Number(kitSel.value));
            }

            function widthIn() {
                return (Number(wFt.value) || 0) * 12 + (Number(wIn.value) || 0);
            }

            // Pick the kit from the width. Returns true when the kit changed.
            function autoKit() {
                const s = seriesFor(widthIn());
                line.kitOk = false;
                if (!s) { kitLabel.textContent = "Enter the door width"; kitLabel.className = "form-control-plaintext text-muted py-1"; return false; }
                if (s === "too-wide") { kitLabel.textContent = "Wider than 18' 4\" - call AA Impact"; kitLabel.className = "form-control-plaintext text-danger fw-bold py-1"; return false; }
                const p = products.find((x) => x.name.startsWith(s));
                if (!p) { kitLabel.textContent = s + " kit not available"; kitLabel.className = "form-control-plaintext text-danger fw-bold py-1"; return false; }
                line.kitOk = true;
                kitLabel.textContent = p.name;
                kitLabel.className = "form-control-plaintext fw-bold py-1";
                if (Number(kitSel.value) === p.id) return false;
                kitSel.value = p.id;
                return true;
            }

            // Kit attributes. Roller Size follows the track size and the kit's Drum
            // follows our drum dropdown, so both stay hidden.
            const HIDDEN = ["Roller Size", "Drum"];
            function buildAttrs() {
                // Keep the options the dealer already ticked when the kit changes (e.g. width).
                const keepChecked = Object.values(line.checks || {}).filter((c) => c.cb.checked).map((c) => c.name);
                attrsBox.innerHTML = "";
                optsBox.innerHTML = "";
                line.selects = {};
                line.checks = {};
                let hasMulti = false;
                product().attributes.forEach((a) => {
                    if (a.multi) {
                        hasMulti = true;
                        a.values.forEach((v) => {
                            const cb = el("input", { type: "checkbox", class: "form-check-input me-1", value: v.id, onchange: price });
                            line.checks[v.id] = { cb, name: v.name };
                            cb.checked = keepChecked.includes(v.name);
                            const extra = v.price_extra ? " (+" + money(v.price_extra) + ")" : "";
                            optsBox.appendChild(el("label", { class: "form-check-label" }, [cb, document.createTextNode(v.name + extra)]));
                        });
                        return;
                    }
                    const sel = el("select", { class: "form-select form-select-sm", onchange: price },
                        a.values.map((v) => el("option", { value: v.id, text: v.name + (v.price_extra ? " (+" + money(v.price_extra) + ")" : "") })));
                    line.selects[a.name] = { sel, values: a.values };
                    const col = el("div", { class: "col-6 col-md-3" }, [el("label", { class: "form-label small mb-1", text: a.name }), sel]);
                    if (a.values.length === 1 || HIDDEN.includes(a.name)) col.classList.add("d-none");
                    attrsBox.appendChild(col);
                    if (a.name === "Panels") {
                        // Our Drum dropdown sits right after Panels.
                        attrsBox.appendChild(el("div", { class: "col-6 col-md-3" }, [
                            el("label", { class: "form-label small mb-1", text: "Drum" }), drumSel, drumHint,
                        ]));
                    }
                });
                if (!line.selects["Panels"]) {
                    attrsBox.appendChild(el("div", { class: "col-6 col-md-3" }, [
                        el("label", { class: "form-label small mb-1", text: "Drum" }), drumSel, drumHint,
                    ]));
                }
                optsBox.parentElement.classList.toggle("d-none", !hasMulti);
            }

            function pickByPrefix(attrName, prefixes) {
                const s = line.selects[attrName];
                if (!s) return false;
                for (const pre of prefixes) {
                    const v = s.values.find((x) => x.name.startsWith(pre));
                    if (v) { s.sel.value = v.id; return true; }
                }
                return false;
            }

            function kitDrums() {
                const s = line.selects["Drum"];
                return s ? s.values.map((v) => v.name) : [];
            }

            // Drums offered for this lift type (standard ones only if the kit has them).
            // High-lift drums only show for High Lift; standard ones only otherwise.
            function drumChoices() {
                const kd = kitDrums();
                const list = liftSel.value === "highlift" ? HL_DRUMS : STD_DRUMS;
                const inKit = list.filter((d) => kd.some((n) => n.startsWith(d)));
                // A kit without high-lift drums set up yet still gets the list (AA swaps the drum).
                return inKit.length ? inKit : list.slice();
            }

            function fillDrums(keep) {
                const choices = drumChoices();
                const cur = drumSel.value;
                drumSel.innerHTML = "";
                choices.forEach((d) => drumSel.appendChild(el("option", { value: d, text: HL_DRUMS.includes(d) ? d + " (High Lift)" : d })));
                if (keep && choices.includes(cur)) drumSel.value = cur;
            }

            function autoDrum() {
                const choices = drumChoices();
                const w = Number(weight.value) || 0;
                const need = drumFor(liftSel.value, w, Number(hlInput.value) || 0);
                let pick = need;
                if (!choices.includes(need)) {
                    // Kit series does not carry that drum: take the next bigger one it has.
                    const order = liftSel.value === "highlift" ? HL_DRUMS : STD_DRUMS;
                    pick = order.slice(order.indexOf(need)).find((d) => choices.includes(d)) || choices[choices.length - 1];
                }
                if (pick) drumSel.value = pick;
            }

            function syncKitDrum() {
                const d = drumSel.value;
                const ok = pickByPrefix("Drum", [d]);
                if (!ok && line.selects["Drum"]) {
                    // High-lift drum is not a kit variant: keep the kit's biggest drum, AA swaps it.
                    const s = line.selects["Drum"];
                    s.sel.value = s.values[s.values.length - 1].id;
                }
                drumHint.textContent = ok ? "" : "This kit has no " + d + " yet: AA swaps the drum.";
            }

            function syncRoller() {
                const t = trackSel.value;
                if (t) pickByPrefix("Roller Size", [t.charAt(0) + '"']);
            }

            function syncLift() {
                hlCol.classList.toggle("d-none", liftSel.value !== "highlift");
            }

            function heightIn() {
                return (Number(hFt.value) || 0) * 12 + (Number(hIn.value) || 0);
            }

            function autoPanels() {
                const p = panelsFor(heightIn());
                if (p) pickByPrefix("Panels", [p + " Panel"]);
            }

            function refreshDrum() {
                fillDrums(false);
                autoDrum();
                syncKitDrum();
            }

            function springsChecked() {
                return Object.values(line.checks).some((c) => c.name === "Springs" && c.cb.checked);
            }

            // Spring spec from the Spring Engineering model (spring_bridge.js).
            function springSpec() {
                springBox.classList.toggle("d-none", !springsChecked());
                spResult.innerHTML = "";
                if (!springsChecked()) return null;
                if (typeof window.aaSpringCalc !== "function") {
                    spResult.textContent = "Spring calculator not available.";
                    return null;
                }
                let r;
                try {
                    r = window.aaPickSprings({
                        liftType: liftSel.value, highLift: Number(hlInput.value) || 0, trackType: trackSel.value,
                        drum: drumSel.value, widthIn: widthIn(), heightIn: heightIn(), weight: Number(weight.value) || 0,
                    });
                } catch (e) {
                    r = { error: "Could not calculate the springs." };
                }
                if (r.error) {
                    spResult.appendChild(el("div", { class: "text-warning-emphasis", text: r.error }));
                    line.springWarnings = [];
                    return null;
                }
                const n = r.spec.springs;
                r.spec.springsSpec.forEach((x) => spResult.appendChild(el("div", {
                    text: (x.role === "Spring" ? n + " x " : n + " x " + x.role + ": ") + x.wire + '" wire, ' + x.id + '" ID, ' + x.length + '" long',
                })));
                r.warnings.forEach((w) => spResult.appendChild(el("div", {
                    class: w.severity === "red" ? "text-danger" : "text-warning-emphasis", text: "\u26A0 " + w.message,
                })));
                line.springWarnings = r.warnings.filter((w) => w.severity === "red").map((w) => w.message);
                return r.spec;
            }

            function ptavIds() {
                const ids = Object.values(line.selects).map((s) => Number(s.sel.value));
                Object.values(line.checks).forEach((c) => c.cb.checked && ids.push(Number(c.cb.value)));
                return ids;
            }

            let seq = 0;
            function price() {
                const my = ++seq;
                line.subtotal = null;
                if (!line.kitOk) { priceEl.textContent = "-"; refreshTotal(); return; }
                priceEl.textContent = "...";
                rpc("/dealer/order/price", { template_id: product().id, ptav_ids: ptavIds(), qty: Number(qty.value) || 1, line: line.payload() })
                    .then((r) => {
                        if (my !== seq) return;
                        breakdown.innerHTML = "";
                        if (r.error) { priceEl.textContent = "-"; priceEl.title = r.error; }
                        else {
                            line.subtotal = r.subtotal;
                            priceEl.textContent = money(r.subtotal);
                            if ((r.extras || []).length || (r.notes || []).length) {
                                breakdown.appendChild(el("div", { text: "Kit: " + money(r.kit_price) + " each" }));
                                (r.extras || []).forEach((x) => breakdown.appendChild(
                                    el("div", { text: x.label + ": " + x.name + (x.qty > 1 ? " x" + x.qty : "") + " - " + money(x.unit_price) })));
                                (r.notes || []).forEach((n) => breakdown.appendChild(el("div", { class: "text-warning-emphasis", text: n })));
                            }
                        }
                        refreshTotal();
                    })
                    .catch(() => { if (my === seq) priceEl.textContent = "-"; });
            }

            line.payload = () => ({
                template_id: product().id,
                ptav_ids: ptavIds(),
                qty: Number(qty.value) || 0,
                tag: tag.value,
                width: wFt.value || wIn.value ? (wFt.value || 0) + "' " + (wIn.value || 0) + '"' : "",
                height: hFt.value || hIn.value ? (hFt.value || 0) + "' " + (hIn.value || 0) + '"' : "",
                weight: weight.value,
                width_in: widthIn(),
                height_in: heightIn(),
                track_type: trackSel.value,
                lift_type: liftSel.value,
                high_lift: liftSel.value === "highlift" ? hlInput.value : "",
                drum: drumSel.value,
                spring_spec: springSpec(),
                spring_warnings: line.springWarnings || [],
            });
            line.copyInto = (other) => {
                Object.entries(line.inputs).forEach(([k, i]) => (other.inputs[k].value = i.value));
                other.autoKit();
                other.kitSel.value = kitSel.value;
                other.buildAttrs();
                Object.entries(line.selects).forEach(([k, s]) => other.selects[k] && (other.selects[k].sel.value = s.sel.value));
                Object.entries(line.checks).forEach(([k, c]) => other.checks[k] && (other.checks[k].cb.checked = c.cb.checked));
                Object.entries(line.inputs).forEach(([k, i]) => (other.inputs[k].value = i.value));
                other.syncLift();
                other.fillDrums(false);
                other.drumSel.value = drumSel.value;
                other.syncKitDrum();

                other.price();
            };
            line.kitSel = kitSel;
            line.isEmpty = () => !widthIn() && !heightIn() && !weight.value;
            line.remove = () => {
                lines.splice(lines.indexOf(line), 1);
                card.remove();
            };

            // Mark a field the dealer has to look at; the mark goes away once it is changed.
            function flag(input, msg) {
                input.classList.add(msg === "required" ? "is-invalid" : "aa-check");
                if (msg && msg !== "required") input.title = msg;
                const clear = () => { input.classList.remove("is-invalid", "aa-check"); input.removeAttribute("title"); };
                input.addEventListener("change", clear, { once: true });
            }

            // Fill this door from one door of an uploaded work order (wo_reader.py).
            line.fill = (d, wo) => {
                const unsure = d.unsure || [];
                if (d.width_in) { const [f, i] = splitInches(d.width_in); wFt.value = f; wIn.value = i || ""; }
                if (d.height_in) { const [f, i] = splitInches(d.height_in); hFt.value = f; hIn.value = i || ""; }
                qty.value = d.quantity || 1;
                tag.value = ["Mark " + (d.mark || "").replace(/^mark\s*/i, ""), wo.job].filter((x) => x && x.trim() !== "Mark").join(" - ").slice(0, 80);
                liftSel.value = d.lift_type === "highlift" ? "highlift" : "standard";
                hlInput.value = d.lift_type === "highlift" && d.high_lift ? d.high_lift : "";
                trackSel.value = d.track_type || "";
                weight.value = "";

                autoKit();
                buildAttrs();
                syncLift();
                syncRoller();
                autoPanels();
                if (d.track_color) pickByPrefix("Finish Color", [d.track_color]);
                refreshDrum();

                // What the dealer must check.
                flag(weight, "required");
                weight.placeholder = "lb - required";
                if (!d.width_in || unsure.includes("width_in")) { flag(wFt, "Check the width"); flag(wIn, "Check the width"); }
                if (!d.height_in || unsure.includes("height_in")) { flag(hFt, "Check the height"); flag(hIn, "Check the height"); }
                if (!d.track_type || unsure.includes("track_size") || unsure.includes("track_radius")) flag(trackSel, "Check the track type");
                if (unsure.includes("lift_type")) flag(liftSel, "Check the lift type");
                if (d.lift_type === "highlift" && (!d.high_lift || unsure.includes("high_lift_in"))) flag(hlInput, "Check the high lift");
                const colorSel = line.selects["Finish Color"];
                if (colorSel && (!d.track_color || unsure.includes("track_color"))) flag(colorSel.sel, "Check the color");

                const bits = [];
                bits.push("From work order" + (wo.wo_number ? " " + wo.wo_number : "") + (d.mark ? ", Mark " + d.mark.replace(/^mark\s*/i, "") : ""));
                const s = seriesFor(widthIn());
                if (d.series && s && s !== "too-wide" && s !== "AA-" + d.series) bits.push("the WO says series " + d.series + ", the width gives " + s);
                if (d.frame_color) bits.push("frame: " + d.frame_color);
                if (d.notes) bits.push("handwritten: " + d.notes);
                woBox.textContent = bits.join(" \u00B7 ") + ". Check the highlighted fields and enter the weight.";
                woBox.classList.remove("d-none");
                price();
            };

            line.autoKit = autoKit;
            line.buildAttrs = buildAttrs;
            line.price = price;
            line.syncLift = syncLift;
            line.fillDrums = fillDrums;
            line.syncKitDrum = syncKitDrum;
            line.drumSel = drumSel;
            line.inputs = { wFt, wIn, hFt, hIn, weight, qty, trackSel, liftSel, hlInput };

            kitSel.addEventListener("change", () => { buildAttrs(); syncRoller(); autoPanels(); refreshDrum(); price(); });
            [hFt, hIn].forEach((i) => i.addEventListener("change", () => { autoPanels(); price(); }));
            [wFt, wIn].forEach((i) => i.addEventListener("change", () => {
                if (autoKit()) { buildAttrs(); syncRoller(); autoPanels(); refreshDrum(); }
                price();
            }));
            [weight, hlInput].forEach((i) => i.addEventListener("change", () => { autoDrum(); syncKitDrum(); price(); }));
            trackSel.addEventListener("change", () => { syncRoller(); price(); });
            liftSel.addEventListener("change", () => { syncLift(); refreshDrum(); price(); });
            drumSel.addEventListener("change", () => { syncKitDrum(); price(); });
            qty.addEventListener("change", price);

            linesBox.appendChild(card);
            lines.push(line);
            renumber();
            if (copyFrom) copyFrom.copyInto(line);
            else { buildAttrs(); refreshDrum(); price(); }
            return line;
        }

        root.querySelector("#aa_add_line").addEventListener("click", () => addLine());
        addLine();

        // ── Upload a work order PDF: read it on the server, fill one door per Mark ──
        const woFile = root.querySelector("#aa_wo_file");
        const woBtn = root.querySelector("#aa_wo_upload");
        const woStatus = root.querySelector("#aa_wo_status");
        if (woFile && woBtn) {
            woBtn.addEventListener("click", () => woFile.click());
            woFile.addEventListener("change", () => {
                const file = woFile.files && woFile.files[0];
                woFile.value = "";
                if (!file) return;
                woStatus.className = "small w-100 text-muted";
                if (file.size > 20 * 1024 * 1024) { woStatus.className = "small w-100 text-danger"; woStatus.textContent = "The file is too big (20 MB max)."; return; }
                woBtn.disabled = true;
                woStatus.textContent = "Reading " + file.name + "... this takes about half a minute.";
                const reader = new FileReader();
                reader.onload = () => {
                    const b64 = String(reader.result).split(",")[1] || "";
                    rpc("/dealer/order/read_pdf", { pdf_base64: b64 })
                        .then((wo) => {
                            if (wo.error) throw new Error(wo.error);
                            lines.filter((l) => l.isEmpty()).forEach((l) => l.remove());
                            wo.doors.forEach((d) => addLine().fill(d, wo));
                            renumber();
                            refreshTotal();
                            const po = root.querySelector("#aa_po");
                            if (!po.value && wo.wo_number) po.value = "WO " + wo.wo_number.replace(/^\s*WO\s*#?\s*/i, "");
                            const notes = root.querySelector("#aa_notes");
                            const extra = [wo.client && "Client: " + wo.client, wo.job && "Job: " + wo.job, wo.quote_number && "Quote: " + wo.quote_number].filter(Boolean).join(" | ");
                            if (extra && !notes.value.includes(extra)) notes.value = (notes.value ? notes.value + " | " : "") + extra;
                            woStatus.className = "small w-100 text-success";
                            woStatus.textContent = wo.doors.length + (wo.doors.length === 1 ? " door" : " doors") +
                                " filled in from " + file.name + ". Check each door, enter the weights, then place the order.";
                            lines[lines.length - wo.doors.length].inputs.weight.scrollIntoView({ behavior: "smooth", block: "center" });
                        })
                        .catch((e) => { woStatus.className = "small w-100 text-danger"; woStatus.textContent = e.message; })
                        .finally(() => { woBtn.disabled = false; });
                };
                reader.onerror = () => { woBtn.disabled = false; woStatus.className = "small w-100 text-danger"; woStatus.textContent = "Could not open the file."; };
                reader.readAsDataURL(file);
            });
        }

        submitBtn.addEventListener("click", () => {
            errorEl.textContent = "";
            const po = root.querySelector("#aa_po").value.trim();
            if (!po) { errorEl.textContent = "Please enter your PO number."; root.querySelector("#aa_po").focus(); return; }
            const noKit = lines.findIndex((l) => !l.kitOk);
            if (noKit >= 0) { errorEl.textContent = "Door " + (noKit + 1) + ": enter a door width up to 18' 4\"."; return; }
            const noWeight = lines.findIndex((l) => !(Number(l.inputs.weight.value) > 0));
            if (noWeight >= 0) { errorEl.textContent = "Door " + (noWeight + 1) + ": enter the door weight."; lines[noWeight].inputs.weight.focus(); return; }
            const missing = lines.findIndex((l) => !l.payload().track_type);
            if (missing >= 0) { errorEl.textContent = "Door " + (missing + 1) + ": choose the track type."; return; }
            const noHl = lines.findIndex((l) => l.payload().lift_type === "highlift" && !(Number(l.payload().high_lift) > 0));
            if (noHl >= 0) { errorEl.textContent = "Door " + (noHl + 1) + ": enter the high lift in inches."; return; }
            submitBtn.disabled = true;
            submitBtn.textContent = "Placing order...";
            rpc("/dealer/order/submit", {
                po_number: po,
                pickup_date: root.querySelector("#aa_pickup").value || null,
                notes: root.querySelector("#aa_notes").value,
                lines: lines.map((l) => l.payload()),
            })
                .then((r) => {
                    if (r.error) throw new Error(r.error);
                    window.location.href = r.redirect;
                })
                .catch((e) => {
                    errorEl.textContent = e.message;
                    submitBtn.disabled = false;
                    submitBtn.textContent = "Place order — charge to account";
                });
        });
    }

    function boot() {
        const root = document.getElementById("aa_dealer_order");
        if (root && !root.dataset.aaReady) {
            root.dataset.aaReady = "1";
            init(root);
        }
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
    else boot();
})();
