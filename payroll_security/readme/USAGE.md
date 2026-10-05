| Action                                                         | Minimum level |
| -------------------------------------------------------------- | ------------- |
| Read payslips, batches, lines                                  | Reader        |
| Create/edit draft payslips and open batches, compute, generate | Preparer      |
| Cancel or reset an unconfirmed payslip                         | Preparer      |
| Confirm, refund, cancel/reset a confirmed payslip              | Approver      |
| Close or reopen a batch                                        | Approver      |
| Edit structures, rules, categories, registers, rule inputs     | Administrator |

Every check is made in Python as well as on the buttons, so a direct RPC call
(`write({'state': 'done'})`, the change-state wizard) meets the same rule.

Salary rules and structures carry a chatter: formula, condition, amounts, category,
`active` and the rule list of a structure are tracked.

Every change to an employee's bank account (created, number, bank, holder, archived,
deleted, and Odoo's own "trusted for payments" flag where `account` is installed) is
also logged on the **employee's** chatter, with the author and the number masked but for
its last four digits. Odoo keeps logging it on the work contact as well. Who may trust
an account is still decided by Odoo alone (`account.group_validate_bank_account`): no
payroll level includes it.
