"""What each level sees: state buttons and menus."""

from lxml import etree

from odoo.tests import tagged

from .common import PayrollSecurityCommon

APPROVER_ONLY = {"action_payslip_done", "refund_sheet"}
PREPARER_UP = {"compute_sheet", "action_payslip_draft", "onchange_employee"}


@tagged("post_install", "-at_install")
class TestButtonsPerLevel(PayrollSecurityCommon):
    def _buttons(self, model, user):
        arch = etree.fromstring(
            self.env[model].with_user(user).get_view(view_type="form")["arch"]
        )
        return [node.get("name") for node in arch.iter("button")]

    def test_payslip_buttons(self):
        reader = set(self._buttons("hr.payslip", self.reader))
        self.assertFalse(
            reader & (APPROVER_ONLY | PREPARER_UP | {"action_payslip_cancel"})
        )

        preparer = self._buttons("hr.payslip", self.preparer)
        # Every copy of the approver's buttons is gone, not only OCA's own.
        self.assertFalse(set(preparer) & APPROVER_ONLY)
        self.assertTrue(PREPARER_UP <= set(preparer))
        # Only the cancel for unconfirmed payslips.
        self.assertEqual(preparer.count("action_payslip_cancel"), 1)

        approver = self._buttons("hr.payslip", self.approver)
        self.assertTrue((APPROVER_ONLY | PREPARER_UP) <= set(approver))
        self.assertEqual(approver.count("action_payslip_cancel"), 2)

    def test_payslip_shows_who_computed(self):
        arch = self.env["hr.payslip"].get_view(view_type="form")["arch"]
        self.assertIn('name="computed_by_id"', arch)

    def test_batch_buttons(self):
        generate = str(self.env.ref("payroll.action_hr_payslip_by_employees").id)
        preparer = set(self._buttons("hr.payslip.run", self.preparer))
        self.assertFalse(preparer & {"close_payslip_run", "draft_payslip_run"})
        self.assertIn(generate, preparer)
        # Every copy of "Generate payslips", not only OCA's own.
        reader = self._buttons("hr.payslip.run", self.reader)
        self.assertNotIn(generate, reader)
        approver = set(self._buttons("hr.payslip.run", self.approver))
        self.assertTrue({"close_payslip_run", "draft_payslip_run"} <= approver)

    def test_settings_offer_four_eyes_to_the_administrator(self):
        arch = self.env["res.config.settings"].get_view(view_type="form")["arch"]
        self.assertIn('name="payroll_four_eyes"', arch)


@tagged("post_install", "-at_install")
class TestMenusPerLevel(PayrollSecurityCommon):
    def _visible(self, user):
        menus = self.env["ir.ui.menu"].with_user(user)
        return menus.browse(menus._visible_menu_ids())

    def test_reader_sees_payslips_and_batches_but_not_configuration(self):
        visible = self._visible(self.reader)
        for xmlid in (
            "payroll.payroll_menu_root",
            "payroll.hr_payslip_menu",
            "payroll.hr_payslip_run_menu",
        ):
            with self.subTest(menu=xmlid):
                self.assertIn(self.env.ref(xmlid), visible)
        self.assertNotIn(self.env.ref("payroll.payroll_menu_configuration"), visible)

    def test_configuration_is_for_the_administrator(self):
        menu = self.env.ref("payroll.payroll_menu_configuration")
        self.assertNotIn(menu, self._visible(self.approver))
        self.assertIn(menu, self._visible(self.manager))

    def test_users_outside_payroll_do_not_see_the_app(self):
        self.assertNotIn(
            self.env.ref("payroll.payroll_menu_root"), self._visible(self.plain)
        )
