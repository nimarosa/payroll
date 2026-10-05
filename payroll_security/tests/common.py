from odoo.tests.common import TransactionCase, new_test_user

# The payroll chain, lowest first; each level implies the previous one.
READER = "payroll_security.group_payroll_reader"
PREPARER = "payroll_security.group_payroll_preparer"
APPROVER = "payroll.group_payroll_user"
MANAGER = "payroll.group_payroll_manager"
# Orthogonal add-on (Extra Rights), implies READER.
PAYMENT = "payroll_security.group_payroll_payment"


class PayrollSecurityCommon(TransactionCase):
    """One user per role plus a computable payslip, in the current company.

    No ACL is simulated for sibling modules. Where they are installed (the AR
    localization, payroll_salary_table...), computing or opening a payslip reads
    their models with the user's rights, and the auto_install glue that ships
    with them (a localization, another bridge module) grants
    the payroll levels that access for real.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.company = cls.env.company
        cls.reader = cls._user("sec_reader", READER)
        cls.preparer = cls._user("sec_preparer", PREPARER)
        cls.preparer_2 = cls._user("sec_preparer_2", PREPARER)
        cls.approver = cls._user("sec_approver", APPROVER)
        cls.approver_2 = cls._user("sec_approver_2", APPROVER)
        cls.manager = cls._user("sec_manager", MANAGER)
        cls.payment = cls._user("sec_payment", PAYMENT)
        cls.plain = cls._user("sec_plain")

        cls.category = cls.env["hr.salary.rule.category"].create(
            {"name": "Security basic", "code": "SECBASIC"}
        )
        cls.rule = cls.env["hr.salary.rule"].create(
            {
                "name": "Security salary",
                "code": "SECWAGE",
                "category_id": cls.category.id,
                "amount_select": "code",
                "amount_python_compute": "result = contract.wage",
                "sequence": 1,
            }
        )
        cls.structure = cls.env["hr.payroll.structure"].create(
            {
                "name": "Security structure",
                "code": "SECSTRUCT",
                "rule_ids": [(4, cls.rule.id)],
            }
        )
        cls.employee = cls.env["hr.employee"].create({"name": "Security employee"})
        cls.contract = cls.env["hr.contract"].create(
            {
                "name": "Security contract",
                "employee_id": cls.employee.id,
                "wage": 1000.0,
                "date_start": "2026-01-01",
                "struct_id": cls.structure.id,
                "state": "open",
            }
        )

    @classmethod
    def _user(cls, login, *groups):
        return new_test_user(
            cls.env,
            login=login,
            groups=",".join(("base.group_user",) + groups),
            company_id=cls.env.company.id,
            company_ids=[(6, 0, cls.env.company.ids)],
        )

    @classmethod
    def _slip(cls, **values):
        vals = {
            "employee_id": cls.employee.id,
            "contract_id": cls.contract.id,
            "struct_id": cls.structure.id,
            "date_from": "2026-03-01",
            "date_to": "2026-03-31",
        }
        vals.update(values)
        return cls.env["hr.payslip"].create(vals)

    @classmethod
    def _run(cls, **values):
        vals = {
            "name": "Security batch",
            "date_start": "2026-03-01",
            "date_end": "2026-03-31",
        }
        vals.update(values)
        return cls.env["hr.payslip.run"].create(vals)
