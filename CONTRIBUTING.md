# Contributing to WaveRider

Thank you for helping improve a practical, receive-only foxhunting instrument.

## Before changing code

1. Read [`AGENTS.md`](AGENTS.md) for the hardware and evidence boundaries.
2. Read [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) before changing a
   user-visible contract.
3. Open an issue for changes that affect GPIO, power rails, USB routing,
   persistent storage, firmware loading, or radio behavior.

## Development workflow

1. Fork the repository and create a focused branch.
2. Install the development environment:

   ```text
   python3 -m pip install '.[installer,dev]'
   ```

3. Run the checks:

   ```text
   python3 -m pytest -q tests
   sh -n install.sh uninstall.sh bin/foxhuntctl bin/foxhunt-guard
   ```

4. Add or update tests and documentation with the change.
5. Open a pull request. Direct pushes to `main` are not accepted.

WaveRider currently has one maintainer, so GitHub does not require a second
person's approval or a CODEOWNER approval. A pull request can be merged only by
an account with repository write access after the required Python 3.11, Python
3.13, and canonical native-release checks pass and all review conversations are
resolved. These protections apply to administrators; outside contributors may
propose changes but cannot merge or push to `main`.

## Hardware claims

- State whether a result is host-tested, injected on hardware, or physically
  observed by a person.
- Do not report dBm without a calibration profile for the complete RF path.
- Do not add transmit behavior. WaveRider is receive-only.
- Never probe an undocumented GPIO or power control in a normal application
  path. Diagnostics must be bounded, opt-in, and restore prior state.

## Licensing contributions

By submitting a contribution, you agree that your software contribution is
licensed under GPL-3.0-or-later and your documentation/original artwork
contribution is licensed under CC BY-SA 4.0, as described in
[`LICENSES.md`](LICENSES.md). You retain copyright in your contribution.
