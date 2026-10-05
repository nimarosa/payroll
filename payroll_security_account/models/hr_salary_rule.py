from odoo import fields, models


class HrSalaryRule(models.Model):
    """Where a rule posts is configuration too: tracked in the chatter
    `payroll_security` gives salary rules, next to their formula."""

    _inherit = "hr.salary.rule"

    account_debit = fields.Many2one(tracking=True)
    account_credit = fields.Many2one(tracking=True)
    analytic_account_id = fields.Many2one(tracking=True)
    account_tax_id = fields.Many2one(tracking=True)
