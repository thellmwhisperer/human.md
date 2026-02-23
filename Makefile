.PHONY: test test-python test-node test-e2e lint lint-python lint-shell check

test: test-python test-node

test-python:
	python -m pytest tests/test_guard.py -v

test-node:
	node --test tests/test_guard.mjs

test-e2e:
	bash tests/test_install.sh

lint: lint-python lint-shell

lint-python:
	ruff check guard/core.py tests/test_guard.py

lint-shell:
	shellcheck guard/hook.sh guard/wrapper.bash guard/wrapper.zsh install.sh uninstall.sh

check: lint test
