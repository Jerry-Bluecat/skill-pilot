# Skill Pilot 项目规则

给在本仓库工作的 agent（Codex、Claude 等）。开始前先读 [docs/STATUS.md](docs/STATUS.md)，需要背景时再读 [PLAN.md](PLAN.md)（需求与全部决策史，开头有 2026-10-11 的“方向调整”）。`docs/handoff-*.md`、`docs/*-report.md`、`docs/spikes.md` 是开发历史，按需查。

## 用户与方向

- 用户不是程序员。界面、确认框、报错、给用户的回复一律中文大白话，不出现 symlink、diff、git、TOML、hash 这类词。
- 最初要解决的四个问题：各 agent 分别管技能；更新不用专门开对话；同一技能多份副本导致版本冲突；装了什么不知道、不用的占上下文。新功能先问是否服务于这四个问题之一。
- **做减法**：能删就删，不为假想需求加功能、加配置、加 AI 调用。只有用户在设置里填了 AI 服务的 key，才会自动调用它给技能起中文名和分组；其余 AI 功能仍只作可选按钮。
- 用户不想逐条确认：能由规则或证据决定的不要做成待确认项；批量操作默认全选，让用户只挑例外。

## 真实数据与安全边界

- 真实数据：`~/.skill-pilot/`（`store/` 技能正本 git 仓库、`bases/`、`registry.json`、`agents.json`、`logs/`、`backups/`、`labels.json` 中文名与分组、`settings.json` 含 API key：不复制进模拟 home、不进备份和日志、不在回复里出现），四个技能根 `~/.codex/skills`、`~/.agents/skills`（Codex 与 DSH 共读）、`~/.claude/skills`、`~/.gemini/config/skills`，以及 `~/.codex/config.toml` 的 `[skills] config`。
- 旧版留下的用量数据库只保留，不读取、改写、删除或复制进模拟 home。
- 永远不碰：`~/.claude/skills/synced/`（Claude 桌面 app 自管）、`~/.codex/skills/.system/`、各家插件和内置目录、`~/.agents/.skill-lock.json`（只读）。
- 开发和测试只用系统临时目录里的模拟 home（`scripts/make-fake-home.py`；`tests/__init__.py` 断言目标 home 在临时目录）。对真实 home 运行本工具一律带 `SKILL_PILOT_READ_ONLY=1`。
- 对真实技能库做分配、更新、清理、改来源、撤销，必须是用户在当次对话里明确要求的；优先让用户自己在看板上点。
- 不要结束或干扰用户正在运行的看板进程（`python3.11 -m skill_pilot ui`）。不运行 `lark-cli update`、`npx skills`，不执行任何技能里的脚本。
- 动真实环境前后各取一次指纹（四个技能根的条目与链接目标、`~/.skill-pilot/` 文件、Codex 配置、来源记录），用 `~/.skill-pilot/logs/` 区分用户自己在看板上的操作。

## 运行与测试

- 解释器固定为 `/Users/j/.local/share/uv/python/cpython-3.11-macos-aarch64-none/bin/python3.11`（`python3` 指向 Codex 运行时，可能变化；系统 3.9 没有 `tomllib`）。只用标准库。
- 全量测试：`PYTHONDONTWRITEBYTECODE=1 <上面的解释器> -m unittest discover -q`（约 40 秒）。前端改动后另跑 `node --check skill_pilot/web/static/app.js`。
- 启动器与命令行入口：`sh scripts/build-app.sh` 生成 `~/Applications/Skill Pilot.app` 和 `~/.local/bin/skill-pilot`。
- 代码量检查：`find skill_pilot -name "*.py" -o -name "*.js" -o -name "*.html" | xargs wc -l`。

## 结构速览

| 位置 | 作用 |
| --- | --- |
| `skill_pilot/profiles/` | agent 档案：技能根、共享关系、停用方式、手动调用标记 |
| `scan.py`、`store.py`、`sync.py` | 盘点、统一仓库与迁移备份、按分配表对账链接 |
| `operations.py`、`codex_config.py` | 分配、依赖、安装、收编、操作记录与撤销；Codex 停用条目只增删工具自己加的 |
| `updates.py`、`sources/`、`normalization.py` | 检查更新（后台任务、逐条结果）、GitHub/飞书来源、嵌套 SKILL.md 改名 |
| `labels.py` | 本机 AI 服务设置、中文名与分组、分批整理与安全保存 |
| `cleanup.py` | 手动挑选技能撤下、已撤下名单与恢复 |
| `web/` | 本机看板（`127.0.0.1` 随机端口加口令；`static/` 为前端） |
| `skill/skill-pilot/` | 装给各 agent 的 `skill-pilot` 技能 |
| `docs/dependency-decisions.json` | 技能依赖判定表（依赖只来自这里和看板手动加减） |
| `docs/source-attribution.md` | 来源归属表（“自制”不检查更新） |

## Git

本仓库连接 GitHub 公开仓库 [Simonlau4/skill-pilot](https://github.com/Simonlau4/skill-pilot)。只在用户要求时提交或推送，只暂存本次相关文件；本机技能库、设置和密钥不上传。
