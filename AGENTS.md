# Contributor guidance

Before changing native firmware or its build/release path, read
`wilibsp/AGENTS.md` completely. If a tool truncates that file, continue in
chunks until EOF. The pinned WiliBSP contract is mandatory for this external
FreeWili 2 app repository.

This project is a receive-only field instrument for FreeWili 2 devices with an
onboard CM0 and a compatible RTL-SDR. Preserve the maintenance-console recovery
path in every USB-host or boot-configuration change.

Do not claim absolute dBm accuracy without a calibration profile tied to the
specific dongle, tuner-gain setting, antenna path, and attenuator state. The
default signal unit is relative dBFS.

Keep the runtime dependency-light and offline-installable. The target CM0 has
limited RAM and may have no network connection.
