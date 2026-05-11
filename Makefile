.PHONY: test doctor build check demo clean

test:
	PYTHONPATH=src python -m unittest discover -s tests -v

doctor:
	PYTHONPATH=src python -m agent_flight_recorder doctor

build:
	python -m build

check: test build doctor

demo:
	PYTHONPATH=src python -m agent_flight_recorder init --force
	PYTHONPATH=src python -m agent_flight_recorder start --capture-output -- python -c "print('demo command')"
	PYTHONPATH=src python -m agent_flight_recorder report

clean:
	rm -rf .agent-flight/sessions .agent-flight/manifest.json .agent-flight/pr-report.md build dist *.egg-info
