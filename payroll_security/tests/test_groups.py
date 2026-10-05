from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import APPROVER, MANAGER, PAYMENT, PREPARER, READER


@tagged("post_install", "-at_install")
class TestRoleGraph(TransactionCase):
    def _implied(self, xmlid):
        return self.env.ref(xmlid).trans_implied_ids

    def test_reader_is_a_plain_internal_user(self):
        implied = self._implied(READER)
        self.assertIn(self.env.ref("base.group_user"), implied)
        # No HR officer: it would open every employee file, bank account
        # included, to an auditor.
        self.assertNotIn(self.env.ref("hr.group_hr_user"), implied)

    def test_preparer_reads_and_is_hr_officer(self):
        implied = self._implied(PREPARER)
        self.assertIn(self.env.ref(READER), implied)
        self.assertIn(self.env.ref("hr.group_hr_user"), implied)

    def test_payment_is_an_add_on_that_reads(self):
        group = self.env.ref(PAYMENT)
        self.assertIn(self.env.ref(READER), group.trans_implied_ids)
        self.assertEqual(
            group.category_id, self.env.ref("base.module_category_usability")
        )
        # Nobody gets it by implication.
        implying = self.env["res.groups"].search([("implied_ids", "in", group.ids)])
        self.assertFalse(implying)

    def test_payroll_category_is_a_four_level_selection(self):
        category = self.env.ref("payroll.module_category_payroll")
        found = [
            (kind, groups)
            for app, kind, groups, _name in self.env[
                "res.groups"
            ].get_groups_by_application()
            if app == category
        ]
        self.assertEqual(len(found), 1)
        kind, groups = found[0]
        self.assertEqual(kind, "selection")
        self.assertEqual(
            groups.mapped(lambda g: g.get_external_id()[g.id]),
            [READER, PREPARER, APPROVER, MANAGER],
        )
