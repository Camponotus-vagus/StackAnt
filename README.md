# StackAnt

Focus-stacking GUI for macro entomology photography.

Takes a video (or folder of images) of a specimen photographed with a manual
focus pull, extracts and filters frames, runs focus stacking, and exports a
publication-ready composite image.

**Status:** in development — see `docs/PLAN.md` for the build roadmap.

## Requirements

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/)
- [focus-stack](https://github.com/PetteriAimonen/focus-stack) (CLI tool by Petteri Aimonen)

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## License

MIT — see `LICENSE`.
