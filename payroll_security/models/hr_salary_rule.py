from odoo import api, fields, models

# The context that turns every mail.thread side effect off on create.
NO_THREAD = {
    "tracking_disable": True,
    "mail_create_nosubscribe": True,
    "mail_create_nolog": True,
    "mail_notrack": True,
}


class HrSalaryRule(models.Model):
    """Config changes are audited in the chatter: the administrator is the
    top of the chain, and the control over them is the record of what they
    changed, not a permission."""

    _name = "hr.salary.rule"
    _inherit = ["hr.salary.rule", "mail.thread"]

    name = fields.Char(tracking=True)
    code = fields.Char(tracking=True)
    active = fields.Boolean(tracking=True)
    category_id = fields.Many2one(tracking=True)
    quantity = fields.Char(tracking=True)
    condition_select = fields.Selection(tracking=True)
    condition_python = fields.Text(tracking=True)
    condition_range = fields.Char(tracking=True)
    condition_range_min = fields.Float(tracking=True)
    condition_range_max = fields.Float(tracking=True)
    amount_select = fields.Selection(tracking=True)
    amount_fix = fields.Float(tracking=True)
    amount_percentage = fields.Float(tracking=True)
    amount_percentage_base = fields.Char(tracking=True)
    amount_python_compute = fields.Text(tracking=True)


class HrPayslipLine(models.Model):
    """`hr.payslip.line` is a prototype copy of `hr.salary.rule` (its `_inherit`
    with another `_name`), so it inherits the mail.thread added above. A
    computed line is not a document anybody follows: without this, every
    compute would subscribe the user to each line and track its values."""

    _inherit = "hr.payslip.line"

    @api.model_create_multi
    def create(self, vals_list):
        return super(HrPayslipLine, self.with_context(**NO_THREAD)).create(vals_list)

    def _track_get_fields(self):
        return set()
