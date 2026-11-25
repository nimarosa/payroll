from odoo import _, api, fields, models
from odoo.exceptions import UserError

# A contract in one of these states covers (or covered) the period.
CONTRACT_STATES = ("open", "close")


class HrPayslipEmployees(models.TransientModel):
    _name = "hr.payslip.employees"
    _description = "Generate payslips for all selected employees"

    employee_ids = fields.Many2many(
        "hr.employee", "hr_employee_group_rel", "payslip_id", "employee_id", "Employees"
    )
    payslip_run_id = fields.Many2one(
        "hr.payslip.run",
        string="Payslip Batch",
        readonly=True,
        default=lambda self: self._get_payslip_run(),
    )
    date_start = fields.Date(related="payslip_run_id.date_start")
    date_end = fields.Date(related="payslip_run_id.date_end")
    line_ids = fields.One2many(
        "hr.payslip.employees.line",
        "wizard_id",
        string="Employees to Pay",
        default=lambda self: self._get_default_line_ids(),
    )

    @api.model
    def _get_payslip_run(self):
        context = self.env.context
        if context.get("active_model", "hr.payslip.run") != "hr.payslip.run":
            return self.env["hr.payslip.run"]
        return self.env["hr.payslip.run"].browse(context.get("active_id")).exists()

    @api.model
    def _get_period_contracts(self, run):
        """The contracts overlapping the period of the batch.

        Latest first, so that the first one of each employee is the one that
        applies when somebody changed contracts within the period.
        """
        return self.env["hr.contract"].search(
            [
                ("company_id", "=", run.company_id.id),
                ("state", "in", CONTRACT_STATES),
                ("date_start", "<=", run.date_end),
                "|",
                ("date_end", "=", False),
                ("date_end", ">=", run.date_start),
            ],
            order="date_start desc, id desc",
        )

    @api.model
    def _get_default_line_ids(self):
        """Everybody with a contract in the period who has no payslip yet.

        The structure of the batch is not a filter: it replaces the one of
        the contract on every payslip, which is how a one-off run (a bonus, a
        thirteenth month) is paid to all the contracts of the period.
        """
        run = self._get_payslip_run()
        if not run:
            return []
        already = run.slip_ids.filtered(lambda slip: slip.state != "cancel").employee_id
        contract_by_employee = {}
        for contract in self._get_period_contracts(run):
            employee = contract.employee_id
            if employee in already or employee in contract_by_employee:
                continue
            contract_by_employee[employee] = contract
        return [
            fields.Command.create(
                {"employee_id": employee.id, "contract_id": contract.id}
            )
            for employee, contract in sorted(
                contract_by_employee.items(),
                key=lambda item: (item[0].name or "", item[0].id),
            )
        ]

    def compute_sheet(self):
        payslips = self.env["hr.payslip"]
        # Employees given explicitly (a script, another module) win over the
        # proposed list, which is what the form works with.
        if not self.employee_ids and self.line_ids:
            self.employee_ids = self.line_ids.employee_id
        [data] = self.read()
        active_id = self.env.context.get("active_id")
        if active_id:
            [run_data] = (
                self.env["hr.payslip.run"]
                .browse(active_id)
                .read(["date_start", "date_end", "credit_note", "struct_id"])
            )
        from_date = run_data.get("date_start")
        to_date = run_data.get("date_end")
        struct_id = run_data.get("struct_id")
        if not data["employee_ids"]:
            raise UserError(
                _(
                    "The list is empty: there is nobody to pay. "
                    "Add at least one employee."
                )
            )
        for employee in self.env["hr.employee"].browse(data["employee_ids"]):
            slip_data = self.env["hr.payslip"].get_payslip_vals(
                from_date, to_date, employee.id, contract_id=False, struct_id=struct_id
            )
            res = {
                "employee_id": employee.id,
                "name": slip_data["value"].get("name"),
                "struct_id": slip_data["value"].get("struct_id"),
                "contract_id": slip_data["value"].get("contract_id"),
                "payslip_run_id": active_id,
                "input_line_ids": [
                    (0, 0, x) for x in slip_data["value"].get("input_line_ids")
                ],
                "worked_days_line_ids": [
                    (0, 0, x) for x in slip_data["value"].get("worked_days_line_ids")
                ],
                "date_from": from_date,
                "date_to": to_date,
                "credit_note": run_data.get("credit_note"),
                "company_id": employee.company_id.id,
            }
            payslips += self.env["hr.payslip"].create(res)
        payslips._compute_name()
        payslips.compute_sheet()
        return {"type": "ir.actions.act_window_close"}


class HrPayslipEmployeesLine(models.TransientModel):
    _name = "hr.payslip.employees.line"
    _description = "Employee to pay in a payslip batch"
    _order = "id"

    wizard_id = fields.Many2one(
        "hr.payslip.employees", required=True, ondelete="cascade"
    )
    employee_id = fields.Many2one("hr.employee", required=True)
    contract_id = fields.Many2one("hr.contract")
    struct_id = fields.Many2one(related="contract_id.struct_id")

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        """A line added by hand looks up its own contract of the period."""
        for line in self:
            run = line.wizard_id.payslip_run_id or line.wizard_id._get_payslip_run()
            if not line.employee_id or not run:
                continue
            contracts = line.wizard_id._get_period_contracts(run).filtered(
                lambda contract, employee=line.employee_id: contract.employee_id
                == employee
            )
            line.contract_id = contracts[:1]
