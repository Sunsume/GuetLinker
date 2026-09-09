# GuetLinker

[简体中文](README.md) | **English**

A cross-platform desktop client project for the Guilin University of Electronic
Technology campus network. The current source uses Vue 3 and TypeScript for its
dark pixel-style interface, while Tauri 2 and Rust provide desktop integration,
portal authentication, connectivity monitoring, and self-service access. No
Python runtime is required.

The current version has been validated on Windows. macOS and Linux builds remain
on the development roadmap.

> This is an unofficial open-source client. It is not affiliated with or
> endorsed by GUET Network Center or the vendor of Dr.COM. Make sure your use
> complies with the rules of your network environment.

## Download

| Windows | macOS | Linux |
|---|---|---|
| [Download v1.0.0 Windows x64](https://github.com/Sunsume/GuetLinker/releases/download/v1.0.0/GuetLinker-Windows-x64.exe) | - | - |

`-` means that a build has not been released for that platform yet; it does not
mean the platform is outside the project's roadmap. No installer has been
published for the migrated source yet; use the development instructions below
to run or build it from source.

## Features

- GUET Dr.COM wireless and Ethernet login with verified logout
- Portal-state monitoring, IPv4/IPv6 display, and automatic reconnect
- Machine-bound encrypted credential storage
- Self-service login, CAPTCHA, account status, and date-range traffic queries
- Windows autostart, start minimized, system tray, and single-instance behavior
- Responsive dark pixel-style interface

## Account Boundaries

GuetLinker uses two independent sessions:

1. Credentials on the **Connection & Settings** page authenticate the Dr.COM
   campus network session.
2. Credentials on the **Account** page authenticate the campus self-service
   management system.

A successful self-service login does not mean that the campus network is online.
The live result on the Status page is always the source of truth for connectivity.

## Structure

```text
GuetLinker/
├─ src/                     Vue pages, state logic, and visual assets
├─ src-tauri/
│  ├─ src/                  Rust authentication, monitoring, config, and commands
│  ├─ capabilities/         Tauri permissions
│  └─ Cargo.toml            Rust dependencies
├─ package.json             Frontend and development commands
└─ README.md
```

## Platform Status and Requirements

- Windows: Currently validated
- macOS: Planned; no official build is available yet
- Linux: Planned; no official build is available yet
- Node.js, Rust, and the Tauri prerequisites for the target platform
- A network environment that can reach the GUET campus portal

## Development and Testing

Install dependencies and start the development build from the repository root:

```powershell
npm install
npm run tauri dev
```

Frontend check:

```powershell
npm run build
```

Rust checks:

```powershell
cd src-tauri
cargo test --lib
cargo clippy --all-targets --all-features -- -D warnings
```

No installer is generated for now. Run `npm run tauri build` only when a package
is needed.

## Scope

The current protocol and page parsers target the GUET campus network. The target
platforms are Windows, macOS, and Linux, but only Windows has been validated so
far. Portal and operating-system updates may require corresponding compatibility
changes.

## License

MIT
