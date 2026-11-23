<div align="center">

# Bitwarden Duplicate Merger

**查找并合并 Bitwarden 密码库中的重复登录项，任何修改前都有审核界面。**

[![tests](https://github.com/ThomLaurent/bitwarden-duplicate-merger/actions/workflows/tests.yml/badge.svg)](https://github.com/ThomLaurent/bitwarden-duplicate-merger/actions/workflows/tests.yml)
[![release](https://img.shields.io/github/v/release/ThomLaurent/bitwarden-duplicate-merger?label=download)](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)
[![license](https://img.shields.io/badge/license-Unlicense-blue)](../../LICENSE)

[English](../../README.md) · [Français](README.fr.md) · [Español](README.es.md) · [Deutsch](README.de.md) · 简体中文

<img src="../screenshots/review-conflict.png" alt="审核界面：三个 Steam 登录项，包含两个不同的密码" width="900">

</div>

从浏览器或其他密码管理器导入后，密码库里常常有同一个账号的多个副本：`www.amazon.com`、`login.amazon.com` 和 `amazon.com/ap/signin`，用户名和密码都相同。Bitwarden 本身无法合并它们，手动处理几百个登录项需要好几个小时。

本工具会把这些重复项分组，为每组给出合并建议，让你在本地网页中检查并修改每个决定，然后通过 Bitwarden 官方 CLI 只应用你确认过的内容。

## 工作流程

1. **启动工具。** Bitwarden CLI 解锁密码库，浏览器中打开一个页面。
2. **审核建议。** 域名和用户名相同的登录项会被分组。规则无法自行决定的组（密码不同、包含通行密钥等）会被标出。
3. **随意修改**：保留哪一项、名称、密码、TOTP、备注、URI、哪些项不参与合并。需要时可以手动分组（例如 `ebay.com` 和 `ebay.co.uk`）。
4. **随时中断和继续。** 决定会保存到文件中，重启电脑后也能继续。
5. **应用** 全部或部分已确认的组。报告会列出执行结果，并优先显示你与规则不同的决定。

## 保证

- **主密码永远不会到达本工具。** 只有 Bitwarden CLI 读取它；工具只接收会话密钥并保存在内存中。
- **秘密信息不会写入磁盘或日志。** 密码、TOTP 密钥、字段值和备注只在内存中比较。只有点击 "show" 时页面才显示。
- **未经你确认不会做任何修改**，并且只应用已确认的组。
- **不会执行过期的计划。** 应用每个组之前，工具会向 Bitwarden 确认其中的项在你审核后没有变化。若有变化，则跳过该组并在报告中说明。
- **可撤销。** 重复项进入 Bitwarden 回收站（保留 30 天），保留的项保持原有 ID、附件和通行密钥，应用前还会生成加密备份。
- **仅限本地。** 页面只在 `127.0.0.1` 上提供，并使用随机令牌保护。除 `bw` 连接你的 Bitwarden 服务器以及下文所述的 `bw` 下载外，没有任何网络访问。
- **官方 Bitwarden CLI。** 如果没有安装 `bw`，本工具会提议从 Bitwarden 在 GitHub 上的发布版本下载，并校验其 SHA-256。之后每月检查一次，保持这份副本为最新版本。
- **小巧易读。** 约 2300 行 Python 和 JavaScript，只用标准库，没有需要审计的依赖。

## 快速开始

<details open>
<summary><b>Windows</b></summary>

1. 从 [最新版本](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest) 下载 **`bw-dedupe-windows-x64.exe`**。
2. 把它放进单独的文件夹，例如在“文档”中新建一个 `bw-dedupe` 文件夹。你的决定和报告会保存在它旁边。
3. 双击运行。如果 Windows 显示“Windows 已保护你的电脑”，点击 **更多信息**，再点击 **仍要运行**：该文件没有签名。
4. 会打开一个黑色窗口。第一次运行时，它会提议下载 Bitwarden 官方命令行工具：按回车键。
5. 在该窗口中登录 Bitwarden：电子邮件、主密码，以及两步登录验证码（如果你启用了）。输入密码时不会显示任何字符，这是正常的。
6. 审核页面会在浏览器中打开。

</details>

<details>
<summary><b>macOS</b></summary>

1. 从 [最新版本](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest) 下载 **`bw-dedupe-macos-arm64`**。它适用于搭载 Apple 芯片（M1 或更新）的 Mac；Intel Mac 请从源码运行。
2. 打开“终端”应用，然后逐条运行以下命令。第二条命令让 macOS 允许运行未签名的文件。
   ```bash
   cd ~/Downloads
   ```
   ```bash
   chmod +x bw-dedupe-macos-arm64 && xattr -d com.apple.quarantine bw-dedupe-macos-arm64
   ```
   ```bash
   ./bw-dedupe-macos-arm64
   ```
3. 第一次运行时，本工具会提议下载 Bitwarden 官方命令行工具：按回车键。
4. 在终端中登录 Bitwarden：电子邮件、主密码，以及两步登录验证码（如果你启用了）。输入密码时不会显示任何字符，这是正常的。
5. 审核页面会在浏览器中打开。

</details>

<details>
<summary><b>Linux</b></summary>

从 [最新版本](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest) 下载 **`bw-dedupe-linux-x64`**，然后在终端中运行：

```bash
chmod +x bw-dedupe-linux-x64
```
```bash
./bw-dedupe-linux-x64
```

第一次运行时，本工具会提议下载官方 Bitwarden CLI。按 `bw` 的提示登录，然后在打开的页面中审核。

</details>

<details>
<summary><b>从源码运行</b>（任何装有 Python 3.10+ 的系统）</summary>

无需安装任何东西：

```bash
git clone https://github.com/ThomLaurent/bitwarden-duplicate-merger
```
```bash
cd bitwarden-duplicate-merger
```
```bash
python bw_dedupe.py
```

</details>

**先试用**一个虚构的密码库，无需 Bitwarden CLI 或账号：在终端中加上 `--demo` 启动，例如 `python bw_dedupe.py --demo`。不会向任何密码库写入内容。

可执行文件自带 Python，因此无论你安装的 Python 版本如何，只要 `bw` 的命令不变，就能继续使用。每个文件都由 GitHub Actions 从本仓库构建，可以这样验证：

```bash
gh attestation verify bw-dedupe-windows-x64.exe --repo ThomLaurent/bitwarden-duplicate-merger
```

更多内容（英文）：[使用指南](../USAGE.md)。

## 项目状态

本工具**按原样**分享，之后大概率不会再改进。我写它是为了清理自己的密码库，觉得公开分享比自己留着更好。希望它能帮你省下重新开发所需的时间和 token，更重要的是，省下手动合并几百个登录项的时间。

Issue 和 Pull Request 可能得不到回复。欢迎 fork：代码属于公有领域（[Unlicense](../../LICENSE)），[AGENTS.md](../../AGENTS.md) 为你和 AI 编程助手说明了代码结构。

本项目与 Bitwarden, Inc. 无关。"Bitwarden" 是 Bitwarden, Inc. 的商标。
