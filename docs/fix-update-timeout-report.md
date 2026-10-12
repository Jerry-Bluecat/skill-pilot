# 检查更新超时修复回报

需求正本：[PLAN.md](../PLAN.md) §1、§4.4；执行范围：[handoff-fix-update-timeout.md](handoff-fix-update-timeout.md)。日期：2026-10-11。

## 状态

**完成，验收通过。** 真实 home 仅检查一次，两个目标技能均明确返回“有更新”；149 项全量单测在另一模拟看板持续运行时通过，14 项浏览器检查通过。代码总行数没有增加。没有更新真实技能、启动或干扰用户看板、修改启动器、commit 或 push。

## 给用户的大白话总结

检查更新时直接拿上游当前版本和本机比较，huashu-nuwa、agent-reach 已能正常查出新版。
默认用上游的；只有你选“保留我的”或“交给 Codex 合并”才查历史，过程中显示“正在找你改过的地方…”。

## 修改与验证范围

- 基准不可靠时，仅下载上游当前版本，完成嵌套技能说明改名、引用调整等标准处理后比较全部文件。相同显示“已是最新”，不同显示“有更新”，同时说明“无法判断你是否改过，默认用上游的”，不把未知情况说成“你改过”或“本机没改过”。
- 默认更新前保留原有确认、备份与撤销；更新后保存上游当前版本和处理后内容的基准，下次检查先比较上游目录版本，相同即跳过内容下载和历史查询。已按“保留我的”处理的版本仍显示“这一版已看过”。
- 历史查询从检查阶段移到“保留我的”选择入口、对应的执行入口及合并入口，单独限时 300 秒。完成后同步“你的改动”和“上游的改动”对比；失败不写入技能目录，重试使用新的临时目录；历史查询期间上游又变了则要求重新检查。保留选择校准期间暂停更新按钮。
- 删除检查期使用的历史校准分支、重复的历史候选读取和重复的标准处理。测试启动器显式使用本用例的临时锁文件；所有模拟服务使用临时 home、独立锁和随机端口。

修改的应用代码仅为 `skill_pilot/updates.py`、`skill_pilot/sources/update_github.py`、`skill_pilot/web/server.py`、`skill_pilot/web/static/app.js`。其余修改为相关测试、模拟验证脚本及本回报。改动记录：[本轮修改对比](../work/fix-update-timeout.patch)。

## 真实只读检查

本轮仅执行一次：

```sh
SKILL_PILOT_READ_ONLY=1 PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify-update-check-readonly.py fix-update-timeout-readonly
```

| 项目 | 结果 |
| --- | --- |
| agent-reach | 有更新；5.760 秒出现结果；基准不可靠，没有报错 |
| huashu-nuwa | 有更新；15.345 秒出现结果；基准不可靠，没有报错 |
| 全部检查 | 97 个技能、24 个仓库；24.529 秒完成；已查 97、剩余 0 |
| 汇总 | 有更新 7、已是最新 56、自制不检查 34、失败 0 |
| 真实写入 | 未执行更新；仅查询上游和在系统临时目录下载 |
| 前后指纹 | 核对 13 个位置，全部一致 |

上述单项时间是从准备整份检查名单开始，到观察到该条结果的累计时间；总耗时包含名单准备和整个检查任务，不包含前后指纹计算。

指纹范围包含完整 `.skill-pilot` 数据目录，以及仓库、基准、登记表、接入名单、操作记录、四个助手的技能根（含共享根）、Codex 配置和来源记录。没有重启或操作用户正在运行的看板。本次真实检查总耗时较上一轮约 98 秒明显缩短；耗时仍会随网络变化。

证据：[结果、耗时与前后指纹](../work/fix-update-timeout-readonly.json)、[逐条结果日志](../work/fix-update-timeout-readonly.txt)。

## 代码行数

按照交接卡要求统计，不包括测试、验证脚本或报告：

```sh
find skill_pilot -name "*.py" -o -name "*.js" -o -name "*.html" | xargs wc -l
```

| 范围 | 修改前 | 修改后 | 变化 |
| --- | ---: | ---: | ---: |
| updates.py | 314 | 327 | +13 |
| sources/update_github.py | 231 | 211 | -20 |
| web/server.py | 343 | 344 | +1 |
| web/static/app.js | 509 | 515 | +6 |
| skill_pilot 总计 | **4,442** | **4,442** | **0** |

证据：[最终原始计数](../work/fix-update-timeout-line-count-after.txt)。

## 测试命令与结果

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_update_check tests.test_m5_fixes.NormalizationTests -q
# Ran 26 tests in 12.349s — OK

PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify-update-timeout-tests.py
# 内部执行：PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -q
# 最终复验：Ran 149 tests in 38.246s — OK；验证脚本记录整体 38.434 秒
# 另一模拟看板全程存活，原锁文件保持不变；两边 home、运行目录、锁和端口相互隔离

node --check skill_pilot/web/static/app.js
# 通过

PYTHONDONTWRITEBYTECODE=1 python3 scripts/serve-fix-update-check-fixture.py
node scripts/verify-update-timeout-ui.cjs
# 14 项浏览器检查通过，脚本异常 0 项
```

回归测试用计数替身和命令记录证明：基准不可靠时不调用历史校准、不拉取完整历史；内容相同返回最新；默认更新保存新基准后跳过下载；标准改名后的基准也能快速比较；选择保留或合并才校准；保留校准只执行一次且限时大于检查限时；校准失败、重试和上游变化不写入本机技能。原有备份、精确撤销、所选技能状态校验、共享下载、并发上限和超时隔离均通过。

浏览器实际点击验证了未知基准说明、默认上游选择、选择保留时的等待提示及按钮暂停、校准后的真实改动、刷新接续和默认更新。浏览器测试首次因刷新后仍处在总览页而等待隐藏元素，修正验证脚本切回检查更新页后通过，应用代码没有因此增加改动。

证据：[回归测试](../work/fix-update-timeout-regression-tests.txt)、[全量单测](../work/fix-update-timeout-tests.txt)、[并存看板验证](../work/fix-update-timeout-tests.json)、[浏览器结果](../work/fix-update-timeout-ui-acceptance.json)、[浏览器日志](../work/fix-update-timeout-ui-tests.txt)。本轮模拟看板、浏览器、下载目录及临时 home 均已退出或清理。

新代码在用户下一次启动看板时生效；当前正在运行的旧看板没有被本轮操作。
