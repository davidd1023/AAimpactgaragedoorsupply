import { Interaction } from '@web/public/interaction';
import { registry } from '@web/core/registry';
import { rpc } from '@web/core/network/rpc';

/**
 * THE SLOT PICKER ON THE CHECKOUT PAGE.
 *
 * Two jobs. It saves the day and the window as they are chosen, so nothing
 * depends on the customer pressing anything extra; and it shows or hides
 * itself as the delivery method changes, because the question only applies
 * to an order somebody is coming to collect.
 *
 * THE SERVER DECIDES WHETHER THE SLOT IS GOOD, not this. Every answer carries
 * back the problem, if there is one, from the same method the payment gate
 * uses - so the page cannot tell the customer one thing while the checkout
 * believes another.
 */
export class AAPickupSlot extends Interaction {
    static selector = '#aa_pickup_slot';
    dynamicContent = {
        '#aa_pickup_day': { 't-on-change': this.save },
        '#aa_pickup_window': { 't-on-change': this.save },
    };

    setup() {
        this.dayEl = this.el.querySelector('#aa_pickup_day');
        this.windowEl = this.el.querySelector('#aa_pickup_window');
        this.warningEl = this.el.querySelector('#aa_pickup_warning');
        this.pickupIds = JSON.parse(this.el.dataset.pickupIds || '[]');
    }

    start() {
        this.sync();
        // The delivery radios live outside this element, so the change is
        // watched on the document rather than through dynamicContent.
        const bound = this.sync.bind(this);
        document.addEventListener('change', bound, true);
        this.registerCleanup(
            () => document.removeEventListener('change', bound, true));
    }

    /** Show the question only when the order is being collected. */
    sync(ev) {
        if (ev && ev.target && ev.target.name !== 'o_delivery_radio') {
            return;
        }

        const chosen = document.querySelector(
            'input[name="o_delivery_radio"]:checked');
        const id = chosen ? parseInt(chosen.dataset.dmId, 10) : null;
        const collecting = id !== null && this.pickupIds.includes(id);

        this.el.classList.toggle('d-none', !collecting);
    }

    async save() {
        const result = await this.waitFor(rpc('/shop/pickup_slot', {
            date: this.dayEl.value,
            slot: this.windowEl.value,
        }));

        if (!this.warningEl) {
            return;
        }

        this.warningEl.textContent = result.problem || '';
        this.warningEl.classList.toggle('d-none', !result.problem);
    }
}

registry.category('public.interactions').add('aa_pickup_slots.slot', AAPickupSlot);
