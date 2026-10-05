"""Structural changes to `payroll`'s noupdate records, and the one-time user
migration.

`payroll.group_payroll_user`, `payroll.group_payroll_manager`, the department
rule `payroll.hr_payroll_rule_officer` and the `base.default_user` template
all come from a noupdate file of `payroll` (and `hr_contract`). An XML record
of this module reaches them on install only and is ignored on every upgrade,
so they are written from Python:

- `apply_structure` is idempotent: it runs on install, and any later
  migration script may call it again;
- `migrate_users` runs once, on install: it must never run again, or it would
  hand contract edition back to someone an administrator removed it from on
  purpose.
"""

import logging

from odoo import Command

from .models.common import APPROVER as APPROVER_LEVEL
from .models.common import MANAGER as MANAGER_LEVEL
from .models.common import ROLE_NAMES, role_name

_logger = logging.getLogger(__name__)

APPROVER = "payroll.group_payroll_user"
MANAGER = "payroll.group_payroll_manager"
PREPARER = "payroll_security.group_payroll_preparer"
READER = "payroll_security.group_payroll_reader"
PAYMENT = "payroll_security.group_payroll_payment"
CONTRACT_MANAGER = "hr_contract.group_hr_contract_manager"
OFFICER_RULE = "payroll.hr_payroll_rule_officer"
HR_OFFICER = "hr.group_hr_user"

# The stock groups this module renames: their level here, and the name
# `payroll` gives them.
RENAMED = {
    APPROVER: (APPROVER_LEVEL, "Officer"),
    MANAGER: (MANAGER_LEVEL, "Manager"),
}
ALL_COMPANIES_DOMAIN = "[(1, '=', 1)]"
OFFICER_RULE_DOMAIN = (
    "['|','|', ('employee_id.user_id', '=', user.id), "
    "('employee_id.department_id', '=', False), "
    "('employee_id.department_id.manager_id.user_id', '=', user.id)]"
)
# payroll's own ACLs this module lowers to read-only for the approver.
CONFIG_ACLS = (
    "payroll.access_hr_payroll_structure",
    "payroll.access_hr_contribution_register",
    "payroll.access_hr_salary_rule_category",
    "payroll.access_hr_rule_input_officer",
)


def _installed_langs(env):
    # en_US is always the source value, installed or not.
    return {code for code, _name in env["res.lang"].get_installed()} | {"en_US"}


def _rename(env, xmlid, names):
    group = env.ref(xmlid, raise_if_not_found=False)
    if group:
        group.update_field_translations("name", names)


def _role_names(env, level):
    """The name of `level` in every installed language: the English one as the
    source value, this module's own translation of it everywhere else."""
    names = {"en_US": ROLE_NAMES[level]}
    for lang in _installed_langs(env) - {"en_US"}:
        names[lang] = role_name(env(context=dict(env.context, lang=lang)), level)
    return names


def apply_structure(env):
    """Put the stock groups, rule and template where the role model wants
    them. Safe to run any number of times."""
    approver = env.ref(APPROVER)
    for xmlid, (level, _stock_name) in RENAMED.items():
        _rename(env, xmlid, _role_names(env, level))

    # The approver sits on top of the preparer and no longer edits contracts.
    approver.implied_ids = [
        Command.link(env.ref(PREPARER).id),
        Command.unlink(env.ref(CONTRACT_MANAGER).id),
    ]

    # Scope is the company, for every level (the department rule is OR-ed
    # with the approver rule anyway; neutralising it keeps the record honest).
    rule = env.ref(OFFICER_RULE, raise_if_not_found=False)
    if rule and rule.domain_force != ALL_COMPANIES_DOMAIN:
        rule.domain_force = ALL_COMPANIES_DOMAIN

    # A new user no longer starts as payroll and contracts administrator.
    template = env.ref("base.default_user", raise_if_not_found=False)
    if template:
        remove = env["res.groups"]
        for xmlid in (MANAGER, APPROVER, PREPARER, READER, PAYMENT, CONTRACT_MANAGER):
            remove |= env.ref(xmlid)
        found = template.groups_id & remove
        if found:
            template.groups_id = [Command.unlink(group.id) for group in found]
            _logger.info(
                "payroll_security: removed %s from the default user template",
                ", ".join(found.mapped("full_name")),
            )
        _drop_hr_officer_from_template(env, template)


def _drop_hr_officer_from_template(env, template):
    """HR Officer reached the template only through the payroll/contracts
    chain (both imply it). Once those groups are gone, drop it too, unless
    another group still in the template implies it, i.e. someone wanted it
    there for a reason of their own. Existing users are not touched."""
    hr_officer = env.ref(HR_OFFICER)
    if hr_officer not in template.groups_id:
        return
    others = template.groups_id - hr_officer
    if hr_officer in others.trans_implied_ids:
        return
    template.groups_id = [Command.unlink(hr_officer.id)]
    _logger.info(
        "payroll_security: removed %s from the default user template",
        hr_officer.full_name,
    )


def migrate_users(env):
    """Existing payroll users keep editing contracts, now explicitly, and
    the ones whose rights change are logged."""
    approver = env.ref(APPROVER)
    manager = env.ref(MANAGER)
    contract_manager = env.ref(CONTRACT_MANAGER)
    groups = (approver | manager).with_context(active_test=False)
    # Neither OdooBot nor the new-user template (apply_structure cleans it).
    members = groups.users.filtered(lambda user: not user.share) - (
        env.ref("base.user_root") | env.ref("base.default_user")
    )
    missing = members.filtered(lambda user: contract_manager not in user.groups_id)
    if missing:
        missing.write({"groups_id": [Command.link(contract_manager.id)]})
    _logger.info(
        "payroll_security: %s payroll user(s) keep contract edition, now as an "
        "explicit '%s' group: %s",
        len(members),
        contract_manager.full_name,
        ", ".join(sorted(members.mapped("login"))) or "(none)",
    )
    officers = approver.users - manager.users
    if officers:
        # INFO, not WARNING: it is the expected outcome of installing this
        # module, reported so that someone reviews the list.
        _logger.info(
            "payroll_security: these Approver (former Officer) users are not "
            "Administrator and lose write access to structures, categories, "
            "contribution registers and rule inputs: %s",
            ", ".join(sorted(officers.mapped("login"))),
        )


def post_init_hook(env):
    migrate_users(env)
    apply_structure(env)


def uninstall_hook(env):
    """Back to stock `payroll`: names, contracts implication, department rule
    and the approver's configuration ACLs. The default user template is NOT
    given payroll administration back on purpose."""
    # The stock English name back, and no translation of ours left behind:
    # the other languages show it until `payroll` reloads its own (any
    # upgrade of `payroll` does).
    langs = _installed_langs(env) - {"en_US"}
    for xmlid, (_level, stock_name) in RENAMED.items():
        _rename(env, xmlid, {"en_US": stock_name, **dict.fromkeys(langs, False)})
    env.ref(APPROVER).implied_ids = [Command.link(env.ref(CONTRACT_MANAGER).id)]
    rule = env.ref(OFFICER_RULE, raise_if_not_found=False)
    if rule:
        rule.domain_force = OFFICER_RULE_DOMAIN
    for xmlid in CONFIG_ACLS:
        access = env.ref(xmlid, raise_if_not_found=False)
        if access:
            access.write({"perm_write": True, "perm_create": True, "perm_unlink": True})
