from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    payroll_salary_journal_id = fields.Many2one(
        "account.journal",
        string="Salary journal",
        domain="[('type', '=', 'general'), ('company_id', '=', id)]",
        help="Journal where payslips and payslip batches are posted. Empty, "
        "the first general journal of the company is used; if there is "
        "none either, creating a batch asks for one before going on.",
    )

    def _get_payroll_salary_journal(self):
        """The journal a payslip or a batch should use when none names one.

        This company's own setting first; OCA `payroll_account`'s own
        default otherwise (the first general journal of the company), so a
        company that never touched the setting sees no change at all. Empty
        when neither resolves -- callers turn that into a message, not a
        silent gap.
        """
        self.ensure_one()
        return self.payroll_salary_journal_id or self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", self.id)], limit=1
        )
