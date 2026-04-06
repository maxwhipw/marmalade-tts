"""
marmalade-tts test suite.

Tests are organized into:
  test_preprocessing.py   — text normalization rules
  test_config.py          — YAML config get/set/load/save
  test_effects.py         — audio effects parsing, resolution, sox chain building
  test_cli.py             — CLI argument parsing and dispatch (no synthesis)
  test_daemon.py          — daemon status/path helpers
  test_smoke.py           — integration smoke tests (require engine binaries)

Run all unit tests (no engines needed):
  python -m pytest tests/ -v -m "not smoke"

Run smoke tests (requires engines installed):
  python -m pytest tests/ -v -m smoke

Run everything:
  python -m pytest tests/ -v
"""
