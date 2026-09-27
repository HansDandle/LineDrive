# Contributing to LineDrive

Thanks for helping. Bug reports, guide-question phrasings that don't work, and pull requests are all welcome.

## Reporting a bug

Open an issue with:

- what you did and what you expected
- your setup: Docker or native, OS, HDHomeRun model
- the log (`docker logs linedrive`, or the terminal running `python dvr_web.py`)

For Ask LineDrive, include the exact question and what it answered. Those make good test cases.

## Development setup

```sh
git clone https://github.com/HansDandle/LineDrive.git
cd LineDrive
pip install -r requirements.txt pytest
python dvr_web.py        # http://localhost:5050
pytest                   # no tuner needed
```

A second copy for experiments shouldn't share a data folder with your real one. Run it from another folder with its own `config.json` and `DVR_PORT=5051`. Only one copy can run a schedule at a time.

## Pull requests

- Keep changes focused, and add or update a test when you change behavior (`tests/`).
- Match the surrounding style: plain Python, no new frameworks, vanilla JS in `static/js/`.
- UI changes should work on a phone and on Fire TV's Silk browser (`/guide?tv=1`).
- New settings go in `config_template.json` (with a `comment`) and, if people will want to change them, on the Settings page.

## Scope

LineDrive is a DVR for HDHomeRun tuners and over-the-air TV. Features that help record, find, or organize broadcasts fit. Features aimed at acquiring content from other sources don't.
