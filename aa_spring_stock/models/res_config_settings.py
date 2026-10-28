"""THE TWO NUMBERS BEHIND "DAYS LEFT", as settings rather than as code.

Owner, 2026-10-28: *"send a warning somewhere that at the current pace of
orders being made we will likely run out of material in x amount of days."*

Both halves of that sentence are judgements, not facts:

  * **HOW FAR BACK "THE CURRENT PACE" REACHES.** Too short and one big dealer
    order makes the shop look like it is running out; too long and a busy
    fortnight is averaged away into nothing. Thirty days to start with,
    because it spans more than one of his order cycles without reaching back
    into a different season.
  * **HOW FEW DAYS LEFT IS WORTH A WARNING.** He chose FOURTEEN when asked -
    about what it takes to get a steel order placed and delivered. That is
    his supplier's lead time, which changes, and is not a number for me to
    bury in a view.

Read live by the SQL view (`aa.spring.stock.summary`), so changing either one
changes the screen on the next refresh with no module update.
"""

from odoo import fields, models

#: Days of history the pace is measured over.
DEFAULT_PACE_DAYS = 30

#: Days of material left that is worth a warning (owner's choice, 2026-10-28).
DEFAULT_WARN_DAYS = 14


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    aa_spring_pace_days = fields.Integer(
        string="Measure the spring pace over (days)",
        default=DEFAULT_PACE_DAYS,
        config_parameter="aa_spring_stock.pace_days",
        help="How far back to look when working out how much coil is being "
             "used per day. Shorter reacts faster and is noisier; longer is "
             "steadier and slower to notice a change.")
    aa_spring_runout_warn_days = fields.Integer(
        string="Warn when spring material is under (days)",
        default=DEFAULT_WARN_DAYS,
        config_parameter="aa_spring_stock.runout_warn_days",
        help="A wire and I.D. with fewer than this many days of coil left, at "
             "the current pace, is flagged Running Out on Inventory > "
             "Springs > Spring Inventory. Set it to about how long a steel "
             "order takes to arrive.")
