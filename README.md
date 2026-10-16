# Skill Pilot · 本机技能管理

统一管理本机多个 agent 的技能：每个技能只存一份，决定哪个 agent 能用哪些，按需检查上游更新，撤下不需要的。内置 Codex、Claude、Antigravity、DSH 的接入规则，也可在看板接入发现的其他 agent。

## 安装

当前支持 macOS 本地桌面。需要 Python 3.11.4 或更高版本，以及可用的 Git；飞书技能更新另外需要 Node.js 和 npm。Python 最低版本用于支持下载文件的安全解包，见 [Python 官方说明](https://docs.python.org/3.11/library/tarfile.html#extraction-filters)；飞书工具的依赖与账号配置见 [飞书官方安装说明](https://github.com/larksuite/cli#installation--quick-start)。

从 GitHub 获取源码后，在项目文件夹运行：

```bash
git clone https://github.com/Simonlau4/skill-pilot.git
cd skill-pilot
sh scripts/build-app.sh
```

也可下载并解压 GitHub 的源码 ZIP，在解压出的项目文件夹运行最后一条命令。安装器会识别当前用户可用的 Python 和工具位置，生成应用与命令行入口；用户名、项目位置和路径中的空格均可不同。若有多个 Python，可用 `SKILL_PILOT_PYTHON="/你的路径/python3" sh scripts/build-app.sh` 指定一个符合要求的版本。

双击当前用户 `Applications` 文件夹里的 **Skill Pilot.app** 打开看板，按页面提示选择要接入的 agent、核对首次整理结果。项目文件夹需要保留；移动后在新位置重新运行安装命令。命令行可用 `~/.local/bin/skill-pilot`，或把 `~/.local/bin` 加入自己的命令搜索路径后用 `skill-pilot`。

已有飞书工具会自动识别。新用户先按官方说明安装并用自己的账号授权；若要将工具装在当前用户目录，可执行：

```bash
npm install --global --prefix "$HOME/.local" @larksuite/cli
export PATH="$HOME/.local/bin:$PATH"
lark-cli --version
```

本机看板会识别常见的用户安装目录、Homebrew 和 nvm 环境；在其他目录安装工具时，先让命令在终端可用，再运行一次 Skill Pilot 安装命令，桌面入口会记住这些工具位置。SP 更新飞书时将新版放在当前用户的 `~/.local` 中，并优先使用；更新前备份，可撤销。

## 更新程序

在原项目文件夹获取新版文件：

```bash
git pull --ff-only
```

使用源码 ZIP 的用户，将新版解压到新的项目文件夹，再运行 `sh scripts/build-app.sh`，并正常关闭旧看板后打开新位置的应用。同一项目位置更新后，刷新浏览器即可应用新版；当前操作会先完成，原地址和检查结果保留。刷新负责应用已下载的文件，不会替你从 GitHub 下载。

从旧版首次升级到这一版时，先重新运行 `sh scripts/build-app.sh` 更新安装入口，再正常关闭全部旧看板页面后重开一次。以后普通更新只需获取文件并刷新；安装入口有变动或项目文件夹移动时，再运行安装命令。

## 怎么用

- **打开看板**：双击 `~/Applications/Skill Pilot.app`（或 Spotlight 搜 “Skill Pilot”）。关掉页面 30 秒后程序自动退出。
- **应用程序更新**：程序文件更新到本机后，刷新浏览器即可生效；正在执行的操作会先完成，原地址和已检查的结果保留。首次从不支持此功能的旧版升级时，仍需正常重开一次看板。
- **在对话里用**：首次整理后，打开看板会给已接入的 agent 安装 `skill-pilot` 技能，可以直接说“看看 Claude 有哪些技能”“把 X 也给 Antigravity”。
- **命令行**：`skill-pilot status`、`skill-pilot list --agent claude`、`skill-pilot check-updates`、`skill-pilot cleanup --list`，加 `--json` 输出结构化结果。

看板里的主要操作：

| 页面 | 做什么 |
| --- | --- |
| 技能 | 选择给哪个 agent 加上或撤下技能，依赖的技能自动一起带上，核对后应用 |
| 技能 → 检查更新 | 按一下才查；可单独更新或全部更新；失败项列出原因，其他项继续；飞书技能整组更新 |
| 清理 | 手动选择不需要的技能，从各 agent 撤下（文件保留） |
| 已撤下 / 操作记录 | 恢复撤下的技能；任何一次改动都能撤销 |
| 设置 → 分享技能配置 | 导出在用技能、来源和分配；收到配置后先预览，再批量导入，可整批撤销 |

分享给另一位 Skill Pilot 用户的方法见 [分享技能配置](docs/sharing-config.md)。配置不包含技能正文和账号密钥；自制或修改过的技能会列为待补齐。

## 数据放在哪

- 技能正本：`~/.skill-pilot/store/<技能名>/`（git 仓库）。各 agent 技能目录里只是指向它的链接，改技能直接改正本。
- 登记表、基准、操作记录、备份及显示设置：当前用户 `~/.skill-pilot/` 下的 `registry.json`、`bases/`、`logs/`、`backups/`、`labels.json`。账号设置和密钥只保存在用户自己的 `settings.json` 中，不随项目或分享配置导出。
- 管理规则（给所有 agent 看）：[AGENTS.md](AGENTS.md)。

## 开发

先读 [AGENTS.md](AGENTS.md) 和 [docs/STATUS.md](docs/STATUS.md)。需求与决策历史见 [PLAN.md](PLAN.md)。

开发最高准则是 [通用化与可复现](AGENTS.md#最高准则通用化与可复现)。下面以满足上述版本要求的 `python3.11` 为例，测试只在系统临时目录中的模拟用户环境运行。

```bash
PYTHONDONTWRITEBYTECODE=1 python3.11 -m unittest discover -q
SKILL_PILOT_READ_ONLY=1 python3.11 -m skill_pilot status
sh scripts/build-app.sh   # 重新生成启动器和命令行入口
```
