.PHONY: seed full

seed:
	docker compose --profile seed up

full:
	docker compose --profile full up
