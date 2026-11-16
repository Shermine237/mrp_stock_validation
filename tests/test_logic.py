# -*- coding: utf-8 -*-
"""Tests exécutables sans serveur Odoo.

Ils chargent le code réel du module derrière un Odoo factice et vérifient
le comportement effectif, y compris l'emplacement utilisé pour le stock.
"""
import ast
import csv
import importlib.util
import sys
import types
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'mrp_stock_validation'


def _install_fake_odoo():
    if 'odoo' in sys.modules and getattr(sys.modules['odoo'], '_mrp_stock_fake', False):
        return

    class ValidationError(Exception):
        pass

    class UserError(Exception):
        pass

    class Field:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    fields = types.SimpleNamespace(
        Boolean=Field,
        Selection=Field,
        Text=Field,
    )

    def _decorator(*_args, **_kwargs):
        def _wrap(func):
            return func
        return _wrap

    api = types.SimpleNamespace(
        depends=_decorator,
        onchange=_decorator,
        model_create_multi=lambda func: func,
    )

    class Model:
        def action_confirm(self):
            self.super_confirmed = True
            return True

        def write(self, vals):
            self.super_written = dict(vals)
            return True

        def create(self, vals_list):
            created = types.SimpleNamespace(vals_list=vals_list, computed=False)

            def _compute():
                created.computed = True

            created._compute_stock_availability_status = _compute
            return created

    models = types.SimpleNamespace(Model=Model)

    odoo = types.ModuleType('odoo')
    odoo._mrp_stock_fake = True
    odoo.models = models
    odoo.fields = fields
    odoo.api = api
    odoo._ = lambda message: message

    exceptions = types.ModuleType('odoo.exceptions')
    exceptions.ValidationError = ValidationError
    exceptions.UserError = UserError

    sys.modules['odoo'] = odoo
    sys.modules['odoo.exceptions'] = exceptions
    return ValidationError


def _load_model(filename):
    _install_fake_odoo()
    path = MODULE / 'models' / filename
    spec = importlib.util.spec_from_file_location(f'mrp_stock_validation_{filename}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Location:
    def __init__(self, id_, name, parent=None):
        self.id = id_
        self.name = name
        self.display_name = name
        self.location_id = parent


class Product:
    def __init__(self, id_, name, uom_name='Unité(s)'):
        self.id = id_
        self.name = name
        self.uom_name = uom_name


class Uom:
    def __init__(self, name):
        self.name = name


class Move:
    def __init__(self, product, location, qty, uom_name='Unité(s)', state='draft'):
        self.product_id = product
        self.location_id = location
        self.product_uom_qty = qty
        self.product_uom = Uom(uom_name)
        self.state = state


class Quant:
    def __init__(self, product, location, available_quantity, quantity=None):
        self.product_id = product
        self.location_id = location
        self.available_quantity = available_quantity
        self.quantity = quantity if quantity is not None else available_quantity


class QuantModel:
    def __init__(self):
        self.quants = []
        self.calls = []

    def _location_matches(self, quant_location, location, strict):
        if strict:
            return quant_location.id == location.id
        current = quant_location
        while current:
            if current.id == location.id:
                return True
            current = current.location_id
        return False

    def _get_available_quantity(self, product, location, lot_id=None, package_id=None,
                                owner_id=None, strict=False, allow_negative=False):
        self.calls.append({
            'product_id': product.id,
            'location_id': location.id,
            'strict': strict,
        })
        total = sum(
            quant.available_quantity
            for quant in self.quants
            if quant.product_id.id == product.id
            and self._location_matches(quant.location_id, location, strict)
        )
        if allow_negative or total > 0:
            return total
        return 0.0


class QuantSet:
    def __init__(self, records):
        self.records = records

    def mapped(self, field_name):
        return [getattr(record, field_name) for record in self.records]


class Env(dict):
    def __init__(self, quants):
        super().__init__()
        self.quant_model = QuantModel()
        self.quant_model.quants = quants

    def __getitem__(self, model_name):
        if model_name != 'stock.quant':
            raise KeyError(model_name)
        return self.quant_model


MrpProduction = _load_model('mrp_production.py').MrpProduction
ProductTemplate = _load_model('product_template.py').ProductTemplate
ValidationError = sys.modules['odoo.exceptions'].ValidationError


class Production(MrpProduction):
    """Un ordre de fabrication unitaire, itérable comme un recordset Odoo."""

    def __init__(self, moves, quants, enabled=True, status='not_checked', location_src=None):
        self.move_raw_ids = list(moves)
        self.env = Env(quants)
        self.stock_validation_enabled = enabled
        self.stock_availability_status = status
        self.missing_components_info = False
        self.location_src_id = location_src
        self.super_confirmed = False

    def __iter__(self):
        yield self


class ProductionSet(MrpProduction):
    def __init__(self, records):
        self._records = list(records)
        self.env = records[0].env
        self.super_confirmed = False

    def __iter__(self):
        return iter(self._records)


class TestComponentLocation(unittest.TestCase):
    def setUp(self):
        self.component_location = Location(1, 'Emplacement des composants')
        self.child_location = Location(2, 'Sous-emplacement', parent=self.component_location)
        self.other_location = Location(3, 'Autre emplacement')
        self.component = Product(10, 'Vis M6')
        self.other_component = Product(11, 'Rondelle')

    def _production(self, moves, quants, enabled=True, location_src=None):
        return Production(
            moves,
            quants,
            enabled=enabled,
            location_src=location_src or self.component_location,
        )

    def test_source_reads_the_mo_component_location(self):
        source = (MODULE / 'models' / 'mrp_production.py').read_text(encoding='utf-8')
        self.assertIn('location_src_id', source)
        self.assertNotIn('move.location_id', source)
        self.assertIn('strict=False', source)

    def test_quantity_is_read_from_component_location_including_children(self):
        move = Move(self.component, self.other_location, 5)
        quants = [
            Quant(self.component, self.component_location, 100),
            Quant(self.component, self.other_location, 4),
            Quant(self.component, self.child_location, 50),
            Quant(self.other_component, self.component_location, 20),
        ]
        production = self._production([move], quants, location_src=self.component_location)

        available = production._get_available_quantity(self.component, production.location_src_id)

        self.assertEqual(available, 150)
        self.assertEqual(production.env.quant_model.calls, [{
            'product_id': self.component.id,
            'location_id': self.component_location.id,
            'strict': False,
        }])

    def test_confirm_uses_stock_on_the_mo_component_location(self):
        move = Move(self.component, self.other_location, 2)
        production = self._production(
            [move],
            [Quant(self.component, self.component_location, 10)],
            location_src=self.component_location,
        )

        self.assertTrue(production.action_confirm())
        self.assertTrue(production.super_confirmed)
        self.assertEqual(
            production.env.quant_model.calls[0]['location_id'],
            self.component_location.id,
        )

    def test_confirm_ignores_stock_that_is_only_on_the_move_location(self):
        move = Move(self.component, self.other_location, 2)
        production = self._production(
            [move],
            [Quant(self.component, self.other_location, 20)],
            location_src=self.component_location,
        )

        with self.assertRaises(ValidationError) as caught:
            production.action_confirm()

        self.assertIn('Emplacement des composants', str(caught.exception))
        self.assertFalse(production.super_confirmed)

    def test_child_locations_of_the_component_location_are_included(self):
        move = Move(self.component, self.other_location, 5)
        production = self._production(
            [move],
            [
                Quant(self.component, self.component_location, 1),
                Quant(self.component, self.child_location, 4),
            ],
        )

        self.assertEqual(
            production._get_available_quantity(self.component, production.location_src_id),
            5,
        )
        self.assertTrue(production.action_confirm())

    def test_several_quants_on_the_same_exact_location_are_summed(self):
        move = Move(self.component, self.component_location, 5)
        production = self._production(
            [move],
            [
                Quant(self.component, self.component_location, 2),
                Quant(self.component, self.component_location, 3),
            ],
        )

        self.assertEqual(production._get_available_quantity(self.component, self.component_location), 5)
        self.assertTrue(production.action_confirm())

    def test_available_quantity_is_used_not_on_hand_quantity(self):
        move = Move(self.component, self.component_location, 5)
        production = self._production(
            [move],
            [Quant(self.component, self.component_location, available_quantity=1, quantity=10)],
        )

        with self.assertRaises(ValidationError) as caught:
            production.action_confirm()

        self.assertIn('Disponible 1.00', str(caught.exception))
        self.assertIn('Manque 4.00', str(caught.exception))


class TestAvailabilityStatus(unittest.TestCase):
    def setUp(self):
        self.location = Location(1, 'Stock')
        self.screw = Product(1, 'Vis')
        self.washer = Product(2, 'Rondelle')

    def _production(self, moves, quants, enabled=True):
        return Production(moves, quants, enabled=enabled, location_src=self.location)

    def test_disabled_validation_is_not_checked(self):
        production = self._production(
            [Move(self.screw, self.location, 5)],
            [],
            enabled=False,
        )
        production._compute_stock_availability_status()
        production._compute_missing_components_info()
        self.assertEqual(production.stock_availability_status, 'not_checked')
        self.assertFalse(production.missing_components_info)

    def test_no_component_is_available(self):
        production = self._production([], [])
        production._compute_stock_availability_status()
        self.assertEqual(production.stock_availability_status, 'available')

    def test_full_stock_is_available_including_exact_quantity(self):
        production = self._production(
            [Move(self.screw, self.location, 5), Move(self.washer, self.location, 2)],
            [Quant(self.screw, self.location, 5), Quant(self.washer, self.location, 3)],
        )
        production._compute_stock_availability_status()
        production._compute_missing_components_info()
        self.assertEqual(production.stock_availability_status, 'available')
        self.assertFalse(production.missing_components_info)

    def test_partial_means_at_least_one_component_fully_covered(self):
        production = self._production(
            [Move(self.screw, self.location, 5), Move(self.washer, self.location, 2)],
            [Quant(self.screw, self.location, 5), Quant(self.washer, self.location, 1)],
        )
        production._compute_stock_availability_status()
        production._compute_missing_components_info()
        self.assertEqual(production.stock_availability_status, 'partial')
        self.assertIn('Rondelle: Besoin 2.00 Unité(s), Disponible 1.00, Manque 1.00', production.missing_components_info)
        self.assertNotIn('Vis:', production.missing_components_info)

    def test_all_components_short_is_unavailable_even_with_some_stock(self):
        production = self._production(
            [Move(self.screw, self.location, 5), Move(self.washer, self.location, 2)],
            [Quant(self.screw, self.location, 4), Quant(self.washer, self.location, 1)],
        )
        production._compute_stock_availability_status()
        self.assertEqual(production.stock_availability_status, 'unavailable')

    def test_cancelled_and_zero_quantity_moves_are_still_counted(self):
        production = self._production(
            [Move(self.screw, self.location, 0, state='cancel'), Move(self.washer, self.location, 1, state='cancel')],
            [],
        )
        production._compute_stock_availability_status()
        self.assertEqual(production.stock_availability_status, 'partial')

    def test_quantity_is_not_converted_to_the_product_uom(self):
        production = self._production(
            [Move(self.screw, self.location, 1, uom_name='Douzaine')],
            [Quant(self.screw, self.location, 1)],
        )
        production._compute_stock_availability_status()
        self.assertEqual(production.stock_availability_status, 'available')


class TestConfirmationAndActions(unittest.TestCase):
    def setUp(self):
        self.location = Location(1, 'Stock')
        self.component = Product(1, 'Vis M6x20')

    def test_confirm_blocked_message_lists_every_missing_component(self):
        production = Production(
            [
                Move(self.component, self.location, 10),
                Move(Product(2, 'Rondelle M6'), self.location, 20),
            ],
            [Quant(self.component, self.location, 5)],
            location_src=self.location,
        )
        with self.assertRaises(ValidationError) as caught:
            production.action_confirm()
        message = str(caught.exception)
        self.assertIn("Impossible de confirmer l'ordre de fabrication", message)
        self.assertIn('Stock', message)
        self.assertIn('Vis M6x20: Besoin 10.00 Unité(s), Disponible 5.00, Manque 5.00', message)
        self.assertIn('Rondelle M6: Besoin 20.00 Unité(s), Disponible 0.00, Manque 20.00', message)
        self.assertFalse(production.super_confirmed)

    def test_disabled_product_can_be_confirmed_without_stock(self):
        production = Production(
            [Move(self.component, self.location, 10)],
            [],
            enabled=False,
            location_src=self.location,
        )
        self.assertTrue(production.action_confirm())
        self.assertTrue(production.super_confirmed)

    def test_one_missing_order_blocks_the_whole_recordset(self):
        ok_order = Production(
            [Move(self.component, self.location, 1)],
            [Quant(self.component, self.location, 1)],
        )
        blocked_order = Production(
            [Move(self.component, self.location, 3)],
            [Quant(self.component, self.location, 1)],
        )
        recordset = ProductionSet([ok_order, blocked_order])
        with self.assertRaises(ValidationError):
            recordset.action_confirm()
        self.assertFalse(recordset.super_confirmed)

    def test_manual_check_notification_for_each_status(self):
        cases = [
            ('available', 'success', 'Tous les composants sont disponibles'),
            ('partial', 'warning', 'Certains composants'),
            ('unavailable', 'danger', 'Aucun composant'),
            ('not_checked', 'info', 'non activée'),
        ]
        for status, message_type, excerpt in cases:
            production = Production([], [], enabled=status != 'not_checked')
            production._compute_stock_availability_status = lambda: None
            production._compute_missing_components_info = lambda: None
            production.stock_availability_status = status
            action = production.action_check_stock_availability()
            self.assertEqual(action['type'], 'ir.actions.client')
            self.assertEqual(action['tag'], 'display_notification')
            self.assertEqual(action['params']['type'], message_type)
            self.assertIn(excerpt, action['params']['message'])

    def test_create_recomputes_status_and_write_only_for_qty_or_moves(self):
        production = Production([], [])
        production.compute_calls = 0

        def _compute():
            production.compute_calls += 1

        production._compute_stock_availability_status = _compute
        created = production.create([{'product_qty': 1}])
        self.assertTrue(created.computed)

        production.write({'product_qty': 2})
        production.write({'move_raw_ids': []})
        production.write({'location_src_id': 1})
        production.write({'origin': 'manual'})
        self.assertEqual(production.compute_calls, 3)
        self.assertEqual(production.super_written['origin'], 'manual')

    def test_force_confirm_is_not_implemented(self):
        self.assertFalse(hasattr(MrpProduction, 'action_force_confirm'))


class TestProductConfiguration(unittest.TestCase):
    def _product(self, mode='strict', enabled=True):
        product = ProductTemplate()
        product.mrp_stock_validation_mode = mode
        product.mrp_stock_validation_enabled = enabled
        return product

    def test_onchange_keeps_validation_enabled_for_strict_and_warning(self):
        for mode in ('strict', 'warning'):
            product = self._product(mode=mode, enabled=False)
            product._onchange_mrp_stock_validation_mode()
            self.assertTrue(product.mrp_stock_validation_enabled)

    def test_onchange_disables_validation_only_for_disabled_mode(self):
        product = self._product(mode='disabled', enabled=True)
        product._onchange_mrp_stock_validation_mode()
        self.assertFalse(product.mrp_stock_validation_enabled)

    def test_confirmation_does_not_read_validation_mode(self):
        source = (MODULE / 'models' / 'mrp_production.py').read_text(encoding='utf-8')
        self.assertNotIn('mrp_stock_validation_mode', source)


class TestModuleArtifacts(unittest.TestCase):
    def test_python_files_compile(self):
        for path in MODULE.rglob('*.py'):
            compile(path.read_text(encoding='utf-8'), str(path), 'exec')

    def test_manifest_declares_odoo_18_and_its_data_files(self):
        manifest = ast.literal_eval((MODULE / '__manifest__.py').read_text(encoding='utf-8'))
        self.assertEqual(manifest['version'], '18.0.1.0.0')
        self.assertEqual(manifest['depends'], ['mrp', 'stock'])
        for relative in manifest['data']:
            self.assertTrue((MODULE / relative).is_file(), relative)

    def test_production_views_expose_status_filters_and_manual_check(self):
        root = ET.parse(MODULE / 'views' / 'mrp_production_views.xml').getroot()
        xml = ET.tostring(root, encoding='unicode')
        self.assertIn('action_check_stock_availability', xml)
        self.assertIn("state not in ('draft', 'confirmed')", xml)
        self.assertIn('mrp.mrp_production_form_view', xml)
        self.assertIn('mrp.mrp_production_tree_view', xml)
        self.assertIn('mrp.view_mrp_production_filter', xml)
        for status in ('available', 'partial', 'unavailable'):
            self.assertIn(status, xml)
        self.assertNotIn('action_force_confirm', xml)
        self.assertNotIn('group_by', xml)
        self.assertNotIn('location_src_id', xml)

    def test_product_view_exposes_both_configuration_fields(self):
        root = ET.parse(MODULE / 'views' / 'product_template_views.xml').getroot()
        xml = ET.tostring(root, encoding='unicode')
        self.assertIn('mrp.product_template_form_view_bom_button', xml)
        self.assertIn("page[@name='inventory']", xml)
        self.assertIn('mrp_stock_validation_enabled', xml)
        self.assertIn('mrp_stock_validation_mode', xml)
        self.assertIn('product.product_template_tree_view', xml)

    def test_data_file_contains_an_invalid_selection_external_id(self):
        root = ET.parse(MODULE / 'data' / 'mrp_stock_validation_data.xml').getroot()
        records = {
            record.attrib['id']: record.attrib['model']
            for record in root.findall('data/record')
        }
        self.assertEqual(records['default_mrp_stock_validation_config'], 'ir.config_parameter')
        self.assertEqual(records['default_mrp_stock_validation_mode'], 'ir.config_parameter')
        self.assertEqual(records['mrp_validation_mode_strict'], 'ir.model.data')
        selection = root.find("data/record[@id='mrp_validation_mode_strict']")
        values = {field.attrib['name']: (field.text or '') for field in selection.findall('field')}
        self.assertEqual(values['model'], 'selection')
        self.assertNotIn('res_id', values)

    def test_security_csv_adds_broad_product_template_rights(self):
        with (MODULE / 'security' / 'ir.model.access.csv').open(encoding='utf-8', newline='') as handle:
            rows = list(csv.DictReader(handle))
        by_id = {row['id']: row for row in rows}
        self.assertEqual(by_id['access_product_template_mrp_user']['perm_write'], '1')
        self.assertEqual(by_id['access_product_template_mrp_user']['perm_create'], '0')
        self.assertEqual(by_id['access_mrp_production_manager']['perm_unlink'], '1')
        self.assertTrue(all(row['model_id:id'] for row in rows))

    def test_config_parameters_are_never_read_by_python(self):
        python = '\n'.join(path.read_text(encoding='utf-8') for path in (MODULE / 'models').glob('*.py'))
        self.assertNotIn('ir.config_parameter', python)
        self.assertNotIn('mrp_stock_validation.default_enabled', python)
        self.assertNotIn('mrp_stock_validation.default_mode', python)


if __name__ == '__main__':
    unittest.main(verbosity=2)
