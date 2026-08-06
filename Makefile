install:
	uv sync

run:
	uv run python main.py --map maps/easy/01_linear_path.txt

debug:
	uv run python -m pdb main.py --map maps/easy/01_linear_path.txt

clean:
	rm -rf __pycache__ .mypy_cache .pytest_cache .ruff_cache .venv

lint:
	flake8 .
	mypy . --warn-return-any --warn-unused-ignores --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs

lint-strict:
	flake8 .
	mypy . --strict