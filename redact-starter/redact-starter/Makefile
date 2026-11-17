.PHONY: demo test

demo:
	python -m app.cli samples/test.txt --level 1
	@echo "---- redacted output ----"
	@cat out/test.redacted.txt

test:
	python -m pytest -q
