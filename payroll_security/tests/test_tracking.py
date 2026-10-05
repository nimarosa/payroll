"""Configuration changes leave a trail; computed lines do not."""

from odoo.tests import tagged

from .common import PayrollSecurityCommon


@tagged("post_install", "-at_install")
class TestConfigTracking(PayrollSecurityCommon):
    def _flush_tracking(self):
        self.env.flush_all()
        self.env.cr.precommit.run()

    def _tracked(self, record, field):
        return self.env["mail.tracking.value"].search(
            [
                ("mail_message_id.model", "=", record._name),
                ("mail_message_id.res_id", "=", record.id),
                ("field_id.name", "=", field),
            ]
        )

    def test_formula_change_is_tracked_with_old_and_new_value(self):
        # Records created in this transaction are not tracked until the
        # pending tracking of their creation is flushed.
        self._flush_tracking()
        rule = self.rule.with_context(tracking_disable=False)
        rule.with_user(self.manager).write(
            {"amount_python_compute": "result = contract.wage * 2"}
        )
        self._flush_tracking()
        value = self._tracked(rule, "amount_python_compute")
        self.assertEqual(len(value), 1)
        self.assertEqual(value.old_value_text, "result = contract.wage")
        self.assertEqual(value.new_value_text, "result = contract.wage * 2")
        self.assertEqual(value.mail_message_id.author_id, self.manager.partner_id)

    def test_structure_rules_change_is_tracked(self):
        structure = self.structure.with_context(tracking_disable=False)
        other = self.rule.copy({"code": "SECOTHER"})
        self._flush_tracking()
        structure.with_user(self.manager).write({"rule_ids": [(4, other.id)]})
        self._flush_tracking()
        self.assertTrue(self._tracked(structure, "rule_ids"))

    def test_computed_lines_are_not_threads_anybody_follows(self):
        slip = self._slip().with_context(tracking_disable=False)
        slip.with_user(self.preparer).compute_sheet()
        self._flush_tracking()
        lines = slip.line_ids
        self.assertTrue(lines)
        followers = self.env["mail.followers"].search(
            [("res_model", "=", "hr.payslip.line"), ("res_id", "in", lines.ids)]
        )
        messages = self.env["mail.message"].search(
            [("model", "=", "hr.payslip.line"), ("res_id", "in", lines.ids)]
        )
        self.assertFalse(followers)
        self.assertFalse(messages)

    def test_forms_carry_a_chatter(self):
        for model in ("hr.salary.rule", "hr.payroll.structure"):
            with self.subTest(model=model):
                arch = self.env[model].get_view(view_type="form")["arch"]
                self.assertIn("<chatter", arch)
