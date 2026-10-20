/** @odoo-module **/
// BUILD YOUR OWN KIT (owner, 2026-10-20): "customer can decide almost
// everything and can add and remove things from their kit".
//
// The page starts from a kit that exists - the customer picks which - and then
// every row can be changed, removed, or added to. Quantities and colours are
// per part, which is what was asked for. Springs, tracks and cables are not
// offered: they are sized from a door, and a custom kit exists because the
// door is not one we have a kit for.
//
// WHAT IS CHOSEN IS KEPT ON THE SERVER, not in the form: /aa/custom-kit/price
// prices it and remembers it against the session, and Add to Cart books from
// that. The same arrangement the door box next door uses, for the same reason
// - Odoo's own cart route has nowhere to put a parts list.

const CURRENCY = (symbol, amount) =>
    `${symbol}${amount.toFixed(2)}`;

function el(tag, attrs = {}, text = "") {
    const node = document.createElement(tag);

    for (const [name, value] of Object.entries(attrs)) {
        if (name === "class") {
            node.className = value;
        } else {
            node.setAttribute(name, value);
        }
    }

    if (text) {
        node.textContent = text;
    }

    return node;
}

class CustomKitPage {
    constructor(root) {
        this.root = root;
        this.data = JSON.parse(root.dataset.kit || "{}");
        this.templateId = parseInt(root.dataset.templateId, 10);
        this.symbol = this.data.currency || "$";
        // variant id -> quantity. The whole state of the page.
        this.chosen = new Map();
        this.render();
        this.fillFromBase();
    }

    get parts() {
        return this.data.parts || [];
    }

    partFor(variantId) {
        return this.parts.find((part) =>
            part.colours.some((colour) => colour.id === variantId));
    }

    // --- building the page ---------------------------------------------------

    render() {
        this.root.classList.remove("d-none");
        this.root.innerHTML = "";
        this.root.appendChild(el("h5", { class: "mb-2" }, "Build your kit"));

        if (!this.parts.length) {
            this.root.appendChild(el("div", { class: "alert alert-info" },
                "No parts are offered yet. Tick “Offer in Custom Kit” on the " +
                "products this kit should be built from."));

            return;
        }

        // Start from an existing kit, which is the fastest way to a kit for a
        // door we do not have one for.
        const bases = this.data.bases || [];

        if (bases.length) {
            const row = el("div", { class: "d-flex align-items-center gap-2 mb-3" });
            row.appendChild(el("label", { class: "form-label mb-0" }, "Start from"));
            this.baseSelect = el("select", { class: "form-select w-auto" });
            this.baseSelect.appendChild(el("option", { value: "" }, "Empty kit"));

            for (const base of bases) {
                const count = Object.keys(base.parts || {}).length;
                this.baseSelect.appendChild(el("option", { value: String(base.id) },
                    count ? base.name : `${base.name} (no contents on file)`));
            }

            this.baseSelect.addEventListener("change", () => this.fillFromBase());
            row.appendChild(this.baseSelect);
            this.root.appendChild(row);
        }

        this.list = el("div", { class: "o_aa_custom_parts" });
        this.root.appendChild(this.list);

        const adder = el("div", { class: "d-flex align-items-center gap-2 mt-2" });
        this.picker = el("select", { class: "form-select w-auto" });
        this.picker.appendChild(el("option", { value: "" }, "Add a part…"));
        let group = null;

        for (const part of this.parts) {
            if (part.category !== group) {
                group = part.category;
                this.optGroup = el("optgroup", { label: group || "Parts" });
                this.picker.appendChild(this.optGroup);
            }

            this.optGroup.appendChild(el("option",
                { value: String(part.colours[0].id) },
                part.code ? `${part.name} (${part.code})` : part.name));
        }

        this.picker.addEventListener("change", () => {
            const id = parseInt(this.picker.value, 10);

            if (id) {
                this.setQuantity(id, (this.chosen.get(id) || 0) + 1);
            }

            this.picker.value = "";
        });
        adder.appendChild(this.picker);
        this.root.appendChild(adder);

        this.total = el("div", { class: "fw-bold mt-3" });
        this.root.appendChild(this.total);
    }

    fillFromBase() {
        this.chosen.clear();
        const id = parseInt(this.baseSelect ? this.baseSelect.value : "", 10);
        const base = (this.data.bases || []).find((b) => b.id === id);

        if (base) {
            for (const [variantId, quantity] of Object.entries(base.parts || {})) {
                const number = parseInt(variantId, 10);

                // Only what this page actually offers: a kit's BoM can hold
                // parts nobody has ticked, and a row the customer cannot see
                // is a row they cannot remove.
                if (this.partFor(number)) {
                    this.chosen.set(number, quantity);
                }
            }
        }

        this.draw();
    }

    setQuantity(variantId, quantity) {
        if (quantity > 0) {
            this.chosen.set(variantId, quantity);
        } else {
            this.chosen.delete(variantId);
        }

        this.draw();
    }

    // --- drawing what is in the kit ------------------------------------------

    draw() {
        this.list.innerHTML = "";

        if (!this.chosen.size) {
            this.list.appendChild(el("div", { class: "text-muted" },
                "Nothing in the kit yet — start from a kit above, or add parts below."));
        }

        let group = null;

        for (const [variantId, quantity] of this.chosen) {
            const part = this.partFor(variantId);

            if (!part) {
                continue;
            }

            if (part.category !== group) {
                group = part.category;
                this.list.appendChild(el("div",
                    { class: "text-uppercase text-muted small mt-2" },
                    group || "Parts"));
            }

            this.list.appendChild(this.rowFor(part, variantId, quantity));
        }

        this.price();
    }

    rowFor(part, variantId, quantity) {
        const row = el("div", { class: "d-flex align-items-center gap-2 py-1" });
        row.appendChild(el("span", { class: "flex-grow-1" }, part.name));

        // PER PART (owner's choice): the colours this part actually has. A
        // product whose colour is in its name has one row of its own instead,
        // because that is what it is.
        if (part.colours.length > 1) {
            const colour = el("select", { class: "form-select form-select-sm w-auto" });

            for (const option of part.colours) {
                const node = el("option", { value: String(option.id) }, option.label);

                if (option.id === variantId) {
                    node.setAttribute("selected", "selected");
                }

                colour.appendChild(node);
            }

            colour.addEventListener("change", () => {
                this.chosen.delete(variantId);
                this.setQuantity(parseInt(colour.value, 10), quantity);
            });
            row.appendChild(colour);
        }

        const number = el("input", {
            type: "number", min: "0", step: "1", value: String(quantity),
            class: "form-control form-control-sm", style: "width: 5rem",
        });
        number.addEventListener("change", () =>
            this.setQuantity(variantId, Math.max(0, parseInt(number.value, 10) || 0)));
        row.appendChild(number);

        const remove = el("button",
            { type: "button", class: "btn btn-sm btn-link text-danger", title: "Remove" }, "✕");
        remove.addEventListener("click", () => this.setQuantity(variantId, 0));
        row.appendChild(remove);

        return row;
    }

    // --- pricing, which is also what tells the server what is in the kit ------

    async price() {
        const parts = [...this.chosen].map(([variant_id, quantity]) =>
            ({ variant_id, quantity }));
        const response = await fetch("/aa/custom-kit/price", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                jsonrpc: "2.0", method: "call",
                params: { template_id: this.templateId, parts, qty: 1 },
            }),
        });
        const result = (await response.json()).result || {};

        this.total.textContent = result.count
            ? `${result.count} part${result.count === 1 ? "" : "s"} — ${CURRENCY(this.symbol, result.total || 0)}`
            : "";
    }
}

// THE ADD TO CART BUTTON WAITS FOR THE PRICE CALL, exactly as the door box
// does: the server books from what it was last told, so it has to have been
// told before the cart route runs.
function wire(root) {
    const page = new CustomKitPage(root);
    const button = document.querySelector("#add_to_cart, .js_check_product");

    if (button) {
        button.addEventListener("click", async (event) => {
            if (button.dataset.aaCustomDone) {
                delete button.dataset.aaCustomDone;

                return;
            }

            event.preventDefault();
            event.stopImmediatePropagation();
            await page.price();
            button.dataset.aaCustomDone = "1";
            button.click();
        }, true);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const root = document.getElementById("aa_custom_kit");

    if (root) {
        wire(root);
    }
});
