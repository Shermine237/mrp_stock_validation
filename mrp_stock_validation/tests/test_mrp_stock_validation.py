# -*- coding: utf-8 -*-

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestMrpStockValidation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search([
            ('company_id', '=', cls.env.company.id),
        ], limit=1)
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.child_location = cls.env['stock.location'].create({
            'name': 'Sous-emplacement composants',
            'location_id': cls.stock_location.id,
            'usage': 'internal',
        })
        cls.other_location = cls.env['stock.location'].create({
            'name': 'Autre emplacement composants',
            'location_id': cls.warehouse.view_location_id.id,
            'usage': 'internal',
        })
        cls.finished = cls.env['product.product'].create({
            'name': 'Produit fini validation stock',
            'type': 'consu',
            'is_storable': True,
        })
        cls.component = cls.env['product.product'].create({
            'name': 'Composant validation stock',
            'type': 'consu',
            'is_storable': True,
        })
        cls.bom = cls.env['mrp.bom'].create({
            'product_tmpl_id': cls.finished.product_tmpl_id.id,
            'product_qty': 1.0,
            'bom_line_ids': [(0, 0, {
                'product_id': cls.component.id,
                'product_qty': 4.0,
            })],
        })
        cls.finished.product_tmpl_id.mrp_stock_validation_enabled = True
        cls.finished.product_tmpl_id.mrp_stock_validation_mode = 'strict'

    def _set_qty(self, product, location, quantity):
        self.env['stock.quant']._update_available_quantity(product, location, quantity)

    def _make_mo(self, location=None, qty=1.0):
        values = {
            'product_id': self.finished.id,
            'product_qty': qty,
            'bom_id': self.bom.id,
        }
        production = self.env['mrp.production'].create(values)
        if location:
            production.location_src_id = location
        return production

    def test_component_moves_follow_the_mo_component_location(self):
        production = self._make_mo(self.other_location)
        self.assertEqual(production.location_src_id, self.other_location)
        self.assertTrue(production.move_raw_ids)
        self.assertEqual(production.move_raw_ids.location_id, self.other_location)

    def test_confirm_accepts_exact_stock_on_component_location(self):
        self._set_qty(self.component, self.stock_location, 4)
        production = self._make_mo(self.stock_location)
        production.action_confirm()
        self.assertEqual(production.state, 'confirmed')
        self.assertEqual(production.stock_availability_status, 'available')

    def test_confirm_accepts_stock_stored_in_a_child_of_location_src(self):
        self._set_qty(self.component, self.child_location, 4)
        production = self._make_mo(self.stock_location)
        self.assertEqual(production.location_src_id, self.stock_location)
        production.action_confirm()
        self.assertEqual(production.state, 'confirmed')
        self.assertEqual(production.stock_availability_status, 'available')

    def test_confirm_rejects_stock_outside_location_src(self):
        self._set_qty(self.component, self.stock_location, 4)
        production = self._make_mo(self.other_location)
        with self.assertRaises(ValidationError):
            production.action_confirm()
        self.assertEqual(production.state, 'draft')

    def test_changing_component_location_checks_the_new_location(self):
        self._set_qty(self.component, self.other_location, 4)
        production = self._make_mo(self.stock_location)
        production.location_src_id = self.other_location
        self.assertEqual(production.move_raw_ids.location_id, self.other_location)
        production.action_confirm()
        self.assertEqual(production.state, 'confirmed')

    def test_warning_mode_still_blocks_confirmation(self):
        self.finished.product_tmpl_id.mrp_stock_validation_mode = 'warning'
        self.finished.product_tmpl_id._onchange_mrp_stock_validation_mode()
        production = self._make_mo(self.stock_location)
        with self.assertRaises(ValidationError):
            production.action_confirm()

    def test_disabled_validation_allows_confirmation_without_stock(self):
        self.finished.product_tmpl_id.mrp_stock_validation_mode = 'disabled'
        self.finished.product_tmpl_id._onchange_mrp_stock_validation_mode()
        self.assertFalse(self.finished.mrp_stock_validation_enabled)
        production = self._make_mo(self.stock_location)
        production.action_confirm()
        self.assertEqual(production.state, 'confirmed')
        self.assertEqual(production.stock_availability_status, 'not_checked')

    def test_manual_check_returns_a_notification(self):
        self._set_qty(self.component, self.stock_location, 4)
        production = self._make_mo(self.stock_location)
        action = production.action_check_stock_availability()
        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(action['params']['type'], 'success')

    def test_partial_quantity_to_produce_scales_component_need(self):
        self._set_qty(self.component, self.stock_location, 4)
        production = self._make_mo(self.stock_location, qty=2.0)
        self.assertEqual(production.move_raw_ids.product_uom_qty, 8)
        with self.assertRaises(ValidationError):
            production.action_confirm()
        self.assertEqual(production.stock_availability_status, 'unavailable')

    def test_reserved_quantity_reduces_available_stock(self):
        self._set_qty(self.component, self.stock_location, 4)
        self.env['stock.quant']._update_reserved_quantity(
            self.component, self.stock_location, 1.0,
        )
        production = self._make_mo(self.stock_location)
        with self.assertRaises(ValidationError):
            production.action_confirm()
