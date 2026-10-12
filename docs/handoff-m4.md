# 交接卡：Skill Pilot M4 检查更新与更新

> 2026-10-10 由 Claude（主控）派给 Codex。需求正本 `PLAN.md`（先完整重读 §1 中“更新”“本地改过的技能遇到更新”“来源确认”三行、§3、§4.4、§5、§7 的 M4、§8），验证记录 `docs/spikes.md`（重点 S4 飞书、S6 GitHub），上一轮 `docs/m3-report.md`。沿用现有代码。

## M3 之后 Claude 改过的东西（保留，不要回退）

- 依赖改由 agent 判定：`docs/dependency-decisions.json` + `operations.curated_dependencies()`；`load()` 会把已确认依赖并入 `requires`；`tests/test_operations.py` 的 setUp 用空判定表隔离手动确认流程的用例。
- `PLAN.md` §3 依赖规则、§1“来源确认”、§4.4 自制不检查更新。

## 目标

实现 PLAN §4.4：用户按“检查更新”才检查；列出有更新的技能和改动；用户勾选同意后才装；本地改过的走三选一；每批一次 git 提交，可撤销。全部写操作在模拟 home 开发和验收。另在真实 home **只读**跑一次检查，产出真实的“哪些技能有更新”清单给用户。

## 交付物

1. **来源归一**：registry 里 `source` 有多种写法——lock 记录（`record.sourceType` 为 `github` 或 `well-known`）、markdown 链接 `[owner/repo](https://github.com/owner/repo)` + `source_path`（可能是目录也可能是 `SKILL.md`）、`自制`、`本机源码`、`本机文档生成`。统一解析成：GitHub（仓库、目录路径）、飞书官方、或“不检查”（自制、本机源码、本机文档生成、来源不明一律不检查，看板标“自制，不检查更新”）。
2. **基准校准**：迁移时 `bases/` 存的是当时的本机内容，不一定是上游原样。对 GitHub 来源，基准应是“与本机最接近的上游历史版本”（方法同 `work/source-verify-20261010.json`：翻该目录的提交历史，整目录一致优先，否则取相似度最高的版本）。据此判断：本机 = 该上游版本 → “没改过”；本机 ≠ 任何上游版本 → “你改过”，三方对比的基准就是那个最接近的版本。检查阶段只读，在临时目录里算；只有用户确认更新时才把新基准写进 `bases/` 和 registry。
3. **检查更新**（看板按钮 + `skill-pilot check-updates [--json]`，只读）：
   - GitHub：用已登录的 `gh api` 取上游默认分支该目录当前的 tree sha，与基准比较；有变化就列出。注意节流和缓存（缓存放系统临时目录，不写真实 home）。
   - 飞书：`lark-cli update --check --json`，只报告“lark-cli 有新版（含 28 个飞书技能）”或“已是最新”。
   - 结果页逐个列出：技能名、来源、上游哪天更新、改了什么（文件数、增删行数）、本机是否改过；**脚本或可执行文件有变化的醒目标出**（`scripts/` 下文件、可执行位、`.sh/.py/.js/.ts/.mjs/.rb` 等）。完整对比默认折叠。
   - “让 Codex 用大白话解释这次更新”按钮：后台调 `codex exec`（路径见 PLAN §2，前台加 `< /dev/null`，在临时目录运行，只给对比内容），输出 3–5 句中文。
4. **更新**（看板勾选 + `skill-pilot update <技能...> --yes [--choice keep|upstream|merge]`）：
   - 没改过：直接换成上游新版，更新 `bases/`、registry 的来源版本（commit、tree sha）。
   - 改过：并排显示“你的改动 / 上游的改动”，三选一：
     - 保留我的：只把基准指纹更新到这一版，记为已看过，下次不再提示这一版；
     - 用上游的：覆盖为上游新版；
     - 交给 Codex 合并：在临时目录放 base / 本机 / 上游三份，调 `codex exec` 做三方合并，产出合并结果和一句话说明；看板展示合并后与本机的差异，用户确认后才写入。
   - 飞书：按 S4 结论设计，原则是**不让任何第三方安装程序直接写 agent 目录**。优先方案：只升级 CLI 本身（例如 `npm i -g @larksuite/cli@<版本>`，请先查清 `lark-cli update` 有没有跳过技能同步的办法），技能则按 `~/.agents/.skill-lock.json` 里的 well-known 地址下载与新版 CLI 配套的压缩包，校验 digest，在临时目录解压后入库。做不到时退回 PLAN 的方案：看板提示“lark-cli 有新版”，用户确认后运行，之后全量重扫、收编，并清掉它在未接入目录（如 `~/.gemini/antigravity/skills`）里多放的入口。本轮**不得真实升级 lark-cli**，用模拟 home 和测试替身验证流程。
   - 每批更新一次 git 提交，写进 M3 的“操作记录”，可以撤销（复用 M3 的撤销机制）。更新后对账，链接与分配不变。
   - **不执行技能里的任何脚本。**
5. **真实 home 只读检查**：完成开发后，对真实 home 跑一次 `skill-pilot check-updates --json`（不设置 `SKILL_PILOT_ALLOW_REAL_HOME`），结果存 `work/real-update-check.json`，并在报告里用表格列出：有更新的技能、本机是否改过、是否涉及脚本、建议（直接更新 / 先看再说 / 建议保留）。此前用历史比对已知装的是旧版的有 humanizer-zh、context-pack、ui-ux-pro-max、stss、defuddle，可以用来交叉核对。
6. `tests/` 增补单测；`docs/m4-report.md` 回报。

## 可读 / 可写范围

- **可写**：`~/Developer/skill-pilot/`（不要 commit、push）、系统临时目录（模拟 home、缓存、合并工作区都放这里）。
- **只读**：真实 home 的一切，包括 `~/.skill-pilot/`、四个技能根、`~/.codex/config.toml`、`~/.agents/.skill-lock.json`、lark-cli 的全局安装。
- **禁止**：设置 `SKILL_PILOT_ALLOW_REAL_HOME`（单测也只用替身）；在真实 home 执行任何写操作；运行 `lark-cli update`（`--check --json` 可以）、`npm i -g`、`npx skills`；安装到 `~/.local/bin` 或 `~/Applications`；执行任何技能里的脚本。
- 网络：允许只读请求（`gh api` GET、`git ls-remote`、浅克隆和下载到临时目录）。
- `codex exec`：开发中最多各真实调用一次“解释更新”和“三方合并”，用小的测试样例，在临时目录运行。

## 验收方式（写操作全部在模拟 home）

- 用本地 git 仓库模拟上游，覆盖：没改过直接更新；改过选“保留我的”（下次不再提示同一版）；改过选“用上游的”；改过交给 Codex 合并（一次真实调用，确认后才写入）；脚本变化被醒目标出；“撤销这次更新”恢复到更新前（技能内容、bases、registry、链接指纹一致）。
- 来源归一覆盖全部写法；自制、本机源码、本机文档生成、来源不明都不检查。
- 基准校准：构造“本机是上游旧版”和“本机在旧版基础上改过”两种情况，判定正确。
- 飞书：用替身覆盖“已是最新”“有新版”的展示，以及选定的更新方案在模拟 home 中的完整流程（含清理多放的入口）；真实环境只跑 `--check --json`。
- 真实 home 只读检查完成并产出清单；所有单测通过，在报告里贴出命令和结果。主控会在你做完后对比真实 home 的指纹，任何改动都算越界。

## 停止条件

- 需要写可写范围之外的地方，就停下这一步，写进报告，其他继续。
- 发现 PLAN 有会改变结果的错误或遗漏，写进报告的“未决项”，不要自己改需求。
- 不要开始 M5（用量与清理）及之后的里程碑。

## 回报格式（写进 `docs/m4-report.md`，最后一条消息只输出这个文件的路径和一句状态）

- 状态：完成 / 完成但有疑虑 / 缺信息 / 受阻
- 给用户的大白话总结（5 行以内）
- 真实环境的更新清单（表格，见交付物第 5 条）
- 用户以后怎么用：检查、更新、三选一、撤销各一句话
- 产出文件清单
- 证据：测试命令与结果、各验收项记录、指纹对比
- 飞书更新最终采用的方案和理由
- 未决项、对 PLAN.md 的修改建议（如有）
