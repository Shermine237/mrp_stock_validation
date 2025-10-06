# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    stock_validation_enabled = fields.Boolean(
        string='Validation de Stock Activée',
        related='product_id.mrp_stock_validation_enabled',
        readonly=True,
        help="Indique si la validation de stock est activée pour ce produit"
    )
    
    stock_availability_status = fields.Selection([
        ('available', 'Stock Disponible'),
        ('partial', 'Stock Partiel'),
        ('unavailable', 'Stock Indisponible'),
        ('not_checked', 'Non Vérifié')
    ], string='Statut Disponibilité', default='not_checked', compute='_compute_stock_availability_status', store=True)
    
    missing_components_info = fields.Text(
        string='Composants Manquants',
        compute='_compute_missing_components_info',
        help="Détails des composants avec stock insuffisant"
    )

    @api.depends('move_raw_ids', 'move_raw_ids.product_uom_qty', 'move_raw_ids.reserved_availability')
    def _compute_stock_availability_status(self):
        """Calcule le statut de disponibilité du stock pour la production"""
        for production in self:
            if not production.stock_validation_enabled:
                production.stock_availability_status = 'not_checked'
                continue
                
            if not production.move_raw_ids:
                production.stock_availability_status = 'available'
                continue
            
            total_components = len(production.move_raw_ids)
            available_components = 0
            
            for move in production.move_raw_ids:
                # Vérifier la disponibilité réelle du stock
                available_qty = self._get_available_quantity(move.product_id, move.location_id)
                if available_qty >= move.product_uom_qty:
                    available_components += 1
            
            if available_components == total_components:
                production.stock_availability_status = 'available'
            elif available_components == 0:
                production.stock_availability_status = 'unavailable'
            else:
                production.stock_availability_status = 'partial'

    @api.depends('move_raw_ids', 'stock_availability_status')
    def _compute_missing_components_info(self):
        """Calcule les informations sur les composants manquants"""
        for production in self:
            if not production.stock_validation_enabled or production.stock_availability_status == 'available':
                production.missing_components_info = False
                continue
            
            missing_info = []
            for move in production.move_raw_ids:
                available_qty = self._get_available_quantity(move.product_id, move.location_id)
                needed_qty = move.product_uom_qty
                
                if available_qty < needed_qty:
                    missing_qty = needed_qty - available_qty
                    missing_info.append(
                        f"• {move.product_id.name}: Besoin {needed_qty:.2f} {move.product_uom.name}, "
                        f"Disponible {available_qty:.2f}, Manque {missing_qty:.2f}"
                    )
            
            production.missing_components_info = '\n'.join(missing_info) if missing_info else False

    def _get_available_quantity(self, product, location):
        """Récupère la quantité disponible d'un produit dans un emplacement"""
        quants = self.env['stock.quant'].search([
            ('product_id', '=', product.id),
            ('location_id', '=', location.id),
        ])
        return sum(quants.mapped('available_quantity'))

    def action_confirm(self):
        """Override de la confirmation pour valider le stock des matières premières"""
        # Vérifier le stock avant confirmation
        self._validate_raw_materials_stock()
        return super().action_confirm()

    def _validate_raw_materials_stock(self):
        """Valide que toutes les matières premières sont disponibles en stock"""
        for production in self:
            if not production.stock_validation_enabled:
                continue
                
            missing_components = []
            
            for move in production.move_raw_ids:
                available_qty = self._get_available_quantity(move.product_id, move.location_id)
                needed_qty = move.product_uom_qty
                
                if available_qty < needed_qty:
                    missing_qty = needed_qty - available_qty
                    missing_components.append({
                        'product': move.product_id.name,
                        'needed': needed_qty,
                        'available': available_qty,
                        'missing': missing_qty,
                        'uom': move.product_uom.name
                    })
            
            if missing_components:
                error_msg = _("Impossible de confirmer l'ordre de fabrication. Stock insuffisant pour les composants suivants:\n\n")
                
                for comp in missing_components:
                    error_msg += _(
                        "• {product}: Besoin {needed:.2f} {uom}, "
                        "Disponible {available:.2f}, Manque {missing:.2f}\n"
                    ).format(**comp)
                
                error_msg += _("\nVeuillez vous assurer que tous les composants sont disponibles avant de confirmer la production.")
                
                raise ValidationError(error_msg)

    def action_check_stock_availability(self):
        """Action pour vérifier manuellement la disponibilité du stock"""
        self._compute_stock_availability_status()
        self._compute_missing_components_info()
        
        if self.stock_availability_status == 'available':
            message = _("Tous les composants sont disponibles en stock.")
            message_type = 'success'
        elif self.stock_availability_status == 'partial':
            message = _("Certains composants ne sont pas disponibles en quantité suffisante.")
            message_type = 'warning'
        elif self.stock_availability_status == 'unavailable':
            message = _("Aucun composant n'est disponible en stock suffisant.")
            message_type = 'danger'
        else:
            message = _("Validation de stock non activée pour ce produit.")
            message_type = 'info'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Vérification de Stock'),
                'message': message,
                'type': message_type,
                'sticky': False,
            }
        }

    def action_force_confirm(self):
        """Action pour forcer la confirmation malgré le stock insuffisant"""
        # Désactiver temporairement la validation pour cette production
        for production in self:
            production.with_context(skip_stock_validation=True).action_confirm()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Production Forcée'),
                'message': _('La production a été confirmée malgré le stock insuffisant.'),
                'type': 'warning',
                'sticky': False,
            }
        }

    def action_confirm(self):
        """Override avec gestion du contexte de validation"""
        if not self.env.context.get('skip_stock_validation'):
            self._validate_raw_materials_stock()
        return super().action_confirm()

    @api.model
    def create(self, vals):
        """Override create pour calculer le statut initial"""
        production = super().create(vals)
        production._compute_stock_availability_status()
        return production

    def write(self, vals):
        """Override write pour recalculer le statut si nécessaire"""
        result = super().write(vals)
        
        # Recalculer si les mouvements de matières premières ont changé
        if any(field in vals for field in ['move_raw_ids', 'product_qty']):
            self._compute_stock_availability_status()
            
        return result
