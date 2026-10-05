from odoo import api, fields, models
from odoo.exceptions import AccessError

from .common import (
    APPROVER,
    CONFIRMING,
    LEVELS,
    PREPARER,
    REFUNDING,
    STAMPING,
    apply_button_groups,
    check_payroll_access,
    is_superuser,
)

# Minimum level per state button. The stock buttons get their groups in
# views/hr_payslip_views.xml; this map also covers copies other modules add
# under the same method name (e.g. a second "Confirm"), which would
# otherwise show to everybody.
PAYSLIP_BUTTON_GROUPS = {
    "action_payslip_done": LEVELS[APPROVER],
    "refund_sheet": LEVELS[APPROVER],
    "compute_sheet": LEVELS[PREPARER],
    "action_payslip_draft": LEVELS[PREPARER],
    "action_payslip_cancel": LEVELS[PREPARER],
    "onchange_employee": LEVELS[PREPARER],
}


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    computed_by_id = fields.Many2one(
        "res.users",
        string="Computed by",
        readonly=True,
        copy=False,
        help="Who last computed this payslip. With the four-eyes option, "
        "that person cannot confirm it.",
    )

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        return apply_button_groups(arch, PAYSLIP_BUTTON_GROUPS), view

    # Guards ------------------------------------------------------------------

    def _check_leaving_done(self, action):
        """Anything that takes a payslip out of `done` is an approver's call."""
        level = APPROVER if self.filtered(lambda s: s.state == "done") else PREPARER
        check_payroll_access(self.env, level, action)

    def _check_four_eyes(self):
        """With the company option on, whoever computed a payslip cannot
        confirm it. A payslip nobody computed yet would be computed by the
        confirmation itself, so it is refused too. Refund copies are exempt:
        they mirror an already approved payslip."""
        if self.env.su or is_superuser(self.env):
            return
        user = self.env.user
        for slip in self.sudo():
            if not (slip.company_id or self.env.company).payroll_four_eyes:
                continue
            if REFUNDING.get() and slip.credit_note:
                continue
            if slip.computed_by_id == user:
                raise AccessError(
                    self.env._(
                        "Four eyes: you computed the payslip %(slip)s, so someone "
                        "else has to confirm it.",
                        slip=slip.display_name,
                    )
                )
            if not slip.computed_by_id:
                raise AccessError(
                    self.env._(
                        "Four eyes: nobody is recorded as having computed the "
                        "payslip %(slip)s. Someone else has to compute it "
                        "before you confirm it.",
                        slip=slip.display_name,
                    )
                )

    # Transitions -------------------------------------------------------------

    def compute_sheet(self):
        check_payroll_access(self.env, PREPARER, self.env._("Computing payslips"))
        res = super().compute_sheet()
        confirming = CONFIRMING.get()
        to_stamp = self.filtered(lambda slip: slip.id not in confirming)
        if to_stamp:
            token = STAMPING.set(True)
            try:
                to_stamp.write({"computed_by_id": self.env.uid})
            finally:
                STAMPING.reset(token)
        return res

    def action_payslip_done(self):
        check_payroll_access(self.env, APPROVER, self.env._("Confirming payslips"))
        self._check_four_eyes()
        token = CONFIRMING.set(CONFIRMING.get() | frozenset(self.ids))
        try:
            return super().action_payslip_done()
        finally:
            CONFIRMING.reset(token)

    def refund_sheet(self):
        check_payroll_access(self.env, APPROVER, self.env._("Refunding payslips"))
        token = REFUNDING.set(True)
        try:
            return super().refund_sheet()
        finally:
            REFUNDING.reset(token)

    def action_payslip_cancel(self):
        self._check_leaving_done(self.env._("Cancelling confirmed payslips"))
        return super().action_payslip_cancel()

    def action_payslip_draft(self):
        self._check_leaving_done(self.env._("Resetting payslips to draft"))
        return super().action_payslip_draft()

    def write(self, vals):
        if not self.env.su:
            if "computed_by_id" in vals and not STAMPING.get():
                raise AccessError(
                    self.env._(
                        "Who computed a payslip is recorded by the computation itself."
                    )
                )
            if "state" in vals:
                self._check_state_write(vals["state"])
        return super().write(vals)

    def _check_state_write(self, new_state):
        """The RPC path: `write({'state': ...})` must not skip the buttons'
        guards (a write rule is evaluated on the rows before the change)."""
        if new_state == "done" or self.filtered(lambda s: s.state == "done"):
            check_payroll_access(
                self.env, APPROVER, self.env._("Confirming or reopening payslips")
            )
            if new_state == "done":
                pending = self.filtered(lambda s: s.id not in CONFIRMING.get())
                pending._check_four_eyes()
        else:
            check_payroll_access(
                self.env, PREPARER, self.env._("Changing the state of payslips")
            )
