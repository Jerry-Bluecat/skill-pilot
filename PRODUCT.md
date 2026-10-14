# Product

<!-- impeccable:product-schema 1 -->

依据 AGENTS.md、docs/STATUS.md 和用户在对话里的说法整理（2026-10-13）；标“推断”的还没跟用户确认。

## Platform

web

## Users

一位不写代码的使用者，在自己的 Mac 上同时用 Codex、Claude、Antigravity、DSH、Zcode 等多个 agent，技能 130 个左右。通常是开完几轮 agent 对话后，花几分钟集中整理：给哪个 agent 加上或撤下技能、检查更新、清理不用的。看不懂文件路径和技术说法，也不想逐条确认。

## Product Purpose

本机看板，把各 agent 的技能放在一处管。最初要解决四个问题：各 agent 分别管；更新要专门开对话；同一技能多份副本互相冲突；装了什么不知道、不用的还占上下文。成功的标准：打开就知道每个 agent 带着多少技能、每次新对话要占用多少 Token，改完马上生效，随时能撤销。

## Positioning

一份技能库分给多个 agent，并且把每个 agent “每次新对话被技能说明占用多少 Token”摆在眼前。

## Operating Context

- 双击 `~/Applications/Skill Pilot.app`，在 Chrome 里打开本机看板，常常一开很久。
- 数据在 `~/.skill-pilot/`，各 agent 的技能文件夹指向这一份。
- 推断：可能在国内网络下使用，界面不依赖外网字体或外部资源。

## Capabilities and Constraints

- 前端只有 `skill_pilot/web/static/` 下的三个文件，不用框架、不用构建工具；后端只用 Python 标准库。
- 所有写入走同一套流程：改了先标“待应用”，统一应用，之后可以撤销。
- 不统计用量（2026-10-13 用户决定：有的 agent 统计不到、能统计的覆盖也不全）。哪些技能该撤下由用户自己在清理页挑，看板只给“每次新对话占用多少 Token”帮用户判断。
- 界面全中文，称 agent，不称“助手”。

## Product Principles

- 做减法：不为假想的需求加功能、加配置。
- 说结果，不说机制：界面里不出现路径、链接、仓库这类说法，技术细节收进“诊断与备份”。
- 能由规则决定的不做成确认；批量操作默认全选，只让用户挑例外。
- 每个写入都能撤销；只有撤下、清理、不再管理这类操作才多问一句。
- 说实话：拿不准的事不下结论，也不拿“统计不到”之类的空话填满页面。

## Accessibility & Inclusion

中文正文不小于 13px，文字对比度不低于 4.5:1；所有操作都能用键盘完成。
