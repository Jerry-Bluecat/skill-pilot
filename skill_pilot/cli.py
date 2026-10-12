import argparse
import json
import shutil
import tempfile
from pathlib import Path

from .scan import scan
from .store import apply, backups, preview, restore
from . import operations


def main():
    parser = argparse.ArgumentParser(description="Skill Pilot：本机技能管理")
    commands = parser.add_subparsers(dest="command", required=True)
    inventory = commands.add_parser("scan", help="盘点本机助手和技能")
    inventory.add_argument("--json", action="store_true", help="输出完整机器可读结果")
    commands.add_parser("ui", help="打开中文看板").add_argument('--json', action='store_true')
    migrate = commands.add_parser("migrate", help="预览迁移或在模拟目录确认执行")
    mode = migrate.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="只读生成迁移预览")
    mode.add_argument("--apply", action="store_true", help="确认执行已核对的预览")
    migrate.add_argument("--plan-id")
    migrate.add_argument("--agents", nargs="+", help="要接入的助手，默认四个主力")
    migrate.add_argument("--choices", help="核对结果文件：choices 与 sources 两个对象")
    migrate.add_argument("--json", action="store_true")
    saved = commands.add_parser("backups", help="查看迁移前备份")
    saved.add_argument("--json", action="store_true")
    usage_command = commands.add_parser('usage', help='查看技能用量和数据覆盖')
    usage_command.add_argument('--json', action='store_true')
    cleanup_command = commands.add_parser('cleanup', help='预览或确认清理长期不用的技能')
    cleanup_mode = cleanup_command.add_mutually_exclusive_group(required=True)
    cleanup_mode.add_argument('--list', action='store_true')
    cleanup_mode.add_argument('--yes', action='store_true')
    cleanup_command.add_argument('--keep', action='extend', nargs='+', default=[])
    cleanup_command.add_argument('--json', action='store_true')
    withdrawn_command = commands.add_parser('restore-withdrawn', help='恢复已撤下技能的原分配')
    withdrawn_command.add_argument('skills', nargs='+')
    withdrawn_command.add_argument('--json', action='store_true')
    source_command = commands.add_parser('set-source', help='补登记来源并重新校准原始版本')
    source_command.add_argument('skill')
    source_command.add_argument('--repo', required=True)
    source_command.add_argument('--path', required=True)
    source_command.add_argument('--yes', action='store_true')
    source_command.add_argument('--json', action='store_true')
    undo = commands.add_parser("restore", help="确认还原到指定备份")
    undo.add_argument("backup_id")
    undo.add_argument("--json", action="store_true")
    checking = commands.add_parser('check-updates', help='只读检查技能更新')
    checking.add_argument('--json', action='store_true')
    updating = commands.add_parser('update', help='核对并更新选中的技能')
    updating.add_argument('skills', nargs='+')
    updating.add_argument('--yes', action='store_true')
    updating.add_argument('--choice', choices=['keep', 'upstream', 'merge'])
    updating.add_argument('--review', help='已生成的合并预览编号')
    updating.add_argument('--merge-id', action='append', default=[], help='已核对合并的 技能=编号')
    updating.add_argument('--confirm-lark-cli', action='store_true', help='单独确认同时升级飞书工具')
    updating.add_argument('--json', action='store_true')
    for name in ('status', 'list', 'assign', 'unassign', 'absorb', 'install', 'log', 'undo'):
        command = commands.add_parser(name)
        command.add_argument('--json', action='store_true')
        if name in {'list', 'assign', 'unassign'}:
            command.add_argument('--agent', required=True)
        if name in {'assign', 'unassign'}:
            command.add_argument('skill')
            command.add_argument('--yes', action='store_true')
        if name == 'absorb':
            command.add_argument('--all', action='store_true')
            command.add_argument('--yes', action='store_true')
        if name == 'install':
            command.add_argument('github_url')
            command.add_argument('--skill', action='append')
            command.add_argument('--agent', action='append', default=[])
            command.add_argument('--yes', action='store_true')
        if name == 'undo':
            command.add_argument('id')
    args = parser.parse_args()
    def fail(error):
        print(json.dumps({'error': str(error)}, ensure_ascii=False) if args.json else str(error))
        raise SystemExit(1)
    if args.command in {'usage','cleanup','restore-withdrawn','set-source'}:
        from . import usage, cleanup
        try:
            if args.command == 'usage':
                result = usage.report()
            elif args.command == 'cleanup':
                result = cleanup.preview() if args.list else cleanup.apply(args.keep,confirmed=True)
            elif args.command == 'restore-withdrawn':
                result = cleanup.restore(args.skills)
            else:
                result = operations.set_source(args.skill,args.repo,args.path,args.yes)
            if args.json:
                print(json.dumps(result,ensure_ascii=False,indent=2))
            elif args.command in {'usage','cleanup'} and (args.command == 'usage' or args.list):
                for agent, row in result['coverage'].items():
                    print(agent+'：'+row['message'])
                if args.command == 'usage':
                    for row in result['skills']:
                        print(row['name']+'：'+('；'.join(a+' '+t[:10] for a,t in row['last_used'].items()) or '没有使用记录'))
                else:
                    print(f'共有 {len(result["candidates"])} 个清理候选。')
                    for row in result['candidates']:
                        print(row['name']+'：分配给 '+ '、'.join(row['assigned_agents'])+'；最近使用 '+(row['last_used_at'] or '没有记录')+f'；描述 {row["description_chars"]} 字')
                    for agent, chars in result['savings'].items():
                        print(f'{agent} 清理后可省 {chars} 字')
                    print('已撤下：'+'、'.join(r['name'] for r in result['withdrawn']))
            else:
                print(result['message'])
                for warning in result.get('path_warnings',[]):
                    print('受影响的文件：'+warning['file'])
            return
        except (ValueError,OSError,KeyError,TypeError) as error:
            fail(error)
    if args.command in {'check-updates', 'update'}:
        from . import updates
        review = None
        keep_review = bool(args.command == 'update' and args.review)
        try:
            if args.command == 'update' and not args.yes:
                raise ValueError('更新需要用户明确同意，请先检查，再加 --yes 执行。')
            if args.command == 'update' and args.review:
                import re
                if not re.fullmatch(r'skill-pilot-updates-[A-Za-z0-9_-]+', args.review):
                    raise ValueError('合并预览编号不正确。')
                directory = Path(tempfile.gettempdir()) / args.review
                review = json.loads((directory / 'review.json').read_text())
                from .store import target_home
                if review['home'] != str(target_home()) or Path(review['temporary']).resolve() != directory.resolve():
                    raise ValueError('这份合并预览不属于当前目录。')
            else:
                review = updates.check()
            if args.command == 'check-updates':
                result = updates.public(review)
            else:
                choice = args.choice or ('merge' if args.merge_id else None)
                choices = {name: choice for name in args.skills} if choice else {}
                if args.choice == 'merge' and not args.review:
                    previews = [updates.prepare_merge(review, name) for name in args.skills]
                    result = {'needs_confirmation': True, 'review_id': review['id'], 'merges': previews,
                              'message': '合并结果已生成，文件未改动。看过对比后，用 --review 和 --merge-id 再确认。'}
                    (Path(review['temporary']) / 'review.json').write_text(json.dumps(review, ensure_ascii=False))
                    keep_review = True
                else:
                    result = updates.apply(review, args.skills, choices, True,
                                           dict(item.split('=', 1) for item in args.merge_id), args.confirm_lark_cli)
                    keep_review = False
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            elif args.command == 'check-updates':
                print(f'发现 {result["update_count"]} 个技能有更新。')
                for row in result['skills']:
                    if row['has_update']:
                        print(f'{row["name"]}：{row.get("updated_at", "")}，{row["file_count"]} 个文件，'
                              f'新增 {row["added_lines"]} 行，删除 {row["removed_lines"]} 行' +
                              ('；你改过' if row['local_modified'] else '；本机没改过') +
                              ('；脚本或执行权限有变化，请先看' if row['script_files'] else ''))
                if result['lark']:
                    print(result['lark']['message'])
                for error in result['errors']:
                    print(error['name'] + '：' + error['error'])
            else:
                print(result['message'])
                for merge in result.get('merges', []):
                    print(merge['name'] + '：' + merge['explanation'] + '\n' + merge['comparison'])
                    print('--review ' + result['review_id'] + ' --merge-id ' + merge['name'] + '=' + merge['merge_id'])
            if result.get('needs_confirmation'):
                raise SystemExit(2)
            if args.command == 'check-updates' and result['errors']:
                raise SystemExit(1)
        except (ValueError, OSError, KeyError, TypeError) as error:
            fail(error)
        finally:
            if review and not keep_review:
                shutil.rmtree(review['temporary'], ignore_errors=True)
        return
    if args.command in {'status', 'list', 'assign', 'unassign', 'absorb', 'install', 'log', 'undo'}:
        try:
            if args.command in {'status', 'list'}:
                data = operations.table()
                if args.command == 'list':
                    if args.agent not in {a['id'] for a in data['agents']}:
                        raise ValueError('这个助手还没有接入。')
                    data = {'agent': args.agent, 'skills': [s for s in data['skills'] if args.agent in s['assigned_agents']]}
            elif args.command in {'assign', 'unassign'}:
                data = operations.apply_assign([{'skill': args.skill, 'agent': args.agent,
                                                  'enabled': args.command == 'assign'}], confirmed=args.yes)
            elif args.command == 'absorb':
                if not args.yes:
                    raise ValueError('收编会移动新装技能，请核对后加 --yes 执行。')
                data = operations.absorb(all_skills=args.all)
            elif args.command == 'install':
                if not args.yes:
                    raise ValueError('安装会把所选技能收进仓库，请核对后加 --yes 执行。')
                from .sources.github import inspect
                review = inspect(args.github_url)
                try:
                    names = args.skill or [s['name'] for s in review['skills']]
                    data = operations.install(review, names, args.agent)
                    if data.get('conflicts'):
                        from .web.server import compare_files
                        for conflict in data['conflicts']:
                            conflict['comparison'] = compare_files(Path(conflict['existing']), Path(conflict['incoming']))
                finally:
                    shutil.rmtree(review['temporary'])
            elif args.command == 'log':
                data = operations.history()
            else:
                data = operations.undo(args.id)
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            elif args.command == 'status':
                for agent in data['agents']:
                    print(f'{agent["name"]}：{agent["count"]} 个技能，描述 {agent["description_chars"]:,} 字；{agent["activation"]}')
                print(f'发现 {len(data["new_skills"])} 个新装的技能。')
            elif args.command == 'list':
                for skill in data['skills']:
                    print(skill['name'] + '：' + skill['description'])
            elif args.command == 'log':
                for record in data:
                    print(f'{record["time"]} {record["message"]}（{"、".join(record["agents"])}） 编号 {record["id"]}' + (' 已撤销' if record['undone'] else ''))
            else:
                print(data['message'])
                for line in data.get('reasons', []) + data.get('dependency_warnings', []):
                    print(line)
                for warning in data.get('path_warnings', []):
                    print('受影响的文件：' + warning['file'])
                if data.get('needs_confirmation'):
                    print('请核对上述影响，加 --yes 执行。')
                for conflict in data.get('conflicts', []):
                    print(conflict['name'] + '：' + conflict['message'])
                    if conflict.get('comparison'):
                        print(conflict['comparison'])
            if isinstance(data, dict) and (data.get('needs_confirmation') or data.get('conflicts')):
                raise SystemExit(2)
            return
        except (ValueError, OSError, KeyError, TypeError) as error:
            fail(error)
    if args.command == "scan":
        data = scan()
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print("本次只读取文件。" + data["count_basis"])
            for agent in data["agents"]:
                if agent["visible_skill_count"] is None:
                    state = {"ignored": "已忽略", "discovered": "已发现，尚未接入"}.get(agent["status"], "可见数量暂时无法确认")
                    print(f'{agent["name"]}：{state}')
                else:
                    print(f'{agent["name"]}：{agent["visible_skill_count"]} 个，描述 {agent["description_chars"]:,} 字')
            print(f'发现 {len(data["conflicts"])} 组同名不同内容的技能。')
    elif args.command == "ui":
        from .web.server import run
        run(json_output=args.json)
    else:
        try:
            if args.command == "migrate":
                if args.apply and not args.plan_id:
                    parser.error("执行迁移需要先预览，并提供 --plan-id。")
                review = json.loads(open(args.choices).read()) if args.choices else {}
                if not isinstance(review, dict):
                    raise ValueError("核对结果的格式不对，请使用含 choices 和 sources 的对象。")
                data = (preview(agent_ids=args.agents) if args.plan else
                        apply(args.plan_id, agent_ids=args.agents, choices=review.get("choices"), sources=review.get("sources")))
            elif args.command == "backups":
                data = backups()
            else:
                data = restore(args.backup_id)
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            elif args.command == "migrate" and args.plan:
                print(f"迁移预览：{len(data['skills'])} 个技能，{len(data['conflicts'])} 组版本差异。")
                print("要接入的助手：" + "、".join(data["agents"]))
                for skill in data["conflicts"]:
                    option = next(o for o in skill["options"] if o["id"] == skill["default"])
                    print(f"{skill['name']}：{option['path']}；{skill['reason']}")
                for agent, before in data["before"].items():
                    print(f"{agent}：可调用 {len(before['available'])} → {len(data['after'][agent]['available'])} 个")
                print(f"预览编号：{data['plan_id']}。文件未改动；确认执行需带上这个编号。")
            elif args.command == "backups":
                for item in data:
                    print(item["backup_id"] + "：迁移前的备份")
                if not data:
                    print("还没有迁移备份。")
            else:
                print(data["message"])
        except (ValueError, OSError) as error:
            fail(error)
