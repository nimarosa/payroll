{
    "name": "Payroll Security - Accounting",
    "version": "18.0.1.0.0",
    "summary": "Approvers confirm payslips and post their journal entries "
    "without accounting rights; salary rule accounts are tracked; a "
    "per-company salary journal setting",
    "author": "Nimarosa, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/payroll",
    "maintainers": ["nimarosa"],
    "development_status": "Beta",
    "license": "LGPL-3",
    "category": "Payroll",
    "depends": [
        "payroll_account",
        "payroll_security",
    ],
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "auto_install": True,
    "installable": True,
}
