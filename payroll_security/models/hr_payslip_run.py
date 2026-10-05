from odoo import api, models
from odoo.exceptions import AccessError

from .common import (
    APPROVER,
    LEVELS,
    PREPARER,
    apply_button_groups,
    check_payroll_access,
    is_superuser,
)

# See PAYSLIP_BUTTON_GROUPS in hr_payslip.py.
RUN_BUTTON_GROUPS = {
    "close_payslip_run": LEVELS[APPROVER],
    "draft_payslip_run": LEVELS[APPROVER],
}


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        groups = dict(RUN_BUTTON_GROUPS)
        # "Generate payslips" is an action button: by then its name is the
        # action id. Localizations add a second one ("add payslips").
        generate = self.env.ref(
            "payroll.action_hr_payslip_by_employees", raise_if_not_found=False
        )
        if generate:
            groups[str(generate.id)] = LEVELS[PREPARER]
        return apply_button_groups(arch, groups), view

    def _check_four_eyes_on_close(self):
        """Closing a batch is approving it: with the company option on, nobody
        closes a batch holding a payslip they computed themselves."""
        if self.env.su or is_superuser(self.env):
            return
        user = self.env.user
        for run in self.sudo():
            if not run.company_id.payroll_four_eyes:
                continue
            own = run.slip_ids.filtered(
                lambda slip: slip.state != "cancel" and slip.computed_by_id == user
            )
            if own:
                raise AccessError(
                    self.env._(
                        "Four eyes: you computed %(count)s payslip(s) of the batch "
                        "%(run)s, so someone else has to close it.",
                        count=len(own),
                        run=run.display_name,
                    )
                )

    def close_payslip_run(self):
        check_payroll_access(self.env, APPROVER, self.env._("Closing batches"))
        self._check_four_eyes_on_close()
        return super().close_payslip_run()

    def draft_payslip_run(self):
        check_payroll_access(self.env, APPROVER, self.env._("Reopening batches"))
        return super().draft_payslip_run()

    def write(self, vals):
        if "state" in vals and not self.env.su:
            check_payroll_access(
                self.env, APPROVER, self.env._("Closing or reopening batches")
            )
            if vals["state"] == "close":
                self._check_four_eyes_on_close()
        return super().write(vals)
