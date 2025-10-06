# Module MRP Stock Validation pour Odoo 18

## Description

Ce module ajoute une fonctionnalité de validation automatique du stock des matières premières avant la confirmation des ordres de fabrication dans Odoo 18. Il permet de bloquer la production des produits finis lorsque les composants nécessaires ne sont pas disponibles en stock suffisant.

## Fonctionnalités

### 🔒 Validation Automatique du Stock
- **Vérification en temps réel** : Contrôle automatique de la disponibilité des matières premières
- **Blocage intelligent** : Empêche la confirmation des ordres de fabrication sans stock suffisant
- **Messages détaillés** : Affichage précis des composants manquants avec quantités

### 📊 Interface Utilisateur Enrichie
- **Indicateurs visuels** : Badges colorés pour le statut de disponibilité du stock
- **Onglet dédié** : Page "Validation Stock" dans les ordres de fabrication
- **Boutons d'action** : Vérification manuelle et confirmation forcée
- **Filtres avancés** : Recherche par statut de stock dans les listes

### ⚙️ Configuration Flexible
- **Par produit** : Activation/désactivation de la validation pour chaque produit
- **Modes de validation** :
  - **Strict** : Blocage complet si stock insuffisant
  - **Avertissement** : Notification avec possibilité de continuer
  - **Désactivé** : Pas de validation

## Installation

1. Copiez le dossier `mrp_stock_validation` dans votre répertoire d'addons Odoo
2. Redémarrez votre serveur Odoo
3. Activez le mode développeur
4. Allez dans Apps → Mettre à jour la liste des apps
5. Recherchez "MRP Stock Validation" et installez le module

## Configuration

### Configuration des Produits

1. Allez dans **Inventaire → Produits → Produits**
2. Ouvrez un produit fabriqué
3. Dans l'onglet **Inventaire**, section **Validation Stock MRP** :
   - Cochez **Validation Stock MRP** pour activer la validation
   - Choisissez le **Mode de Validation** :
     - **Strict** : Bloque la production si stock insuffisant
     - **Avertissement** : Affiche un avertissement mais permet la continuation
     - **Désactivé** : Pas de validation de stock

### Permissions

Le module utilise les groupes de sécurité standard d'Odoo :
- **Utilisateur MRP** : Peut voir les statuts et vérifier le stock
- **Manager MRP** : Peut forcer la confirmation malgré le stock insuffisant

## Utilisation

### Création d'un Ordre de Fabrication

1. Créez un nouvel ordre de fabrication
2. Le système calcule automatiquement le statut de disponibilité :
   - 🟢 **Stock Disponible** : Tous les composants sont en stock
   - 🟡 **Stock Partiel** : Certains composants manquent
   - 🔴 **Stock Indisponible** : Composants insuffisants
   - ⚪ **Non Vérifié** : Validation désactivée

### Vérification Manuelle

- Cliquez sur **Vérifier Stock** pour actualiser le statut
- Consultez l'onglet **Validation Stock** pour les détails

### Confirmation avec Stock Insuffisant

Si vous êtes **Manager MRP** :
1. Utilisez le bouton **Forcer Confirmation** 
2. Confirmez l'action dans la boîte de dialogue
3. L'ordre sera confirmé malgré le stock insuffisant

### Filtres et Recherche

Dans la liste des ordres de fabrication :
- Filtrez par **Stock Disponible**, **Stock Partiel**, ou **Stock Insuffisant**
- Groupez par **Statut Stock** pour une vue d'ensemble
- La colonne **Statut Disponibilité** affiche l'état en temps réel

## Statuts de Stock

| Statut | Description | Couleur | Action |
|--------|-------------|---------|--------|
| **Disponible** | Tous les composants en stock | 🟢 Vert | Confirmation autorisée |
| **Partiel** | Certains composants manquent | 🟡 Orange | Blocage ou avertissement |
| **Indisponible** | Stock insuffisant | 🔴 Rouge | Blocage strict |
| **Non Vérifié** | Validation désactivée | ⚪ Gris | Pas de contrôle |

## Messages d'Erreur

### Exemple de Message de Blocage
```
Impossible de confirmer l'ordre de fabrication. Stock insuffisant pour les composants suivants:

• Vis M6x20: Besoin 10.00 Unité(s), Disponible 5.00, Manque 5.00
• Rondelle M6: Besoin 20.00 Unité(s), Disponible 0.00, Manque 20.00

Veuillez vous assurer que tous les composants sont disponibles avant de confirmer la production.
```

## Architecture Technique

### Modèles Étendus

#### `mrp.production`
- `stock_validation_enabled` : Validation activée (calculé depuis le produit)
- `stock_availability_status` : Statut de disponibilité du stock
- `missing_components_info` : Détails des composants manquants

#### `product.template`
- `mrp_stock_validation_enabled` : Activation de la validation
- `mrp_stock_validation_mode` : Mode de validation (strict/warning/disabled)

### Méthodes Principales

- `_validate_raw_materials_stock()` : Validation du stock des matières premières
- `_compute_stock_availability_status()` : Calcul du statut de disponibilité
- `_get_available_quantity()` : Récupération des quantités disponibles
- `action_check_stock_availability()` : Vérification manuelle du stock
- `action_force_confirm()` : Confirmation forcée (managers uniquement)

## Dépendances

- `mrp` : Module de fabrication Odoo
- `stock` : Module de gestion de stock Odoo

## Compatibilité

- **Version Odoo** : 18.0+
- **Base de données** : PostgreSQL
- **Python** : 3.8+

## Support et Maintenance

### Logs et Débogage

Le module utilise le système de logging standard d'Odoo. Pour activer les logs détaillés :
1. Allez dans **Paramètres → Technique → Logging**
2. Ajoutez un logger pour `mrp_stock_validation` au niveau DEBUG

### Problèmes Courants

**Q : La validation ne fonctionne pas**
R : Vérifiez que la validation est activée sur le produit dans l'onglet Inventaire

**Q : Je ne peux pas forcer la confirmation**
R : Seuls les utilisateurs du groupe "Manager MRP" peuvent forcer la confirmation

**Q : Les quantités affichées semblent incorrectes**
R : Le module utilise les quantités disponibles réelles (stock.quant). Vérifiez vos emplacements de stock.

## Licence

LGPL-3 - Voir le fichier LICENSE pour plus de détails.

## Auteur

Développé pour optimiser la gestion de production et éviter les ruptures de stock dans les processus de fabrication Odoo.
