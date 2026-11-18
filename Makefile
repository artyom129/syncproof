.PHONY: install seed seed-realistic run test reset
install:
	python -m pip install -r requirements.txt
seed:
	python scripts/seed_demo.py
seed-realistic:
	python scripts/seed_demo.py --realistic
run:
	uvicorn app.main:app --reload

test:
	pytest -q
reset:
	rm -f data/syncproof.db
	python scripts/seed_demo.py
