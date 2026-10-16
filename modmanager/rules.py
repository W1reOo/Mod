"""Explicit, auditable installation recipes. No downloaded code is executed."""
RULES = {
    "cyberpunk-archive": {
        "id": "cyberpunk-archive", "name": "Cyberpunk 2077 · Archive", "domain": "cyberpunk2077",
        "game": "Cyberpunk 2077", "steam_id": "1091500", "target": "archive/pc/mod",
        "strip": ["archive/pc/mod"], "extensions": [".archive", ".xl"], "mechanism": "文件部署",
        "requires": [], "note": "适用于 archive 模组；.xl 配套文件需要另外安装 ArchiveXL。不适用于 REDmod 包。",
    },
    "cyberpunk-redscript": {
        "id": "cyberpunk-redscript", "name": "Cyberpunk 2077 · redscript", "domain": "cyberpunk2077",
        "game": "Cyberpunk 2077", "steam_id": "1091500", "target": "r6/scripts",
        "strip": ["r6/scripts"], "extensions": [".reds"], "mechanism": "脚本挂载",
        "requires": ["engine/tools/scc.exe"], "note": "需要先按作者说明安装 redscript；这里只部署脚本，不执行安装器。",
    },
    "stardew-smapi": {
        "id": "stardew-smapi", "name": "Stardew Valley · SMAPI", "domain": "stardewvalley",
        "game": "Stardew Valley", "steam_id": "413150", "target": "Mods",
        "strip": ["Mods"], "extensions": [], "mechanism": "加载器目录",
        "requires_any": ["StardewModdingAPI.exe", "StardewModdingAPI"],
        "note": "需预先安装 SMAPI；每个模组须保留其独立文件夹。不会注入进程或自动运行 DLL。",
    },
    "skyrim-data": {
        "id": "skyrim-data", "name": "Skyrim Special Edition · Data", "domain": "skyrimspecialedition",
        "game": "The Elder Scrolls V: Skyrim Special Edition", "steam_id": "489830", "target": "Data",
        "strip": ["Data"], "extensions": [], "mechanism": "文件替换",
        "requires": [], "note": "仅部署普通 Data 包；ESP/ESM 加载顺序、SKSE、FOMOD 安装器须另行处理。",
    },
    "custom-directory": {
        "id": "custom-directory", "name": "通用 · 独立 MOD 目录", "domain": "",
        "game": "自定义游戏", "steam_id": "", "target": "Mods", "strip": ["Mods"],
        "extensions": [], "mechanism": "目录部署", "requires": [],
        "note": "仅用于确认会加载 Mods 目录的游戏；不会自动推断未知游戏的安装机制。",
    },
}


# Source identities are independent of file deployment recipes.
GAME_SOURCES = {'504230': {'name': 'Celeste', 'domain': 'celeste'}}


def known_domain(name, steam_id=''):
    if steam_id in GAME_SOURCES:
        return GAME_SOURCES[steam_id]['domain']
    for source in GAME_SOURCES.values():
        if name.strip().casefold() == source['name'].casefold():
            return source['domain']
    return ''
