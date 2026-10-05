Assign the level on the user form, Payroll selector. "Payroll: payments" is a checkbox
in Extra Rights and is never implied.

On install:

- Officer and Manager are renamed Approver and Administrator.
- Approver no longer implies Contracts / Administrator. Every user who was a payroll
  user at install time keeps it, as an explicit group (logged).
- The department rule of `payroll` is neutralised: scope is the company.
- The new-user template loses every payroll group and Contracts / Administrator.

Four eyes (off by default): Settings, Payroll, Controls, "Four eyes". Per company:
whoever computed a payslip cannot confirm it, nor close a batch holding payslips they
computed.
