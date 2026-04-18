"""
Seed script: loads extraction cache into Neo4j.
Reads data/processed/extractions.json produced by ingest.py,
applies schema constraints, then writes nodes and edges.

Safe to re-run — uses MERGE so no duplicates are created.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from tqdm import tqdm

from graph.graph_builder import write_extractions
from graph.schema import apply, reset

# ---------------------------------------------------------------------------
# Logging — suppress noisy INFO lines from graph_builder during the run;
# they'd interleave with tqdm. Re-enable DEBUG to file only.
# ---------------------------------------------------------------------------
Path("logs").mkdir(exist_ok=True)

file_handler = logging.FileHandler("logs/seed.log", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))

# Only WARN+ to console (tqdm handles the visual output)
console_handler = logging.StreamHandler(sys.stderr)
console_handler.setLevel(logging.WARNING)

logging.basicConfig(level=logging.DEBUG, handlers=[file_handler, console_handler])
logger = logging.getLogger(__name__)


def _step(msg: str) -> None:
    tqdm.write(f"  {msg}")


if __name__ == "__main__":
    cache_path = Path("data/processed/extractions.json")

    tqdm.write("\nMedGraph AI - seed\n" + "-" * 40)

    # ── 1. Load cache ────────────────────────────────────────────────────────
    _step("Loading extraction cache…")
    if not cache_path.exists():
        tqdm.write(f"[ERROR] No cache at {cache_path}. Run ingest.py first.")
        raise SystemExit(1)

    try:
        with cache_path.open("r", encoding="utf-8") as fp:
            extractions = json.load(fp)
    except Exception as exc:
        tqdm.write(f"[ERROR] Failed to read cache: {exc}")
        raise SystemExit(1)

    if not extractions:
        tqdm.write("[ERROR] Cache is empty. Re-run ingest.py.")
        raise SystemExit(1)

    _step(f"Loaded {len(extractions):,} extraction records")

    # ── 2. Reset + apply schema ──────────────────────────────────────────────
    _step("Resetting graph…")
    reset()
    _step("Applying schema constraints…")
    apply()

    n = len(extractions)

    # ── 3. Build global label map ────────────────────────────────────────────
    with tqdm(
        total=n,
        desc="  Pass 1/3  label map  ",
        unit="rec",
        ncols=80,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
    ) as pbar1:

        # ── 4. Collect + write ───────────────────────────────────────────────
        with tqdm(
            total=n,
            desc="  Pass 2/3  collect    ",
            unit="rec",
            ncols=80,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
        ) as pbar2:

            with tqdm(
                total=1,
                desc="  Pass 3/3  Neo4j write",
                unit="batch",
                ncols=80,
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]",
            ) as pbar3:

                def _on_neo4j_done() -> None:
                    pbar3.update(1)

                stats = write_extractions(
                    extractions,
                    on_label_map_record=pbar1.update,
                    on_collect_record=pbar2.update,
                )
                _on_neo4j_done()

    # ── 5. Summary ───────────────────────────────────────────────────────────
    tqdm.write("\n" + "-" * 40)
    tqdm.write(f"  Records processed : {stats['records']:,}")
    tqdm.write(f"  Nodes written     : {stats['nodes']:,}")
    tqdm.write(f"  Relations written : {stats['relations']:,}")
    if stats["failed"]:
        tqdm.write(f"  Failed records    : {stats['failed']:,}  ← check logs/seed.log")
    tqdm.write("-" * 40)
    tqdm.write("  Done.\n")

    logger.info(
        "Seed complete: records=%s nodes=%s relations=%s failed=%s",
        stats["records"], stats["nodes"], stats["relations"], stats["failed"],
    )
