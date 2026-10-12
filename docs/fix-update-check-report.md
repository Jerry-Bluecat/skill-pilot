# 检查更新：修复回报

需求正本：[PLAN.md](../PLAN.md) 的方向调整与 §4.4。本轮范围：[handoff-fix-update-check.md](handoff-fix-update-check.md)。日期：2026-10-11。

## 状态

**完成。** 143 项单测、22 项浏览器检查通过；代码净增加 121 行，上限为 150 行。真实环境只读检查约 98 秒完成，核对的真实目录指纹均未变。没有重启或干扰正在运行的真实看板，没有提交或上传代码，没有修改启动器。

## 给用户的大白话总结

点“检查更新”后立即显示总数、已查、剩余和正在检查的仓库，查到新版就显示一条。
每条可以直接更新，也可以更新全部已查出的；刷新或关闭页面再打开，进度和已更新结果都能接上。
默认只查正在分配的技能；慢仓库超时后单独提示重试，其他仓库继续检查。

## 真实环境只读检查

本轮只跑了一次，命令为：

```sh
SKILL_PILOT_READ_ONLY=1 PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify-update-check-readonly.py
```

耗时从准备检查名单前开始计算；首次结果按每 0.05 秒观察一次记录。

| 项目 | 实测 |
| --- | ---: |
| 总技能 / GitHub 仓库 | 97 / 24 |
| 默认跳过的已撤下技能 | 33 |
| 第一条结果出现（自制、不检查更新） | 0.060 秒 |
| 第一条 GitHub 结果出现 | 1.530 秒 |
| 第一条可更新结果出现 | 8.845 秒 |
| 全部完成 | 97.961 秒（约 1 分 38 秒） |
| 有更新 / 已是最新 / 这一版已看过 | 2 / 44 / 15 |
| 自制、不检查更新 / 没查成 | 34 / 2 |

有更新的是 `follow-builders` 和 `reverse-engineer-anything`，本轮仅检查，没有更新。`agent-reach` 与 `huashu-nuwa` 所在仓库超过检查时间，分别显示可稍后重试，没有被当成“已是最新”，没有拖住其他仓库。飞书工具以普通检查结果参与进度，本次 CLI 与 28 个官方技能均已是最新。

检查前后核对了统一仓库、基准目录、登记表、接入名单、操作记录、四个助手的技能根（含共享根）、Codex 配置和来源记录，共 13 个位置，全部一致。该指纹结论限定于本次真实只读检查的前后；主控可继续结合自己的全程基线核验。

证据：[耗时、结果与前后指纹](../work/fix-update-check-readonly.json)、[逐条出现记录](../work/fix-update-check-readonly.txt)。

## 修改文件

| 文件 | 修改内容 |
| --- | --- |
| `skill_pilot/updates.py` | 建立后台任务进度；逐条发布结果；默认排除未分配项，支持单独检查已撤下项；按仓库最多并行 4 个；更新前在写入锁内核对所选技能的内容、基准、来源、分配与入口，完成后保留条目状态 |
| `skill_pilot/sources/update_github.py` | 先通过 GitHub API 读取当前目录版本；可信基准相同则跳过下载与历史；不同但基准可信时直接比较基准；不可信才校准历史；同仓库共享下载，查询与读取沿用单仓库 60 秒总限时 |
| `skill_pilot/sources/github.py` | 查询与仓库读取支持传入剩余超时时间 |
| `skill_pilot/sources/lark.py` | 飞书检查和技能包读取支持总限时，保留原来的单独升级确认 |
| `skill_pilot/operations.py` | 在已有事务锁内支持更新操作重新读取登记表、核对所选技能；其他操作继续沿用原校验 |
| `skill_pilot/web/server.py` | 检查立即返回任务；新增进度查询，重复点击复用正在运行的任务；检查中的任务允许页面重开续接；可选 Codex 解释与合并不占住进度锁 |
| `skill_pilot/web/static/app.js` | 顶部进度、逐条追加、逐条更新、更新全部已查出的；保留选择与已更新状态；刷新恢复；已撤下项单独检查 |
| `skill_pilot/web/static/index.html` | 进度提示和相关按钮；说明检查中关闭页面时会等待检查完成 |
| `tests/test_update_check.py` | 新增 13 项回归检查，覆盖后台响应、逐条发布、刷新与重开、扫描中更新、所选技能校验、撤下项、快速比较、共享下载、并发上限、超时和飞书进度 |
| `tests/test_updates.py` | 看板用例等待异步结果；飞书下载模拟适配剩余限时 |
| `tests/test_m5_fixes.py` | 更新用例明确分配测试技能，符合默认只检查已分配项的范围 |
| `scripts/serve-fix-update-check-fixture.py` | 模拟 home：保留一个正在扫描的技能，另一仓库人为超时 |
| `scripts/verify-fix-update-check-ui.cjs` | 独立临时浏览器验证完整点击、刷新、重开与更新流程 |
| `scripts/verify-update-check-readonly.py` | 强制只读的真实检查，记录逐条耗时与指纹 |
| `docs/fix-update-check-report.md` | 本报告 |

## 代码行数

按交接卡指定范围统计，未把测试、验证脚本或报告计入：

```sh
find skill_pilot -name "*.py" -o -name "*.js" -o -name "*.html" | xargs wc -l
```

| 修改前 | 修改后 | 净增加 | 上限 |
| ---: | ---: | ---: | ---: |
| 4,321 | 4,442 | 121 | 150 |

证据：[逐文件前后计数](../work/fix-update-check-line-count.json)、[最终原始计数](../work/fix-update-check-line-count-after.txt)、[代码与测试改动记录](../work/fix-update-check.patch)。

## 测试命令与结果

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -q
# Ran 143 tests in 37.735s — OK

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_m7 tests.test_web -q
# 最终退出说明调整后复验：Ran 18 tests in 3.273s — OK

node --check skill_pilot/web/static/app.js
# 通过

PYTHONDONTWRITEBYTECODE=1 python3 scripts/serve-fix-update-check-fixture.py
node scripts/verify-fix-update-check-ui.cjs
# 22 项浏览器检查通过，JavaScript 异常 0 项
```

模拟看板实测确认：按钮点击后不足 1 秒显示计数；首条结果显示改动与脚本提醒，本机改过的默认用上游，可改保留我的且轮询不会重置选择；扫描未结束时第一条更新成功，后续结果仍可更新；刷新和关闭页面再打开均接回同一任务，已更新条目保留；人为超时计入失败，其他技能继续；更新全部和已撤下页单独检查成功；375 像素窄屏仍可操作。单测另验证了无页面心跳时，正在扫描的后台仍能续接，完成后正常退出。

证据：[全部单测输出](../work/fix-update-check-tests.txt)、[生命周期复验](../work/fix-update-check-lifecycle-tests.txt)、[浏览器结果](../work/fix-update-check-ui-acceptance.json)、[浏览器运行输出](../work/fix-update-check-ui-tests.txt)。全部写入验证使用系统临时 home；模拟看板、浏览器、测试 home 和本轮残留下载目录均已清理。

## 用户需要做什么

关闭所有旧看板页面，等约 30 秒让旧程序退出，再双击 Skill Pilot 打开，修复会在新后台进程中生效。无需重新安装启动器。两个超时仓库可以之后再按“检查更新”重试。

新看板在检查期间关闭页面会继续完成检查，重开可接回进度；检查完成且 30 秒无人浏览时退出。任务状态保留在本次后台进程中，退出后再次启动会重新检查，不自动恢复已经结束的旧任务。
