PROFILE = {
    "id": "antigravity", "name": "Antigravity", "config_dirs": [".gemini/config", ".gemini/antigravity"],
    "apps": ["Antigravity.app"], "cli": "agy",
    "skill_roots": [".gemini/config/skills"],
    "readonly_roots": [(".gemini/antigravity/builtin/skills", "builtin"),
                       (".gemini/antigravity-cli/builtin/skills", "builtin"),
                       (".gemini/config/plugins", "plugin")],
    "disable": "本轮未验证", "usage": "统计不到；隔离复现未得到可靠读取步骤",
    "activation": "新会话核验", "visibility_note": "按用户技能目录盘点；内置和插件另列。",
}
