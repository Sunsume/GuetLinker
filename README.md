# GuetLinker

[English](README_EN.md)

面向桂林电子科技大学校园网的非官方 Windows 客户端。项目采用 Vue 3 + TypeScript 构建暗色像素风界面，使用 Tauri 2 + Rust 完成桌面能力、校园网认证、断线监测和自助服务访问，不需要 Python 运行环境。

## 功能

- GUET Dr.COM 无线 / 有线门户登录与安全注销
- 门户状态识别、IPv4 / IPv6 显示与断线自动重连
- 本机加密保存校园网凭据
- 自助服务登录、验证码、账户状态与指定日期流量查询
- Windows 开机启动、启动时最小化、系统托盘与应用单例
- 可缩放的暗色像素风界面

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

## 开发

先安装 Node.js、Rust 和 Windows 的 Tauri 系统依赖，然后在仓库根目录运行：

```powershell
npm install
npm run tauri dev
```

只检查前端：

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

> 本项目与学校网络中心及 Dr.COM 厂商无隶属或授权关系。请遵守所在网络的管理规定。

## License

MIT
