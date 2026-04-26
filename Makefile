.PHONY: up down ingest seed wipe rebuild logs

up:       ## Start neo4j + app
	docker compose up neo4j app -d

down:     ## Stop all services (data preserved)
	docker compose down --remove-orphans

ingest:   ## Full pipeline: PDFs → extract → Neo4j
	docker compose run --rm --build ingest

seed:     ## Load cached JSON → Neo4j (skip extraction)
	docker compose run --rm --build seed

wipe:     ## Stop all and DELETE Neo4j data (irreversible)
	docker compose down -v --remove-orphans

rebuild:  ## Rebuild app image and restart
	docker compose build --no-cache app
	docker compose up app -d --force-recreate

logs:     ## Tail logs for all running services
	docker compose logs -f
