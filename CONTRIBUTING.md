# Contributing to Photo & Video Media Organizer

Thanks for considering a contribution! This is a small personal project,
so the process is intentionally lightweight.

## Getting set up

1. Fork and clone the repo.
2. Install [Python 3.10+](https://www.python.org/downloads/) (developed
   against 3.13).
3. From the **repository root** (the folder containing `media_organizer/`):

   ```sh
   pip install -r media_organizer/requirements.txt
   ```

4. Run the app to confirm your setup works:

   ```sh
   python -m media_organizer.app.main
   ```

Everything (the GUI, the CLI, tests) must be run from the repository root,
not from inside `media_organizer/` — see `CLAUDE.md` for why (it's a
namespace-package import quirk).

## Running the tests

```sh
python -m pytest
# or, to run a single test:
python -m pytest media_organizer/tests/test_organizer.py::test_name -v
```

Please run the full suite before opening a PR. If you're fixing a bug,
add a test that fails before your fix and passes after — see
`media_organizer/tests/` for examples of the existing style.

## Building the EXE

```powershell
./media_organizer/build_exe.ps1
```

Output lands in `build_output/`, with the `ExifTool/` folder copied
alongside the exe automatically. You don't need to build the exe to
contribute code — it's only necessary if you're testing packaging changes.

## Project structure and conventions

`CLAUDE.md` at the repo root is the living architecture doc — it covers the
extraction/organizer/UI-controller pipeline, the Windows subprocess
handling, and the threading model in detail. Read it before making
non-trivial changes; it'll save you from re-deriving decisions (like why
worker threads never touch Tk widgets directly) that are already settled.

A few things worth knowing up front:

- Follow existing patterns rather than introducing new ones for the same
  problem — this codebase already has conventions for chunked ExifTool
  calls, atomic file placement, and typed event passing between worker
  threads and the GUI.
- Keep pull requests focused. Small, single-purpose PRs are much easier to
  review than ones that mix a feature with unrelated refactoring.
- If you're adding a new supported file format, that list lives in
  `media_organizer/app/config.py`.

## Submitting a change

1. Create a branch off `main`.
2. Make your change, with tests.
3. Confirm `python -m pytest` passes.
4. Open a pull request describing what changed and why.

## License

By contributing, you agree that your contribution is licensed under this
project's [GPL-3.0 License](LICENSE).

## Support

If you'd like to support the project without contributing code, you can do
so at [buymeacoffee.com/alexnyk](https://buymeacoffee.com/alexnyk).
