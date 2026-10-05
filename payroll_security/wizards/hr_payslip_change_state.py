from odoo import models

from ..models.common import PREPARER, check_payroll_access


class HrPayslipChangeState(models.TransientModel):
    _inherit = "hr.payslip.change.state"

    def change_state_confirm(self):
        # The floor; each target state is then guarded by the payslip method
        # the wizard calls (confirming and leaving `done` need the approver).
        check_payroll_access(
            self.env, PREPARER, self.env._("Changing the state of payslips")
        )
        return super().change_state_confirm()
