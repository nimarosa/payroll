from odoo import models

from ..models.common import PREPARER, check_payroll_access


class HrPayslipEmployees(models.TransientModel):
    _inherit = "hr.payslip.employees"

    def compute_sheet(self):
        check_payroll_access(self.env, PREPARER, self.env._("Generating payslips"))
        return super().compute_sheet()
