# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import re
from unittest import mock

from lxml import etree

from odoo.exceptions import AccessError, UserError
from odoo.fields import Date
from odoo.tests import Form
from odoo.tools.safe_eval import safe_eval

from .common import TestPayslipBase

PRIMARY_CLASSES = ("oe_highlight", "btn-primary")


class TestPayslipBatchCommon(TestPayslipBase):
    def setUp(self):
        super().setUp()
        self.apply_contract_cron()
        self.sally_contract = self.sally.contract_ids
        today = Date.today()
        self.run = self.env["hr.payslip.run"].create(
            {
                "name": "Batch under test",
                "date_start": today.replace(day=1),
                "date_end": Date.end_of(today, "month"),
            }
        )

    def _draft_slip(self, contract):
        """A payslip of the batch, created but not computed yet."""
        return self.env["hr.payslip"].create(
            {
                "name": "Payslip",
                "employee_id": contract.employee_id.id,
                "contract_id": contract.id,
                "struct_id": contract.struct_id.id,
                "date_from": self.run.date_start,
                "date_to": self.run.date_end,
                "payslip_run_id": self.run.id,
            }
        )

    def _wizard(self):
        return (
            self.env["hr.payslip.employees"]
            .with_context(active_model="hr.payslip.run", active_id=self.run.id)
            .create({})
        )


class TestPayslipBatchName(TestPayslipBatchCommon):
    def test_default_name_is_the_period(self):
        run = self.env["hr.payslip.run"].create({})
        period = Date.today().strftime("%m/%Y")
        self.assertEqual(run.name, f"Payslip Batch {period}")

    def test_default_name_follows_the_default_period(self):
        run = (
            self.env["hr.payslip.run"]
            .with_context(default_date_start="2011-09-01")
            .create({"date_end": "2011-09-30"})
        )
        self.assertEqual(run.name, "Payslip Batch 09/2011")

    def test_name_follows_the_period_until_somebody_types_one(self):
        run = self.env["hr.payslip.run"].new({"date_start": "2011-09-01"})
        run._onchange_date_start_name()
        self.assertEqual(run.name, "Payslip Batch 09/2011")
        run.name = "Bonus run"
        run.date_start = Date.to_date("2011-10-01")
        run._onchange_date_start_name()
        self.assertEqual(run.name, "Bonus run")

    def test_only_the_exact_shape_is_a_default_name(self):
        run = self.env["hr.payslip.run"]
        self.assertTrue(run._is_default_name("Payslip Batch 09/2011"))
        self.assertFalse(run._is_default_name("Payslip Batch 09/2011 (bonus)"))
        self.assertFalse(run._is_default_name("Payslip Batch September"))
        self.assertFalse(run._is_default_name(False))


class TestPayslipBatchStageAndTotals(TestPayslipBatchCommon):
    def test_stage_follows_the_payslips(self):
        self.assertEqual(self.run.stage, "draft")
        slip = self._draft_slip(self.richard_contract)
        self.assertEqual(self.run.stage, "progress")
        self.assertEqual(self.run.draft_slip_count, 1)
        slip.compute_sheet()
        self.assertEqual(self.run.stage, "progress")
        self.assertEqual(self.run.draft_slip_count, 0)
        self.assertEqual(self.run.verify_slip_count, 1)
        slip.action_payslip_done()
        self.assertEqual(self.run.stage, "confirmed")
        self.run.close_payslip_run()
        self.assertEqual(self.run.stage, "close")
        self.run.draft_payslip_run()
        self.assertEqual(self.run.stage, "confirmed")

    def test_cancelled_payslips_do_not_hold_the_batch_in_progress(self):
        done = self._draft_slip(self.richard_contract)
        cancelled = self._draft_slip(self.sally_contract)
        done.action_payslip_done()
        cancelled.action_payslip_cancel()
        self.assertEqual(self.run.stage, "confirmed")

    def test_net_wage_is_the_net_line(self):
        slip = self._draft_slip(self.richard_contract)
        self.assertEqual(slip.net_wage, 0.0)
        slip.compute_sheet()
        net = slip.line_ids.filtered(lambda line: line.code == "NET")
        self.assertTrue(net.total)
        self.assertEqual(slip.net_wage, net.total)

    def test_net_wage_of_a_refund_is_negative(self):
        slip = self._draft_slip(self.richard_contract)
        slip.action_payslip_done()
        slip.refund_sheet()
        self.assertEqual(slip.refunded_id.net_wage, -slip.net_wage)

    def test_net_total_adds_up_the_payslips_but_the_cancelled_ones(self):
        first = self._draft_slip(self.richard_contract)
        second = self._draft_slip(self.sally_contract)
        self.assertEqual(self.run.net_total, 0.0)
        (first | second).compute_sheet()
        self.assertEqual(self.run.net_total, first.net_wage + second.net_wage)
        second.action_payslip_cancel()
        self.assertEqual(self.run.net_total, first.net_wage)


class TestPayslipBatchBulkActions(TestPayslipBatchCommon):
    def setUp(self):
        super().setUp()
        self.good = self._draft_slip(self.richard_contract)
        self.bad = self._draft_slip(self.sally_contract)

    def _break(self, method, error):
        """Make ``method`` raise ``error`` for ``self.bad`` only."""
        slip_class = type(self.env["hr.payslip"])
        original = getattr(slip_class, method)
        bad = self.bad

        def fake(slips, *args, **kwargs):
            if bad in slips:
                raise error
            return original(slips, *args, **kwargs)

        return mock.patch.object(slip_class, method, fake)

    def test_compute_all_computes_every_draft_payslip(self):
        result = self.run.action_compute_all()
        self.assertEqual(set((self.good | self.bad).mapped("state")), {"verify"})
        self.assertEqual(result["params"]["type"], "success")
        self.assertEqual(result["params"]["next"]["tag"], "soft_reload")

    def test_compute_all_names_the_failures_and_keeps_the_rest(self):
        with self._break("compute_sheet", UserError("Broken rule: BASIC")):
            result = self.run.action_compute_all()
        self.assertEqual(self.good.state, "verify")
        self.assertEqual(self.bad.state, "draft")
        params = result["params"]
        self.assertEqual(params["type"], "warning")
        self.assertTrue(params["sticky"])
        self.assertIn("Sally: Broken rule: BASIC", params["message"])
        body = self.run.message_ids[0].body
        self.assertIn("Sally: Broken rule: BASIC", body)

    def test_confirm_all_computes_and_confirms(self):
        result = self.run.action_confirm_all()
        self.assertEqual(set((self.good | self.bad).mapped("state")), {"done"})
        self.assertEqual(result["params"]["type"], "success")
        self.assertEqual(self.run.stage, "confirmed")

    def test_confirm_all_names_the_failures_and_keeps_the_rest(self):
        with self._break("action_payslip_done", UserError("No account")):
            result = self.run.action_confirm_all()
        self.assertEqual(self.good.state, "done")
        self.assertEqual(self.bad.state, "draft")
        self.assertIn("Sally: No account", result["params"]["message"])
        self.assertEqual(self.run.stage, "progress")

    def test_nothing_pending_is_refused(self):
        self.good.action_payslip_done()
        self.bad.action_payslip_cancel()
        with self.assertRaises(UserError):
            self.run.action_confirm_all()
        with self.assertRaises(UserError):
            self.run.action_compute_all()

    def test_a_missing_access_right_is_not_a_failed_payslip(self):
        with (
            self._break("compute_sheet", AccessError("Not allowed")),
            self.assertRaises(AccessError),
        ):
            self.run.action_compute_all()

    def test_bugs_are_not_swallowed(self):
        with (
            self._break("compute_sheet", ZeroDivisionError("bug")),
            self.assertRaises(ZeroDivisionError),
        ):
            self.run.action_compute_all()


class TestGeneratePayslipsWizard(TestPayslipBatchCommon):
    def _contract(self, name, **values):
        employee = self.env["hr.employee"].create({"name": name})
        return self.Contract.create(
            {
                "name": name,
                "employee_id": employee.id,
                "wage": 1000.0,
                "struct_id": self.sales_pay_structure.id,
                "date_start": "2000-01-01",
                "state": "open",
                **values,
            }
        )

    def test_proposes_whoever_has_a_contract_in_the_period(self):
        left_this_month = self._contract(
            "Left this month", date_end=self.run.date_start, state="close"
        )
        starts_later = self._contract(
            "Starts later", date_start=Date.add(self.run.date_end, days=1)
        )
        left_before = self._contract(
            "Left before",
            date_end=Date.subtract(self.run.date_start, days=1),
            state="close",
        )
        cancelled = self._contract("Cancelled", state="cancel")
        wizard = self._wizard()
        employees = wizard.line_ids.employee_id
        self.assertIn(self.richard_emp, employees)
        self.assertIn(left_this_month.employee_id, employees)
        self.assertNotIn(starts_later.employee_id, employees)
        self.assertNotIn(left_before.employee_id, employees)
        self.assertNotIn(cancelled.employee_id, employees)
        line = wizard.line_ids.filtered(
            lambda item: item.employee_id == self.richard_emp
        )
        self.assertEqual(line.contract_id, self.richard_contract)
        self.assertEqual(line.struct_id, self.developer_pay_structure)
        self.assertEqual(wizard.date_start, self.run.date_start)

    def test_other_companies_are_not_proposed(self):
        other = self.env["res.company"].create({"name": "Another company"})
        stranger = self._contract("Stranger", company_id=other.id)
        stranger.employee_id.company_id = other
        self.assertNotIn(stranger.employee_id, self._wizard().line_ids.employee_id)

    def test_employees_already_in_the_batch_are_not_proposed_again(self):
        self._draft_slip(self.richard_contract)
        employees = self._wizard().line_ids.employee_id
        self.assertNotIn(self.richard_emp, employees)
        self.assertIn(self.sally, employees)

    def test_generates_for_the_lines_left_in_the_list(self):
        wizard = self._wizard()
        wizard.line_ids.filtered(lambda line: line.employee_id == self.sally).unlink()
        wizard.compute_sheet()
        self.assertIn(self.richard_emp, self.run.slip_ids.employee_id)
        self.assertNotIn(self.sally, self.run.slip_ids.employee_id)

    def test_an_empty_list_is_refused(self):
        wizard = self._wizard()
        wizard.line_ids.unlink()
        with self.assertRaises(UserError):
            wizard.compute_sheet()

    def test_employees_given_explicitly_win(self):
        wizard = self._wizard()
        wizard.employee_ids = self.sally
        wizard.compute_sheet()
        self.assertEqual(self.run.slip_ids.employee_id, self.sally)

    def test_a_line_added_by_hand_finds_its_contract(self):
        wizard = self._wizard()
        wizard.line_ids.unlink()
        with Form(wizard) as form, form.line_ids.new() as line:
            line.employee_id = self.sally
            self.assertEqual(line.contract_id, self.sally_contract)


class TestPayslipBatchViews(TestPayslipBatchCommon):
    def _visible_primaries(self, record, **forced):
        arch = etree.fromstring(record.get_view(view_type="form")["arch"])
        visible = []
        for button in arch.findall("./header/button"):
            expression = button.get("invisible") or "False"
            names = set(re.findall(r"[a-z_]+", expression))
            values = {name: record[name] for name in names if name in record._fields}
            values.update(forced)
            if safe_eval(expression, values):
                continue
            if set((button.get("class") or "").split()) & set(PRIMARY_CLASSES):
                visible.append(button.get("name"))
        return visible

    def test_views_render(self):
        for view_type in ("form", "list", "search", "kanban"):
            self.env["hr.payslip.run"].get_view(view_type=view_type)
            self.env["hr.payslip"].get_view(view_type=view_type)
        self.env["hr.payslip.employees"].get_view(view_type="form")

    def test_batch_highlights_one_button_per_step(self):
        generate = str(self.env.ref("payroll.action_hr_payslip_by_employees").id)
        self.assertEqual(self._visible_primaries(self.run), [generate])
        slip = self._draft_slip(self.richard_contract)
        self.run.invalidate_recordset()
        self.assertEqual(self._visible_primaries(self.run), ["action_compute_all"])
        slip.compute_sheet()
        self.run.invalidate_recordset()
        self.assertEqual(self._visible_primaries(self.run), ["action_confirm_all"])
        slip.action_payslip_done()
        self.run.invalidate_recordset()
        self.assertEqual(self._visible_primaries(self.run), ["close_payslip_run"])
        self.run.close_payslip_run()
        self.assertEqual(self._visible_primaries(self.run), [])
