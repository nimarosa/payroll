"""Role checks shared by every guarded payroll transition.

`groups=` on a button only hides it; the RPC goes through regardless. Each
state-changing method therefore calls `check_payroll_access` itself.
"""

from contextvars import ContextVar

from odoo import SUPERUSER_ID
from odoo.exceptions import AccessError

READER = "reader"
PREPARER = "preparer"
APPROVER = "approver"
MANAGER = "manager"

LEVELS = {
    READER: "payroll_security.group_payroll_reader",
    PREPARER: "payroll_security.group_payroll_preparer",
    APPROVER: "payroll.group_payroll_user",
    MANAGER: "payroll.group_payroll_manager",
}

# Payslip ids whose confirmation is running right now. Set by
# action_payslip_done around super(): the recompute OCA runs inside the
# confirmation must not re-stamp `computed_by_id` (that would make the approver
# the one who computed), and the four-eyes check already ran. A ContextVar and
# not the Odoo context on purpose: an RPC client can forge context keys.
CONFIRMING = ContextVar("payroll_security_confirming", default=frozenset())
# True while refund_sheet builds and confirms its reversal payslips: they
# are a copy of an approved payslip, not a new computation.
REFUNDING = ContextVar("payroll_security_refunding", default=False)
# True only while compute_sheet stamps `computed_by_id`.
STAMPING = ContextVar("payroll_security_stamping", default=False)


#: The English name of each level. `role_name` repeats them as literals so the
#: translation export picks them up.
ROLE_NAMES = {
    READER: "Reader",
    PREPARER: "Preparer",
    APPROVER: "Approver",
    MANAGER: "Administrator",
}


def role_name(env, level):
    """The name of `level` in the language of `env`."""
    return {
        READER: env._("Reader"),
        PREPARER: env._("Preparer"),
        APPROVER: env._("Approver"),
        MANAGER: env._("Administrator"),
    }[level]


def check_payroll_access(env, level, action):
    """Raise AccessError unless the current user holds `level` (or is sudo)."""
    if env.su or env.user.has_group(LEVELS[level]):
        return
    raise AccessError(
        env._(
            "%(action)s requires the Payroll role %(role)s.",
            action=action,
            role=role_name(env, level),
        )
    )


def is_superuser(env):
    return env.uid == SUPERUSER_ID


def apply_button_groups(arch, button_groups):
    """Give every object button named in `button_groups` that declares no
    `groups` of its own the minimum level to press it.

    Runs in `_get_view`, on the combined arch and before Odoo strips the nodes
    of groups the user lacks, so it reaches buttons added by any module under
    a guarded method name. A button that already declares groups is left
    alone: the stock ones are set in this module's views, on purpose.
    """
    for node in arch.iter("button"):
        name = node.get("name")
        if name in button_groups and not node.get("groups"):
            node.set("groups", button_groups[name])
    return arch
