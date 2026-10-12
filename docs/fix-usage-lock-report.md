# 首次用量统计阻塞勾选：修复回报

需求正本：[PLAN.md](../PLAN.md)。本轮范围：[handoff-fix-usage-lock.md](handoff-fix-usage-lock.md)。日期：2026-10-11。

## 状态

**完成。** 只修本交接卡指定的问题；全部 130 项单测和 15 项浏览器检查通过，代码净增加 41 行。真实看板保持运行，修复会在下次启动时生效。

## 给用户的大白话总结

第一次统计用量时，技能勾选和分配也能正常操作，grilling 会随 grill-me 一起勾上并说明原因。
页面顶部会显示统计进度，完成后自动更新使用日期；清理名单等统计完成后才生成。
勾选没成功会恢复原状，并在旁边说明原因。

## 修改文件

| 文件 | 修改内容 |
| --- | --- |
| `skill_pilot/usage/__init__.py` | 用量库采用 WAL；每读完一个文件就提交一次；记录统计完成标记；短等待、只读读取，忙、缺失或损坏时返回“正在统计”；提供逐文件进度，并关闭失败时的连接 |
| `skill_pilot/operations.py` | 分配表读取失败不影响预览或应用；显示“正在统计（第一次需要几分钟）”；支持读取看板的临时用量库 |
| `skill_pilot/web/server.py` | 新增进度查询；用量统计和清理不再排队等待；统计忙时自动重试；清理忙或读不到数据时不给名单；移除重复读取用量库的步骤 |
| `skill_pilot/web/static/app.js` | 启动时开始统计，显示进度并自动更新日期；预览失败恢复勾选和待应用改动，同行提示原因；依赖旁显示“因为 grill-me 需要它”；搜索时也显示被自动带上的技能；预览期间暂时禁用相关操作 |
| `skill_pilot/web/static/index.html` | 增加顶部进度提示位置 |
| `skill_pilot/cleanup.py` | 用量库忙或损坏时提示“正在统计，完成后再生成名单”，不输出不完整名单 |
| `tests/test_usage_lock.py` | 新增 6 项回归测试，覆盖长写锁、损坏与缺失、WAL 并发、逐文件提交与进度、扫描中断、接口等待与恢复 |
| `scripts/serve-fix-usage-lock-fixture.py` | 在系统临时目录建立模拟 home，扫描第二个文件时持有写锁，等待浏览器验收释放 |
| `scripts/verify-fix-usage-lock-ui.cjs` | 使用独立临时浏览器配置验证依赖勾选、失败回滚、统计进度、自动重试和刷新 |
| `docs/fix-usage-lock-report.md` | 本报告 |

## 代码行数

使用交接卡指定命令，前后统计范围相同：

```sh
find skill_pilot -name "*.py" -o -name "*.js" -o -name "*.html" | xargs wc -l
```

| 修改前 | 修改后 | 净增加 | 上限 |
| ---: | ---: | ---: | ---: |
| 4,280 | 4,321 | 41 | 60 |

[逐文件前后计数](../work/fix-usage-lock-line-count.json)、[最终原始计数](../work/fix-usage-lock-line-count-after.txt)、[代码改动记录](../work/fix-usage-lock.patch)。

## 测试命令与结果

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -q
# Ran 130 tests in 27.523s — OK

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_usage_lock tests.test_usage -q
# Ran 19 tests — OK

node --check skill_pilot/web/static/app.js
# 通过

PYTHONDONTWRITEBYTECODE=1 python3 scripts/serve-fix-usage-lock-fixture.py
# 启动模拟看板；所有技能和用量写入都在系统临时目录

node scripts/verify-fix-usage-lock-ui.cjs
# 15 项检查通过，浏览器异常 0 项
```

[最终全部单测输出](../work/fix-usage-lock-tests.txt)、[浏览器结构化结果](../work/fix-usage-lock-ui-acceptance.json)、[浏览器运行输出](../work/fix-usage-lock-ui-tests.txt)。

实测结果：

- 另一连接一直持有排他写锁时，`table()` 和 `preview_assign()` 在短等待后成功返回；`grilling` 自动加入 Claude，实际应用也成功。
- WAL 写事务未提交时，另一个连接可以读取已提交日期；提交后能读取新日期。
- 扫描第二个文件持有写锁时，另一连接已能看到第一个文件的提交结果；进度为 `1 / 2`，分配表仍显示“正在统计”，不展示半份统计结果。
- 模拟看板搜索 `grill-me` 后给 Claude 勾选，`grilling` 立即显示为勾上，旁边注明“因为 grill-me 需要它”；释放写锁后，进度消失、真实日期自动出现，待应用分配保留。
- 人为让预览接口报错，勾选和取消勾选都会恢复原状，原因显示在对应格旁边；此前成功的待应用改动保留，接口恢复后可继续勾选。
- 统计期间清理接口立即返回等待说明，没有候选名单，清理按钮禁用；用量库损坏时同样不生成名单。忙时恢复和多页面等待自动重试均有覆盖。

## 范围与用户下一步

本轮没有对真实 home 运行 Skill Pilot，没有修改真实用量库、技能根、配置、来源记录或启动器，没有结束或操作用户正在运行的看板，也没有提交或上传代码。所有写入测试均使用系统临时 home；浏览器采用独立临时配置。本轮创建的模拟看板、浏览器和模拟 home 已清理。真实目录指纹由主控按其任务前基线复核，本轮没有另行声称指纹一致。

用户需要关闭全部看板页面，等约 30 秒让旧程序退出，再双击 Skill Pilot 打开。仅刷新旧页面不足以让后台修复生效；不需要重新安装启动器。
