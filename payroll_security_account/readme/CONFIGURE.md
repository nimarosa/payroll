Nothing is required. Give the Approver level of Payroll to whoever confirms payslips; no
accounting group is needed for the journal entry to be posted.

A Preparer still cannot confirm, and a confirmed payslip can only be cancelled (its
entry reversed) by an Approver. An entry dated in a locked period is refused exactly as
it would be for an accountant.

Optionally, set the salary journal in Payroll > Configuration > Settings > Accounting >
"Salary journal". Leave it empty to keep the stock behaviour (the company's first
general journal); if the company has no general journal at all, creating a batch says so
and names this same path instead of failing with a database error. On install, a company
with exactly one general journal named "Salaries" or "Payroll" (or their translation in
an installed language) gets it proposed automatically; with none or with more than one
candidate, nobody guesses -- set it by hand.
