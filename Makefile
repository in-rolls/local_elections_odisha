PY = .venv/bin/python
RUFF = .venv/bin/ruff

.PHONY: sync collect collect-sec collect-districts data manifest lint verify check

sync:
	uv sync --frozen --all-groups

# network, through the SOCKS tunnel in ODISHA_PROXY (default
# socks5h://localhost:1080); fetches only what fetch_log.csv does not hold
collect: collect-sec collect-districts

collect-sec:
	$(PY) -m local_elections_odisha.collect.sec

collect-districts:
	$(PY) -m local_elections_odisha.collect.districts

data:
	$(PY) -m local_elections_odisha.parse.winners
	$(MAKE) manifest

manifest:
	$(PY) -m local_elections_odisha.build.release write

lint:
	$(RUFF) check .
	$(RUFF) format --check .

verify:
	$(PY) -m local_elections_odisha.build.release verify

check: lint verify
