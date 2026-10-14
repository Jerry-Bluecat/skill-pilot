---
name: Skill Pilot
description: 本机看板：一份技能库，分给多个 agent
colors:
  shell: "#18202E"
  shell-raised: "#262F42"
  shell-ink: "#F2F4F8"
  shell-ink-muted: "#AEB7C5"
  ground: "#EDF0F4"
  surface: "#FFFFFF"
  surface-soft: "#F2F4F8"
  surface-deep: "#E6EAF0"
  line: "#DCE1E8"
  line-strong: "#AEB7C5"
  ink: "#18202E"
  ink-secondary: "#465163"
  ink-muted: "#5F6A7B"
  pending: "#E3A008"
  pending-bg: "#FFF5D6"
  pending-ink: "#6A4A00"
  danger-ink: "#A8251B"
  danger-bg: "#FDECEA"
  agent-1: "#2F5BD3"
  agent-2: "#C4552B"
  agent-3: "#6D4BC2"
  agent-4: "#0F7C6E"
  agent-5: "#93650A"
  agent-6: "#B0346B"
  agent-7: "#3D7A1F"
  agent-8: "#5B6B85"
typography:
  brand:
    fontFamily: "Avenir Next, Avenir, PingFang SC, -apple-system, Microsoft YaHei, sans-serif"
    fontSize: "20px"
    fontWeight: 800
    lineHeight: 1.3
  title:
    fontFamily: "Avenir Next, Avenir, PingFang SC, -apple-system, Microsoft YaHei, sans-serif"
    fontSize: "26px"
    fontWeight: 700
    lineHeight: 1.3
  section:
    fontFamily: "Avenir Next, Avenir, PingFang SC, -apple-system, Microsoft YaHei, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.3
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, PingFang SC, Helvetica Neue, Microsoft YaHei, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.65
  note:
    fontFamily: "PingFang SC, -apple-system, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  meta:
    fontFamily: "PingFang SC, -apple-system, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
  code:
    fontFamily: "SF Mono, ui-monospace, Menlo, monospace"
    fontSize: "12px"
rounded:
  sm: "8px"
  md: "12px"
  tray: "12px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  xxl: "32px"
components:
  button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    height: "34px"
  button-primary:
    backgroundColor: "{colors.shell}"
    textColor: "{colors.shell-ink}"
    rounded: "{rounded.sm}"
  switch-on:
    backgroundColor: "{colors.agent-1}"
    rounded: "{rounded.pill}"
    size: "40px x 24px"
  pending-ring:
    backgroundColor: "{colors.pending}"
  tray:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.tray}"
---

# Skill Pilot 的界面规则

样式都在 `skill_pilot/web/static/app.css` 的 `:root` 里，这里说清怎么用。产品本身的情况见 [PRODUCT.md](PRODUCT.md)。

## Overview

这是一个“干活”的界面：打开就要知道有什么要处理，改完马上生效、随时能撤销。外观只负责四件事：字、配色、疏密，以及一个特色元素，也就是每个 agent 的“开场先读多少字”的条。导航、按钮、开关、表格都用大家熟悉的样子，不自创控件。

页面的使用场景：白天在 Mac 上，开完几轮 agent 对话后花几分钟集中整理技能，所以只做浅色。SP 管理电脑上的本地技能，按桌面窗口设计和验收。

## Colors

- brandkit 的五种品牌色：深墨色 `#18202E`、抬起一层的深墨色 `#262F42`、冷白色 `#F2F4F8`、浅冷灰 `#EDF0F4` 和钢灰 `#AEB7C5`。页头、主按钮和提示条用深墨色，主按钮悬停用第二种深墨色；页面底色用浅冷灰，分组与控件悬停用冷白色，控件边框用钢灰，内容仍放在白色面板上。
- 文字三档：`ink` 正文，`ink-secondary` 说明，`ink-muted` 次要信息；`ink-muted` 只用在 12px 以上，且背景是白色或 `ground`。
- **每个 agent 一种颜色**，按 `/api/table` 给的顺序从 `agent-1` 到 `agent-8` 依次取（`agentColor()`）。页面里凡是代表某个 agent 的地方（色块、字数条、开关打开时）都用它的颜色，别处不用这些颜色做装饰。
- **黄色只表示“改了还没生效”**：开关外圈、托盘、行底色。撤下用 `danger-ink` 字色提醒，不用大片红色。
- 颜色从不单独表达意思：开关有开/关位置，待应用有文字说明。

## Typography

品牌字标和标题用这台 Mac 已有的 Avenir Next，中文标题回退到苹方；正文用系统界面字体，中文仍是苹方。所有字体来自本机。品牌字标 20px / 800，标题 26px / 700，分节 20px / 700；正文 14px，说明 13px，最小 12px，正文行高 1.65。层级靠字号和粗细，不靠颜色。数字一律等宽数字（`tabular-nums`，已在 body 上开启）。技能英文原名用等宽小字跟在中文名后面。

## Layout

- 内容最宽 1440px，左右留 24px（窄屏 16px）。
- 技能页：左栏 300px 放 agent 列表和提醒，右边放所选 agent 的技能；宽度小于 1024px 时左栏变成顶部横排。
- 列表行之间用 1px 细线，分组标题用 `surface-soft` 底色，不用卡片套卡片。
- 页面底部留出 160px，给浮在底部的托盘让位。

## Elevation & Depth

两档阴影：`--shadow-1`（列表、卡片轻轻浮起）和 `--shadow-2`（托盘、详情面板、提示条、对话框）。不用彩色光晕，也不用硬边投影。

## Shapes

控件圆角 8px，面板和底部托盘 12px，开关和标签用全圆角。不用超过 1px 的彩色左边框做强调。

## Components

- **页头**：高度至少 60px，品牌字标与 SP 标志并列，当前导航入口用冷白色细线标明。
- **开关**：加/撤技能都用开关（`role="switch"`），打开时是该 agent 的颜色；改了没生效时外圈多一圈黄。
- **底部托盘**（`#action-bar`）：所有“改了还没生效”的事都进这里，每处一行，写清给谁、加还是撤下、为什么（自动带上的写原因）。手动改的每处都能“不改这处”。
- **确认**：能撤销的操作直接做、事后给撤销提示；只有撤下、清理、不再管理这类操作才弹一次确认框。确认框第一句写结果，不列文件路径。
- **提示条**：右上角深色，带“撤销”的至少停 20 秒。
- **详情面板**：右侧滑出，“谁在用”每个 agent 一行带开关；路径等技术内容收进最后的“技术细节”。
- **字数条**：已生效部分按分组分段；会加上的用黄色斜纹，会撤下的用空心斜纹；每 1 万字一条刻度。

## Do's and Don'ts

- 要：说结果，不说机制。“Codex 看不到它”而不是“链接到统一仓库”；做完的事用过去时。
- 要：拿不到的信息不逐行写“不知道”“统计不到”，要么不显示，要么在页面说明里说一次。
- 要：所有操作能用键盘完成，焦点框清楚，关掉面板后焦点回到原来的位置。
- 不要：路径、仓库、链接、哈希这类词出现在主界面。
- 不要：为一件不需要打断的事弹对话框。
- 不要：用 emoji 或字符代替图标；需要图标时用统一线宽的 SVG。

## 图标

2026-10-14 用 brandkit 建立 SP 图标系统。主标志由相扣的 S 路径和 P 回环组成，表示一份技能库分给多个 agent；只使用深墨色和冷白色。页头标志为 34px，导航图标为 18px，沿用现有文字和选中状态。

六个导航图标共用 24 × 24 网格、1.75 的线宽与圆角：技能用叠层，更新用循环箭头，清理用刷子，记录用时钟，诊断用带波形的盾牌，设置用滑杆。图标与文字一起显示，读屏只读文字。浏览器小图标使用深墨色方底和冷白色标志。

设计板在 `docs/brand/skill-pilot-brandkit.png`；深浅标志与单独的导航图标在 `skill_pilot/web/static/brand/`，浏览器小图标在 `skill_pilot/web/static/favicon.svg`。页面直接内嵌图形，加载不依赖外部服务。

Mac 应用图标使用同一枚 SP 标志，深墨色圆角方底，四周留透明边缘以匹配系统应用图标。1024 × 1024 原稿在 `assets/SkillPilot.svg`，安装素材在 `assets/SkillPilot.icns`，包含 16、32、128、256、512 点及各自两倍尺寸。`scripts/build-app.sh` 会复制图标并写入应用图标配置，重新生成启动器时仍会保留它。
