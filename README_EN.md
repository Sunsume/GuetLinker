# GuetLinker

[简体中文](README.md)

An unofficial Windows campus-network client for Guilin University of Electronic Technology. Vue 3 and TypeScript render the dark pixel-style interface, while Tauri 2 and Rust handle desktop integration, portal authentication, connectivity monitoring, and self-service access. No Python runtime is required.

## Features

- GUET Dr.COM wireless and Ethernet login with verified logout
- Portal-state monitoring, IPv4/IPv6 display, and automatic reconnect
- Machine-bound encrypted credential storage
- Self-service login, CAPTCHA, account status, and date-range traffic queries
- Windows autostart, start minimized, system tray, and single-instance behavior
- Responsive dark pixel-style interface

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

## Development

Install Node.js, Rust, and the Windows Tauri prerequisites, then run from the repository root:

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

No installer is generated for now. Run `npm run tauri build` only when a package is needed.

This project is not affiliated with or endorsed by the university network center or Dr.COM.

## License

MIT
