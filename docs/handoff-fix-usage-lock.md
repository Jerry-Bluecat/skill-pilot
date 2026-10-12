# 交接卡：修正“首次统计用量时勾选表失灵”

> 2026-10-11 由 Claude（主控）派给 Codex。需求正本 `PLAN.md`（先读开头“方向调整”引言），上一轮 `docs/m7-report.md`。这是用户第一次真实使用时发现的问题，只修这一个问题，不加别的功能。

## 现象（用户实际操作）

用户第一次双击打开看板，在勾选表给 Claude 勾上 grill-me，grilling 没有被一起勾上；每个技能的“最近使用”都显示“尚未统计”；页面上没有明显报错。

## 已查明的原因（主控只读核实）

- 看板首次启动时在后台扫描几千份会话记录建立 `~/.skill-pilot/usage.sqlite`，整个过程是一个长写事务（存在 `usage.sqlite-journal`），持续数分钟。
- 勾选时前端调 `/api/assignment/preview` → `operations.preview_assign` → `table()` → `usage.recorded()` 读同一个库，报 `sqlite3.OperationalError: database is locked`，预览失败。
- 前端 `assignment-rows` 的 change 处理在失败时只调 `manageError`，用户没注意到；勾选框停在“已勾”，`draft` 没有按依赖展开。
- 后台登记没问题：registry 里 grill-me 的 `requires` 是 `['grilling']`，用户尚未按“应用”，`assigned_agents` 仍只有 codex。

## 要做的修正

1. 用量库改为 WAL 模式，扫描按文件分小批提交，读写互不阻塞。
2. 分配、预览、应用、清理以外的任何流程都不能因为用量库忙或损坏而失败：`table()` 读不到用量时，“最近使用”显示“正在统计（第一次需要几分钟）”，其余照常。清理名单在用量统计完成前显示“正在统计，完成后再生成名单”，不能用不完整的数据出名单。
3. 前端：预览失败时把刚改的勾选框恢复原状，并在该行旁边用一句大白话说明原因；预览成功时被依赖带上的勾选框要立刻显示为勾上，并在旁边注明“因为 grill-me 需要它”。
4. 首次统计期间，看板顶部显示一行进度（例如“正在统计用量：已读 1,200 / 3,100 份记录”），完成后自动消失并刷新“最近使用”。
5. 补单测：用量库被另一个连接长时间写锁住时，`preview_assign`、`table()` 仍成功；WAL 下并发读写；前端失败时勾选框回滚（可用现有的浏览器验收脚本方式）。

## 可读 / 可写范围

- **可写**：`~/Developer/skill-pilot/`（不要 commit、push）、系统临时目录。
- **只读**：真实 home 的一切，包括 `~/.skill-pilot/`（含 `usage.sqlite`）、四个技能根、Codex 配置、来源记录。对真实 home 运行本工具一律带 `SKILL_PILOT_READ_ONLY=1`。
- **禁止**：结束或干扰用户正在运行的看板进程（`python3.11 -m skill_pilot ui`）；修改真实的 `usage.sqlite`；对真实 home 做任何分配、更新、清理；重新安装启动器（`~/Applications/Skill Pilot.app`、`~/.local/bin/skill-pilot` 不需要改）。
- 硬性约束：`skill_pilot/` 代码总行数（`find skill_pilot -name "*.py" -o -name "*.js" -o -name "*.html" | xargs wc -l`，当前 4,280）增加不超过 60 行。

## 验收方式

- 模拟 home 中，用一个持有写锁的连接模拟“正在统计”，看板勾 grill-me 给 Claude：grilling 立即显示勾上并注明原因，“最近使用”显示“正在统计”；释放锁后自动刷新出真实日期。
- 预览失败的情况（人为让接口报错）：勾选框回滚，行旁显示原因。
- 所有单测通过。主控会对比真实 home 指纹，任何改动都算越界。

## 回报（写进 `docs/fix-usage-lock-report.md`，最后一条消息只输出这个文件的路径和一句状态）

状态、给用户的大白话总结（3 行以内）、改了哪些文件、代码行数前后、测试命令与结果、用户需要做什么（例如重新打开看板）。
