"""The stock groups after install, the user migration and the uninstall."""

from odoo.tests import tagged

from ..hooks import RENAMED, apply_structure, migrate_users, uninstall_hook
from ..models.common import ROLE_NAMES, role_name
from .common import APPROVER, MANAGER, PAYMENT, PREPARER, READER, PayrollSecurityCommon

CONTRACT_MANAGER = "hr_contract.group_hr_contract_manager"


@tagged("post_install", "-at_install")
class TestStructure(PayrollSecurityCommon):
    def test_stock_groups_are_renamed(self):
        self.assertEqual(ROLE_NAMES[RENAMED[APPROVER][0]], "Approver")
        self.assertEqual(ROLE_NAMES[RENAMED[MANAGER][0]], "Administrator")
        langs = [code for code, _name in self.env["res.lang"].get_installed()]
        for xmlid, (level, _stock_name) in RENAMED.items():
            group = self.env.ref(xmlid)
            with self.subTest(group=xmlid, lang="en_US"):
                self.assertEqual(
                    group.with_context(lang="en_US").name, ROLE_NAMES[level]
                )
            # Every other installed language shows this module's translation
            # of the role, never the stock "Officer"/"Manager" one.
            for lang in langs:
                with self.subTest(group=xmlid, lang=lang):
                    self.assertEqual(
                        group.with_context(lang=lang).name,
                        role_name(self.env(context={"lang": lang}), level),
                    )

    def test_approver_no_longer_edits_contracts(self):
        approver = self.env.ref(APPROVER)
        self.assertNotIn(self.env.ref(CONTRACT_MANAGER), approver.trans_implied_ids)
        self.assertIn(self.env.ref(PREPARER), approver.implied_ids)
        access = self.env["ir.model.access"]
        for user in (self.approver, self.manager):
            with self.subTest(user=user.login):
                self.assertTrue(access.with_user(user).check("hr.contract", "read"))
                self.assertFalse(
                    access.with_user(user).check(
                        "hr.contract", "write", raise_exception=False
                    )
                )

    def test_department_rule_is_neutralised(self):
        rule = self.env.ref("payroll.hr_payroll_rule_officer")
        self.assertEqual(rule.domain_force, "[(1, '=', 1)]")

    def test_new_users_start_without_payroll(self):
        template = self.env.ref("base.default_user")
        for xmlid in (READER, PREPARER, APPROVER, MANAGER, PAYMENT, CONTRACT_MANAGER):
            with self.subTest(group=xmlid):
                self.assertNotIn(self.env.ref(xmlid), template.groups_id)
        user = self.env["res.users"].create({"name": "New", "login": "sec_new"})
        self.assertFalse(user.has_group(READER))
        self.assertFalse(user.has_group(CONTRACT_MANAGER))

    def _template_with_payroll_as_only_hr_source(self):
        """The template as `payroll` leaves it on a database where nothing
        else put HR in it: Payroll Manager (+ Contracts) is what implies HR
        Officer. Other apps' managers (Employees, Time Off...) that also
        imply it are stripped here; they are those apps' own defaults."""
        template = self.env.ref("base.default_user")
        hr_officer = self.env.ref("hr.group_hr_user")
        others = template.groups_id.filtered(
            lambda group: hr_officer in group.trans_implied_ids
        )
        template.groups_id = [(3, group.id) for group in others | hr_officer]
        template.groups_id = [(4, self.env.ref(MANAGER).id)]
        self.assertIn(hr_officer, template.groups_id)
        return template

    def test_new_users_are_not_hr_officers(self):
        self._template_with_payroll_as_only_hr_source()
        apply_structure(self.env)
        user = self.env["res.users"].create({"name": "New", "login": "sec_new_hr"})
        self.assertFalse(user.has_group("hr.group_hr_user"))
        self.assertFalse(user.has_group(READER))

    def test_hr_officer_left_by_payroll_is_dropped_existing_users_kept(self):
        template = self._template_with_payroll_as_only_hr_source()
        hr_officer = self.env.ref("hr.group_hr_user")
        officer_user = self._user("sec_hr_kept", "hr.group_hr_user")
        apply_structure(self.env)
        self.assertNotIn(hr_officer, template.groups_id)
        self.assertIn(hr_officer, officer_user.groups_id)

    def test_hr_officer_implied_by_another_template_group_stays(self):
        template = self.env.ref("base.default_user")
        hr_manager = self.env.ref("hr.group_hr_manager")
        template.groups_id = [(4, hr_manager.id)]
        apply_structure(self.env)
        self.assertIn(self.env.ref("hr.group_hr_user"), template.groups_id)
        self.assertIn(hr_manager, template.groups_id)

    def test_structure_is_idempotent(self):
        apply_structure(self.env)
        apply_structure(self.env)
        self.test_approver_no_longer_edits_contracts()
        self.test_stock_groups_are_renamed()

    def test_the_records_rewritten_here_are_noupdate_in_payroll(self):
        """Why hooks.py exists: an upgrade of payroll never touches these, so
        what the hook wrote survives it (and XML of this module could not)."""
        for xmlid in (APPROVER, MANAGER, "payroll.hr_payroll_rule_officer"):
            module, name = xmlid.split(".")
            data = self.env["ir.model.data"].search(
                [("module", "=", module), ("name", "=", name)]
            )
            with self.subTest(xmlid=xmlid):
                self.assertTrue(data.noupdate)


@tagged("post_install", "-at_install")
class TestUserMigration(PayrollSecurityCommon):
    def test_existing_payroll_users_keep_contract_edition_explicitly(self):
        officer = self._user("sec_old_officer", APPROVER)
        boss = self._user("sec_old_manager", MANAGER)
        outsider = self._user("sec_outsider", READER)
        contract_manager = self.env.ref(CONTRACT_MANAGER)
        self.assertNotIn(contract_manager, officer.groups_id)
        with self.assertLogs("odoo.addons.payroll_security.hooks") as logs:
            migrate_users(self.env)
        for user in (officer, boss):
            with self.subTest(user=user.login):
                self.assertIn(contract_manager, user.groups_id)
        self.assertNotIn(contract_manager, outsider.groups_id)
        text = "\n".join(logs.output)
        self.assertIn("sec_old_officer", text)
        # A pure Officer loses configuration write: named in the log.
        self.assertIn("lose write access", text)


@tagged("post_install", "-at_install")
class TestUninstall(PayrollSecurityCommon):
    def test_uninstall_hook_restores_stock_payroll(self):
        uninstall_hook(self.env)
        approver = self.env.ref(APPROVER)
        self.assertIn(self.env.ref(CONTRACT_MANAGER), approver.implied_ids)
        self.assertEqual(approver.with_context(lang="en_US").name, "Officer")
        self.assertNotEqual(
            self.env.ref("payroll.hr_payroll_rule_officer").domain_force,
            "[(1, '=', 1)]",
        )
        self.assertTrue(self.env.ref("payroll.access_hr_payroll_structure").perm_write)
