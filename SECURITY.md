# Security policy

## Supported versions

WaveRider is currently beta software. Security fixes target the latest tagged
prerelease and the `main` branch.

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
- Secrets, device credentials, private keys, and personal configuration do not
  belong in the repository or release archives.
