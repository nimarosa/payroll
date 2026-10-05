"""`propose_salary_journal` (run by `post_init_hook`) suggests an existing
'Salaries'/'Payroll' journal as the initial value of
`payroll_salary_journal_id`, and only when there is exactly one unambiguous
candidate. It never creates a journal."""

from odoo.tests import TransactionCase, tagged

from odoo.addons.payroll_security_account.hooks import propose_salary_journal


@tagged("post_install", "-at_install")
class TestProposeSalaryJournal(TransactionCase):
    def _journal(self, company, code, name):
        return self.env["account.journal"].create(
            {
                "name": name,
                "code": code,
                "type": "general",
                "company_id": company.id,
            }
        )

    def test_proposes_the_only_salaries_journal(self):
        company = self.env["res.company"].create({"name": "With Salaries"})
        journal = self._journal(company, "PSJ1", "Salaries")
        propose_salary_journal(self.env)
        self.assertEqual(company.payroll_salary_journal_id, journal)

    def test_proposes_a_payroll_journal_case_insensitively(self):
        company = self.env["res.company"].create({"name": "With Payroll"})
        journal = self._journal(company, "PSJ2", "PAYROLL")
        propose_salary_journal(self.env)
        self.assertEqual(company.payroll_salary_journal_id, journal)

    def test_does_not_propose_when_ambiguous(self):
        company = self.env["res.company"].create({"name": "With two"})
        self._journal(company, "PSJ3", "Salaries")
        self._journal(company, "PSJ4", "Payroll")
        propose_salary_journal(self.env)
        self.assertFalse(company.payroll_salary_journal_id)

    def test_does_not_propose_without_a_matching_name(self):
        company = self.env["res.company"].create({"name": "No match"})
        self._journal(company, "PSJ5", "Sales")
        propose_salary_journal(self.env)
        self.assertFalse(company.payroll_salary_journal_id)

    def test_does_not_propose_a_substring_match(self):
        # "Salaries and wages" is not "Salaries": ambiguity is for a human.
        company = self.env["res.company"].create({"name": "Long name"})
        self._journal(company, "PSJ6", "Salaries and wages")
        propose_salary_journal(self.env)
        self.assertFalse(company.payroll_salary_journal_id)

    def test_never_creates_a_journal(self):
        company = self.env["res.company"].create({"name": "Empty"})
        propose_salary_journal(self.env)
        self.assertFalse(company.payroll_salary_journal_id)
        self.assertFalse(
            self.env["account.journal"].search([("company_id", "=", company.id)])
        )

    def test_does_not_touch_a_company_that_already_has_the_setting(self):
        company = self.env["res.company"].create({"name": "Already set"})
        existing = self._journal(company, "PSJ7", "Other")
        self._journal(company, "PSJ8", "Salaries")
        company.payroll_salary_journal_id = existing
        propose_salary_journal(self.env)
        self.assertEqual(company.payroll_salary_journal_id, existing)

    def test_proposes_the_name_in_an_installed_language(self):
        """The candidate names are this module's own terms, so a database in
        another language proposes the journal named in that language."""
        self.env["res.lang"]._activate_lang("es_ES")
        company = self.env["res.company"].create({"name": "In Spanish"})
        journal = self._journal(company, "PSJ9", "Sueldos")
        propose_salary_journal(self.env)
        self.assertEqual(company.payroll_salary_journal_id, journal)
