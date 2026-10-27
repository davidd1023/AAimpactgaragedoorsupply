# Pickup slots

A pickup day and two-hour window, chosen at checkout, carried through to the
Work Order sheet and the Dispatch list.

Owner, 2026-10-27: *"At checkout, the customer picks a pickup day and time
window, and it shows on the Work Order and in Dispatch. Done when: the chosen
slot appears on the order and the Dispatch list. (Our lead time is 2 labor
days, after those 2 days they choose when to pick up)."*

## The three answers this is built on

Asked, because each one changes what gets built:

**The lead time starts the next working day and takes two whole ones.** An
order placed **Monday** is collectable from **Thursday**; one placed **Friday**
starts Monday and is collectable **Wednesday**. The day the order is placed
never counts - an order placed at ten to five has had none of it.

**Two-hour windows**: 8-10, 10-12, 12-2, 2-4:30. Tight enough to plan the
counter around, wide enough that nobody is late by ten minutes.

**Pickup orders only, and required.** Anything being delivered is never asked.
Anything being collected cannot be paid for without a slot, so nothing reaches
Dispatch blank for somebody to chase by telephone.

## Which delivery methods count as pickup

A checkbox, **"Collected in person"**, on the delivery method:

> Inventory → Configuration → Delivery Methods → open one

It is ticked once at install for anything that already reads as a collection -
`in_store` type, or a name containing *pickup*, *pick up* or *collect* - and is
yours to change after that. **There is no name matching at runtime**: a rule
that cannot be turned off is worse than a box somebody ticks, because the day
"Pickup rate for freight" is added it would start demanding slots with no way
to say no.

## Where the slot appears

| where | what shows |
|---|---|
| Checkout | the question, under the delivery methods, only when collecting |
| Sales order form | **Pickup**, beside the delivery date |
| Sales order list | a **Pickup** column |
| Work Order sheet | a **Pickup** row in the WHEN block, in red like the deadline |
| Dispatch / transfers list | **Pickup Day** and **Pickup** columns, both sortable |
| Transfers filters | *Collected today* and *Being collected* |

### Why the transfer stores its own copy

The Dispatch list is a list of transfers, and the first thing anybody wants to
do with a pickup time is **sort by it** - who is coming this morning. A related
field reaching through `sale_id` cannot be ordered on in the database, so the
day and window are written onto the transfers when the order is confirmed.

The trade: a slot changed after confirmation needs writing to the transfer
again. That is the price of a column that sorts.

## Days the counter is shut

> Website → Configuration → Settings → **Pickup Slots** → Days closed for
> pickup

Comma-separated, as `2026-12-25, 2026-12-26`. They are neither counted towards
the two working days nor offered to a customer. A date somebody mistypes is
ignored rather than raising - a checkout that 500s over a fat-fingered holiday
is a worse fault than a day staying open.

## Notes for whoever changes this

- **The day is checked twice**, in the controller as the customer chooses and
  again at the payment gate, both through `_aa_pickup_problem`. A select box is
  a suggestion, not a constraint; anyone can post that route a Sunday.
- **`_check_cart_is_ready_to_be_paid` is the only place that can enforce it.**
  The checkout page can be skipped, reloaded or posted to directly.
- **The checkout block is always rendered and hidden with a class.** Odoo swaps
  delivery methods without reloading, so a block only rendered when a pickup
  was already chosen would never appear for somebody who picks one afterwards.
- `website_sale_collect` - Odoo's own click-and-collect - is deliberately not
  used. It is not installed, and installing it would reshape the checkout with
  store selection and per-store stock for a question a checkbox answers.
