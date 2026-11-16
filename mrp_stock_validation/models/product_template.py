# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    mrp_stock_validation_enabled = fields.Boolean(
        string='Validation Stock MRP',
        default=True,
        help="Si activé, la validation du stock des matières premières sera obligatoire "
             "avant de confirmer un ordre de fabrication pour ce produit."
    )
    
    mrp_stock_validation_mode = fields.Selection([
        ('strict', 'Strict - Bloquer si stock insuffisant'),
        ('warning', 'Avertissement - Permettre avec notification'),
        ('disabled', 'Désactivé - Pas de validation')
    ], string='Mode de Validation', default='strict',
       help="Mode de validation du stock pour les ordres de fabrication")

    @api.onchange('mrp_stock_validation_mode')
    def _onchange_mrp_stock_validation_mode(self):
        """Synchronise le champ enabled avec le mode sélectionné"""
        if self.mrp_stock_validation_mode == 'disabled':
            self.mrp_stock_validation_enabled = False
        else:
            self.mrp_stock_validation_enabled = True
