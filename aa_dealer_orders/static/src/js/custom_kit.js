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

// What the Add to Cart button says it is waiting for while the kit is empty.
const EMPTY_KIT = "Choose at least one part before adding this kit to your cart.";

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
        // "" means every part in whatever colour it is listed in.
        this.colour = "";
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

    get categories() {
        // ONE LIST PER CATEGORY (owner, 2026-10-20): "so there would be one
        // list for hinges, one for shafts, and so on. That way the customer
        // wont have to scroll through a giant list".
        //
        // GROUPED BY ID, LABELLED BY NAME: two categories under different
        // parents can both be called Hinges, and they are not the same shelf.
        const groups = new Map();

        for (const part of this.parts) {
            // THE LABEL IS A GOOD ENOUGH KEY on its own if the server sent no
            // key, so an older payload still splits by category instead of
            // piling everything onto one shelf.
            const key = part.category_id || part.category || "none";

            if (!groups.has(key)) {
                groups.set(key, {
                    key, label: part.category || "Other parts", parts: [],
                });
            }

            groups.get(key).parts.push(part);
        }

        // A-Z, and the parts we have no category for last whatever they are
        // called - a shelf of leftovers belongs at the bottom.
        const last = (group) => group.key === "none" || !group.label;

        return [...groups.values()].sort((a, b) =>
            (last(a) - last(b)) || a.label.localeCompare(b.label));
    }

    colourLabels() {
        // The finishes this catalogue actually sells, commonest first, counted
        // over the parts that come in more than one. A product whose colour is
        // in its name has a single variant and no finish to offer, so it is
        // not counted and the kit colour cannot move it.
        //
        // THE FINISH, NOT THE LABEL. A label names the whole variant - "#3
        // Black" - because the per-part dropdown has to be readable now that
        // a hinge is one product with 25 variants. Counting labels here put
        // every size of every colour in this box: owner, 2026-10-22, "showing
        // a lot of options when it should only show 3".
        const counts = new Map();

        for (const part of this.parts) {
            if (part.colours.length < 2) {
                continue;
            }

            for (const colour of part.colours) {
                if (colour.finish) {
                    counts.set(colour.finish, (counts.get(colour.finish) || 0) + 1);
                }
            }
        }

        return [...counts.entries()]
            .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
            .map(([label]) => label);
    }

    variantFor(part, fallbackId) {
        // The kit colour where this part comes in it, and otherwise whatever
        // it already was - a part that is only made in galvanised stays
        // galvanised rather than disappearing from the kit.
        if (this.colour) {
            // Matched on the FINISH, for the same reason the box lists
            // finishes: "Black" has to find the black one whatever size it is.
            const match = part.colours.find(
                (colour) => colour.finish === this.colour);

            if (match) {
                return match.id;
            }
        }

        return fallbackId === undefined ? part.colours[0].id : fallbackId;
    }

    setColour(label) {
        this.colour = label;
        const moved = new Map();

        for (const [variantId, quantity] of this.chosen) {
            const part = this.partFor(variantId);
            const id = part ? this.variantFor(part, variantId) : variantId;

            // SUMMED, not overwritten: a kit holding the white and the black
            // of one part becomes that many of the one colour.
            moved.set(id, (moved.get(id) || 0) + quantity);
        }

        this.chosen = moved;
        this.rebuildShelves();
        this.draw();
    }

    quantityOf(part) {
        return part.colours.reduce(
            (sum, colour) => sum + (this.chosen.get(colour.id) || 0), 0);
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

        const row = el("div",
            { class: "d-flex align-items-center flex-wrap gap-2 mb-3" });

        // Start from an existing kit, which is the fastest way to a kit for a
        // door we do not have one for.
        const bases = this.data.bases || [];

        if (bases.length) {
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
        }

        // ONE COLOUR FOR THE WHOLE KIT (owner, 2026-10-20: "the build your kit
        // makes it so all items added are white so you should add an option to
        // change the auto added products to a different color").
        //
        // Starting from an existing kit fills the rows from that kit's own
        // parts list, and those are the white ones, so every automatic row
        // came out white and had to be changed one at a time. This moves the
        // lot - and sets what a part is added in from here on.
        const colours = this.colourLabels();

        if (colours.length) {
            row.appendChild(el("label",
                { class: "form-label mb-0 ms-md-3" }, "Color"));
            this.colourSelect = el("select", { class: "form-select w-auto" });
            this.colourSelect.appendChild(el("option", { value: "" }, "As listed"));

            for (const label of colours) {
                this.colourSelect.appendChild(
                    el("option", { value: label }, label));
            }

            this.colourSelect.addEventListener("change",
                () => this.setColour(this.colourSelect.value));
            row.appendChild(this.colourSelect);
            row.appendChild(el("span", { class: "text-muted small" },
                "applies to every part that comes in it"));
        }

        if (row.childNodes.length) {
            this.root.appendChild(row);
        }

        this.root.appendChild(el("div",
            { class: "text-uppercase text-muted small" }, "In your kit"));
        this.list = el("div", { class: "o_aa_custom_parts" });
        this.root.appendChild(this.list);

        this.total = el("div", { class: "fw-bold mt-2" });
        this.root.appendChild(this.total);

        // LOCKED FROM THE START, because a kit begins empty and the first
        // pricing call has not been made yet. Unlocked by the first answer
        // that says a part is in it.
        this.lockAddToCart(true, EMPTY_KIT);

        this.root.appendChild(this.catalogue());
    }

    // --- the catalogue: one list per category ---------------------------------

    catalogue() {
        // A SHELF PER CATEGORY, SHUT UNTIL IT IS ASKED FOR. What was here
        // before was every product in one dropdown, which is exactly the giant
        // list the owner asked to be rid of. Now: Hinges, Shafts, Drums - open
        // one, and only its parts are in front of you.
        const box = el("div", { class: "o_aa_custom_catalogue mt-3" });
        box.appendChild(el("h6", { class: "mb-2" }, "Add parts"));

        // AND A SEARCH ACROSS ALL OF THEM, for the customer who knows the part
        // but not which shelf we keep it on.
        const search = el("input", {
            type: "search", class: "form-control form-control-sm mb-2",
            placeholder: "Search every part…",
        });
        search.addEventListener("input",
            () => this.filter(search.value.trim().toLowerCase()));
        box.appendChild(search);

        this.panels = [];
        this.offers = [];

        for (const category of this.categories) {
            box.appendChild(this.panelFor(category));
        }

        return box;
    }

    panelFor(category) {
        const panel = el("div", { class: "o_aa_custom_category border rounded mb-1" });
        const header = el("button", {
            type: "button",
            class: "o_aa_custom_category_head btn w-100 d-flex align-items-center " +
                   "gap-2 text-start",
        });
        const chevron = el("span", { class: "o_aa_custom_chevron text-muted" }, "▸");
        const badge = el("span", { class: "badge text-bg-primary d-none" });
        header.append(
            chevron,
            el("span", { class: "flex-grow-1 fw-bold" }, category.label),
            badge,
            el("span", { class: "text-muted small" },
                `${category.parts.length} part${category.parts.length === 1 ? "" : "s"}`));

        const body = el("div",
            { class: "o_aa_custom_category_body border-top p-2 d-none" });
        panel.append(header, body);

        const entry = { category, panel, body, badge, chevron, open: false, filled: false };
        header.addEventListener("click", () => this.toggle(entry));
        this.panels.push(entry);

        return panel;
    }

    toggle(entry, force) {
        const open = force === undefined ? !entry.open : force;

        // BUILT THE FIRST TIME IT IS OPENED. A catalogue of a few thousand
        // parts would otherwise be a few thousand rows of markup on a page
        // where most customers want two shelves.
        if (open && !entry.filled) {
            entry.filled = true;

            for (const part of entry.category.parts) {
                entry.body.appendChild(this.offerFor(part));
            }

            this.badges();
        }

        if (force === undefined) {
            // ONE SHELF AT A TIME, which is the whole point of splitting them.
            for (const other of this.panels) {
                if (other !== entry && other.open) {
                    this.toggle(other, false);
                }
            }
        }

        entry.open = open;
        entry.body.classList.toggle("d-none", !open);
        entry.chevron.textContent = open ? "▾" : "▸";
    }

    offerFor(part) {
        const row = el("div",
            { class: "o_aa_custom_offer d-flex align-items-center gap-2 py-1" });
        row.dataset.search = `${part.name} ${part.code}`.toLowerCase();
        row.appendChild(el("span", { class: "flex-grow-1" },
            part.code ? `${part.name} (${part.code})` : part.name));

        // Which colour the Add button adds: the kit colour when this part
        // comes in it. The quantity and the colour can both be changed
        // afterwards, in the kit itself.
        let variantId = this.variantFor(part);

        if (part.colours.length > 1) {
            const colour = el("select",
                { class: "form-select form-select-sm w-auto", "aria-label": "Color" });

            for (const option of part.colours) {
                const node = el("option",
                    { value: String(option.id) }, option.label);

                if (option.id === variantId) {
                    node.setAttribute("selected", "selected");
                }

                colour.appendChild(node);
            }

            colour.addEventListener("change",
                () => { variantId = parseInt(colour.value, 10); });
            row.appendChild(colour);
        }

        const mark = el("span", { class: "badge text-bg-light d-none" });
        row.appendChild(mark);

        const add = el("button",
            { type: "button", class: "btn btn-sm btn-outline-primary" }, "Add");
        add.addEventListener("click",
            () => this.setQuantity(variantId, (this.chosen.get(variantId) || 0) + 1));
        row.appendChild(add);

        this.offers.push({ part, node: mark });

        return row;
    }

    rebuildShelves() {
        // After a colour change, every Add button adds the new colour and
        // every row's dropdown shows it, so the rows that were already built
        // are thrown away and built again.
        this.offers = [];

        for (const entry of this.panels || []) {
            entry.body.innerHTML = "";
            entry.filled = false;

            if (entry.open) {
                entry.filled = true;

                for (const part of entry.category.parts) {
                    entry.body.appendChild(this.offerFor(part));
                }
            }
        }
    }

    filter(term) {
        for (const entry of this.panels) {
            if (!term) {
                entry.panel.classList.remove("d-none");

                // EVERYTHING BACK ON THE SHELF. Without this, the rows a
                // previous search hid stayed hidden, and the shelf opened
                // later looking half empty.
                for (const row of entry.body.querySelectorAll(".o_aa_custom_offer")) {
                    row.classList.remove("d-none");
                }

                this.toggle(entry, false);

                continue;
            }

            if (!entry.filled) {
                this.toggle(entry, true);
            }

            const hitCategory = entry.category.label.toLowerCase().includes(term);
            let matches = 0;

            for (const row of entry.body.querySelectorAll(".o_aa_custom_offer")) {
                const hit = hitCategory || row.dataset.search.includes(term);
                row.classList.toggle("d-none", !hit);
                matches += hit ? 1 : 0;
            }

            // A SHELF WITH NOTHING ON IT GOES AWAY, so a search leaves only
            // the categories that have what was asked for.
            entry.panel.classList.toggle("d-none", !matches);
            this.toggle(entry, Boolean(matches));
        }
    }

    badges() {
        // How many of each part, and of each category, are in the kit - so the
        // shut shelves still say what is on them.
        for (const { part, node } of this.offers || []) {
            const quantity = this.quantityOf(part);
            node.textContent = quantity ? `${quantity} in kit` : "";
            node.classList.toggle("d-none", !quantity);
        }

        for (const entry of this.panels || []) {
            const quantity = entry.category.parts.reduce(
                (sum, part) => sum + this.quantityOf(part), 0);
            entry.badge.textContent = quantity ? String(quantity) : "";
            entry.badge.classList.toggle("d-none", !quantity);
        }
    }

    fillFromBase() {
        this.chosen.clear();
        const id = parseInt(this.baseSelect ? this.baseSelect.value : "", 10);
        const base = (this.data.bases || []).find((b) => b.id === id);

        if (base) {
            for (const [variantId, quantity] of Object.entries(base.parts || {})) {
                const number = parseInt(variantId, 10);
                const part = this.partFor(number);

                // Only what this page actually offers: a kit's BoM can hold
                // parts nobody has ticked, and a row the customer cannot see
                // is a row they cannot remove.
                if (part) {
                    // IN THE KIT'S COLOUR, not the colour the kit we copied
                    // happens to be built in. These are the rows the owner
                    // was changing one at a time.
                    const id = this.variantFor(part, number);
                    this.chosen.set(id, (this.chosen.get(id) || 0) + quantity);
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

        this.badges();
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

    price() {
        // ONE AT A TIME, IN ORDER. Every change used to fire its own call and
        // they raced: the server keeps the last list it is told about, so an
        // older call landing late replaced the kit with an earlier version of
        // itself - and the cart books from exactly that. Chaining them means
        // the call the Add to Cart click waits for is the last one there is.
        this.queue = (this.queue || Promise.resolve())
            .catch(() => {})
            .then(() => this.sendPrice());

        return this.queue;
    }

    lockAddToCart(locked, why) {
        // BOOTSTRAP'S OWN DISABLED STATE, which puts pointer-events: none on
        // the button, so the click cannot happen at all while the kit is in
        // mid-air. No listener of ours sits on Odoo's button; when it is
        // enabled, its click is Odoo's alone.
        const button = document.querySelector("#add_to_cart");

        if (!button) {
            return;
        }

        button.classList.toggle("disabled", Boolean(locked));
        button.setAttribute("aria-disabled", locked ? "true" : "false");

        if (why) {
            button.setAttribute("title", why);
        } else {
            button.removeAttribute("title");
        }
    }

    get partsList() {
        return [...this.chosen].map(([variant_id, quantity]) =>
            ({ variant_id, quantity }));
    }

    async sendPrice() {
        const parts = this.partsList;
        // ON THE PAGE ITSELF, where the Add to Cart request picks it up. This
        // is what the patch at the top of this file reads, and it is written
        // before the call goes out rather than after it comes back: the cart
        // must carry the kit even if this call never lands.
        this.root.dataset.aaParts = JSON.stringify(parts);
        this.lockAddToCart(true, "Saving your kit…");

        try {
            const response = await fetch("/aa/custom-kit/price", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    jsonrpc: "2.0", method: "call",
                    params: { template_id: this.templateId, parts, qty: 1 },
                }),
            });
            const body = await response.json();
            const result = body.result || {};

            if (body.error || !response.ok) {
                throw new Error(body.error ? JSON.stringify(body.error) : response.status);
            }

            this.total.textContent = result.count
                ? `${result.count} part${result.count === 1 ? "" : "s"} — ${CURRENCY(this.symbol, result.total || 0)}`
                : "";
            this.showPrice(result.total || 0);

            // SAID ON THE PAGE when the server would not take something that
            // was offered, instead of a kit that is quietly short.
            const refused = parts.length - (result.count || 0);
            this.warn(refused > 0
                ? `${refused} part${refused === 1 ? "" : "s"} could not be added to this kit.`
                : "");
            // AN EMPTY KIT CANNOT BE ADDED (owner, 2026-10-28: "you shouldnt
            // be able to add the custom kit to the cart when there is nothing
            // on it"). The server refuses it outright - this is so the
            // customer is told before they click rather than after.
            this.lockAddToCart(!result.count, result.count ? "" : EMPTY_KIT);
        } catch (error) {
            // THE BUTTON STAYS LOCKED. The kit is still on the page and still
            // in this browser; what is not certain is that the cart knows
            // about it, and a kit added now would be a box of nothing.
            this.warn("Your kit could not be saved just now - change anything " +
                      "on it, or reload the page, before adding it to the cart.");

            throw error;
        }
    }

    /* THE PRICE AT THE TOP OF THE PAGE FOLLOWS THE KIT.
     *
     * Owner, 2026-10-27: *"the store doesnt detect that items have been added
     * to the kit so it still believes the price is zero."* The button is fixed
     * on the server - see `custom_kit_zero_price.py` - but a page that goes on
     * saying $0.00 while the builder underneath it says $236.91 is still
     * telling the customer something untrue, and it is the headline price they
     * will remember when the cart disagrees.
     *
     * DISPLAY ONLY. Nothing is priced from this: the cart is built on the
     * server from what the session remembers, and this number is read from the
     * answer that same call returned. If the element is not there - a theme, a
     * page somebody has rebuilt in the editor - nothing happens, because a
     * viewer that throws here would take the whole builder down with it.
     */
    showPrice(total) {
        const span = document.querySelector(
            ".product_price .oe_currency_value, .oe_price .oe_currency_value");

        if (!span) {
            return;
        }

        if (this.priceAsBuilt === undefined) {
            this.priceAsBuilt = span.textContent;
        }

        /* Nothing chosen puts back exactly what the page was rendered with,
         * rather than a zero formatted by this file - the server's formatting
         * is the one the rest of the shop uses. */
        span.textContent = total
            ? CURRENCY("", total).trim()
            : this.priceAsBuilt;
    }

    warn(message) {
        if (!this.warning) {
            this.warning = el("div", { class: "text-danger small mt-1" });
            this.total.after(this.warning);
        }

        this.warning.textContent = message || "";
    }
}

// NOTHING TOUCHES THE ADD TO CART CLICK.
//
// WHAT THIS REPLACES, and why, 2026-10-20: the click used to be caught here,
// held while the kit was sent to the server, and then let through on a second,
// synthetic click. The production log shows exactly what that did - dozens of
// POST /aa/custom-kit/price and, in sixteen hours, not one POST
// /shop/cart/add. The click went in and never came out: Odoo 19 binds the
// #add_to_cart handler straight onto that node, and a re-dispatched click
// does not reliably reach it. The kit was never the problem; the button was.
//
// There is nothing to hold the click for anyway. The kit is sent on every
// change, so the server already has it by the time anybody clicks. The one
// gap - a click in the instant between a change and its call landing - is
// closed by DISABLING the button while a call is in flight, which is a thing
// done to our own page rather than to Odoo's event.
function wire(root) {
    return new CustomKitPage(root);
}

// RUN NOW IF THE PAGE IS ALREADY HERE. This bundle is loaded lazily, after
// DOMContentLoaded has been and gone, so a listener for that event is a
// listener that never fires - the builder kept its d-none and the page showed
// only the ordinary product options, which is why the owner reported seeing
// "only the trims" after ticking a part (2026-10-20). kit_page.js next door
// has always done it this way; I did not copy the one line that mattered.
function boot() {
    const root = document.getElementById("aa_custom_kit");

    if (root && !root.dataset.aaReady) {
        root.dataset.aaReady = "1";
        wire(root);
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
} else {
    boot();
}
