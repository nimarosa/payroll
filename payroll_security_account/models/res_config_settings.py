from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """The field lives on the company (each one settles through its own
    journal), but nobody looks for a payroll setting on the company form:
    `hr.payslip.run`'s "no journal" error sends the user HERE, next to
    OCA's own `module_payroll_account` toggle."""

    _inherit = "res.config.settings"

    payroll_salary_journal_id = fields.Many2one(
        related="company_id.payroll_salary_journal_id",
        readonly=False,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
    )
