"""The journal entry of a payslip follows the payroll role, not the accounting
one: an approver with no accounting group confirms and cancels, and the
entry still carries the approver as its author."""

from datetime import date

from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.payroll_security.tests.common import PayrollSecurityCommon

ACCOUNTING_GROUPS = (
    "account.group_account_readonly",
    "account.group_account_invoice",
    "account.group_account_user",
    "account.group_account_manager",
)


class PayrollSecurityAccountCommon(PayrollSecurityCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env["account.account"]
        cls.expense = Account.create(
            {
                "name": "Security salaries",
                "code": "SECEXP01",
                "account_type": "expense",
                "company_ids": [(6, 0, cls.company.ids)],
            }
        )
        cls.payable = Account.create(
            {
                "name": "Security salaries payable",
                "code": "SECPAY01",
                "account_type": "liability_current",
                "company_ids": [(6, 0, cls.company.ids)],
            }
        )
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Security salaries",
                "code": "SECSU",
                "type": "general",
                "company_id": cls.company.id,
                "default_account_id": cls.payable.id,
            }
        )
        rule = cls.rule.with_company(cls.company)
        rule.account_debit = cls.expense
        rule.account_credit = cls.payable
        cls.contract.journal_id = cls.journal

    @classmethod
    def _slip(cls, **values):
        values.setdefault("journal_id", cls.journal.id)
        return super()._slip(**values)

    @classmethod
    def _run(cls, **values):
        values.setdefault("journal_id", cls.journal.id)
        return super()._run(**values)

    def _computed_slip(self, **values):
        slip = self._slip(**values)
        slip.with_user(self.preparer).compute_sheet()
        self.assertEqual(slip.computed_by_id, self.preparer)
        return slip


@tagged("post_install", "-at_install")
class TestConfirmPostsEntry(PayrollSecurityAccountCommon):
    def test_approver_has_no_accounting_rights(self):
        # The premise of every other test here.
        for group in ACCOUNTING_GROUPS:
            with self.subTest(group=group):
                self.assertFalse(self.approver.has_group(group))
        moves = self.env["account.move"].with_user(self.approver)
        self.assertFalse(moves.has_access("create"))

    def test_approver_confirms_and_the_entry_is_theirs(self):
        slip = self._computed_slip()
        slip.with_user(self.approver).action_payslip_done()
        self.assertEqual(slip.state, "done")
        move = slip.move_id
        self.assertTrue(move)
        self.assertEqual(move.state, "posted")
        self.assertEqual(move.create_uid, self.approver)
        self.assertEqual(set(move.line_ids.create_uid.ids), {self.approver.id})
        self.assertEqual(
            set(move.line_ids.account_id.ids),
            {
                self.expense.id,
                self.payable.id,
            },
        )
        self.assertEqual(slip.computed_by_id, self.preparer)

    def test_preparer_cannot_confirm(self):
        slip = self._computed_slip()
        with self.assertRaisesRegex(AccessError, "Approver"):
            slip.with_user(self.preparer).action_payslip_done()
        self.assertEqual(slip.state, "verify")
        self.assertFalse(slip.move_id)

    def test_reader_cannot_confirm(self):
        slip = self._computed_slip()
        with self.assertRaisesRegex(AccessError, "Approver"):
            slip.with_user(self.reader).action_payslip_done()
        self.assertFalse(slip.move_id)

    def test_four_eyes_still_applies(self):
        self.company.payroll_four_eyes = True
        slip = self._slip()
        slip.with_user(self.approver).compute_sheet()
        with self.assertRaisesRegex(AccessError, "Four eyes"):
            slip.with_user(self.approver).action_payslip_done()
        self.assertFalse(slip.move_id)
        slip.with_user(self.approver_2).action_payslip_done()
        self.assertEqual(slip.move_id.create_uid, self.approver_2)

    def test_lock_date_is_respected(self):
        # sudo() lifts access rights, never the lock dates: as for anybody,
        # Odoo 18 posts an entry of a locked period on the first open date
        # instead of inside the locked period. Set in SQL: the ORM refuses to
        # lock a period with unreconciled bank lines, which a clone of a real
        # database may well have.
        self.env.cr.execute(
            "UPDATE res_company SET fiscalyear_lock_date = %s WHERE id = %s",
            ("2026-03-31", self.company.id),
        )
        self.env["res.company"].invalidate_model()
        slip = self._computed_slip()
        slip.with_user(self.approver).action_payslip_done()
        move = slip.move_id
        self.assertEqual(move.state, "posted")
        self.assertGreater(move.date, date(2026, 3, 31))

    def test_lock_date_protects_cancelling(self):
        # Reversing an entry of a locked period follows the same rule: the
        # reversal is dated today, never inside the locked period.
        slip = self._computed_slip()
        slip.with_user(self.approver).action_payslip_done()
        self.env.cr.execute(
            "UPDATE res_company SET fiscalyear_lock_date = %s WHERE id = %s",
            ("2026-04-30", self.company.id),
        )
        self.env["res.company"].invalidate_model()
        self.env["ir.config_parameter"].set_param("payroll.allow_cancel_payslips", True)
        move = slip.move_id
        slip.with_user(self.approver).action_payslip_cancel()
        reversal = slip.cancelled_move_ids - move
        self.assertEqual(reversal.state, "posted")
        self.assertGreater(reversal.date, date(2026, 4, 30))

    def test_refund_posts_the_reversal_as_the_approver(self):
        slip = self._computed_slip()
        slip.with_user(self.approver).action_payslip_done()
        slip.with_user(self.approver).refund_sheet()
        refund = slip.refunded_id
        self.assertEqual(refund.state, "done")
        self.assertEqual(refund.move_id.state, "posted")
        self.assertEqual(refund.move_id.create_uid, self.approver)


@tagged("post_install", "-at_install")
class TestCancelReversesEntry(PayrollSecurityAccountCommon):
    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].set_param("payroll.allow_cancel_payslips", True)
        self.slip = self._computed_slip()
        self.slip.with_user(self.approver).action_payslip_done()
        self.move = self.slip.move_id

    def test_approver_cancels_and_the_entry_is_reversed(self):
        self.slip.with_user(self.approver).action_payslip_cancel()
        self.assertEqual(self.slip.state, "cancel")
        self.assertFalse(self.slip.move_id)
        self.assertIn(self.move, self.slip.cancelled_move_ids)
        reversal = self.slip.cancelled_move_ids - self.move
        self.assertEqual(reversal.state, "posted")
        self.assertEqual(reversal.create_uid, self.approver)

    def test_preparer_cannot_cancel_a_confirmed_payslip(self):
        with self.assertRaisesRegex(AccessError, "Approver"):
            self.slip.with_user(self.preparer).action_payslip_cancel()
        with self.assertRaisesRegex(AccessError, "Approver"):
            self.slip.with_user(self.preparer)._cancel_accounting_entry()
        self.assertEqual(self.slip.state, "done")
        self.assertEqual(self.slip.move_id, self.move)


@tagged("post_install", "-at_install")
class TestRuleAccountTracking(PayrollSecurityAccountCommon):
    def _flush_tracking(self):
        self.env.flush_all()
        self.env.cr.precommit.run()

    def test_account_changes_are_tracked(self):
        other = self.expense.copy({"code": "SECEXP02"})
        self._flush_tracking()
        rule = self.rule.with_company(self.company).with_context(tracking_disable=False)
        rule.write({"account_debit": other.id})
        self._flush_tracking()
        value = self.env["mail.tracking.value"].search(
            [
                ("mail_message_id.model", "=", "hr.salary.rule"),
                ("mail_message_id.res_id", "=", rule.id),
                ("field_id.name", "=", "account_debit"),
            ]
        )
        self.assertEqual(len(value), 1)
        self.assertEqual(value.old_value_integer, self.expense.id)
        self.assertEqual(value.new_value_integer, other.id)

    def test_tracked_fields(self):
        fields = self.env["hr.salary.rule"]._fields
        for name in (
            "account_debit",
            "account_credit",
            "analytic_account_id",
            "account_tax_id",
        ):
            with self.subTest(field=name):
                self.assertTrue(fields[name].tracking)
