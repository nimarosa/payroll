"""Every view of this module must be valid at the moment a FRESH install
creates it, not only once the whole module is loaded.

Odoo validates each ``ir.ui.view`` record as the data file loads it, against
whatever views exist at that instant. A record that xpaths a node only a LATER
record of this same module creates therefore loads fine on a database where
the module is already installed (``-u``: the later record is already there)
and dies on a fresh ``-i`` with "cannot be located in parent view". That is
exactly how 18.0.2.18.0's ``$DEPLOY_ENSURE_MODULES`` install broke production
while every ``-u`` in dev stayed green.

An Odoo test only ever runs with the module already installed, so it cannot
repeat the install. What it can do is rebuild the state each record met at
install time: walk this module's views in data-file order and, for each one,
render its model's views with every LATER record of the module deactivated
(inactive views and their children are left out of the combined arch).
"""

import ast
import os

from lxml import etree

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools.misc import file_path

MODULE = "payroll_security"


def _view_xmlids_in_load_order():
    """``ir.ui.view`` record ids, in the order a fresh install loads them."""
    manifest = file_path(f"{MODULE}/__manifest__.py")
    with open(manifest) as handle:
        data_files = ast.literal_eval(handle.read())["data"]
    xmlids = []
    for data_file in data_files:
        if not data_file.endswith(".xml"):
            continue
        tree = etree.parse(file_path(os.path.join(MODULE, data_file)))
        for record in tree.iter("record"):
            if record.get("model") == "ir.ui.view":
                xmlids.append(record.get("id"))
    return xmlids


@tagged("post_install", "-at_install")
class TestFreshInstallViewOrder(TransactionCase):
    def test_views_found(self):
        # Guard the guard: an empty walk would pass for the wrong reason.
        self.assertGreaterEqual(len(_view_xmlids_in_load_order()), 4)

    def test_each_view_valid_without_the_ones_loaded_after_it(self):
        views = [
            self.env.ref(f"{MODULE}.{xmlid}") for xmlid in _view_xmlids_in_load_order()
        ]
        for index, view in enumerate(views):
            later = self.env["ir.ui.view"].union(*views[index + 1 :])
            root = view
            while root.mode == "extension" and root.inherit_id:
                root = root.inherit_id
            with self.subTest(view=view.xml_id):
                # `ir.ui.view.write` clears the view cache itself, so the
                # render below really recombines the arch.
                later.write({"active": False})
                try:
                    self.env[root.model].get_view(view_id=root.id, view_type=root.type)
                finally:
                    later.write({"active": True})
