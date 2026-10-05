{
    "name": "Payroll Security",
    "version": "18.0.1.0.0",
    "summary": "Payroll roles by duty: reader, preparer, approver, administrator "
    "and a payment add-on, with per-operation rules and guarded state changes",
    "author": "Nimarosa, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/payroll",
    "maintainers": ["nimarosa"],
    "development_status": "Beta",
    "license": "LGPL-3",
    "category": "Payroll",
    "depends": [
        # Every group, model, view and menu this module re-gates. Nothing
        # else on purpose: siblings (payroll_account, a localization)
        # get their own bridge modules.
        "payroll",
    ],
    "data": [
        "security/payroll_security_groups.xml",
        "security/ir.model.access.csv",
        "security/payroll_security_rules.xml",
        "views/hr_payslip_views.xml",
        "views/hr_payslip_run_views.xml",
        "views/hr_salary_rule_views.xml",
        "views/hr_payroll_structure_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    # The stock groups, the department rule and base.default_user live in a
    # noupdate file of `payroll`: XML reaches them on install only, so the
    # structural changes are (re)applied from Python. See hooks.py.
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "installable": True,
}
