Glue between `payroll_security` and `payroll_account`, installed automatically when both
are.

Confirming a payslip posts its journal entry. With the payroll roles of
`payroll_security`, the person who confirms is the Approver, and an Approver does not
need, and usually should not have, accounting rights. This module keeps both true:

- confirming, cancelling and reversing a payslip check the payroll role (and the
  four-eyes rule) with the user's own rights first, and only then create, post or
  reverse the journal entry with `sudo()`;
- `sudo()` keeps the real user, so the entry's author (`create_uid`) is the Approver who
  confirmed it, not the superuser;
- `sudo()` lifts access rights only: lock dates, balanced entries and every other
  accounting constraint still apply;
- changes to the accounts, analytic account and tax of a salary rule are tracked in its
  chatter, next to the formula changes `payroll_security` already tracks.

`payroll_account` also makes `hr.payslip.run.journal_id` required, defaulting to the
company's first general journal -- nothing, for a company with none, which turns into a
raw database error the moment a batch is created. A per-company "Salary journal" setting
fixes that: it wins over the stock default, batches and payslips fall back to the stock
behaviour when it is not set, and a company with neither gets a clear message instead of
the database error.
