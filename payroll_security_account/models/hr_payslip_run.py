from odoo import api, fields, models
from odoo.exceptions import UserError


class HrPayslipRun(models.Model):
    """`payroll_account` makes `journal_id` required with no per-company
    escape hatch: a company with no general journal at all gets a raw
    NOT NULL violation straight from Postgres the moment a batch is created,
    because the field's own default (the first general journal) resolves to
    nothing. `res.company.payroll_salary_journal_id` gives that default a
    say first, and `create()` turns the remaining gap -- neither the setting
    nor a general journal exists -- into a message that names where to fix
    it, instead of a database error.
    """

    _inherit = "hr.payslip.run"

    journal_id = fields.Many2one(
        default=lambda self: self.env.company._get_payroll_salary_journal()
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("journal_id"):
                continue
            company = self.env["res.company"].browse(
                vals.get("company_id") or self.env.company.id
            )
            journal = company._get_payroll_salary_journal()
            if not journal:
                raise UserError(
                    self.env._(
                        "The company %(company)s has no salary journal set, "
                        "and no general journal to use by default. Choose one "
                        "in Payroll > Configuration > Settings > Accounting > "
                        '"Salary journal".',
                        company=company.display_name,
                    )
                )
            vals["journal_id"] = journal.id
        return super().create(vals_list)
