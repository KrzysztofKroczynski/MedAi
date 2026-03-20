# Neo4j schema initialization.
# Applies uniqueness constraints and indexes to Neo4j.
# Must be safe to run multiple times (use CREATE CONSTRAINT IF NOT EXISTS).
# Constraints to create:
#   - UNIQUE on Drug.name
#   - UNIQUE on ActiveIngredient.name
#   - UNIQUE on Indication.name
#   - UNIQUE on Contraindication.name
#   - UNIQUE on AdverseEffect.name
#   - UNIQUE on PatientGroup.name
# Also creates a fulltext index on Drug.name for fuzzy name lookups.
# Exposes an apply() function for import by other scripts.
# When run directly (python graph/schema.py), calls apply() and exits.
