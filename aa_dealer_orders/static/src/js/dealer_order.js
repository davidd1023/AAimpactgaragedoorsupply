/** @odoo-module ignore **/
/* AA Dealer Quick Order - plain JS, no framework. Runs only on /dealer/order. */
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

    // Door height (inches) -> "N Panels" value; weight + height -> drum.
    function panelsFor(heightIn) {
        if (!heightIn) return null;
        if (heightIn <= 99) return 4; // 8'3"
        if (heightIn <= 123) return 5; // 10'3"
        if (heightIn <= 147) return 6; // 12'3"
        if (heightIn <= 171) return 7; // 14'3"
        return 8;
    }
    const DRUMS = ["D400-96", "D400-144", "D525-216"];
    function drumFor(weight, heightIn) {
        if (!weight && !heightIn) return null;
        if ((weight || 0) <= 530 && (heightIn || 0) <= 96) return 0;
        if ((weight || 0) <= 750 && (heightIn || 0) <= 144) return 1;
        return 2;
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
            const wIn = el("input", { type: "number", min: "0", max: "11", class: "form-control", placeholder: "in" });
            const hFt = el("input", { type: "number", min: "0", class: "form-control", placeholder: "ft" });
            const hIn = el("input", { type: "number", min: "0", max: "11", class: "form-control", placeholder: "in" });
            const weight = el("input", { type: "number", min: "0", class: "form-control", placeholder: "lb" });
            const qty = el("input", { type: "number", min: "1", value: "1", class: "form-control" });
            const priceEl = el("div", { class: "aa-price", text: "-" });
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
                    el("div", { class: "row g-2 mb-2" }, [
                        field("Kit", kitSel, "col-12 col-md-4"),
                        field("Door / job tag", tag, "col-12 col-md-4"),
                        field("Quantity", qty, "col-6 col-md-2"),
                        el("div", { class: "col-6 col-md-2 d-flex flex-column justify-content-end align-items-end" }, [
                            el("div", { class: "small text-muted", text: "Line total" }), priceEl,
                        ]),
                    ]),
                    el("div", { class: "row g-2 mb-2" }, [
                        dim("Width", wFt, wIn), dim("Height", hFt, hIn), field("Door weight", weight, "col-6 col-md-2"),
                        el("div", { class: "col-12 col-md-6 small text-muted d-flex align-items-end", text: "Height and weight pick Panels and Drum for you (you can still change them)." }),
                    ]),
                    attrsBox,
                    el("div", { class: "mt-2" }, [el("div", { class: "form-label small mb-1 fw-bold", text: "Add to your order" }), optsBox]),
                ]),
            ]);

            function product() {
                return products.find((p) => p.id === Number(kitSel.value));
            }

            function buildAttrs() {
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
                            const extra = v.price_extra ? " (+" + money(v.price_extra) + ")" : "";
                            optsBox.appendChild(el("label", { class: "form-check-label" }, [cb, document.createTextNode(v.name + extra)]));
                        });
                        return;
                    }
                    const sel = el("select", { class: "form-select form-select-sm", onchange: price },
                        a.values.map((v) => el("option", { value: v.id, text: v.name + (v.price_extra ? " (+" + money(v.price_extra) + ")" : "") })));
                    line.selects[a.name] = { sel, values: a.values };
                    const col = el("div", { class: "col-6 col-md-3" }, [el("label", { class: "form-label small mb-1", text: a.name }), sel]);
                    if (a.values.length === 1) col.classList.add("d-none"); // e.g. "Kit Contents: Included"
                    attrsBox.appendChild(col);
                });
                optsBox.parentElement.classList.toggle("d-none", !hasMulti);
            }

            function pickByPrefix(attrName, prefixes) {
                const s = line.selects[attrName];
                if (!s) return;
                for (const pre of prefixes) {
                    const v = s.values.find((x) => x.name.startsWith(pre));
                    if (v) { s.sel.value = v.id; return; }
                }
            }

            function autoPick() {
                const h = (Number(hFt.value) || 0) * 12 + (Number(hIn.value) || 0);
                const w = Number(weight.value) || 0;
                const panels = panelsFor(h);
                if (panels) pickByPrefix("Panels", [panels + " Panel"]);
                const d = drumFor(w, h);
                if (d !== null) pickByPrefix("Drum", DRUMS.slice(d)); // smallest allowed drum that is big enough
                price();
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
                priceEl.textContent = "...";
                rpc("/dealer/order/price", { template_id: product().id, ptav_ids: ptavIds(), qty: Number(qty.value) || 1 })
                    .then((r) => {
                        if (my !== seq) return;
                        if (r.error) { priceEl.textContent = "-"; priceEl.title = r.error; }
                        else { line.subtotal = r.subtotal; priceEl.textContent = money(r.subtotal); }
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
            });
            line.copyInto = (other) => {
                other.kitSel.value = kitSel.value;
                other.buildAttrs();
                Object.entries(line.selects).forEach(([k, s]) => other.selects[k] && (other.selects[k].sel.value = s.sel.value));
                Object.entries(line.checks).forEach(([k, c]) => other.checks[k] && (other.checks[k].cb.checked = c.cb.checked));
                [["wFt", wFt], ["wIn", wIn], ["hFt", hFt], ["hIn", hIn], ["weight", weight], ["qty", qty]].forEach(([k, i]) => (other.inputs[k].value = i.value));
                other.price();
            };
            line.kitSel = kitSel;
            line.buildAttrs = buildAttrs;
            line.price = price;
            line.inputs = { wFt, wIn, hFt, hIn, weight, qty };

            kitSel.addEventListener("change", () => { buildAttrs(); autoPick(); });
            [wFt, wIn, hFt, hIn, weight].forEach((i) => i.addEventListener("change", autoPick));
            qty.addEventListener("change", price);

            linesBox.appendChild(card);
            lines.push(line);
            renumber();
            if (copyFrom) copyFrom.copyInto(line);
            else { buildAttrs(); price(); }
        }

        root.querySelector("#aa_add_line").addEventListener("click", () => addLine());
        addLine();

        submitBtn.addEventListener("click", () => {
            errorEl.textContent = "";
            const po = root.querySelector("#aa_po").value.trim();
            if (!po) { errorEl.textContent = "Please enter your PO number."; root.querySelector("#aa_po").focus(); return; }
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
