# Skill Pilot 当前状态

更新：2026-10-13。新对话先读这一页。

## 已经能用的

用户已在真实环境亲手完成三项验收：清理 30 个长期不用的技能、给 Claude 分配 grill-me（grilling 自动跟上）、在看板检查更新并装上 huashu-nuwa 等 10 个新版。

| 原始问题 | 现状 |
| --- | --- |
| 各 agent 分别管 | 技能页直接勾选；依赖自动带上 |
| 更新不用开对话 | 双击看板 → 检查更新，约 25 秒查完、边查边显示、可逐条更新 |
| 多份副本版本冲突 | 2026-10-10 完成迁移，每个技能只存一份（`~/.skill-pilot/store/`），各 agent 目录为链接 |
| 装了不知道、占上下文 | 看板显示全部技能与描述字数；用量统计 + 60 天清理 |

2026-10-12 的真实数据：登记 130 个技能，97 个分配给至少一个 agent，33 个已撤下。各 agent 技能数与描述字数：Codex 89 个 / 27,448 字，DSH 63 / 17,681，Claude 46 / 12,236，Antigravity 39 / 10,185。统一仓库共 9 次提交。

代码：`skill_pilot/` 约 7,600 行（另有样式 `app.css` 约 870 行、agent 档案 `profiles/catalog.json`）；185 项单测全部通过。启动器 `~/Applications/Skill Pilot.app`、命令行 `~/.local/bin/skill-pilot`、四个 agent 已装 `skill-pilot` 技能。

前端：2026-10-11 重做完成（DSH 执行三轮，Claude 在模拟 home 逐页验收，用户确认合并）。仍是 `index.html` + `app.css` + `app.js` 三个文件、不引入框架和构建工具；四个主页面（技能 / 检查更新 / 清理 / 操作记录）+ 低调的“诊断与备份”；所有写入统一走确认框 → 忙碌态与锁定 → 带撤销的提示（`runWrite()`）。交接与验收记录见 [handoff-frontend-redesign.md](handoff-frontend-redesign.md)、[frontend-redesign-report.md](frontend-redesign-report.md)（含旧功能 → 新位置对照表）。

技能页可读性（2026-10-12，Codex 执行，Claude 在模拟 home + 本机假 AI 服务上逐项验收）：技能显示中文名和一句话说明（英文原名小字跟在后面），按用途分组、默认收起，在用技能多的组排前面，组标题行写各 agent 分到几个；首页不显示来源标签。中文名和分组存在用户自己的 `~/.skill-pilot/labels.json`，只影响显示；用户的 130 个技能已迁入（Claude 手写的 12 组）。新增低调的“设置”页：选 AI 服务、填 key、保存并试一下；填了 key 才会在打开看板时自动给没有中文名的技能起名（每批 25 个，只发名字和最多 500 字说明），也可“重新整理全部”（留 `labels.previous.json`）。key 存在权限 0600 的 `settings.json`，不复制进模拟 home、不进备份和日志、不出现在任何接口返回里。没有分组时平铺原名并提示去设置。用户真实环境目前没填 key。交接与报告见 [handoff-llm-labels.md](handoff-llm-labels.md)、[llm-labels-report.md](llm-labels-report.md)。

看板长时间开着不再断（2026-10-12，Claude）：原来页面每 10 秒报一次“还开着”，后台 30 秒没收到就退出；Chrome 会把放在后台超过 5 分钟的标签页放慢到每分钟一次，后台因此提前退出，用户只能重开。现在每个页面带自己的编号报到，关闭或刷新时说一声再见（真实 Chrome 关标签页、刷新均已实测送达）；还有页面开着就一直保持，所有页面都关掉后仍在 30 秒内退出。页面没说再见又 24 小时没动静（直接退出 Chrome、浏览器崩溃）才退出，这期间双击 Skill Pilot 会直接接上它。新一次检查更新开始时，删掉上一次检查下载的临时文件，免得长时间运行时越积越多。

勾选不等待 + agent 通用化（2026-10-13，后台 Codex、页面 DSH，Claude 在模拟 home 与浏览器逐项验收）：
- 勾选：每次勾选的后台核对从约 2.5 秒降到约 0.02 秒（`preview_assign()` 不再重算整张表）；勾选框只在写入时禁用，改了没应用的格子标“待应用”，依赖带上的标“自动带上”并写明原因；仍是“勾完统一按应用”（用户确认）。连点时作废在途预览，不会丢勾选（浏览器实测）。
- agent 不再写死：四份 Python 档案换成数据 `skill_pilot/profiles/catalog.json`，用户自定义的存 `~/.skill-pilot/agents.json` 的 `custom`；放置、停用、扫描、用量、迁移都按档案走（共用目录、停用机制、是否递归、手动调用标记、用量读取器都是档案字段）。现有四个 agent 的放置位置、Codex 停用条目、可见名单、扫描和表格结果与改前逐项一致（16 种组合测试 + 用户数据模拟副本对照）。除档案、各用量读取器、`codex_config.py`、`research.py` 外，代码和页面里不出现具体 agent 名。
- 增减 agent：看板自动发现 `~/.<名字>/skills` 这类目录，设置页“agent”一栏可接入（核对框按“已在用仓库 / 改成统一管理 / 收进仓库 / 内容不同要选 / 原样留着”分类）、不再管理（文件夹里的技能原样留着、照常能用，进“没在管理的 agent”，可再接入）、忽略；都可撤销。接入时把绕道的链接改成直连统一仓库。新 agent 没有用量读取器时显示“统计不到”，分配给它的技能不进清理名单。用户真实环境里会被建议的是 Trae、Zcode（各 28 个，全是指向现有技能的链接）。
- 用词：看板和后台提示统一说 agent，不说“助手”（用户要求）；“让 Codex 解释 / 交给 Codex 合并”保留 Codex，因为确实调用 Codex。
- 交接与报告：[handoff-generic-agents.md](handoff-generic-agents.md)、[generic-agents-report.md](generic-agents-report.md)（含全部接口字段）、[handoff-generic-agents-frontend.md](handoff-generic-agents-frontend.md)、[generic-agents-frontend-report.md](generic-agents-frontend-report.md)。

## 下一步（按优先级）

1. **新 agent 的剩余部分**：接入和管理已完成（见上）。未做：“让 Codex 查一下”调研按钮（2026-10-13 用户同意改为直接接入、调研只作可选）；Trae、Zcode 等的用量读取器；手动填目录添加 agent。是否在真实环境接入 Trae、Zcode 由用户在看板上自己决定。
2. 小问题：
   - 后端 `store.guard()` 对未解析的 `/var/...` 模拟 home 会判成只读（真实 home 不受影响）；手测模拟 home 时用 `cd "$FAKE" && pwd -P` 得到的 `/private/var/...` 路径启动；
   - 浏览器请求 `/favicon.ico` 得到 403，控制台留一条报错，不影响使用；
   - `follow-builders` 的上游每天更新资讯数据，检查更新几乎每次都会列出它；
   - Antigravity 的用量统计不到，所以分配给它的技能不会进清理名单；Claude 的会话记录只保留 30 天；
   - `/api/agents` 在用户数据上约 1～3 秒（每次重算版本号和发现目录），页面已不阻塞写入完成提示；以后频繁刷新可考虑缓存；
   - 这一轮代码净增约 1,000 行（主要是接入/不再管理和设置页 agent 一栏），可找时间做一次精简；
   - `interview-skills` 的来源更正（`jennifer88huang/interview-skills` 根目录）尚未写入真实登记表；它已撤下，不急，需要时运行 `skill-pilot set-source interview-skills --repo jennifer88huang/interview-skills --path . --yes`。

## 注意

- Codex 桌面 app 会自己改 `~/.codex/config.toml`（如给运行过的项目目录加信任条目、加功能开关），核对指纹时不要误判为本工具改的。
- 用户首次打开看板时，用量统计要几分钟；已改为不阻塞其他操作。
- 改了代码要让后台换新：请用户关掉全部看板页面，30 秒内退出。若用户曾直接退出 Chrome，旧后台可能还在（最长 24 小时）；经用户同意后结束临时目录 `skill-pilot-<uid>-*.lock` 里记录的进程。
- 项目代码备份在 GitHub 私有仓库 [Simonlau4/skill-pilot](https://github.com/Simonlau4/skill-pilot)；本机技能库、设置和用量数据不上传。
