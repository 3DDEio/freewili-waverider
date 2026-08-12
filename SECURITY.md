# Security policy

## Supported versions

Security fixes target the latest supported `0.1.x` release and the `main`
branch. Prereleases are supported only until the next prerelease or stable
release of the same line.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that could damage hardware,
escape the bounded installer, modify persistent firmware, expose credentials,
or enable unintended radio transmission.

Use GitHub's **Private vulnerability reporting** feature on this repository.
Include:

- affected version or commit;
- FreeWili hardware/firmware version;
- reproduction steps that minimize hardware risk;
- expected and observed behavior;
- whether persistent storage, power controls, or radio behavior are involved.

The maintainers will acknowledge a complete report as soon as practical,
coordinate a fix privately, and publish credit unless anonymity is requested.

## Security boundaries

- WaveRider is receive-only.
- The native installer must reject QSPI-targeted images and execute only from
  volatile SRAM/PSRAM.
- Public releases must include checksums.
- Release tags must match the project version and point to a commit already in
  protected `main`; GitHub Actions dependencies are pinned to reviewed commits.
- The serial installer transfers only an explicit CM0 runtime allowlist. It
  must never package arbitrary untracked files from a maintainer checkout.
- Secrets, device credentials, private keys, and personal configuration do not
  belong in the repository or release archives.
