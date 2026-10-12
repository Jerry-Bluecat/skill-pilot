PROFILE = {
    "id": "claude", "name": "Claude", "config_dirs": [".claude"],
    "apps": ["Claude.app"], "cli": "claude",
    "skill_roots": [".claude/skills"],
    "readonly_roots": [(".claude/plugins", "plugin_cache"), (".claude/skills/synced", "builtin")],
    "disable": "本轮未验证", "usage": "会话文件中的技能调用或读取",
    "activation": "目录改变后会动态刷新", "visibility_note": "按用户技能目录盘点；插件和桌面同步技能另列。",
}
