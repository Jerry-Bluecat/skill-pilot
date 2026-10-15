# Skill Pilot · 本机技能管理

统一管理本机四个 agent（Codex、Claude、Antigravity、DSH）的技能：每个技能只存一份，决定哪个 agent 能用哪些，按需检查上游更新，清理长期不用的。

## 怎么用

- **打开看板**：双击 `~/Applications/Skill Pilot.app`（或 Spotlight 搜 “Skill Pilot”）。关掉页面 30 秒后程序自动退出。
- **在对话里用**：四个 agent 都装了 `skill-pilot` 技能，可以直接说“看看 Claude 有哪些技能”“把 X 也给 Antigravity”。
- **命令行**：`skill-pilot status`、`skill-pilot list --agent claude`、`skill-pilot check-updates`、`skill-pilot cleanup --list`，加 `--json` 输出结构化结果。

看板里的主要操作：

| 页面 | 做什么 |
| --- | --- |
| 勾选表 | 勾选哪个 agent 用哪个技能，依赖的技能自动一起勾上，按“应用”生效 |
| 检查更新 | 按一下才查；边查边显示，每条可单独更新；本机改过的默认用上游版本 |
| 清理 | 60 天没人用的技能默认全选，取消要留的，按一下从各 agent 撤下（文件保留） |
| 已撤下 / 操作记录 | 恢复撤下的技能；任何一次改动都能撤销 |
| 设置 → 分享技能配置 | 导出在用技能、来源和分配；收到配置后先预览，再批量导入，可整批撤销 |

分享给另一位 Skill Pilot 用户的方法见 [分享技能配置](docs/sharing-config.md)。配置不包含技能正文和账号密钥；自制或修改过的技能会列为待补齐。

## 数据放在哪

- 技能正本：`~/.skill-pilot/store/<技能名>/`（git 仓库）。各 agent 技能目录里只是指向它的链接，改技能直接改正本。
- 登记表、基准、用量、操作记录、备份：`~/.skill-pilot/` 下的 `registry.json`、`bases/`、`usage.sqlite`、`logs/`、`backups/`。
- 管理规则（给所有 agent 看）：`/Users/j/Documents/AI-Workbench/docs/skills-management.md`。

## 开发

先读 [AGENTS.md](AGENTS.md) 和 [docs/STATUS.md](docs/STATUS.md)。需求与决策历史见 [PLAN.md](PLAN.md)。

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/j/.local/share/uv/python/cpython-3.11-macos-aarch64-none/bin/python3.11 -m unittest discover -q
SKILL_PILOT_READ_ONLY=1 ./skill-pilot status
sh scripts/build-app.sh   # 重新生成启动器和命令行入口
```
