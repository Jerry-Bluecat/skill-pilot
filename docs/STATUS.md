# Skill Pilot 当前状态

更新：2026-10-12。新对话先读这一页。

## 已经能用的

用户已在真实环境亲手完成三项验收：清理 30 个长期不用的技能、给 Claude 分配 grill-me（grilling 自动跟上）、在看板检查更新并装上 huashu-nuwa 等 10 个新版。

| 原始问题 | 现状 |
| --- | --- |
| 各 agent 分别管 | 技能页直接勾选；依赖自动带上 |
| 更新不用开对话 | 双击看板 → 检查更新，约 25 秒查完、边查边显示、可逐条更新 |
| 多份副本版本冲突 | 2026-10-10 完成迁移，每个技能只存一份（`~/.skill-pilot/store/`），各 agent 目录为链接 |
| 装了不知道、占上下文 | 看板显示全部技能与描述字数；用量统计 + 60 天清理 |

2026-10-12 的真实数据：登记 130 个技能，97 个分配给至少一个 agent，33 个已撤下。各 agent 技能数与描述字数：Codex 89 个 / 27,448 字，DSH 63 / 17,681，Claude 46 / 12,236，Antigravity 39 / 10,185。统一仓库共 9 次提交。

代码：`skill_pilot/` 约 6,560 行（另有样式 `app.css` 847 行）；163 项单测全部通过。启动器 `~/Applications/Skill Pilot.app`、命令行 `~/.local/bin/skill-pilot`、四个 agent 已装 `skill-pilot` 技能。

前端：2026-10-11 重做完成（DSH 执行三轮，Claude 在模拟 home 逐页验收，用户确认合并）。仍是 `index.html` + `app.css` + `app.js` 三个文件、不引入框架和构建工具；四个主页面（技能 / 检查更新 / 清理 / 操作记录）+ 低调的“诊断与备份”；所有写入统一走确认框 → 忙碌态与锁定 → 带撤销的提示（`runWrite()`）。交接与验收记录见 [handoff-frontend-redesign.md](handoff-frontend-redesign.md)、[frontend-redesign-report.md](frontend-redesign-report.md)（含旧功能 → 新位置对照表）。

技能页可读性（2026-10-12，Codex 执行，Claude 在模拟 home + 本机假 AI 服务上逐项验收）：技能显示中文名和一句话说明（英文原名小字跟在后面），按用途分组、默认收起，在用技能多的组排前面，组标题行写各助手分到几个；首页不显示来源标签。中文名和分组存在用户自己的 `~/.skill-pilot/labels.json`，只影响显示；用户的 130 个技能已迁入（Claude 手写的 12 组）。新增低调的“设置”页：选 AI 服务、填 key、保存并试一下；填了 key 才会在打开看板时自动给没有中文名的技能起名（每批 25 个，只发名字和最多 500 字说明），也可“重新整理全部”（留 `labels.previous.json`）。key 存在权限 0600 的 `settings.json`，不复制进模拟 home、不进备份和日志、不出现在任何接口返回里。没有分组时平铺原名并提示去设置。用户真实环境目前没填 key。交接与报告见 [handoff-llm-labels.md](handoff-llm-labels.md)、[llm-labels-report.md](llm-labels-report.md)。

## 下一步（按优先级）

1. **识别新 agent**（PLAN 的 M6）：看板发现未接入的 agent（目前有 WorkBuddy、Cursor、Trae；Kimi 已设为忽略），按“调研”交给 Codex 查官方说明、起草接入档案，用户确认后接入。尚未开始。
2. 小问题：
   - 后端 `store.guard()` 对未解析的 `/var/...` 模拟 home 会判成只读（真实 home 不受影响）；手测模拟 home 时用 `cd "$FAKE" && pwd -P` 得到的 `/private/var/...` 路径启动；
   - 浏览器请求 `/favicon.ico` 得到 403，控制台留一条报错，不影响使用；
   - `follow-builders` 的上游每天更新资讯数据，检查更新几乎每次都会列出它；
   - Antigravity 的用量统计不到，所以分配给它的技能不会进清理名单；Claude 的会话记录只保留 30 天；
   - `interview-skills` 的来源更正（`jennifer88huang/interview-skills` 根目录）尚未写入真实登记表；它已撤下，不急，需要时运行 `skill-pilot set-source interview-skills --repo jennifer88huang/interview-skills --path . --yes`。

## 注意

- Codex 桌面 app 会自己改 `~/.codex/config.toml`（如给运行过的项目目录加信任条目、加功能开关），核对指纹时不要误判为本工具改的。
- 用户首次打开看板时，用量统计要几分钟；已改为不阻塞其他操作。
- 项目代码备份在 GitHub 私有仓库 [Simonlau4/skill-pilot](https://github.com/Simonlau4/skill-pilot)；本机技能库、设置和用量数据不上传。
