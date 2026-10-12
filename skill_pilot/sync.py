"""M2 reconciliation keeps existing entry paths, including compatibility aliases."""
import os
from pathlib import Path

from .profiles import PROFILES


def desired_links(registry, home):
    home = Path(home)
    links = {}
    profiles = {p["id"]: p for p in PROFILES}
    for name, skill in registry["skills"].items():
        assigned = set(skill["assigned_agents"])
        entries = set(skill.get("entries", []))
        shared = ".agents/skills"
        # Keep every original entry for hard-coded paths and existing disable
        # settings. For missing coverage, derive placement from assignments.
        for agent in sorted(assigned):
            profile = profiles[agent]
            covered = any(any(Path(entry).is_relative_to(Path(root)) and
                              (agent != "dsh" or Path(entry).parent == Path(root))
                              for root in profile["skill_roots"]) for entry in entries)
            if covered:
                continue
            root = (shared if agent in {"codex", "dsh"} and {"codex", "dsh"} <= assigned else
                    next(r for r in profile["skill_roots"] if r != shared))
            entries.add(str(Path(root) / name))
        for relative in entries:
            links[str(home / relative)] = str(home / ".skill-pilot/store" / name)
    return links


def reconcile(registry, home, guard):
    """No new assignments in M2: preserve roots, nesting and disabled entries."""
    from .store import remove
    changed = []
    for source, target in sorted(desired_links(registry, home).items()):
        path = guard(Path(source))
        guard(Path(target))
        if path.is_symlink() and os.readlink(path) == target:
            continue
        remove(path, guard)
        guard(path.parent).mkdir(parents=True, exist_ok=True)
        guard(path).symlink_to(target, target_is_directory=True)
        changed.append(source)
    return changed


def visibility(home):
    """User skills only; no discovery, plugin execution or session startup."""
    from .scan import is_disabled, read_disabled, scan_root
    home = Path(home)
    disabled = read_disabled(home / ".codex/config.toml", home)
    if disabled["error"]:
        raise ValueError("Codex 的停用设置没能读懂，请先修复后再预览。")
    result = {}
    cache = {}
    for profile in PROFILES:
        available, automatic, versions = {}, {}, {}
        for relative in profile["skill_roots"]:
            root = home / relative
            inventory = scan_root(root, profile["id"] != "dsh", cache)
            if inventory["errors"]:
                raise ValueError("有技能目录没能完整读取，请解决后重新预览。")
            for skill in inventory["skills"]:
                if not skill["valid"] or (profile["id"] == "codex" and is_disabled(skill, disabled)):
                    continue
                available.setdefault(skill["name"], skill)
                versions.setdefault(skill["name"], set()).add(skill["digest"])
                if not skill.get("model_invocable", True) and profile["id"] in {"codex", "dsh"}:
                    continue
                if profile["id"] == "codex" and not skill.get("codex_implicit_invocation", True):
                    continue
                automatic.setdefault(skill["name"], skill)
        result[profile["id"]] = {"available": sorted(available), "automatic": sorted(automatic),
                                  "versions": {n: sorted(v) for n, v in sorted(versions.items())}}
    return result


def assignment_entries(name, agents):
    """The shared root has exactly two readers: Codex and DSH."""
    agents = set(agents)
    entries = []
    if 'dsh' in agents:
        entries.append('.agents/skills/' + name)
    elif 'codex' in agents:
        entries.append('.codex/skills/' + name)
    for agent, root in [('claude', '.claude/skills'), ('antigravity', '.gemini/config/skills')]:
        if agent in agents:
            entries.append(root + '/' + name)
    return sorted(entries)


def reconcile_assignments(registry, home, checked, changed_names, entries_override=None):
    from .codex_config import write
    from .store import check_links
    for name in sorted(changed_names):
        skill = registry['skills'][name]
        target = home / '.skill-pilot/store' / name
        check_links(target, home)
        desired = (entries_override[name] if entries_override and name in entries_override else
                   assignment_entries(name, skill['assigned_agents']))
        for relative in sorted(set(skill.get('entries', [])) | set(desired)):
            path = checked(home / relative)
            if path.exists() or path.is_symlink():
                if not path.is_symlink() or path.resolve() != target.resolve():
                    raise ValueError('技能入口出现了外部改动，请先收编或刷新后再应用。')
                if relative not in desired:
                    path.unlink()
            elif relative in desired:
                checked(path.parent).mkdir(parents=True, exist_ok=True)
                path.symlink_to(str(target), target_is_directory=True)
        skill['entries'] = desired
    disabled = {name for name, skill in registry['skills'].items()
                if 'dsh' in skill['assigned_agents'] and 'codex' not in skill['assigned_agents']
                and any(Path(e).is_relative_to('.agents/skills') for e in skill.get('entries', []))}
    write(home, registry, disabled, checked)
