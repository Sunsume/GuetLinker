# GuetLinker

**简体中文** | [English](README_EN.md)

[![Tauri](https://img.shields.io/badge/Tauri-2.0-24C8D8?logo=tauri&logoColor=white)](https://tauri.app/)
[![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D?logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![Rust](https://img.shields.io/badge/Rust-2021-DEA584?logo=rust&logoColor=white)](https://www.rust-lang.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

面向**桂林电子科技大学（GUET）**校园网的现代化桌面客户端。

采用 **Tauri 2 + Rust** 作为高性能系统后端，前端使用 **Vue 3 + TypeScript + Vite** 构建独特的暗色复古像素艺术界面。彻底摒弃传统 Python 运行时依赖，具有轻量、瞬时启动、低内存占用及便携分发的特点。

当前版本已在 Windows 10 / 11 上完成全面验证；macOS 与 Linux 版本已纳入后续跨平台路线。

> [!IMPORTANT]
> **免责声明**：本项目为桂电学生自发维护的非官方开源工具，与桂林电子科技大学网络中心及 Dr.COM 厂商无隶属或官方授权关系。使用前请确保遵守学校网络管理规定。

---

## 📥 下载与安装

> [!TIP]
> **版本说明**：GitHub Releases 提供两种 Windows x64 版本供您选择：
> - 🚀 **绿色免安装版 (`GuetLinker_*_x64_Portable.exe`)**：纯单文件，解压或下载即可双击直接运行，适合放 U 盘或快速使用。
> - 📦 **标准安装包版 (`GuetLinker_*_x64-setup.exe`)**：带有安装向导，自动配置开始菜单、桌面图标与卸载支持。
>
> 建议前往 [GitHub Releases](https://github.com/Sunsume/GuetLinker/releases) 下载最新版本，或按下方指引直接[从源码构建](#5-打包生成-windows-安装包与便携版)。

| 平台 | 架构 | 新版状态 (Tauri 2) | 下载与获取 |
| :--- | :--- | :--- | :--- |
| **Windows** | x64 | **已验证** | [前往 Releases 下载便携版 / 安装包](https://github.com/Sunsume/GuetLinker/releases) |
| **macOS** | Apple Silicon / Intel | 计划中 | 适配中 |
| **Linux** | x64 | 计划中 | 适配中 |

<details>
<summary><b>历史版本归档 (Legacy Python 版)</b></summary>

- [下载 v1.0.0 Windows x64 (Python 单文件版)](https://github.com/Sunsume/GuetLinker/releases/download/v1.0.0/GuetLinker-Windows-x64.exe)
- *注：旧版本基于 PyInstaller 打包，包含旧版 Qt 界面，不包含当前 Tauri 2 架构的性能优化与像素风新特性。*
</details>

---

## ✨ 核心特性

- 🚀 **校园网认证 (Dr.COM)**
  - 自动探测并适配桂电校园网 Web 认证门户（`http://10.0.1.5/`）。
  - 支持无线 (WLAN) 与有线以太网接入。
  - 支持运营商快捷切换：**校园网**、**中国移动**、**中国联通**、**中国电信**、**中国广电**。
  - 本地 IP 地址（IPv4 / IPv6）与网络适配器状态动态呈现。
  - 支持随时安全注销与连接过程中即时“取消连接”。

- 🔄 **智能监测与休眠唤醒自愈**
  - 后台轻量级定时巡检校园网在线状态。
  - **休眠唤醒自愈**：笔记本睡眠/合盖唤醒后自动重置过期会话，缓冲等待网卡与 DHCP 完成协商并立即触发网络探测与重连，杜绝传统客户端唤醒后长时间假死。
  - 断网即时检测，可配置毫秒级退避重连机制。
  - 人性化逻辑：用户手动点击“断开”后自动挂起重连，避免与手动操作冲突。

- 🔒 **本地凭据安全存储**
  - 校园网密码绝不使用明文存储，采用 **AES-256-GCM** 高强度加密算法保存。
  - 密钥基于**本机设备硬件信息**动态派生，即使配置文件外泄也无法在其他机器解密。
  - 界面输入默认脱敏遮盖（`••••••••`），仅在显式点击眼睛按钮时调用原生 Rust 命令解密查看。

- 📊 **自助服务与流量查询**
  - 集成学校自助服务管理系统（Self-Service）。
  - 支持验证码动态拉取、图形刷新与校验。
  - 实时查询账户基础状态、异常警告记录。
  - 自定义日期范围查询**国内/国际**的上行、下行流量明细与汇总。

- 📈 **实时网络质量监测与延迟波形图**
  - 基于 Rust 异步非特权 TCP 握手测量，微秒级精准获取关键节点延迟：校园网关（`10.0.1.5:80`）、桂电官网（`www.guet.edu.cn:443`）、公共 DNS（`223.5.5.5:53`）以及互联网出口（`www.baidu.com:443`）。
  - 动态呈现 16 采样点复古像素延迟波形柱状图，网络抖动与波动一目了然。

- 🩺 **一键网络体检与诊断报障报告**
  - 全链路多点分级诊断：网卡与本地 IP 分配 -> 校园网关连通性 -> DNS 域名解析 -> 外网出口连通性 -> 本地账号凭据配置。
  - 输出彩色结构化体检卡片，并针对不同故障级别给出排障指引建议。
  - 支持**一键复制标准化排障报告（ASCII 报表）**，便于直接复制后向桂电网络报障群或网络中心提交工单。

- 🌐 **公网与代理出口 IP 实时探测与安全防护**
  - 自动探测对外真实的公网出口 IP、物理落地所在地（国家、省份、城市）与接入运营商 / IDC 机房。
  - **智能识别网络出口安全状态**：
    - 🚀 **代理翻墙出口（已生效）**：实时抓取海外/云服务器代理落地节点，确认代理加速生效且未走校内出口。
    - 🟢 **运营商商业专线（安全直连）**：中国移动/电信/联通商业宽带出口，绕过教育网行为审计。
    - ⚠️ **校园教育网出口（高危警示）**：智能识别 CERNET 出口，警示同学严禁开启翻墙工具，避免被学校系统抓包封号。
  - 提供一键【刷新出口】功能，切换代理节点或 Wi-Fi 后秒级更新。

- 🎮 **沉浸式像素风桌面体验**
  - 专属定制的暗色复古像素风格 UI（集成开源 Fusion Pixel 像素字体与 Pixelarticons）。
  - 优雅的无边框像素窗口（640×820 黄金比例），支持顶部拖拽条及快捷最小化。
  - **系统托盘动态状态**：常驻任务栏托盘，根据网络状态呈现动态颜色图标（🟢 在线 / 🔴 离线 / 🟡 重连中），支持右键状态速览、一键连接/断开、检查更新与安全退出。
  - **应用内自动检查更新**：集成 GitHub Releases 自动比对，启动时静默预检，支持在“关于”页与托盘菜单中一键检查新版本、浏览更新日志并直链下载免安装便携版或安装包。
  - **桌面通知**：网络重连、上线或异常状态气泡提示（支持静默模式）。
  - **开机自启** 与 **启动时最小化** 偏好设置。
  - **单实例运行限制**：防止重复打开多份客户端，重复启动时自动唤醒并聚焦已有窗口。

---

## 🛡️ 账户边界与安全设计

GuetLinker 在设计上严格区分两套彼此独立的会话系统：

```text
┌─────────────────────────┐          ┌─────────────────────────┐
│     校园网 Dr.COM 会话    │          │      自助服务管理会话     │
│   (用于设备接入互联网访问)    │          │   (用于查询账户与流量用量)   │
└────────────┬────────────┘          └────────────┬────────────┘
             │                                    │
    由“连接与设置”页驱动                     由“账户”页驱动
    通过设备门户端口认证                      通过自助服务管理接口交互
```

1. **凭据边界**：“连接与设置”中的账号凭据用于网络端口 Dr.COM 登录；“账户”页用于访问教务网络服务系统。两套系统凭据可独立填写与维护。
2. **状态边界**：自助服务登录成功仅代表拥有系统查询权限，**不代表校园网已连接**；实际连网状态始终以“状态”主控面板的实时检测为准。
3. **隐私保证**：本应用不包含任何遥测、埋点或第三方跟踪代码，所有网络请求仅直接与桂电校园网门户及自助服务系统通信。

---

## 📂 项目结构

```text
GuetLinker/
├─ src/                             # 前端用户界面 (Vue 3 + TypeScript + Vite)
│  ├─ assets/                       # 静态资源 (Fusion Pixel 字体、纹理背景、Logo)
│  ├─ components/                   # UI 组件 (PixelIcon 像素图标等)
│  ├─ composables/                  # 组合式业务逻辑 (useNetwork 状态机)
│  ├─ pages/                        # 业务页面
│  │  ├─ StatusPage.vue             # 状态主面板 (连接状态、IP信息、控制按钮)
│  │  ├─ SettingsPage.vue           # 连接与设置 (凭据配置、通知、开机自启)
│  │  ├─ AccountPage.vue            # 自助服务 (验证码登录、账户状态、流量统计)
│  │  └─ AboutPage.vue              # 关于页面 (版本信息、项目链接)
│  ├─ App.vue                       # 主视窗框架 (自定义像素标题栏、标签导航)
│  ├─ main.ts                       # 前端入口
│  └─ styles.css                    # 像素艺术样式系统与变量
├─ src-tauri/                       # 后端原生能力 (Tauri 2 + Rust)
│  ├─ src/
│  │  ├─ auth.rs                    # Dr.COM 认证协议、登录注销与运营商解析
│  │  ├─ commands.rs                # Tauri IPC 供前端调用的命令集
│  │  ├─ config.rs                  # 本机配置存储与 AES-256-GCM 加解密
│  │  ├─ diagnostics.rs             # 网络质量时序探测与一键网络体检诊断
│  │  ├─ error.rs                   # 统一错误类型与处理
│  │  ├─ lib.rs                     # Tauri 插件装配、系统托盘与单实例管理
│  │  ├─ main.rs                    # 桌面端可执行程序入口
│  │  ├─ monitor.rs                 # 网络心跳探测与自动重连调度
│  │  ├─ network.rs                 # 网卡、本地 IP 与 MAC 探测
│  │  ├─ portal.rs                  # 校园网 Portal 探测与重定向嗅探
│  │  ├─ self_service.rs            # 自助服务登录会话、验证码及流量爬取解析
│  │  └─ state.rs                   # 共享应用状态管理
│  ├─ capabilities/                 # Tauri 权限策略定义
│  ├─ icons/                        # 跨平台客户端图标
│  ├─ Cargo.toml                    # Rust 依赖项与打包配置
│  └─ tauri.conf.json               # Tauri 应用与视窗尺寸配置文件
├─ package.json                     # 前端依赖配置与构建脚本
├─ tsconfig.json                    # TypeScript 编译器配置
├─ vite.config.ts                   # Vite 打包配置
├─ README.md                        # 中文文档
└─ README_EN.md                     # 英文文档
```

---

## 🛠️ 环境要求

- **操作系统**：Windows 10 / 11（x64）
- **开发工具链**：
  - [Node.js](https://nodejs.org/) (>= 18.0.0) & npm
  - [Rust](https://www.rust-lang.org/) (>= 1.77.0)
  - Windows C++ 构建工具（Visual Studio 2017+ 或 [Build Tools for Visual Studio](https://visualstudio.microsoft.com/visual-cpp-build-tools/)，勾选“使用 C++ 的桌面开发”）
  - WebView2（Windows 10 / 11 默认已预装）
- **网络环境**：可直连访问桂电校园网 Portal 认证页面（`10.0.1.5`）的局域网环境。

---

## 💻 开发与测试

### 1. 克隆仓库并安装依赖

```powershell
git clone https://github.com/Sunsume/GuetLinker.git
cd GuetLinker
npm install
```

### 2. 启动桌面端调试

```powershell
npm run tauri dev
```

该命令将启动 Vite 开发服务器，并在原生 Tauri 窗口中热重载运行客户端。

### 3. 前端类型检查与构建

```powershell
npm run build
```

### 4. 运行 Rust 后端测试与 Lint

```powershell
cd src-tauri
cargo test --lib
cargo clippy --all-targets --all-features -- -D warnings
```

### 5. 打包生成 Windows 安装包与便携版

在仓库根目录执行：

```powershell
npm run tauri build
```

构建成功后，将在以下路径生成轻量的 NSIS 安装包与单文件便携版：
- 安装包：`src-tauri/target/release/bundle/nsis/GuetLinker_2.3.4_x64-setup.exe`
- 便携版：`src-tauri/target/release/guetlinker-desktop.exe`

---

## ❓ 常见问题排查 (FAQ)

<details>
<summary><b>Q1: 运行 cargo 或 npm run tauri dev 报错 <code>link.exe not found</code>？</b></summary>

这是由于 Windows 系统尚未安装或识别 MSVC C++ 构建工具链。请通过 Visual Studio Installer 安装 **“使用 C++ 的桌面开发”** 组件，并在安装完成后重新打开终端窗口。
</details>

<details>
<summary><b>Q2: 为什么提示“无法访问校园网认证门户”？</b></summary>

请确认当前设备已连接至桂电有线网络或校园网 WiFi（如 `GUET-WiFi`），并且能通过浏览器打开 `http://10.0.1.5/`。在校外或通过非校园网接入时无法完成 Dr.COM 登录。
</details>

<details>
<summary><b>Q3: 自助服务验证码显示空白或刷新失败？</b></summary>

学校自助服务系统在访问繁忙或跨网段访问时可能发生超时。可前往“连接与设置”保存正确的学号密码后，在“账户”页点击刷新图标重试拉取。
</details>

<details>
<summary><b>Q4: 配置文件保存在哪里？</b></summary>

所有本地持久化配置（含加密凭据）保存在系统应用数据目录下：
- Windows: `%APPDATA%\com.guetlinker.desktop\config.json`
</details>

---

## 📜 开源协议

本项目采用 [MIT License](LICENSE) 授权开源。为桂电子弟而造，欢迎提交 Issue 与 Pull Request 共同改进！
