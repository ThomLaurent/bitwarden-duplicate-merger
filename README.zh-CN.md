<div align="center">

# Bitwarden Duplicate Merger

**查找并合并 Bitwarden 密码库中的重复登录项，任何修改前都有审核界面。**

[![tests](https://github.com/ThomLaurent/bitwarden-duplicate-merger/actions/workflows/tests.yml/badge.svg)](https://github.com/ThomLaurent/bitwarden-duplicate-merger/actions/workflows/tests.yml)
[![release](https://img.shields.io/github/v/release/ThomLaurent/bitwarden-duplicate-merger?label=download)](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)
[![license](https://img.shields.io/badge/license-Unlicense-blue)](LICENSE)

[English](README.md) · [Français](README.fr.md) · [Español](README.es.md) · [Deutsch](README.de.md) · 简体中文

<img src="docs/screenshots/review-conflict.png" alt="审核界面：三个 Steam 登录项，包含两个不同的密码" width="900">

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
- **仅限本地。** 页面只在 `127.0.0.1` 上提供，并使用随机令牌保护。除 `bw` 连接你的 Bitwarden 服务器外，没有任何网络访问。
- **小巧易读。** 约 2000 行 Python 和 JavaScript，只用标准库，没有需要审计的依赖。

## 快速开始

1. 安装 [Bitwarden CLI](https://bitwarden.com/help/cli/)（`bw`）。
2. 从 [最新版本](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest) 下载适合你系统的可执行文件，并在终端中运行：
   ```bash
   ./bw-dedupe-linux-x64
   ```
   或者使用任意 Python 3.10+ 从源码运行，无需安装任何东西：
   ```bash
   git clone https://github.com/ThomLaurent/bitwarden-duplicate-merger
   cd bitwarden-duplicate-merger
   python bw_dedupe.py
   ```
3. 按 `bw` 的提示解锁密码库，然后在打开的页面中审核。

可执行文件自带 Python，因此无论你安装的 Python 版本如何，只要 `bw` 的命令不变，就能继续使用。每个文件都由 GitHub Actions 从本仓库构建，可以这样验证：

```bash
gh attestation verify bw-dedupe-linux-x64 --repo ThomLaurent/bitwarden-duplicate-merger
```

更多内容（英文）：[使用指南](docs/USAGE.md)。

## 项目状态

本工具**按原样**分享，之后大概率不会再改进。我写它是为了清理自己的密码库，觉得公开分享比自己留着更好。希望它能帮你省下重新开发所需的时间和 token，更重要的是，省下手动合并几百个登录项的时间。

Issue 和 Pull Request 可能得不到回复。欢迎 fork：代码属于公有领域（[Unlicense](LICENSE)），[AGENTS.md](AGENTS.md) 为你和 AI 编程助手说明了代码结构。

本项目与 Bitwarden, Inc. 无关。"Bitwarden" 是 Bitwarden, Inc. 的商标。
