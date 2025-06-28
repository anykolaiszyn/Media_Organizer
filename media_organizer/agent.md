# Prompt for GitHub Copilot or any AI Assistant

I'm developing a Python/Tkinter-based Media Organizer app. I'm no longer using Docker — this is a local-first project designed to run on desktop environments.

My `TODO.md` file has been reorganized to clearly separate **Open Tasks** and **Completed Tasks**, but it still contains markdownlint formatting issues (e.g., missing blank lines around headings and lists).

Please proceed with the following:

- Fix all markdownlint issues in `TODO.md` (add blank lines where required, fix list formatting, etc.).
- Ensure the file is fully compliant with standard Markdown linting rules.
- Do not modify the wording or order of tasks — just correct the formatting.
- Preserve all comments and structure exactly as-is.

This formatting update ensures future Copilot or assistant sessions can seamlessly resume work without distractions from linter warnings.

---

## 🤝 How the AI Should Work With Me

- **Collaborate iteratively**: I will guide direction and priorities — you support me by scaffolding code, refining logic, and suggesting structure improvements.
- **Favor modularity**: Keep logic and responsibilities separated across files (UI, metadata, file ops, etc.).
- **Respect what exists**: Don't rewrite working components unless there’s a clear improvement or requested change.
- **Propose, don’t presume**: When adding features, offer suggested patterns and filenames, and wait for confirmation if unsure.
- **Be code-aware**: If logic can be abstracted or reused, recommend utility functions or helper modules.
- **Adapt to local workflows**: Assume this is run from the desktop, not a server or container.
- **Be linter-friendly**: Format code and markdown to avoid future warnings or cleanup work.
- **Support future extensions**: If changes could affect CLI mode, web UI, or new file types, include a `TODO:` or comment block with guidance.

Let’s build cleanly, modularly, and with future flexibility in mind.
