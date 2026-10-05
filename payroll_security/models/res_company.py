from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    payroll_four_eyes = fields.Boolean(
        string="Payroll: four eyes",
        help="Whoever computes a payslip cannot confirm it, nor close a batch "
        "holding payslips they computed.",
    )
