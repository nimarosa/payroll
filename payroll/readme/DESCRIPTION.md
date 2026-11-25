Manage your employee payroll records.

This module is a backport from Odoo SA and as such, it is not included
in the OCA CLA. That means we do not have a copy of the copyright on it
like all other OCA modules.

## Default salary structure

A default salary structure speeds up contract creation. Set it on the
company as the general default, and on an employee only when that
specific employee needs a different one; left empty on the employee,
the company default applies.

## Payslip batches

A payslip batch is worked as a sequence of steps, and its form highlights
only the next one:

1. **Generate Payslips**: the wizard comes filled with every employee
   that has a contract overlapping the period of the batch (running, or
   ended within it) and no payslip in the batch yet, along with the
   contract and the structure each one will be paid with. Remove whoever
   should not be paid, or add somebody, and generate.
2. **Compute All** computes every pending payslip, each in its own
   savepoint: a payslip that fails (a broken rule, a missing value) does
   not stop the others, and is listed with its error in the notification
   and in the chatter of the batch.
3. **Confirm All** confirms them the same way.
4. **Close**, offered once every payslip is confirmed or cancelled.

The stage of the batch (Draft, In Progress, Confirmed, Closed) is derived
from its payslips and can be filtered and grouped by. The batch also shows
its net total: the sum of the net wage of its payslips, cancelled ones
excluded. The net wage of a payslip is the total of its line with code
`NET`; a localization whose net is computed otherwise overrides
`hr.payslip._get_net_wage()`.

A new batch is named after its period (*Payslip Batch 09/2025*); the name
follows the start date until somebody types another one.

On the payslip form, likewise, only one button is highlighted at a time:
*Compute Sheet* until the payslip has lines, *Confirm* afterwards. The
computation is the first tab, and the structure can be changed until the
payslip is confirmed.
