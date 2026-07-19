# RomM Companion

A native, largely vibe-coded, desktop companion for [RomM](https://romm.app), built with PySide6.

## Development

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt

python romm_companion.py
python -m unittest discover -s tests
ruff check . && .venv/bin/ruff format --check .  # lint and format
mypy                                             # type check
```
