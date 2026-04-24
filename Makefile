.PHONY: test eval ci clean

PYTHON := python

test:
	$(PYTHON) -m unittest discover tests/characterization/ -v

eval:
	$(PYTHON) tests/eval/score.py

ci: test eval

scouts:
	$(PYTHON) scripts/scouts.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f scripts/scouts_output.json
