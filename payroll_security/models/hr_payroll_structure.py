from odoo import fields, models


class HrPayrollStructure(models.Model):
    """Structure changes are audited in the chatter."""

    _name = "hr.payroll.structure"
    _inherit = ["hr.payroll.structure", "mail.thread"]

    name = fields.Char(tracking=True)
    code = fields.Char(tracking=True)
    parent_id = fields.Many2one(tracking=True)
    rule_ids = fields.Many2many(tracking=True)
