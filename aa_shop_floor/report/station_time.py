"""HOW LONG A JOB TAKES, BY WORKER, BY TASK, BY DAY.

Owner, 2026-10-27: *"A dashboard from the timer history: average time per task
type, per worker, per day. Done when: you can see how long Michel takes per
spring order. (Only visible for admins). We already have the history thing in
the shop floor so you only have to make some adjustments so that we can see
more information from it."*

IT READS THE SAME CLOCK THE HISTORY DOES, one level down. The Shop Floor
History lists WORK ORDERS and shows `duration`, which Odoo adds up from the
work order's time log. This reads that log itself - `mrp.workcenter
.productivity`, one entry per start-and-stop - because of one thing the work
order cannot answer: **who**. A work order carries `employee_ids`, a
MANY-TO-MANY, and "how long does Michel take" cannot be grouped out of a
many-to-many. The time log carries `employee_id`, one per entry, which is
exactly the question.

ONE ROW PER WORKER PER JOB, not per button press. Somebody who starts a
spring, breaks for lunch and finishes it after leaves three entries in the
log; three rows would make the average a third of the truth. The rows are
summed back to one per (worker, work order), so an average over them is an
average over JOBS - which is what "how long Michel takes per spring order"
asks.

WHAT IS LEFT OUT, and why:

  * TIMERS STILL RUNNING. A job in progress has a duration that is still
    growing, and averaging it in says a job took however long it is into it.
  * ANYTHING BUT PRODUCTIVE TIME. Odoo logs blocked and down time against the
    same work order through a different loss type; counting a breakdown as
    time Michel took to wind a spring would be a lie about Michel.

THE DAY IS THE DAY THE WORK STARTED, read in UTC. The shop works 7:00 to 4:00
Eastern, which is 11:00 to 20:00 UTC - the same calendar day either way - so
no job lands on the wrong date. A night shift would need a timezone here.
"""

from odoo import fields, models, tools

STATION_KINDS = [
    ("spring", "Spring"),
    ("kit", "Hardware Kit"),
    ("cable", "Lift Cables"),
    ("other", "Other"),
]


class AaStationTime(models.Model):
    _name = "aa.station.time"
    _description = "Station Time"
    _auto = False
    _order = "day desc, employee_id"
    _rec_name = "order_ref"

    employee_id = fields.Many2one(
        "hr.employee", string="Worker", readonly=True)
    workorder_id = fields.Many2one(
        "mrp.workorder", string="Job", readonly=True)
    production_id = fields.Many2one(
        "mrp.production", string="Manufacturing Order", readonly=True)
    workcenter_id = fields.Many2one(
        "mrp.workcenter", string="Station", readonly=True)
    #: FROM THE PRODUCTION, not the work order. `mrp.workorder.product_id`
    #: is computed and not stored, so there is no column to select.
    product_id = fields.Many2one(
        "product.product", string="Product", readonly=True)

    station_kind = fields.Selection(
        STATION_KINDS, string="Task", readonly=True)
    wo_number = fields.Char(string="W/O #", readonly=True)
    order_ref = fields.Char(string="Order", readonly=True)

    day = fields.Date(string="Day", readonly=True)
    started = fields.Datetime(string="Started", readonly=True)

    #: THE HEADLINE. Averaged by default, because the question is "how long
    #: does one take" and every row is one job.
    minutes = fields.Float(
        string="Average time", readonly=True, aggregator="avg",
        help="Minutes this worker spent on this job.")

    #: The same number, added up. "How long does one take" and "how much of
    #: the week went on this" are both real questions and neither answers the
    #: other, so both are measures.
    total_minutes = fields.Float(
        string="Total time", readonly=True, aggregator="sum")

    jobs = fields.Integer(string="Jobs", readonly=True, aggregator="sum")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    min(log.id)                           AS id,
                    log.employee_id                       AS employee_id,
                    log.workorder_id                      AS workorder_id,
                    wo.production_id                      AS production_id,
                    wo.workcenter_id                      AS workcenter_id,
                    prod.product_id                       AS product_id,
                    COALESCE(prod.aa_station_kind, 'other') AS station_kind,
                    prod.aa_wo_number                     AS wo_number,
                    prod.origin                           AS order_ref,
                    min(log.date_start)::date             AS day,
                    min(log.date_start)                   AS started,
                    sum(log.duration)                     AS minutes,
                    sum(log.duration)                     AS total_minutes,
                    1                                     AS jobs
                FROM mrp_workcenter_productivity log
                JOIN mrp_workorder wo
                  ON wo.id = log.workorder_id
                JOIN mrp_production prod
                  ON prod.id = wo.production_id
                JOIN mrp_workcenter_productivity_loss loss
                  ON loss.id = log.loss_id
                JOIN mrp_workcenter_productivity_loss_type kind
                  ON kind.id = loss.loss_id
                WHERE log.employee_id IS NOT NULL
                  AND log.date_end IS NOT NULL
                  AND kind.loss_type = 'productive'
                GROUP BY
                    log.employee_id, log.workorder_id, wo.production_id,
                    wo.workcenter_id, prod.product_id, prod.aa_station_kind,
                    prod.aa_wo_number, prod.origin
            )
        """ % self._table)
