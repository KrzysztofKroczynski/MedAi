# Neo4j schema initialization.
# Runs once on ingest startup to apply uniqueness constraints and indexes.
# Constraints to create:
#   - UNIQUE on Drug.name
#   - UNIQUE on ActiveIngredient.name
#   - UNIQUE on Indication.name
#   - UNIQUE on Contraindication.name
#   - UNIQUE on AdverseEffect.name
#   - UNIQUE on PatientGroup.name
# Also creates a fulltext index on Drug.name for fuzzy name lookups.
