# How to contribute

Português: [CONTRIBUTING.md](CONTRIBUTING.md)

Thank you for your interest. The project is at an early stage of technical proofs; before sending anything, open an issue describing the idea.

## Running the tests
The environment is a conda environment named `openbim`, using only the conda-forge channel. Step by step in [docs/dev-setup.md](docs/dev-setup.md) (in Portuguese). In short:

```bash
conda env create -f environment.yml
conda activate openbim
QT_QPA_PLATFORM=offscreen pytest
```

CI runs the same on Linux and Windows; both must be green to merge. Do not send code without tests.

## Research only from public sources
To learn how a feature should work, use only:
- public documentation and online help of other programs;
- open standards (IFC, IDS, BCF, bSDD) and open-source code with an identified license;
- articles and books (only the ideas, without copying text);
- behavior tests done by you with a program you legally own and models of your own.

**We do not accept:** reverse engineering or inspection of binaries and proprietary formats (`.rvt`, `.rfa`, `.pln`, DWG through a closed SDK); closed SDKs (ODA, RealDWG); icons, screens, help texts or trademarks of other programs; excerpts of ABNT standards in code, documents or tests.

## Research sheet
Every feature inspired by other software needs a sheet before the implementation proposal. Open an issue (or write it in the PR text) using this template:

```
Feature: (short name)
Reference software: (name and version, if any)
Sources consulted: (links to public documentation, open standard, licensed open-source code)
How the feature behaves: (description in your own words, no copied text or screenshots)
What was NOT done: (confirm: no reverse engineering, no closed SDK, no copied icons, screens or help text)
License of any code you intend to reuse: (SPDX or "none")
Proposed decision: (what to implement and what to leave out)
```

## Licenses
- The project is AGPL-3.0-or-later. Only code with a compatible license enters: MIT, BSD, Apache-2.0, ISC, MPL-2.0, LGPL, GPL-3 and AGPL-3.
- **Not accepted:** GPL-2.0-only, code without a license, proprietary code, CC-BY-NC or CC-BY-ND material.
- All copied code carries a comment with origin, license and version, and a line in [THIRD_PARTY.md](THIRD_PARTY.md).
- **We do not accept code of proprietary origin**, even with good intentions.

## Architecture decisions
Changes that affect structure (processes, file format, dependencies) go through an ADR in [docs/adr/](docs/adr/). See the index for how to propose one.

## Personal data
Never send client or third-party projects to the public repository.
