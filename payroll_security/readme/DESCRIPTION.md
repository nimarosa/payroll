Splits payroll access by duty instead of the two stock groups (Officer, Manager).

The Payroll category on the user form becomes one selector with four levels, each
including the previous one:

| Level | Group                                     | Duty                                                      |
| ----- | ----------------------------------------- | --------------------------------------------------------- |
| 1     | `payroll_security.group_payroll_reader`   | Reader (audit): reads payslips, batches and reports       |
| 2     | `payroll_security.group_payroll_preparer` | Preparer: builds batches, loads inputs, computes payslips |
| 3     | `payroll.group_payroll_user`              | Approver: confirms, refunds, closes and reopens           |
| 4     | `payroll.group_payroll_manager`           | Administrator: salary structures, rules and parameters    |

An orthogonal add-on in Extra Rights, `payroll_security.group_payroll_payment`
("Payroll: payments"), reads payroll and is meant for whoever issues the payment files.
Nobody gets it by implication.

The stock groups are re-used, not replaced: every third-party ACL and menu that points
at them keeps working.

Besides the roles, the module adds:

- record rules per operation (a Preparer only changes payslips and batches that are not
  confirmed yet) and the multi-company rules `payroll` lacks on batches and payslip
  lines;
- server-side checks on every state change, so a direct RPC call meets the same rule as
  the buttons;
- an optional four-eyes control, per company;
- a chatter on salary rules and structures that tracks every configuration change;
- a log of every change to an employee's bank account on the employee's own chatter.
