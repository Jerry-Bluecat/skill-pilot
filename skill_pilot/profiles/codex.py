PROFILE = {
    "id": "codex", "name": "Codex", "config_dirs": [".codex"],
    "apps": ["ChatGPT.app", "Codex.app"], "cli": "codex",
    "skill_roots": [".agents/skills", ".codex/skills"],
    "readonly_roots": [(".codex/skills/.system", "builtin"),
                       (".codex/plugins/cache", "plugin_cache"),
                       (".codex/plugins/user", "plugin"),
                       (".codex/vendor_imports", "vendor")],
    "disable": "config.toml 中按名称或文件位置停用",
    "usage": "会话文件中的实际工具调用", "activation": "新会话生效",
    "visibility_note": "已扣除停用项及仅限手动调用项；内置、插件和候选库另列，其安装存在不代表已在本次会话启用。",
}
