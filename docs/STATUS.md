# Skill Pilot 当前状态

更新：2026-10-13。新对话先读这一页。

## 已经能用的

用户已在真实环境亲手完成三项验收：清理 30 个长期不用的技能、给 Claude 分配 grill-me（grilling 自动跟上）、在看板检查更新并装上 huashu-nuwa 等 10 个新版。

| 原始问题 | 现状 |
| --- | --- |
| 各 agent 分别管 | 技能页直接勾选；依赖自动带上 |
| 更新不用开对话 | 双击看板 → 检查更新，约 25 秒查完、边查边显示、可逐条更新 |
| 多份副本版本冲突 | 2026-10-10 完成迁移，每个技能只存一份（`~/.skill-pilot/store/`），各 agent 目录为链接 |
| 装了不知道、占上下文 | 看板按 agent 显示技能和“开场先读多少字”；清理页自己挑要撤下的（2026-10-13 起不再统计用量） |

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

看板体检（2026-10-13，Claude）：用户觉得前端仍粗糙、考虑推倒重来，且以后前端不交给 Codex。已从 GitHub 装 Impeccable（`pbakaus/impeccable` 的 `.claude/skills/impeccable`），只分给 Claude；按项目规矩不运行它自带的程序，只用它的方法。在模拟 home 上按它的“挑毛病”流程做了体检，结果 25/40，问题清单见 [frontend-critique-2026-10-13.md](frontend-critique-2026-10-13.md)。结论是保留“待应用 → 应用 → 撤销”这套交互，重做首页组织、用词和排版。用户选了“重做外观和首页、先出技能页几个版本挑”：产品说明写在根目录 [PRODUCT.md](../PRODUCT.md)；技能页样稿 A 总表 / B 按 agent / C 技能清单在 `work/skills-prototype/`（不进仓库，含用户技能数据；`build-data.py` 重新生成数据，`.claude/launch.json` 的 `skills-prototype` 在 8765 端口打开）。用户选了 B，已做进真实看板（Claude，模拟 home 上浏览器逐项验收，185 项单测通过）：
- 新的整体样子：深色页头、浅冷灰底、每个 agent 一种颜色（按表里顺序取色，页面仍不写死 agent），正文 14px、说明 13px、对比度达标；样式变量全换，其他页面沿用原结构、自动换成新样子。
- 技能页：左栏选 agent，每个带“开场先读多少字”的条（按分组分段，改了没应用时显示变长或变短）；右边是它“在用 / 可以加的”技能，用开关加撤；左栏下面提醒新 agent 和检查更新。
- 改动托盘：每处一行，自动带上的写明原因、不能单独取消；手动改的可“不改这处”（自动带上的跟着退回）。加技能直接应用、事后可撤销；撤下才弹一次确认。“受影响的文件”改成托盘里一行可展开的提示。
- 技能详情：“谁在用”每个 agent 一行带开关；“会一起带上 / 谁要用它”用标签；加依赖的下拉框默认空、选了才能点；存放位置和入口路径收进“技术细节”。
- 操作记录和完成提示改成过去时（“给 Claude 加了 2 个”）。
- 看板每次打开页面都重新读前端文件，用户刷新正开着的看板就是新样子。

## 下一步（按优先级）

0. **拿掉用量统计、清理改成手动挑**（2026-10-13 用户决定，已完成）：后端由 Codex 在单独副本里做（删除 `skill_pilot/usage/`、60 天规则和 `/api/usage*`、`usage` 命令；清理改为 `GET /api/cleanup` 只给已撤下列表、`POST /api/cleanup/preview`、`POST /api/cleanup/apply {skills}`；命令行 `cleanup <技能...> [--yes]`），Claude 审阅后合并；前端由 Claude 改：技能页和详情不再显示使用情况，清理页列出分给 agent 的技能（开场字数多的在前、可搜），勾选后进托盘、核对依赖和文件提示后撤下，可撤销、可恢复。176 项单测通过，模拟 home 上撤下、撤销、恢复、撤销恢复都实测通过。交接与报告见 [handoff-remove-usage.md](handoff-remove-usage.md)、[remove-usage-report.md](remove-usage-report.md)。用户的 `~/.skill-pilot/usage.sqlite` 留在原地没动，以后可手动删。
   - 后台进程要换新：用户需关掉全部看板页面、半分钟后重开；换新前别用清理页（新页面配旧后台会报错停下，不会误撤）。
   - `skill/skill-pilot/SKILL.md` 已改成新命令（去掉 `usage`、清理改为点名撤下、称 agent）。用户同意后，2026-10-13 用 `operations._run` 同一套流程（先备份、写操作记录、可撤销）把统一仓库里的 skill-pilot 换成新版，操作记录“把 skill-pilot 技能说明换成新版”；前后指纹只多了备份、记录和这份文件。自制技能没有现成的“从本地更新”入口，以后再改这份说明要么照此做，要么加一个正式入口。
   其他页面已细改说法（2026-10-13，Claude）：操作记录（不再列“影响：一串 agent”，技能用中文名）、设置页 agent 一栏（不列文件夹路径）；页面和所选 agent 记在地址里，刷新回到原处。界面规则写在根目录 [DESIGN.md](../DESIGN.md)。检查更新页和诊断页结构未动。

1. **新 agent 的剩余部分**：接入和管理已完成（见上）。未做：“让 Codex 查一下”调研按钮（2026-10-13 用户同意改为直接接入、调研只作可选）；手动填目录添加 agent。是否在真实环境接入 Trae、Zcode 由用户在看板上自己决定。
2. 小问题：
   - 后端 `store.guard()` 对未解析的 `/var/...` 模拟 home 会判成只读（真实 home 不受影响）；手测模拟 home 时用 `cd "$FAKE" && pwd -P` 得到的 `/private/var/...` 路径启动；
   - 浏览器请求 `/favicon.ico` 得到 403，控制台留一条报错，不影响使用；
   - `follow-builders` 的上游每天更新资讯数据，检查更新几乎每次都会列出它；
   - `/api/agents` 在用户数据上约 1～3 秒（每次重算版本号和发现目录），页面已不阻塞写入完成提示；以后频繁刷新可考虑缓存；
   - 这一轮代码净增约 1,000 行（主要是接入/不再管理和设置页 agent 一栏），可找时间做一次精简；
   - `interview-skills` 的来源更正（`jennifer88huang/interview-skills` 根目录）尚未写入真实登记表；它已撤下，不急，需要时运行 `skill-pilot set-source interview-skills --repo jennifer88huang/interview-skills --path . --yes`。

## 注意

- Codex 桌面 app 会自己改 `~/.codex/config.toml`（如给运行过的项目目录加信任条目、加功能开关），核对指纹时不要误判为本工具改的。
- 改了代码要让后台换新：请用户关掉全部看板页面，30 秒内退出。若用户曾直接退出 Chrome，旧后台可能还在（最长 24 小时）；经用户同意后结束临时目录 `skill-pilot-<uid>-*.lock` 里记录的进程。
- 项目代码备份在 GitHub 私有仓库 [Simonlau4/skill-pilot](https://github.com/Simonlau4/skill-pilot)；本机技能库和设置不上传。
