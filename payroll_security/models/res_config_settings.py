from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    payroll_four_eyes = fields.Boolean(
        related="company_id.payroll_four_eyes", readonly=False
    )
