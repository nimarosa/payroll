"""Changes to an employee's bank account land on the EMPLOYEE's chatter.

Odoo (account) already tracks `acc_number`, `partner_id` and
`allow_out_payment`, but on the chatter of the work contact, which nobody in
payroll looks at. The bank account is where a payroll fraud happens, so the trail has
to be where the payroll people read.
"""

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import PREPARER, PayrollSecurityCommon

TRUST_FIELD = "allow_out_payment"


@tagged("post_install", "-at_install")
class TestBankAccountLog(PayrollSecurityCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contact = cls.env["res.partner"].create({"name": "Security contact"})
        cls.employee.work_contact_id = cls.contact
        cls.bank = cls.env["res.bank"].create({"name": "Security Bank"})
        cls.other_bank = cls.env["res.bank"].create({"name": "Other Bank"})
        # Whoever loads the accounts: a Preparer (HR officer, so hr's record rule
        # shows employee accounts) plus whichever groups this stack grants
        # full access on bank accounts to (base's partner manager, or
        # account_payment_order's payments group, which replaces it).
        cls.bank_groups = cls._bank_editor_groups()
        cls.clerk = cls._user("sec_clerk", PREPARER)
        cls.clerk.groups_id = [(4, group.id) for group in cls.bank_groups]

    @classmethod
    def _bank_editor_groups(cls):
        access = cls.env["ir.model.access"].search(
            [
                ("model_id.model", "=", "res.partner.bank"),
                ("perm_create", "=", True),
                ("perm_write", "=", True),
                ("perm_unlink", "=", True),
                ("group_id", "!=", False),
            ]
        )
        return access.group_id

    def _messages(self, employee=None):
        employee = employee or self.employee
        return self.env["mail.message"].search(
            [("model", "=", "hr.employee"), ("res_id", "=", employee.id)],
            order="id desc",
        )

    def _account(self, number="0070001230000000012345", **values):
        vals = {
            "acc_number": number,
            "partner_id": self.contact.id,
            "bank_id": self.bank.id,
        }
        vals.update(values)
        return self.env["res.partner.bank"].with_user(self.clerk).create(vals)

    def test_create_is_logged_on_the_employee_masked(self):
        before = self._messages()
        self._account()
        message = self._messages() - before
        self.assertEqual(len(message), 1)
        self.assertIn("****2345", message.body)
        self.assertNotIn("0070001230000000012345", message.body)
        self.assertIn("Security Bank", message.body)
        self.assertIn(self.clerk.name, message.body)
        self.assertEqual(message.author_id, self.clerk.partner_id)

    def test_number_change_shows_old_and_new_masked(self):
        account = self._account()
        before = self._messages()
        account.with_user(self.clerk).write(
            {"acc_number": "0070001230000000067890", "bank_id": self.other_bank.id}
        )
        message = self._messages() - before
        self.assertEqual(len(message), 1)
        self.assertIn("****2345", message.body)
        self.assertIn("****7890", message.body)
        self.assertIn("Security Bank", message.body)
        self.assertIn("Other Bank", message.body)
        self.assertNotIn("0070001230000000067890", message.body)

    def test_an_unrelated_write_logs_nothing(self):
        account = self._account()
        before = self._messages()
        account.with_user(self.clerk).write({"acc_holder_name": "Other holder"})
        self.assertFalse(self._messages() - before)

    def test_unlink_is_logged(self):
        account = self._account()
        before = self._messages()
        account.with_user(self.clerk).unlink()
        message = self._messages() - before
        self.assertEqual(len(message), 1)
        self.assertIn("****2345", message.body)

    def test_the_account_selected_on_the_employee_is_found_too(self):
        """An account of another partner picked on the employee file."""
        stranger = self.env["res.partner"].create({"name": "Otro contacto"})
        account = self._account(partner_id=stranger.id)
        self.employee.bank_account_id = account
        before = self._messages()
        account.with_user(self.clerk).write({"acc_number": "0070001230000000011111"})
        self.assertEqual(len(self._messages() - before), 1)

    def test_moving_the_account_to_another_partner_logs_on_both(self):
        account = self._account()
        other = self.env["hr.employee"].create({"name": "Other employee"})
        other_contact = self.env["res.partner"].create({"name": "Otro contacto"})
        other.work_contact_id = other_contact
        before = self._messages() | self._messages(other)
        account.with_user(self.clerk).write({"partner_id": other_contact.id})
        self.assertEqual(len(self._messages() - before), 1)
        self.assertEqual(len(self._messages(other) - before), 1)

    def test_accounts_of_non_employees_are_left_alone(self):
        stranger = self.env["res.partner"].create({"name": "Proveedor"})
        messages = self.env["mail.message"].search_count(
            [("model", "=", "hr.employee")]
        )
        self.env["res.partner.bank"].create(
            {"acc_number": "0070001230000000099999", "partner_id": stranger.id}
        )
        self.assertEqual(
            self.env["mail.message"].search_count([("model", "=", "hr.employee")]),
            messages,
        )

    # ------------------------------------------------------------------
    # allow_out_payment (Odoo's own "trusted account", from `account`)
    # ------------------------------------------------------------------
    def _require_trust_field(self):
        if TRUST_FIELD not in self.env["res.partner.bank"]._fields:
            self.skipTest("`account` is not installed: no trusted accounts")

    def test_the_preparer_cannot_trust_on_create(self):
        """Odoo drops the flag at create for anyone who may not trust."""
        self._require_trust_field()
        account = self._account(**{TRUST_FIELD: True})
        self.assertFalse(account[TRUST_FIELD])

    def test_the_preparer_cannot_trust_on_write(self):
        self._require_trust_field()
        account = self._account()
        with self.assertRaises(UserError):  # ValidationError is a subclass
            account.with_user(self.clerk).write({TRUST_FIELD: True})
        self.assertFalse(account[TRUST_FIELD])

    def test_trusting_is_logged_on_the_employee(self):
        self._require_trust_field()
        # hr's record rule hides employee accounts from non HR officers.
        validator = self._user(
            "sec_validator", "account.group_validate_bank_account", "hr.group_hr_user"
        )
        validator.groups_id = [(4, group.id) for group in self.bank_groups]
        account = self._account()
        before = self._messages()
        account.with_user(validator).write({TRUST_FIELD: True})
        message = self._messages() - before
        self.assertEqual(len(message), 1)
        self.assertIn("trusted for payments", message.body)
        self.assertIn(validator.name, message.body)
