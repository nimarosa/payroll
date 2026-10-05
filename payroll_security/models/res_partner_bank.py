"""Mirror every change to an employee's bank account on the employee file.

Odoo (`account`) tracks the account number, holder and "trusted" flag on the
chatter of the work CONTACT, which nobody in payroll reads. Here each create,
change or deletion of an account that belongs to an employee -- through the
work contact or selected on the employee file -- is also logged on the
EMPLOYEE's chatter: who, what changed (number masked but for its last four
digits), and the bank.

No dependency on `account`: `allow_out_payment` is declared by `base`; only
the rule on who may set it comes from `account`. Deliberately not switched
off by `tracking_disable`: it is an audit trail, and any RPC client can forge
a context key.
"""

from contextvars import ContextVar

from markupsafe import Markup, escape

from odoo import api, models

#: The fields whose change is worth telling the payroll people about.
LOGGED_FIELDS = ("acc_number", "bank_id", "partner_id", "allow_out_payment", "active")
VISIBLE_DIGITS = 4
#: Ids being deleted right now. Some module archives an account on its way to
#: deletion; that write is part of the deletion, logged once as such. A
#: ContextVar and not a context key: an RPC client could forge the latter to
#: write without a trace.
UNLINKING = ContextVar("payroll_security_bank_unlinking", default=frozenset())


def mask_number(number):
    """Return `number` hidden but for its last four characters."""
    if not number:
        return "—"
    return "****" + number[-VISIBLE_DIGITS:]


class ResPartnerBank(models.Model):
    _inherit = "res.partner.bank"

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        accounts = super().create(vals_list)
        for account, employees in accounts._payroll_employees().items():
            account._payroll_log(
                employees,
                self.env._("Bank account added: %s.", account._payroll_label()),
            )
        return accounts

    def write(self, vals):
        fields = self._payroll_logged_fields(vals)
        if not fields or set(self.ids) <= UNLINKING.get():
            return super().write(vals)
        before = {account: {name: account[name] for name in fields} for account in self}
        employees_before = self._payroll_employees()
        res = super().write(vals)
        employees_after = self._payroll_employees()
        for account in self:
            employees = employees_before.get(account, self.env["hr.employee"])
            employees |= employees_after.get(account, self.env["hr.employee"])
            changes = account._payroll_changes(before[account], fields)
            if employees and changes:
                account._payroll_log(
                    employees,
                    Markup("%s<ul>%s</ul>")
                    % (
                        self.env._(
                            "Bank account %s changed:",
                            mask_number(before[account].get("acc_number"))
                            if "acc_number" in before[account]
                            else mask_number(account.acc_number),
                        ),
                        Markup("").join(
                            Markup("<li>%s</li>") % change for change in changes
                        ),
                    ),
                )
        return res

    def unlink(self):
        logs = [
            (employees, account._payroll_label())
            for account, employees in self._payroll_employees().items()
        ]
        token = UNLINKING.set(UNLINKING.get() | set(self.ids))
        try:
            res = super().unlink()
        finally:
            UNLINKING.reset(token)
        for employees, label in logs:
            self._payroll_log(employees, self.env._("Bank account deleted: %s.", label))
        return res

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _payroll_logged_fields(self, vals):
        return [name for name in LOGGED_FIELDS if name in vals and name in self._fields]

    def _payroll_employees(self):
        """Map each account of `self` to the employees it belongs to.

        Read under sudo: the user editing the account (an accountant trusting
        it, say) needs no access to employee files for the trail to be kept.
        """
        if not self:
            return {}
        employees = (
            self.env["hr.employee"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    "|",
                    ("bank_account_id", "in", self.ids),
                    ("work_contact_id", "in", self.sudo().partner_id.ids),
                ]
            )
        )
        result = {}
        for account in self:
            partner = account.sudo().partner_id
            owners = employees.filtered(
                lambda employee,
                account=account,
                partner=partner: employee.sudo().bank_account_id == account
                or (partner and employee.work_contact_id == partner)
            )
            if owners:
                result[account] = owners
        return result

    def _payroll_label(self):
        self.ensure_one()
        account = self.sudo()
        label = mask_number(account.acc_number)
        if account.bank_id:
            label = f"{label} ({account.bank_id.name})"
        if "allow_out_payment" in self._fields:
            label = "{}, {}".format(
                label,
                self.env._("trusted for payments")
                if account.allow_out_payment
                else self.env._("not trusted for payments"),
            )
        return label

    def _payroll_changes(self, before, fields):
        """Return one human line per logged field that really changed."""
        self.ensure_one()
        account = self.sudo()
        yes, no = self.env._("Yes"), self.env._("No")
        labels = {
            "acc_number": self.env._("Number"),
            "bank_id": self.env._("Bank"),
            "partner_id": self.env._("Holder"),
            "allow_out_payment": self.env._("Account trusted for payments"),
            "active": self.env._("Active"),
        }
        render = {
            "acc_number": mask_number,
            "bank_id": lambda bank: bank.name or "—",
            "partner_id": lambda partner: partner.display_name or "—",
            "allow_out_payment": lambda flag: yes if flag else no,
            "active": lambda flag: yes if flag else no,
        }
        changes = []
        for name in fields:
            old, new = before[name], account[name]
            if old == new:
                continue
            changes.append(f"{labels[name]}: {render[name](old)} → {render[name](new)}")
        return changes

    def _payroll_log(self, employees, body):
        user = self.env.user
        body = Markup("%s<br/>%s") % (
            escape(body) if not isinstance(body, Markup) else body,
            self.env._("By %s.", user.name),
        )
        for employee in employees.sudo():
            employee._message_log(body=body, author_id=user.partner_id.id)
