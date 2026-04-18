.PHONY: seed full wipe reset

seed:
	-docker compose down --remove-orphans
	docker compose --profile seed up --build --force-recreate --exit-code-from seed

full:
	-docker compose down --remove-orphans
	docker compose --profile full up --force-recreate

wipe:
	-docker compose down -v --remove-orphans
	-docker network prune -f

reset: wipe seed
