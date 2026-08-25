MAP ?= maps/challenger/01_the_impossible_dream.txt

install:
	uv sync

run:
	uv run python main.py --map $(MAP)

debug:
	uv run python -m pdb -- main.py --map $(MAP)

clean:
	rm -rf __pycache__ .mypy_cache .pytest_cache .ruff_cache .venv dist build *.egg-info

lint:
	uv run flake8 .
	uv run mypy . --warn-return-any --warn-unused-ignores --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs

lint-strict:
	uv run flake8 .
	uv run mypy . --strict