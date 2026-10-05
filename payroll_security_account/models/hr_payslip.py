from odoo import models

from odoo.addons.payroll_security.models.common import (
    APPROVER,
    check_payroll_access,
)


class HrPayslip(models.Model):
    """The journal entry follows the payroll role, not the accounting one.

    Each transition runs every payroll check with the user's own rights --
    ACL and record rules on the payslips, the role, four-eyes -- and only then
    hands the rest to ``super()`` in superuser mode. ``sudo()`` keeps
    ``env.uid``, so the entry is authored by the real user, and it lifts access
    rights only: lock dates and every accounting constraint still apply.

    Under ``sudo()`` the checks of ``payroll_security`` further down the chain
    see ``env.su`` and pass: they already ran here, with the real rights, so
    nothing runs twice and nothing is skipped.
    """

    _inherit = "hr.payslip"

    def action_payslip_done(self):
        if self.env.su:
            return super().action_payslip_done()
        check_payroll_access(self.env, APPROVER, self.env._("Confirming payslips"))
        self.check_access("write")
        self._check_four_eyes()
        return super(HrPayslip, self.sudo()).action_payslip_done()

    def action_payslip_cancel(self):
        if self.env.su:
            return super().action_payslip_cancel()
        self._check_leaving_done(self.env._("Cancelling confirmed payslips"))
        self.check_access("write")
        return super(HrPayslip, self.sudo()).action_payslip_cancel()

    def _compute_journal_id(self):
        """A further, LOWER-priority tier under `payroll_account`'s own:
        the batch's journal wins, then the contract's, and only when
        NEITHER exists does the company's `payroll_salary_journal_id`
        setting (or its own fallback, the first general journal) get a say.
        A payslip is never required to have one -- unlike a batch -- so this
        only fills a gap `super()` left, it never raises.
        """
        res = super()._compute_journal_id()
        for payslip in self:
            if not payslip.journal_id:
                company = payslip.company_id or self.env.company
                payslip.journal_id = company._get_payroll_salary_journal()
        return res

    def _cancel_accounting_entry(self):
        # Only a confirmed payslip has an entry to undo: an approver's call.
        if self.env.su:
            return super()._cancel_accounting_entry()
        check_payroll_access(
            self.env, APPROVER, self.env._("Reversing payslip journal entries")
        )
        self.check_access("write")
        return super(HrPayslip, self.sudo())._cancel_accounting_entry()
