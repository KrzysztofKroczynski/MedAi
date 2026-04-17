.PHONY: seed full wipe reset

seed:
	-docker compose down --remove-orphans
	docker compose --profile seed up --force-recreate

full:
	-docker compose down --remove-orphans
	docker compose --profile full up --force-recreate

wipe:
	-docker compose down -v --remove-orphans
	-docker network prune -f

reset: wipe seed
