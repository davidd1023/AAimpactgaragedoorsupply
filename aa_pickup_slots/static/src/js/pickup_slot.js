import { Interaction } from '@web/public/interaction';
import { registry } from '@web/core/registry';
import { rpc } from '@web/core/network/rpc';

const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const MONTHS = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
];

/**
 * THE SLOT PICKER ON THE CHECKOUT PAGE.
 *
 * Three jobs:
 *
 *   * a CALENDAR to pick the day from, rather than a list of dates (owner,
 *     2026-10-27). Drawn here from the days the server says are allowed, so a
 *     square that can be clicked is a day that will be accepted - the two
 *     cannot drift apart because there is only one list;
 *   * saving the day and the window as they are chosen, so nothing depends on
 *     the customer pressing anything extra;
 *   * HOLDING THE CHECKOUT BUTTON until both are answered. He found he could
 *     carry on without choosing either: "the customer needs to pick a date and
 *     time before they can confirm their order". The server refuses as well -
 *     a disabled button is a courtesy, not a lock - but being told at the
 *     payment step that you should have answered a question two pages ago is
 *     no way to buy anything.
 */
export class AAPickupSlot extends Interaction {
    static selector = '#aa_pickup_slot';
    dynamicContent = {
        '#aa_pickup_day_button': { 't-on-click': this.toggleCalendar },
        '.aa-times__pick': { 't-on-click': this.chooseTime },
    };

    setup() {
        this.dayEl = this.el.querySelector('#aa_pickup_day');
        this.buttonEl = this.el.querySelector('#aa_pickup_day_button');
        this.calendarEl = this.el.querySelector('#aa_pickup_calendar');
        this.timeEl = this.el.querySelector('#aa_pickup_time');
        this.warningEl = this.el.querySelector('#aa_pickup_warning');

        this.days = JSON.parse(this.el.dataset.days || '[]');
        this.pickupIds = JSON.parse(this.el.dataset.pickupIds || '[]');

        // The month the calendar opens on: the chosen day, else the first one
        // that can be chosen at all.
        const opening = this.dayEl.value || this.days[0] || null;
        this.year = opening ? parseInt(opening.slice(0, 4), 10)
                            : new Date().getFullYear();
        this.month = opening ? parseInt(opening.slice(5, 7), 10) - 1
                             : new Date().getMonth();
    }

    start() {
        this.drawCalendar();
        this.sync();

        // The delivery radios and the checkout button both live outside this
        // element, so they are watched on the document.
        const onChange = this.sync.bind(this);
        const onAway = this.closeIfAway.bind(this);
        document.addEventListener('change', onChange, true);
        document.addEventListener('click', onAway, true);
        this.registerCleanup(() => {
            document.removeEventListener('change', onChange, true);
            document.removeEventListener('click', onAway, true);
        });
    }

    // --- is this order even being collected ------------------------------

    get collecting() {
        const chosen = document.querySelector(
            'input[name="o_delivery_radio"]:checked');
        const id = chosen ? parseInt(chosen.dataset.dmId, 10) : null;

        return id !== null && this.pickupIds.includes(id);
    }

    sync(ev) {
        if (ev && ev.target && ev.target.name !== 'o_delivery_radio') {
            return;
        }

        this.el.classList.toggle('d-none', !this.collecting);
        this.holdTheButton();
    }

    // --- the button they cannot press yet --------------------------------

    /**
     * Disable the checkout button while a collection has no slot.
     *
     * There are two of these in the DOM - one for mobile, one for desktop -
     * so both are handled rather than whichever happens to be showing.
     */
    holdTheButton() {
        const answered = Boolean(this.dayEl.value && this.timeEl.value);
        const hold = this.collecting && !answered;

        for (const button of document.getElementsByName(
                'website_sale_main_button')) {
            button.classList.toggle('disabled', hold);
            button.classList.toggle('pe-none', hold);
            button.setAttribute('aria-disabled', hold ? 'true' : 'false');

            if ('disabled' in button) {
                button.disabled = hold;
            }
        }

        if (this.warningEl && hold) {
            this.warningEl.textContent =
                'Please choose the day and time you will collect this order.';
            this.warningEl.classList.remove('d-none');
        } else if (this.warningEl && !this.warningEl.dataset.fromServer) {
            this.warningEl.classList.add('d-none');
        }
    }

    // --- the calendar -----------------------------------------------------

    toggleCalendar() {
        const open = this.calendarEl.classList.toggle('d-none');
        this.buttonEl.setAttribute('aria-expanded', open ? 'false' : 'true');
    }

    closeIfAway(ev) {
        if (this.calendarEl.classList.contains('d-none')) {
            return;
        }

        if (!this.el.contains(ev.target)) {
            this.calendarEl.classList.add('d-none');
            this.buttonEl.setAttribute('aria-expanded', 'false');
        }
    }

    /** ISO for a day of the month being shown, without timezone arithmetic. */
    iso(day) {
        return `${this.year}-${String(this.month + 1).padStart(2, '0')}`
            + `-${String(day).padStart(2, '0')}`;
    }

    drawCalendar() {
        const first = this.days[0];
        const last = this.days[this.days.length - 1];

        this.calendarEl.replaceChildren();

        const head = document.createElement('div');
        head.className = 'aa-cal__head';

        const back = this.monthButton('‹', -1, first);
        const title = document.createElement('span');
        title.className = 'aa-cal__month';
        title.textContent = `${MONTHS[this.month]} ${this.year}`;
        const forward = this.monthButton('›', 1, last);

        head.append(back, title, forward);

        const grid = document.createElement('div');
        grid.className = 'aa-cal__grid';

        for (const name of DOW) {
            const cell = document.createElement('div');
            cell.className = 'aa-cal__dow';
            cell.textContent = name;
            grid.append(cell);
        }

        // Monday-first, which is how the week reads on a work calendar.
        const starts = (new Date(this.year, this.month, 1).getDay() + 6) % 7;
        const length = new Date(this.year, this.month + 1, 0).getDate();

        for (let blank = 0; blank < starts; blank++) {
            const cell = document.createElement('button');
            cell.type = 'button';
            cell.className = 'aa-cal__day aa-cal__day--empty';
            cell.disabled = true;
            grid.append(cell);
        }

        for (let day = 1; day <= length; day++) {
            const iso = this.iso(day);
            const cell = document.createElement('button');
            cell.type = 'button';
            cell.className = 'aa-cal__day';
            cell.textContent = String(day);
            cell.disabled = !this.days.includes(iso);

            if (iso === this.dayEl.value) {
                cell.classList.add('aa-cal__day--chosen');
            }

            if (!cell.disabled) {
                cell.addEventListener(
                    'click', () => this.chooseDay(iso, day));
            }

            grid.append(cell);
        }

        this.calendarEl.append(head, grid);
    }

    monthButton(glyph, step, bound) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-sm btn-light';
        button.textContent = glyph;
        button.setAttribute(
            'aria-label', step < 0 ? 'Previous month' : 'Next month');

        // Never past the months that hold a selectable day - an empty grid
        // somebody can page into for ever is a dead end.
        const edge = bound
            ? parseInt(bound.slice(0, 4), 10) * 12
              + parseInt(bound.slice(5, 7), 10) - 1
            : null;
        const here = this.year * 12 + this.month;
        button.disabled = edge === null
            || (step < 0 ? here <= edge : here >= edge);

        if (!button.disabled) {
            button.addEventListener('click', () => {
                this.month += step;

                if (this.month < 0) {
                    this.month = 11;
                    this.year -= 1;
                } else if (this.month > 11) {
                    this.month = 0;
                    this.year += 1;
                }

                this.drawCalendar();
            });
        }

        return button;
    }

    /**
     * A time button pressed. The whole open day is on screen as buttons
     * rather than behind a dropdown, so this only has to move the marker.
     */
    chooseTime(ev) {
        const pressed = ev.target.closest('.aa-times__pick');

        if (!pressed) {
            return;
        }

        for (const button of this.el.querySelectorAll('.aa-times__pick')) {
            button.setAttribute('aria-checked',
                button === pressed ? 'true' : 'false');
        }

        this.timeEl.value = pressed.dataset.time;
        this.save();
    }

    chooseDay(iso, day) {
        this.dayEl.value = iso;
        this.buttonEl.textContent =
            `${DOW[(new Date(this.year, this.month, day).getDay() + 6) % 7]}`
            + `, ${day} ${MONTHS[this.month]} ${this.year}`;
        this.calendarEl.classList.add('d-none');
        this.buttonEl.setAttribute('aria-expanded', 'false');
        this.drawCalendar();
        this.save();
    }

    // --- saving -----------------------------------------------------------

    async save() {
        this.holdTheButton();

        const result = await this.waitFor(rpc('/shop/pickup_slot', {
            date: this.dayEl.value,
            time: parseFloat(this.timeEl.value) || 0,
        }));

        if (!this.warningEl) {
            return;
        }

        // A problem the SERVER found outranks the nudge about an unanswered
        // question, and must not be wiped by the next keystroke.
        if (result.problem) {
            this.warningEl.dataset.fromServer = '1';
            this.warningEl.textContent = result.problem;
            this.warningEl.classList.remove('d-none');
        } else {
            delete this.warningEl.dataset.fromServer;
            this.warningEl.classList.add('d-none');
            this.holdTheButton();
        }
    }
}

registry.category('public.interactions').add('aa_pickup_slots.slot', AAPickupSlot);
