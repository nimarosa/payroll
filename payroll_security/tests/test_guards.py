"""Every state change checks the role in Python, buttons and RPC alike."""

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import PayrollSecurityCommon


@tagged("post_install", "-at_install")
class TestPayslipGuards(PayrollSecurityCommon):
    def test_reader_cannot_compute(self):
        slip = self._slip()
        with self.assertRaisesRegex(AccessError, "Preparer"):
            slip.with_user(self.reader).compute_sheet()

    def test_preparer_computes_and_is_stamped(self):
        slip = self._slip()
        slip.with_user(self.preparer).compute_sheet()
        self.assertEqual(slip.state, "verify")
        self.assertEqual(slip.computed_by_id, self.preparer)

    def test_preparer_cannot_confirm_by_button_or_rpc(self):
        slip = self._slip()
        slip.with_user(self.preparer).compute_sheet()
        with self.assertRaisesRegex(AccessError, "Approver"):
            slip.with_user(self.preparer).action_payslip_done()
        with self.assertRaisesRegex(AccessError, "Approver"):
            slip.with_user(self.preparer).write({"state": "done"})
        self.assertEqual(slip.state, "verify")

    def test_approver_confirms(self):
        slip = self._slip()
        slip.with_user(self.preparer).compute_sheet()
        slip.with_user(self.approver).action_payslip_done()
        self.assertEqual(slip.state, "done")
        # The recompute inside the confirmation does not make the approver the
        # one who computed.
        self.assertEqual(slip.computed_by_id, self.preparer)

    def test_preparer_cancels_unconfirmed_but_not_confirmed(self):
        slip = self._slip()
        slip.with_user(self.preparer).compute_sheet()
        slip.with_user(self.preparer).action_payslip_cancel()
        self.assertEqual(slip.state, "cancel")
        slip.with_user(self.preparer).action_payslip_draft()
        self.assertEqual(slip.state, "draft")

        done = self._slip()
        done.compute_sheet()
        done.action_payslip_done()
        self.env["ir.config_parameter"].set_param("payroll.allow_cancel_payslips", True)
        with self.assertRaisesRegex(AccessError, "Approver"):
            done.with_user(self.preparer).action_payslip_cancel()
        with self.assertRaisesRegex(AccessError, "Approver"):
            done.with_user(self.preparer).write({"state": "draft"})
        done.with_user(self.approver).action_payslip_cancel()
        self.assertEqual(done.state, "cancel")

    def test_refund_needs_approver(self):
        done = self._slip()
        done.compute_sheet()
        done.action_payslip_done()
        with self.assertRaisesRegex(AccessError, "Approver"):
            done.with_user(self.preparer).refund_sheet()
        done.with_user(self.approver).refund_sheet()
        self.assertTrue(done.refunded_id)
        self.assertEqual(done.refunded_id.state, "done")

    def test_computed_by_cannot_be_forged(self):
        slip = self._slip()
        slip.with_user(self.preparer).compute_sheet()
        with self.assertRaises(AccessError):
            slip.with_user(self.preparer).write({"computed_by_id": self.approver.id})
        self.assertFalse(slip.copy().computed_by_id)

    def test_change_state_wizard_follows_the_same_guards(self):
        slip = self._slip()
        slip.with_user(self.preparer).compute_sheet()
        wizard = (
            self.env["hr.payslip.change.state"]
            .with_user(self.preparer)
            .with_context(active_ids=slip.ids)
            .create({"state": "done"})
        )
        with self.assertRaisesRegex(AccessError, "Approver"):
            wizard.change_state_confirm()
        reader_wizard = (
            self.env["hr.payslip.change.state"]
            .with_user(self.reader)
            .with_context(active_ids=slip.ids)
            .create({"state": "verify"})
        )
        with self.assertRaisesRegex(AccessError, "Preparer"):
            reader_wizard.change_state_confirm()


@tagged("post_install", "-at_install")
class TestBatchGuards(PayrollSecurityCommon):
    def test_generate_payslips_needs_preparer(self):
        run = self._run()
        wizard_model = self.env["hr.payslip.employees"].with_context(active_id=run.id)
        with self.assertRaises(AccessError):
            wizard_model.with_user(self.reader).create(
                {"employee_ids": [(6, 0, self.employee.ids)]}
            ).compute_sheet()
        # An HR officer outside payroll opens the wizard (OCA's ACL) but
        # does not generate: the guard, called directly.
        hr_officer = self._user("sec_hr_officer", "hr.group_hr_user")
        wizard = wizard_model.sudo().create(
            {"employee_ids": [(6, 0, self.employee.ids)]}
        )
        with self.assertRaises(AccessError):
            wizard.with_user(hr_officer).compute_sheet()
        self.assertFalse(run.slip_ids)
        wizard = wizard_model.with_user(self.preparer).create(
            {"employee_ids": [(6, 0, self.employee.ids)]}
        )
        wizard.compute_sheet()
        # Localizations may add eligible employees of their own; ours is in.
        self.assertIn(self.employee, run.slip_ids.employee_id)

    def test_close_and_reopen_need_approver(self):
        run = self._run()
        for method, values in (
            ("close_payslip_run", None),
            ("write", {"state": "close"}),
        ):
            with self.subTest(method=method):
                bound = getattr(run.with_user(self.preparer), method)
                with self.assertRaisesRegex(AccessError, "Approver"):
                    bound(values) if values else bound()
        run.with_user(self.approver).close_payslip_run()
        self.assertEqual(run.state, "close")
        with self.assertRaisesRegex(AccessError, "Approver"):
            run.with_user(self.preparer).draft_payslip_run()
        run.with_user(self.approver).draft_payslip_run()
        self.assertEqual(run.state, "draft")


@tagged("post_install", "-at_install")
class TestFourEyes(PayrollSecurityCommon):
    def test_off_by_default_same_user_computes_and_confirms(self):
        self.assertFalse(self.company.payroll_four_eyes)
        slip = self._slip()
        slip.with_user(self.approver).compute_sheet()
        slip.with_user(self.approver).action_payslip_done()
        self.assertEqual(slip.state, "done")

    def test_on_same_user_is_refused_other_user_passes(self):
        self.company.payroll_four_eyes = True
        slip = self._slip()
        slip.with_user(self.approver).compute_sheet()
        with self.assertRaisesRegex(AccessError, "Four eyes"):
            slip.with_user(self.approver).action_payslip_done()
        with self.assertRaisesRegex(AccessError, "Four eyes"):
            slip.with_user(self.approver).write({"state": "done"})
        slip.with_user(self.approver_2).action_payslip_done()
        self.assertEqual(slip.state, "done")

    def test_on_recompute_by_other_user_moves_the_stamp(self):
        self.company.payroll_four_eyes = True
        slip = self._slip()
        slip.with_user(self.approver).compute_sheet()
        slip.with_user(self.approver_2).compute_sheet()
        self.assertEqual(slip.computed_by_id, self.approver_2)
        slip.with_user(self.approver).action_payslip_done()
        self.assertEqual(slip.state, "done")

    def test_on_never_computed_payslip_is_refused(self):
        self.company.payroll_four_eyes = True
        slip = self._slip()
        with self.assertRaisesRegex(AccessError, "Four eyes"):
            slip.with_user(self.approver).action_payslip_done()

    def test_on_refund_is_not_blocked(self):
        self.company.payroll_four_eyes = True
        slip = self._slip()
        slip.with_user(self.preparer).compute_sheet()
        slip.with_user(self.approver).action_payslip_done()
        slip.with_user(self.approver).refund_sheet()
        self.assertEqual(slip.refunded_id.state, "done")

    def test_on_closing_a_batch_with_own_payslips_is_refused(self):
        self.company.payroll_four_eyes = True
        run = self._run()
        slip = self._slip(payslip_run_id=run.id)
        slip.with_user(self.approver).compute_sheet()
        slip.with_user(self.approver_2).action_payslip_done()
        with self.assertRaisesRegex(AccessError, "Four eyes"):
            run.with_user(self.approver).close_payslip_run()
        run.with_user(self.approver_2).close_payslip_run()
        self.assertEqual(run.state, "close")
