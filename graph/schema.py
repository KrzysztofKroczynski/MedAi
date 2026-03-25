# Neo4j schema initialization.
# Applies uniqueness constraints and indexes to Neo4j.
# Must be safe to run multiple times (use CREATE CONSTRAINT IF NOT EXISTS).
# Constraints to create:
#   - UNIQUE on Drug.name
#   - UNIQUE on ActiveIngredient.name
#   - UNIQUE on Indication.name
#   - UNIQUE on Contraindication.name
#   - UNIQUE on AdverseEffect.name
#   - UNIQUE on Dose.name
#   - UNIQUE on PatientGroup.name
# Also creates a fulltext index on Drug.name for fuzzy name lookups.
# Exposes an apply() function for import by other scripts.
# When run directly (python graph/schema.py), calls apply() and exits.

import logging
from shared.neo4j_client import get_driver

logger = logging.getLogger(__name__)

_CONSTRAINTS = [
    ("drug_name_unique",             "Drug",             "name"),
    ("active_ingredient_name_unique", "ActiveIngredient", "name"),
    ("indication_name_unique",        "Indication",       "name"),
    ("contraindication_name_unique",  "Contraindication", "name"),
    ("adverse_effect_name_unique",    "AdverseEffect",    "name"),
    ("dose_name_unique",              "Dose",             "name"),
    ("patient_group_name_unique",     "PatientGroup",     "name"),
]

_FULLTEXT_INDEX = "drugNameFulltext"


def apply() -> None:
    """Apply all constraints and indexes. Safe to call multiple times."""
    driver = get_driver()
    with driver.session() as session:
        # Uniqueness constraints
        for constraint_name, label, prop in _CONSTRAINTS:
            cypher = (
                f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
            )
            session.run(cypher)
            logger.info("Constraint applied: %s", constraint_name)

        # Full-text index on Drug.name for fuzzy/case-insensitive lookups
        existing = session.run(
            "SHOW FULLTEXT INDEXES WHERE name = $name", name=_FULLTEXT_INDEX
        ).data()
        if not existing:
            session.run(
                f"CREATE FULLTEXT INDEX {_FULLTEXT_INDEX} "
                f"FOR (n:Drug) ON EACH [n.name]"
            )
            logger.info("Fulltext index created: %s", _FULLTEXT_INDEX)
        else:
            logger.info("Fulltext index already exists: %s", _FULLTEXT_INDEX)

    logger.info("Schema applied successfully.")


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    apply()
    print("Neo4j schema applied.")
