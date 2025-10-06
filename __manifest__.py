# -*- coding: utf-8 -*-
{
    'name': 'MRP Stock Validation',
    'version': '18.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Bloquer la production des produits finis sans stock de matières premières',
    'description': """
Module de validation de stock pour la fabrication
=================================================

Ce module ajoute une validation automatique du stock des matières premières
avant de permettre la confirmation d'un ordre de fabrication.

Fonctionnalités:
- Vérification automatique du stock disponible pour chaque composant
- Blocage de la confirmation si stock insuffisant
- Messages d'erreur détaillés indiquant les composants manquants
- Configuration par produit pour activer/désactiver la validation
- Rapport de disponibilité des matières premières
    """,
    'author': 'Votre Société',
    'website': 'https://www.votresite.com',
    'depends': [
        'mrp',
        'stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/mrp_production_views.xml',
        'views/product_template_views.xml',
        'data/mrp_stock_validation_data.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
