# OpenBIM Studio

Português: [README.md](README.md)

Open, general-purpose BIM software with IFC as the model's source of truth. The core is not tied to any country; the first regional package, which defines version 1.0, is **Brazil**: residential legal and executive design to the ABNT standard. Other countries come later as regional packages.

> The name "OpenBIM Studio" is provisional.

## Stage
**Phase 0: technical proofs.** There is no usable version yet. Nothing here promises a delivery date.

## Transparency: who builds it, how, and for whom

**Who builds it.** OpenBIM Studio is a one-person project: Rafael, an architect, who defines what the software must do and accepts or rejects each step. He does not write code. The code is written by artificial intelligence agents (Claude models from Anthropic), led by a "technical lead" that is also an AI. Today there is no team of experienced programmers behind it.

**How the code is made.** Every task starts as a written card with acceptance criteria. The **tests** are written by a different AI than the one that writes the **code**, and the code does not go in unless those tests pass. Delicate parts (the Python/C++ bridge, multi-threaded work, file saving) get a **cross review** by a stronger model and only go in once approved. All tests run automatically on Windows and Linux on every change; nothing enters the main code with a failing test. The reports of those reviews are public in `docs/state/reports/`.

**What this does not guarantee.** Automatic tests and AI review catch a lot, but not everything. Projects built with AI tend to fail on usability details: windows that do not resize, odd navigation and selection, things that worked and later break. For that reason we will have specific regression tests (window, zoom, selection, shortcuts) before any usable release, and we want **external human review** of the critical parts.

**For whom.** For architects who cannot afford expensive BIM subscriptions, especially people starting out and working in small Brazilian towns, where a subscription can weigh up to 20% of a year's income. That is why the software is open (AGPL-3.0), with no account, no cloud and no telemetry.

**What does NOT exist yet.** There is no usable version. Today there are technical proofs: opening and displaying models, selecting parts, the Python/C++ bridge and performance measurements. There is no modeling yet, no sheets, no PDF, no DXF, and no promised date. There is also no community or external review yet. If you want to read the code and criticize it, you are welcome: see [CONTRIBUTING.en.md](CONTRIBUTING.en.md).

**Systems.** Windows and Linux: supported. **macOS: best effort, no guarantee**; it may build there, but nobody tests it by hand and failures there block nothing.

## What the project aims to be
- Windows and Linux supported; macOS: best effort, no guarantee.
- Version 1.0 focus (Brazil package): a residential house, from modeling to title-block sheets, in PDF, DXF and IFC.
- No account, no cloud, no telemetry: your files are yours.
- A project is **two files with the same name**: `Casa.ifc` (the model, clean, opens in any BIM program) and `Casa.obim` (views, sheets and dimensions, in an open format).

## License
GNU Affero General Public License v3 or later (AGPL-3.0-or-later). Full text in [LICENSE](LICENSE). Third-party components: [THIRD_PARTY.md](THIRD_PARTY.md).

## Learn more
- Plan summary: [v2/00_resumo_executivo.md](v2/00_resumo_executivo.md)
- How to contribute: [CONTRIBUTING.en.md](CONTRIBUTING.en.md)
