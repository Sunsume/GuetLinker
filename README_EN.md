# GuetLinker

[简体中文](README.md) | **English**

[![Tauri](https://img.shields.io/badge/Tauri-2.0-24C8D8?logo=tauri&logoColor=white)](https://tauri.app/)
[![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D?logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![Rust](https://img.shields.io/badge/Rust-2021-DEA584?logo=rust&logoColor=white)](https://www.rust-lang.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A modern desktop client for the **Guilin University of Electronic Technology (GUET)** campus network.

Built with **Tauri 2 + Rust** as a high-performance native backend and **Vue 3 + TypeScript + Vite** for a distinctive dark retro pixel-art interface. It completely eliminates legacy Python runtime dependencies, delivering lightweight performance, instantaneous startup, minimal memory consumption, and clean standalone installer distribution.

The current version is thoroughly validated on Windows 10 / 11; macOS and Linux ports are on the roadmap.

> [!IMPORTANT]
> **Disclaimer**: This is an unofficial open-source utility independently developed and maintained by students. It is not affiliated with or officially endorsed by the GUET Network Center or Dr.COM vendors. Please ensure compliance with campus network regulations when using this software.

---

## 📥 Downloads & Installation

> [!TIP]
> **Version Notice**: GitHub Releases provides two Windows x64 distributions:
> - 🚀 **Portable Standalone (`GuetLinker_*_x64_Portable.exe`)**: Single-file executable. Just download and run without installation—ideal for USB drives or quick deployment.
> - 📦 **Standard Setup (`GuetLinker_*_x64-setup.exe`)**: Guided installer that configures Start Menu shortcuts, desktop icons, and standard uninstallation.
>
> Visit [GitHub Releases](https://github.com/Sunsume/GuetLinker/releases) for the latest release, or follow the instructions below to [build directly from source](#5-package-windows-installer--portable-executable).

| Platform | Architecture | Status (Tauri 2) | Download & Availability |
| :--- | :--- | :--- | :--- |
| **Windows** | x64 | **Validated** | [Visit Releases for Portable / Installer](https://github.com/Sunsume/GuetLinker/releases) |
| **macOS** | Apple Silicon / Intel | Planned | In Progress |
| **Linux** | x64 | Planned | In Progress |

<details>
<summary><b>Archived Releases (Legacy Python Version)</b></summary>

- [Download v1.0.0 Windows x64 (Python Standalone)](https://github.com/Sunsume/GuetLinker/releases/download/v1.0.0/GuetLinker-Windows-x64.exe)
- *Note: This legacy build was packaged via PyInstaller with the older Qt interface, and does not include the performance improvements or pixel-art design of the Tauri 2 architecture.*
</details>

---

## ✨ Key Features

- 🚀 **Campus Network Authentication (Dr.COM)**
  - Automatically probes and adapts to the GUET Web Portal (`http://10.0.1.5/`).
  - Supports both wireless (WLAN) and Ethernet wired connections.
  - Quick ISP switching: **Campus Network (校园网)**, **China Mobile**, **China Unicom**, **China Telecom**, and **China Broadnet**.
  - Displays local IP addresses (IPv4 / IPv6) and network interface status dynamically.
  - Verified logout and immediate "Cancel Connection" support while a request is in flight.

- 🔄 **Intelligent Monitoring & Sleep/Wake Self-Healing**
  - Lightweight background heartbeat checks for campus network connectivity.
  - **Sleep/Wake Self-Healing**: Automatically resets stale sessions when a laptop wakes from sleep or hibernation, waits for adapter DHCP re-association, and immediately triggers connection probes to avoid long freezes.
  - Immediate disconnect detection with configurable exponential backoff reconnection.
  - Intuitive behavior: Pauses auto-reconnect when manually disconnected by the user to avoid fighting manual intent.

- 🔒 **Secure Local Credential Storage**
  - Credentials are never stored in plaintext—encrypted using **AES-256-GCM**.
  - Encryption key is dynamically derived from **machine hardware identity**, preventing decrypted access even if the configuration file is transferred to another device.
  - Passwords are masked (`••••••••`) by default in the interface and temporarily decrypted via native Rust commands only when the eye button is toggled.

- 📊 **Self-Service & Traffic Accounting**
  - Integrated with the campus self-service management portal.
  - In-app CAPTCHA image fetching, manual refreshing, and validation.
  - Real-time account status and anomaly warning inspection.
  - Custom date-range querying for **domestic and international** upstream, downstream, and combined traffic usage.

- 📈 **Real-Time Network Quality & Latency Waveform**
  - High-precision, microsecond-level async non-privileged TCP handshake timing for key endpoints: Campus Gateway (`10.0.1.5:80`), GUET Official Portal (`www.guet.edu.cn:443`), Public DNS (`223.5.5.5:53`), and Public WAN (`www.baidu.com:443`).
  - Dynamic 16-bar retro pixel waveform rendering real-time network stability, latency jitter, and packet loss.

- 🩺 **One-Click Network Health Check & Diagnostic Report**
  - Comprehensive multi-tier automated diagnostics: Local adapter & IP allocation -> Campus Gateway reachability -> DNS resolution -> Public WAN route -> Local stored credentials integrity.
  - Generates structured, color-coded diagnostic assessment cards with targeted troubleshooting advice.
  - **1-Click Formatted Report Export**: Copies a clean ASCII diagnostic breakdown directly to the clipboard for instant submission to the student campus IT support group.

- 🌐 **Public Egress & Proxy Node Real-Time Detection**
  - Automatically identifies real public outbound IP, geographic physical location (country, province/region, city), and ISP / datacenter provider.
  - **Intelligent Egress Security State Recognition**:
    - 🚀 **Proxy Egress Node (Active)**: Accurately identifies overseas / cloud proxy nodes, verifying that traffic bypasses campus firewalls.
    - 🟢 **Commercial ISP (Direct Safe)**: China Mobile / Telecom / Unicom commercial line, bypassing CERNET behavioral audit.
    - ⚠️ **CERNET Campus Exit (High Risk Alert)**: Detects school education network exit and alerts users against opening proxies to prevent student ID suspension.
  - One-click "Refresh Egress" button for instant status refresh after changing proxy nodes or networks.

- 🎮 **Immersive Retro Pixel-Art Desktop Experience**
  - Custom dark retro pixel art UI theme, bundling the open-source Fusion Pixel font and Pixelarticons.
  - Frameless pixel window frame (640×820 aspect ratio) with custom top drag area and quick minimization.
  - **Dynamic System Tray Status**: Persistent notification area icon reflecting live status with dynamic colors (🟢 Online / 🔴 Disconnected / 🟡 Reconnecting) and quick right-click actions including update checks.
  - **In-App Update Checking**: Background checking on launch, plus on-demand checks from the About page and tray menu with release notes and direct download links for both portable and installer packages.
  - **Native Notifications**: Desktop toast popups for reconnect, login, or network failure (with quiet mode support).
  - **Launch Preferences**: Windows autostart on boot and start-minimized to system tray.
  - **Single-Instance Enforcement**: Prevents redundant instances; launching again automatically reveals and focuses the existing window.

---

## 🛡️ Account Boundaries & Security Architecture

GuetLinker strictly isolates two independent session layers:

```text
┌─────────────────────────┐          ┌─────────────────────────┐
│  Dr.COM Portal Session  │          │   Self-Service Session  │
│  (For internet access)  │          │ (For traffic & account) │
└────────────┬────────────┘          └────────────┬────────────┘
             │                                    │
Driven by "Connection & Settings"        Driven by "Account" page
Authenticated via portal gateway        Communicates via self-service API
```

1. **Credential Boundary**: The "Connection & Settings" page authenticates the network port for Dr.COM gateway access; the "Account" page logs into the student service portal. The two credentials can be configured and managed separately.
2. **State Boundary**: A successful login to the self-service portal only means account queries are authorized; **it does not mean the device has internet access**. The live status displayed on the "Status" console is always the source of truth.
3. **Privacy Guarantee**: GuetLinker contains zero telemetry, analytics, or third-party trackers. All network packets communicate directly and strictly with GUET network portals and self-service servers.

---

## 📂 Project Structure

```text
GuetLinker/
├─ src/                             # Frontend UI (Vue 3 + TypeScript + Vite)
│  ├─ assets/                       # Static assets (Fusion Pixel font, textures, logo)
│  ├─ components/                   # Reusable components (PixelIcon, etc.)
│  ├─ composables/                  # Composables & business state (useNetwork)
│  ├─ pages/                        # Views & pages
│  │  ├─ StatusPage.vue             # Main dashboard (network status, IPs, controls)
│  │  ├─ SettingsPage.vue           # Settings (credentials, notification, autostart)
│  │  ├─ AccountPage.vue            # Self-service (CAPTCHA, account state, traffic query)
│  │  └─ AboutPage.vue              # About view (version info, repository links)
│  ├─ App.vue                       # Root application shell (custom titlebar & nav)
│  ├─ main.ts                       # Frontend entry point
│  └─ styles.css                    # Pixel art style system and design tokens
├─ src-tauri/                       # Native backend (Tauri 2 + Rust)
│  ├─ src/
│  │  ├─ auth.rs                    # Dr.COM protocol, login/logout, and ISP parsing
│  │  ├─ commands.rs                # Tauri IPC commands callable from Vue
│  │  ├─ config.rs                  # Configuration store & AES-256-GCM encryption
│  │  ├─ diagnostics.rs             # Network latency probes & one-click diagnostics
│  │  ├─ error.rs                   # Unified error definitions
│  │  ├─ lib.rs                     # Tauri plugin initialization, tray, and single-instance
│  │  ├─ main.rs                    # Desktop binary entry point
│  │  ├─ monitor.rs                 # Heartbeat checks and auto-reconnect scheduler
│  │  ├─ network.rs                 # Network adapter, local IP, and MAC discovery
│  │  ├─ portal.rs                  # Portal sniffing and redirect detection
│  │  ├─ self_service.rs            # Self-service session, CAPTCHA, and traffic parser
│  │  └─ state.rs                   # Shared application state
│  ├─ capabilities/                 # Tauri permission policies
│  ├─ icons/                        # Application icons
│  ├─ Cargo.toml                    # Rust dependencies and crate metadata
│  └─ tauri.conf.json               # Tauri configuration (window size, bundle settings)
├─ package.json                     # Node.js dependencies & scripts
├─ tsconfig.json                    # TypeScript configuration
├─ vite.config.ts                   # Vite configuration
├─ README.md                        # Simplified Chinese documentation
└─ README_EN.md                     # English documentation
```

---

## 🛠️ Requirements & Prerequisites

- **Operating System**: Windows 10 / 11 (x64)
- **Toolchains**:
  - [Node.js](https://nodejs.org/) (>= 18.0.0) & npm
  - [Rust](https://www.rust-lang.org/) (>= 1.77.0)
  - Windows C++ Build Tools (Visual Studio 2017+ or [Build Tools for Visual Studio](https://visualstudio.microsoft.com/visual-cpp-build-tools/), select "Desktop development with C++")
  - WebView2 (built into Windows 10 / 11)
- **Network Environment**: Local network with access to the GUET Dr.COM portal (`10.0.1.5`).

---

## 💻 Development & Testing

### 1. Clone & Install Dependencies

```powershell
git clone https://github.com/Sunsume/GuetLinker.git
cd GuetLinker
npm install
```

### 2. Start Desktop Debugging

```powershell
npm run tauri dev
```

This launches the Vite dev server and opens the application in a native Tauri window with hot reloading.

### 3. Frontend Check & Build

```powershell
npm run build
```

### 4. Rust Backend Tests & Clippy

```powershell
cd src-tauri
cargo test --lib
cargo clippy --all-targets --all-features -- -D warnings
```

### 5. Package Windows Installer & Portable Executable

From the repository root:

```powershell
npm run tauri build
```

Upon completion, an NSIS installer and a portable standalone executable will be generated at:
- Installer: `src-tauri/target/release/bundle/nsis/GuetLinker_2.3.3_x64-setup.exe`
- Portable: `src-tauri/target/release/guetlinker-desktop.exe`

---

## ❓ Frequently Asked Questions (FAQ)

<details>
<summary><b>Q1: <code>link.exe not found</code> when running cargo or npm run tauri dev?</b></summary>

This means the MSVC C++ toolchain is missing or not detected on your Windows system. Install the **"Desktop development with C++"** workload via Visual Studio Installer, then restart your terminal.
</details>

<details>
<summary><b>Q2: "Cannot reach campus portal" error?</b></summary>

Ensure your machine is connected to the GUET wired network or campus Wi-Fi (e.g. `GUET-WiFi`) and that `http://10.0.1.5/` can be opened in a browser. Dr.COM authentication is only reachable from within the campus network.
</details>

<details>
<summary><b>Q3: Blank CAPTCHA or failed refresh in Self-Service?</b></summary>

The campus self-service server can experience high load or connection timeouts. Save your student ID and password in "Connection & Settings" first, then click the refresh icon on the "Account" page to fetch a new CAPTCHA.
</details>

<details>
<summary><b>Q4: Where is the configuration file stored?</b></summary>

All persisted settings (including encrypted credentials) are stored under the user app data directory:
- Windows: `%APPDATA%\com.guetlinker.desktop\config.json`
</details>

---

## 📜 License

This project is licensed under the [MIT License](LICENSE). Made with care for the GUET community. Contributions, issues, and PRs are warmly welcomed!
