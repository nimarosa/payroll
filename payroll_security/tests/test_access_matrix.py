"""The role x model x operation matrix, and the rows each role may touch.

ACLs say which models a role reaches; record rules say which rows, per
operation. Both are checked here the way the ORM checks them for a user, so a
module that later grants something to the wrong group fails a named cell.
"""

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import PayrollSecurityCommon

R = "r"
CRUD = "rwcu"
NONE = ""

PAYSLIP_MODELS = (
    "hr.payslip",
    "hr.payslip.line",
    "hr.payslip.input",
    "hr.payslip.worked_days",
)
CONFIG_MODELS = (
    "hr.payroll.structure",
    "hr.salary.rule",
    "hr.salary.rule.category",
    "hr.contribution.register",
    "hr.rule.input",
)
OPERATIONS = {"r": "read", "w": "write", "c": "create", "u": "unlink"}

# role -> model -> allowed operations. hr.contract for the approver and the
# administrator is covered by the user-migration tests: their contracts
# implication is cut there.
MATRIX = {
    "reader": {
        **dict.fromkeys(PAYSLIP_MODELS, R),
        "hr.payslip.run": R,
        **dict.fromkeys(CONFIG_MODELS, R),
        "hr.contract": R,
        "hr.payroll.structure.type": R,
        "hr.employee": R,
    },
    "preparer": {
        **dict.fromkeys(PAYSLIP_MODELS, CRUD),
        "hr.payslip.run": CRUD,
        **dict.fromkeys(CONFIG_MODELS, R),
        "hr.contract": R,
        "hr.payroll.structure.type": R,
        "hr.employee": CRUD,
    },
    "approver": {
        **dict.fromkeys(PAYSLIP_MODELS, CRUD),
        "hr.payslip.run": CRUD,
        **dict.fromkeys(CONFIG_MODELS, R),
    },
    "manager": {
        **dict.fromkeys(PAYSLIP_MODELS, CRUD),
        "hr.payslip.run": CRUD,
        **dict.fromkeys(CONFIG_MODELS, CRUD),
    },
    "payment": {
        **dict.fromkeys(PAYSLIP_MODELS, R),
        "hr.payslip.run": R,
        **dict.fromkeys(CONFIG_MODELS, R),
        "hr.contract": R,
        "hr.employee": R,
    },
    "plain": {
        **dict.fromkeys(PAYSLIP_MODELS, NONE),
        "hr.payslip.run": NONE,
        **dict.fromkeys(CONFIG_MODELS, NONE),
        "hr.contract": NONE,
    },
}


@tagged("post_install", "-at_install")
class TestAccessMatrix(PayrollSecurityCommon):
    def test_model_access(self):
        access = self.env["ir.model.access"]
        for role, models in MATRIX.items():
            user = getattr(self, role)
            for model, allowed in models.items():
                for letter, operation in OPERATIONS.items():
                    with self.subTest(role=role, model=model, operation=operation):
                        self.assertEqual(
                            access.with_user(user).check(
                                model, operation, raise_exception=False
                            ),
                            letter in allowed,
                        )


@tagged("post_install", "-at_install")
class TestRowRules(PayrollSecurityCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.slip_draft = cls._slip()
        cls.slip_done = cls._slip()
        cls.slip_done.compute_sheet()
        cls.slip_done.write({"state": "done"})
        cls.run_draft = cls._run(name="Open batch")
        cls.run_closed = cls._run(name="Closed batch")
        cls.run_closed.write({"state": "close"})

    def _allowed(self, records, user, operation):
        try:
            records.with_user(user).check_access(operation)
        except AccessError:
            return False
        return True

    def test_preparer_touches_only_unconfirmed_payslips(self):
        self.assertTrue(self._allowed(self.slip_draft, self.preparer, "write"))
        self.assertTrue(self._allowed(self.slip_draft, self.preparer, "unlink"))
        self.assertTrue(self._allowed(self.slip_done, self.preparer, "read"))
        for operation in ("write", "unlink"):
            with self.subTest(operation=operation):
                self.assertFalse(
                    self._allowed(self.slip_done, self.preparer, operation)
                )

    def test_preparer_touches_only_the_lines_of_unconfirmed_payslips(self):
        lines = self.slip_done.line_ids
        self.assertTrue(lines)
        self.assertTrue(self._allowed(lines, self.preparer, "read"))
        self.assertFalse(self._allowed(lines, self.preparer, "write"))
        self.assertFalse(self._allowed(lines, self.preparer, "unlink"))
        inputs = self.slip_done.input_line_ids
        worked = self.slip_done.worked_days_line_ids
        for records in (inputs, worked):
            if records:
                self.assertFalse(self._allowed(records, self.preparer, "write"))

    def test_preparer_touches_only_open_batches(self):
        self.assertTrue(self._allowed(self.run_draft, self.preparer, "write"))
        self.assertTrue(self._allowed(self.run_closed, self.preparer, "read"))
        self.assertFalse(self._allowed(self.run_closed, self.preparer, "write"))
        self.assertFalse(self._allowed(self.run_closed, self.preparer, "unlink"))

    def test_approver_and_manager_touch_everything(self):
        for user in (self.approver, self.manager):
            for records in (self.slip_done, self.run_closed, self.slip_done.line_ids):
                with self.subTest(user=user.login, model=records._name):
                    self.assertTrue(self._allowed(records, user, "write"))

    def test_reader_reads_every_payslip_and_writes_none(self):
        for records in (self.slip_draft, self.slip_done, self.run_closed):
            with self.subTest(model=records._name, state=records.state):
                self.assertTrue(self._allowed(records, self.reader, "read"))
                self.assertFalse(self._allowed(records, self.reader, "write"))

    def test_department_scope_is_gone(self):
        """OCA's Officer rule hid payslips of departments the user does not
        manage. Scope is the company now, for every level."""
        boss = self.env["hr.employee"].create({"name": "Jefe ajeno"})
        department = self.env["hr.department"].create(
            {"name": "Depto ajeno", "manager_id": boss.id}
        )
        self.employee.department_id = department
        for user in (self.reader, self.preparer, self.approver):
            with self.subTest(user=user.login):
                found = (
                    self.env["hr.payslip"]
                    .with_user(user)
                    .search([("id", "=", self.slip_draft.id)])
                )
                self.assertEqual(found, self.slip_draft)

    def test_reader_reads_contracts_and_employees(self):
        self.assertTrue(self._allowed(self.contract, self.reader, "read"))
        self.assertTrue(self._allowed(self.employee, self.reader, "read"))
        self.assertFalse(self._allowed(self.contract, self.reader, "write"))


@tagged("post_install", "-at_install")
class TestMultiCompany(PayrollSecurityCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        other = cls.env["res.company"].create({"name": "Other security company"})
        if "account.journal" in cls.env:
            # With accounting a batch needs a salary journal, and a bare new
            # company has none (no chart of accounts, no general journal).
            cls.env["account.journal"].create(
                {
                    "name": "Foreign salaries",
                    "code": "SUEAJ",
                    "type": "general",
                    "company_id": other.id,
                }
            )
        cls.other_run = cls.env["hr.payslip.run"].create(
            {
                "name": "Foreign batch",
                "company_id": other.id,
                "date_start": "2026-03-01",
                "date_end": "2026-03-31",
            }
        )
        slip = cls.env["hr.payslip"].create(
            {
                "employee_id": cls.employee.id,
                "contract_id": cls.contract.id,
                "struct_id": cls.structure.id,
                "date_from": "2026-03-01",
                "date_to": "2026-03-31",
            }
        )
        slip.compute_sheet()
        cls.other_lines = slip.line_ids
        slip.company_id = other

    def test_other_company_batches_and_lines_are_invisible(self):
        for user in (self.reader, self.approver, self.manager):
            with self.subTest(user=user.login):
                runs = self.env["hr.payslip.run"].with_user(user)
                self.assertFalse(runs.search([("id", "=", self.other_run.id)]))
                lines = self.env["hr.payslip.line"].with_user(user)
                self.assertFalse(lines.search([("id", "in", self.other_lines.ids)]))
