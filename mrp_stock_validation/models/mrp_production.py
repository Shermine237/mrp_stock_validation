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

    @api.depends(
        'move_raw_ids', 'move_raw_ids.product_uom_qty', 'move_raw_ids.product_id',
        'location_src_id', 'stock_validation_enabled',
    )
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
                available_qty = production._get_available_quantity(
                    move.product_id, production.location_src_id,
                )
                if available_qty >= move.product_uom_qty:
                    available_components += 1
            
            if available_components == total_components:
                production.stock_availability_status = 'available'
            elif available_components == 0:
                production.stock_availability_status = 'unavailable'
            else:
                production.stock_availability_status = 'partial'

    @api.depends(
        'move_raw_ids', 'move_raw_ids.product_uom_qty', 'move_raw_ids.product_id',
        'location_src_id', 'stock_availability_status', 'stock_validation_enabled',
    )
    def _compute_missing_components_info(self):
        """Calcule les informations sur les composants manquants"""
        for production in self:
            if not production.stock_validation_enabled or production.stock_availability_status == 'available':
                production.missing_components_info = False
                continue
            
            missing_info = []
            for move in production.move_raw_ids:
                available_qty = production._get_available_quantity(
                    move.product_id, production.location_src_id,
                )
                needed_qty = move.product_uom_qty
                
                if available_qty < needed_qty:
                    missing_qty = needed_qty - available_qty
                    missing_info.append(
                        f"• {move.product_id.name}: Besoin {needed_qty:.2f} {move.product_uom.name}, "
                        f"Disponible {available_qty:.2f}, Manque {missing_qty:.2f}"
                    )
            
            production.missing_components_info = '\n'.join(missing_info) if missing_info else False

    def _get_available_quantity(self, product, location):
        """Quantité disponible dans l'emplacement des composants et ses sous-emplacements.

        ``location`` est ``location_src_id`` de l'ordre de fabrication
        (onglet Divers, « Emplacement des composants »). ``strict=False``
        reprend le calcul standard d'Odoo : l'emplacement et ses enfants.
        """
        if not product or not location:
            return 0.0
        return self.env['stock.quant']._get_available_quantity(
            product, location, strict=False,
        )

    def _validate_raw_materials_stock(self):
        """Valide que toutes les matières premières sont disponibles en stock"""
        for production in self:
            if not production.stock_validation_enabled:
                continue
                
            missing_components = []
            location = production.location_src_id

            for move in production.move_raw_ids:
                available_qty = production._get_available_quantity(move.product_id, location)
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
                location_name = location.display_name if location else _("non défini")
                error_msg = _(
                    "Impossible de confirmer l'ordre de fabrication. "
                    "Stock insuffisant dans l'emplacement « %(location)s » pour les composants suivants:\n\n"
                ) % {'location': location_name}
                
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


    def action_confirm(self):
        """Override de la confirmation pour valider le stock des matières premières"""
        self._validate_raw_materials_stock()
        return super().action_confirm()

    @api.model_create_multi
    def create(self, vals_list):
        """Override create pour calculer le statut initial"""
        productions = super().create(vals_list)
        productions._compute_stock_availability_status()
        return productions

    def write(self, vals):
        """Override write pour recalculer le statut si nécessaire"""
        result = super().write(vals)
        
        # Recalculer si les mouvements de matières premières ont changé
        if any(field in vals for field in ['move_raw_ids', 'product_qty', 'location_src_id']):
            self._compute_stock_availability_status()
            
        return result
