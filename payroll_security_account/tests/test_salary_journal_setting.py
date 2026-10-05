"""`payroll_account` makes `hr.payslip.run.journal_id` required, defaulting
to the company's first general journal -- nothing, for a company with none,
which is a raw `NotNullViolation` the moment a batch is created.
`res.company.payroll_salary_journal_id` gives that default a say first, and
`create()` turns the remaining gap into a message that names where to fix
it, instead of the database error."""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSalaryJournalSetting(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # The fixture company may already carry a proposed value (a real
        # salary journal `propose_salary_journal` found on
        # install) -- start every test in this class from a clean slate so
        # they exercise the fallback chain, not whatever the fixture data
        # happens to be named.
        cls.company.payroll_salary_journal_id = False
        # No chart of accounts was ever installed on this one, so it has no
        # journal of any kind -- the one situation `payroll_account`'s own
        # default cannot resolve on its own.
        cls.bare_company = cls.env["res.company"].create({"name": "No journals"})

    def _journal(self, company, code, name="Test journal"):
        return self.env["account.journal"].create(
            {
                "name": name,
                "code": code,
                "type": "general",
                "company_id": company.id,
            }
        )

    def _run_vals(self, company, **extra):
        vals = {
            "name": "Salary journal batch",
            "company_id": company.id,
            "date_start": "2026-05-01",
            "date_end": "2026-05-31",
        }
        vals.update(extra)
        return vals

    def test_setting_wins_over_ocas_own_default(self):
        ocas_default = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", self.company.id)],
            limit=1,
        )
        self.assertTrue(ocas_default, "the fixture company needs a general journal")
        salary_journal = self._journal(self.company, "TSTSU")
        self.company.payroll_salary_journal_id = salary_journal
        run = self.env["hr.payslip.run"].create(self._run_vals(self.company))
        self.assertEqual(run.journal_id, salary_journal)
        self.assertNotEqual(run.journal_id, ocas_default)

    def test_falls_back_to_ocas_default_when_not_configured(self):
        self.assertFalse(self.company.payroll_salary_journal_id)
        ocas_default = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", self.company.id)],
            limit=1,
        )
        run = self.env["hr.payslip.run"].create(self._run_vals(self.company))
        self.assertEqual(run.journal_id, ocas_default)

    def test_clear_error_when_nothing_resolves(self):
        self.assertFalse(
            self.env["account.journal"].search(
                [("company_id", "=", self.bare_company.id)]
            )
        )
        with self.assertRaisesRegex(UserError, "Salary journal"):
            self.env["hr.payslip.run"].create(self._run_vals(self.bare_company))
        # And naming the exact settings path, per the design.
        with self.assertRaisesRegex(UserError, "Settings > Accounting"):
            self.env["hr.payslip.run"].create(self._run_vals(self.bare_company))

    def test_explicit_journal_is_still_respected(self):
        other = self._journal(self.company, "TSTOT", "Other journal")
        self.company.payroll_salary_journal_id = self._journal(
            self.company, "TSTDF", "Default journal"
        )
        run = self.env["hr.payslip.run"].create(
            self._run_vals(self.company, journal_id=other.id)
        )
        self.assertEqual(run.journal_id, other)

    def test_payslip_falls_back_to_the_setting_with_no_run_and_no_contract_journal(
        self,
    ):
        salary_journal = self._journal(self.company, "TSTPS")
        self.company.payroll_salary_journal_id = salary_journal
        employee = self.env["hr.employee"].create(
            {"name": "Journal employee", "company_id": self.company.id}
        )
        contract = self.env["hr.contract"].create(
            {
                "name": "Journal contract",
                "employee_id": employee.id,
                "wage": 1000.0,
                "date_start": "2026-01-01",
                "state": "open",
                "company_id": self.company.id,
            }
        )
        self.assertFalse(contract.journal_id)
        slip = self.env["hr.payslip"].create(
            {
                "employee_id": employee.id,
                "contract_id": contract.id,
                "date_from": "2026-05-01",
                "date_to": "2026-05-31",
            }
        )
        self.assertEqual(slip.journal_id, salary_journal)

    def test_payslip_still_has_no_journal_when_nothing_resolves(self):
        employee = self.env["hr.employee"].create(
            {"name": "Employee without journal", "company_id": self.bare_company.id}
        )
        contract = self.env["hr.contract"].create(
            {
                "name": "Contract without journal",
                "employee_id": employee.id,
                "wage": 1000.0,
                "date_start": "2026-01-01",
                "state": "open",
                "company_id": self.bare_company.id,
            }
        )
        slip = self.env["hr.payslip"].create(
            {
                "employee_id": employee.id,
                "contract_id": contract.id,
                # `company_id` defaults to `self.env.company` on a bare
                # create() -- the onchange that would otherwise pick it up
                # from the employee only fires in the UI -- so it has to be
                # explicit for this to actually exercise `bare_company`.
                "company_id": self.bare_company.id,
                "date_from": "2026-05-01",
                "date_to": "2026-05-31",
            }
        )
        # A standalone payslip is not required to have one -- unlike a batch,
        # it fails at posting time, not at create() -- so this is a plain
        # empty value, never a UserError.
        self.assertFalse(slip.journal_id)
