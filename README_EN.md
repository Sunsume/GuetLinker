# GuetLinker 🌐

[简体中文](README.md) | **English**

A cross-platform desktop client project for the Guilin University of Electronic
Technology campus network. It provides Dr.COM authentication, live connection
monitoring, optional automatic reconnection, and access to selected account and
traffic information from the campus self-service system.

The current `v1.0.0` release provides a Windows x64 build. macOS and Linux builds
are on the development roadmap.

> This is an unofficial open-source client. It is not affiliated with or
> endorsed by GUET Network Center or the vendor of Dr.COM. Make sure your use
> complies with the rules of your network environment.

## Download

| Windows | macOS | Linux |
|---|---|---|
| [Download Windows x64](https://github.com/Sunsume/GuetLinker/releases/download/v1.0.0/GuetLinker-Windows-x64.exe) | - | - |

`-` means that a build has not been released for that platform yet; it does not
mean that the platform is outside the project's roadmap.

## Features

- **Campus network login**: Authenticate through the GUET Dr.COM portal with a
  student ID, password, and ISP selection.
- **Live status monitoring**: Detect the current session, base account, access
  provider, IPv4 address, and IPv6 address.
- **Optional auto-reconnect**: Retry authentication after a detected outage only
  when the user enables this option.
- **Dynamic ISP list**: Fetch and cache provider options from the portal while
  preserving the user's previous selection.
- **Self-service account**: Sign in to the separate management system through a
  dedicated dialog, including CAPTCHA handling when required.
- **Account and traffic data**: Show account status, recent/historical anomaly
  information, and international/domestic upload and download traffic for a
  selected date range.
- **Desktop integration**: A shared Qt interface with system tray, minimized
  startup, and single-instance enforcement. Startup launch and packaging will be
  adapted for each operating system.

## Account Boundaries

GuetLinker uses two independent sessions:

1. Credentials on the **Connection & Settings** page authenticate the Dr.COM
   campus network session.
2. Credentials on the **Account** page authenticate the campus self-service
   management system.

A successful self-service login does not mean that the campus network is online.
The live result on the Status page is always the source of truth for connectivity.

## Platform Status and Requirements

- Windows: A tested x64 release is currently available
- macOS: Planned; no official build is available yet
- Linux: Planned; no official build is available yet
- Python 3.11+
- A network environment that can reach the GUET campus portal

## Running from Source

The following workflow is currently verified on Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python src/main.py
```

On first launch, enter the campus network credentials and select an ISP on the
**Connection & Settings** page. Sign in separately on the **Account** page only
when self-service account or traffic information is needed.

Platform-specific dependency, permission, and packaging instructions for macOS
and Linux will be added after their ports are validated.

## Development and Testing

```bash
pip install -e .[dev]
pytest -q
```

The project uses PySide6, httpx, BeautifulSoup4, and cryptography. Core network
requests run in background workers to keep the Qt interface responsive.

## Packaging

```bash
pyinstaller --noconfirm guetlinker.spec
```

The current command generates the Windows executable at `dist/GuetLinker.exe`.
macOS and Linux will use their own packaging entry points. Build artifacts for
all platforms remain outside the source repository.

## Privacy and Safety

- Campus network passwords are stored only on the local machine and encrypted
  with Fernet.
- Self-service passwords and CAPTCHA values are used only for the current session
  and are never written into project files.
- The repository excludes personal accounts, runtime logs, saved web pages,
  binaries, and internal development-history documents.
- The application asks for confirmation before disconnecting. Real disconnection
  testing must be performed by the user.
- Obtain binaries only from trusted sources and review the source when possible.

## Scope

The current protocol and page parsers target the GUET campus network. The target
platforms are Windows, macOS, and Linux, while `v1.0.0` has only completed Windows
release validation. Portal and operating-system updates may require corresponding
compatibility changes.

## License

MIT
