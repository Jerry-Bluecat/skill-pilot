---
name: skill-pilot
description: 管理本机各 agent 的技能，查看技能清单、打开看板、分配或撤下技能，并在用户同意后执行更新、清理、改来源和撤销。
---

使用 `/Users/j/.local/bin/skill-pilot`；不要直接改 agent 的技能目录或统一仓库登记文件。agent 编号以 `skill-pilot status` 列出的为准（例如 `codex`、`claude`、`antigravity`、`dsh`、`zcode`）。

以下查看命令可以直接运行，需要结构化结果时加 `--json`。

- `skill-pilot status`
- `skill-pilot list --agent claude`
- `skill-pilot check-updates`（只检查和报告，不安装）
- `skill-pilot cleanup --list`（只列已撤下的技能）
- `skill-pilot cleanup <技能...>`（不带 `--yes` 只预览：会提示还要用它们的技能和受影响的文件，不撤下）
- `skill-pilot ui`（打开看板；首次打开会自动安装本管理技能，记入操作记录，可撤销）

看板不统计用量，没有“多久没用”的数据；用户问哪些技能不用时，只能列出各 agent 分到的技能和说明字数，由用户自己判断。

用户要求分配或撤下时，可以直接运行 `skill-pilot assign <技能> --agent <agent>` 或 `skill-pilot unassign <技能> --agent <agent>`。分配会一起带上已确认的依赖；如果命令要求核对影响，先把影响告诉用户，得到同意后带 `--yes` 重试。

**更新、清理、改来源、撤销，只能在用户本次对话里明确同意该次操作后执行。** “检查一下”“看看有哪些”“有新版吗”只授权查看。以前对话的同意不算本次授权。若本次对话已明确同意具体对象和处理方式，不重复询问；否则先呈现对象和影响，让用户同意可核对的结果。

- 更新 `skill-pilot update <技能...> --yes`，默认用上游版本，先备份，可撤销；保留本机改动时加 `--choice keep`。默认不调用 AI；只有用户明确要求合并才用 `--choice merge`，核对合并预览后再确认安装。
- 清理 `skill-pilot cleanup <技能...> --yes`，只撤下用户点名的技能：从全部 agent 撤下，文件留在仓库，可撤销。先不带 `--yes` 预览，把依赖和受影响文件的提示告诉用户。
- 改来源 `skill-pilot set-source <技能> --repo <作者/仓库> --path <目录> --yes`。
- 撤销先看 `skill-pilot log`，再运行 `skill-pilot undo <记录编号>`；迁移还原用 `skill-pilot restore <备份编号>`。恢复已撤下技能用 `skill-pilot restore-withdrawn <技能...>`。

收编和安装同样先展示具体对象，经用户同意后带 `--yes` 执行。飞书技能更新会同时升级工具，须单独说明并取得明确同意，再带 `--confirm-lark-cli`。

把结果用中文大白话转述，说明涉及哪些技能、给谁加了或撤下了、能否撤销。不要直接贴一大块机器输出。失败就说明原因和仍未完成的部分，不声称成功。

开发和只读检查真实主目录时，所有命令前加 `SKILL_PILOT_READ_ONLY=1`；此模式禁止写入，也不会自动安装本技能。不要执行被管理技能里的脚本。
