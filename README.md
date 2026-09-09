# GuetLinker

**简体中文** | [English](README_EN.md)

面向桂林电子科技大学校园网的跨平台桌面客户端项目。当前源码使用 Vue 3 + TypeScript
构建暗色像素风界面，并由 Tauri 2 + Rust 提供桌面能力、校园网认证、断线监测和
自助服务访问，不需要 Python 运行环境。

当前版本已在 Windows 上验证；macOS 和 Linux 版本在后续开发计划中。

> 本项目是非官方开源客户端，与桂林电子科技大学网络中心及 Dr.COM 厂商无隶属或
> 授权关系。使用前请确认符合所在网络的管理规定。

## 下载

| Windows | macOS | Linux |
|---|---|---|
| [下载 v1.0.0 Windows x64](https://github.com/Sunsume/GuetLinker/releases/download/v1.0.0/GuetLinker-Windows-x64.exe) | - | - |

`-` 表示对应平台版本尚未发布，并非项目不支持该平台方向。当前源码迁移后的安装包
尚未发布，需要时可按下方开发说明从源码运行或构建。

## 功能

- GUET Dr.COM 无线 / 有线门户登录与安全注销
- 门户状态识别、IPv4 / IPv6 显示与断线自动重连
- 本机加密保存校园网凭据
- 自助服务登录、验证码、账户状态与指定日期流量查询
- Windows 开机启动、启动时最小化、系统托盘与应用单例
- 可缩放的暗色像素风界面

## 账户边界

GuetLinker 使用两套彼此独立的会话：

1. “连接与设置”页中的账号用于校园网 Dr.COM 认证；
2. “账户”页中的账号用于学校自助服务管理系统。

自助服务登录成功不代表校园网已经在线；实际网络状态始终以状态页的实时检测结果
为准。

## 目录

```text
GuetLinker/
├─ src/                     Vue 页面、状态逻辑和视觉资源
├─ src-tauri/
│  ├─ src/                  Rust 认证、监测、配置与 Tauri 命令
│  ├─ capabilities/         Tauri 权限
│  └─ Cargo.toml            Rust 依赖
├─ package.json             前端与开发命令
└─ README.md
```

## 平台状态与环境要求

- Windows：当前已验证
- macOS：计划支持，暂未提供正式构建
- Linux：计划支持，暂未提供正式构建
- Node.js、Rust 和对应平台的 Tauri 系统依赖
- 可访问桂电校园网门户的网络环境

## 开发与测试

在仓库根目录安装依赖并启动开发版本：

```powershell
npm install
npm run tauri dev
```

检查前端：

```powershell
npm run build
```

检查 Rust：

```powershell
cd src-tauri
cargo test --lib
cargo clippy --all-targets --all-features -- -D warnings
```

当前不生成安装包；需要时再运行 `npm run tauri build`。

## 适用范围

当前协议和页面解析针对桂林电子科技大学校园网环境。项目目标平台包括 Windows、
macOS 和 Linux，但目前仅完成 Windows 验证。学校门户或操作系统接口升级后，部分
功能可能需要同步适配。

## License

MIT
