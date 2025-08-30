# Copyright 2025 Open Source Integrators (www.opensourceintegrators.com)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrSalaryRuleTag(models.Model):
    _name = "hr.salary.rule.tag"
    _description = "Salary Rule Tag"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        help=("Code for the tag. If not set the name will be used in uppercase.")
    )
    description = fields.Text(
        translate=True,
        help=(
            "Describe the purpose of this tag and how it should be used "
            "in salary calculations."
        ),
    )
    sequence = fields.Integer(default=10, help="Used to order tags in views")
    active = fields.Boolean(
        default=True,
        help="If unchecked, this tag will be hidden from most views "
        "without being deleted.",
    )
    color = fields.Integer(string="Color Index")
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        help="Company to which this tag belongs",
    )
    salary_rules_ids = fields.Many2many(
        "hr.salary.rule",
        "hr_salary_rule_tag_rel",
        "tag_id",
        "rule_id",
        string="Salary Rules",
        help="Salary rules that use this tag",
    )
    salary_rules_count = fields.Integer(
        compute="_compute_salary_rules_count",
        string="# Rules",
        store=True,
        help="Number of salary rules using this tag",
    )

    _sql_constraints = [
        (
            "name_company_unique",
            "unique(name, company_id)",
            "Tag name must be unique per company!",
        ),
        (
            "code_company_unique",
            "unique(code, company_id)",
            "Tag code must be unique per company!",
        ),
    ]

    @api.depends("salary_rules_ids")
    def _compute_salary_rules_count(self):
        """Compute the number of salary rules using each tag."""
        for tag in self:
            tag.salary_rules_count = len(tag.salary_rules_ids)

    @api.constrains("name")
    def _check_name_valid_identifier(self):
        """Ensure tag name can be used as a Python identifier when converted."""
        for tag in self:
            # Convert to uppercase and replace spaces/special chars with underscores
            identifier = re.sub(r"[^a-zA-Z0-9_]", "_", tag.name.upper())
            # Check if it's a valid Python identifier
            if not identifier.isidentifier():
                raise ValidationError(
                    _(
                        "Tag name '%(name)s' cannot be converted to a valid "
                        "Python identifier. Please use only letters, numbers, "
                        "and underscores, and don't start with a number.",
                        name=tag.name,
                    )
                )

    @api.constrains("code")
    def _check_code_valid_identifier(self):
        """Ensure tag code is a valid Python identifier if provided."""
        for tag in self:
            if tag.code and not tag.code.isidentifier():
                raise ValidationError(
                    _(
                        "Tag code '%(code)s' must be a valid Python identifier. "
                        "Please use only letters, numbers, and underscores, "
                        "and don't start with a number.",
                        code=tag.code,
                    )
                )

    def get_tag_code(self):
        """Return the code to use in salary rule computations."""
        self.ensure_one()
        if self.code:
            return self.code
        # Convert name to valid Python identifier
        return re.sub(r"[^a-zA-Z0-9_]", "_", self.name.upper())
