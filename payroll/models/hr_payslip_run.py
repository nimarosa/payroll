# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re

from dateutil.relativedelta import relativedelta
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

# The period, as written in the default name of a batch.
PERIOD_FORMAT = "%m/%Y"
PERIOD_KEY = "%(period)s"
PERIOD_PATTERN = r"\d{2}/\d{4}"

# A payslip in one of these states expects nothing more from its batch.
SETTLED_SLIP_STATES = ("done", "cancel")
# The ones "Compute All" and "Confirm All" go through.
PENDING_SLIP_STATES = ("draft", "verify")


class HrPayslipRun(models.Model):
    _name = "hr.payslip.run"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Payslip Batches"
    _order = "id desc"

    name = fields.Char(
        required=True,
        readonly=True,
        default=lambda self: self._get_default_name(),
    )
    slip_ids = fields.One2many(
        "hr.payslip",
        "payslip_run_id",
        string="Payslips",
        readonly=True,
    )
    state = fields.Selection(
        [("draft", "Draft"), ("close", "Close")],
        string="Status",
        index=True,
        readonly=True,
        copy=False,
        tracking=1,
        default="draft",
    )
    stage = fields.Selection(
        [
            ("draft", "Draft"),
            ("progress", "In Progress"),
            ("confirmed", "Confirmed"),
            ("close", "Closed"),
        ],
        compute="_compute_stage",
        store=True,
        help="Draft: the batch has no payslips yet. In Progress: some payslips "
        "are not confirmed yet. Confirmed: every payslip is confirmed (or "
        "cancelled). Closed: the batch has been closed.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        copy=False,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    date_start = fields.Date(
        string="Date From",
        required=True,
        readonly=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )
    date_end = fields.Date(
        string="Date To",
        required=True,
        readonly=True,
        default=lambda self: fields.Date.today().replace(day=1)
        + relativedelta(months=+1, day=1, days=-1),
    )
    credit_note = fields.Boolean(
        readonly=True,
        help="If its checked, indicates that all payslips generated from here "
        "are refund payslips.",
    )
    slip_count = fields.Integer(
        compute="_compute_slip_count", string="Number of Payslips"
    )
    draft_slip_count = fields.Integer(
        string="Payslips to Compute", compute="_compute_pending_slip_counts"
    )
    verify_slip_count = fields.Integer(
        string="Payslips to Confirm", compute="_compute_pending_slip_counts"
    )
    net_total = fields.Monetary(
        compute="_compute_net_total",
        store=True,
        help="Sum of the net wages of the payslips of the batch, cancelled "
        "ones excluded. A payslip that is not computed yet adds nothing.",
    )
    struct_id = fields.Many2one(
        "hr.payroll.structure",
        string="Structure",
        readonly=True,
        help="Defines the rules that have to be applied to this payslip batch, "
        "accordingly to the contract chosen. If you let empty the field "
        "contract, this field isn't mandatory anymore and thus the rules "
        "applied will be all the rules set on the structure of all contracts "
        "of the employee valid for the chosen period",
    )

    @api.model
    def _get_name_template(self):
        """The default name of a batch; ``%(period)s`` is its month."""
        return _("Payslip Batch %(period)s")

    @api.model
    def _get_default_name(self, date_start=None):
        date_start = date_start or self.env.context.get("default_date_start")
        date_start = fields.Date.to_date(date_start) or fields.Date.context_today(self)
        return self._get_name_template() % {
            "period": date_start.strftime(PERIOD_FORMAT)
        }

    @api.model
    def _is_default_name(self, name):
        """Whether ``name`` has the exact shape of a default name."""
        pattern = re.escape(self._get_name_template()).replace(
            re.escape(PERIOD_KEY), PERIOD_PATTERN
        )
        return bool(re.fullmatch(pattern, name or ""))

    @api.onchange("date_start")
    def _onchange_date_start_name(self):
        """The name follows the period for as long as nobody typed one."""
        for run in self:
            if run.date_start and (not run.name or run._is_default_name(run.name)):
                run.name = run._get_default_name(run.date_start)

    @api.depends("slip_ids")
    def _compute_slip_count(self):
        for payslip_run in self:
            payslip_run.slip_count = len(payslip_run.slip_ids)

    @api.depends("state", "slip_ids.state")
    def _compute_stage(self):
        for run in self:
            live = run.slip_ids.filtered(lambda slip: slip.state != "cancel")
            if run.state == "close":
                run.stage = "close"
            elif not live:
                run.stage = "draft"
            elif all(slip.state in SETTLED_SLIP_STATES for slip in live):
                run.stage = "confirmed"
            else:
                run.stage = "progress"

    @api.depends("slip_ids.state")
    def _compute_pending_slip_counts(self):
        for run in self:
            states = run.slip_ids.mapped("state")
            run.draft_slip_count = states.count("draft")
            run.verify_slip_count = states.count("verify")

    @api.depends("slip_ids.state", "slip_ids.net_wage")
    def _compute_net_total(self):
        for run in self:
            live = run.slip_ids.filtered(lambda slip: slip.state != "cancel")
            run.net_total = sum(live.mapped("net_wage"))

    def action_open_payslips(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("payroll.hr_payslip_action")
        action["domain"] = [("payslip_run_id", "=", self.id)]
        action["context"] = {"default_payslip_run_id": self.id}
        return action

    def draft_payslip_run(self):
        return self.write({"state": "draft"})

    def close_payslip_run(self):
        return self.write({"state": "close"})

    def action_compute_all(self):
        """Compute every pending payslip of the batch, one by one."""
        self.ensure_one()
        return self._run_on_pending_slips(
            "compute_sheet", _("Compute All"), _("%s payslips computed.")
        )

    def action_confirm_all(self):
        """Confirm every pending payslip of the batch, one by one."""
        self.ensure_one()
        return self._run_on_pending_slips(
            "action_payslip_done", _("Confirm All"), _("%s payslips confirmed.")
        )

    def _run_on_pending_slips(self, method, title, done):
        """Call ``method`` on each pending payslip, each in its own savepoint.

        One payslip at a time, so that a single broken rule or missing value
        does not leave a whole batch unprocessed: the payslips that work move
        on, the others are named with their error in the notification and in
        the chatter. Only ``UserError`` is caught, as it is how a data problem
        is reported; a missing access right is not one, and anything else is
        a bug that has to surface.
        """
        self.ensure_one()
        slips = self.slip_ids.filtered(
            lambda slip: slip.state in PENDING_SLIP_STATES
        ).sorted(lambda slip: (slip.employee_id.name or "", slip.id))
        if not slips:
            raise UserError(
                _("The batch %s has no pending payslips.", self.display_name)
            )
        failures = []
        for slip in slips:
            try:
                with self.env.cr.savepoint():
                    getattr(slip, method)()
            except AccessError:
                raise
            except UserError as error:
                _logger.info(
                    "%s failed on payslip %s of batch %s: %s",
                    method,
                    slip.id,
                    self.id,
                    error,
                )
                failures.append(
                    (slip, str(error.args[0]) if error.args else str(error))
                )
        if not failures:
            return self._get_batch_notification(title, done % len(slips), "success")
        lines = [f"{slip.employee_id.name}: {message}" for slip, message in failures]
        summary = _(
            "%(ok)s of %(total)s payslips ready. %(failed)s failed:",
            ok=len(slips) - len(failures),
            total=len(slips),
            failed=len(failures),
        )
        items = Markup("").join(Markup("<li>%s</li>") % escape(line) for line in lines)
        self.message_post(
            body=Markup("<p><b>%s</b>: %s</p><ul>%s</ul>") % (title, summary, items)
        )
        return self._get_batch_notification(
            title, "\n".join([summary, *lines]), "warning", sticky=True
        )

    def _get_batch_notification(self, title, message, notification_type, sticky=False):
        """A notification that reloads the form once it is dismissed."""
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": notification_type,
                "sticky": sticky,
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }
