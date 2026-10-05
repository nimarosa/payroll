- Scope is the company. A narrower scope (by department, as the stock Officer rule
  attempted) is not implemented.
- The employee portal (an employee reading their own payslips) is out of scope.
- Sibling modules that add models (`payroll_rule_time_parameter`,
  `payroll_contract_advantages`) keep their own access rules, written for the two stock
  groups: the Reader and the Preparer get no access to them from this module.
- On uninstall the stock group names come back in English; the other languages follow
  the next time `payroll` is upgraded.
- The Reader reads employees through an access rule of its own, without being an HR
  Officer. Some fields of the employee form are reserved to HR Officers, so upgrading a
  module that extends that form (`payroll` itself, for one) logs an "Access Rights
  Inconsistency" warning for it. A Reader never opens that form from Payroll.
