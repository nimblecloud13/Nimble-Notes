"""Nimble Themes for Python: the same token values the browser files carry.

Copy this file into the app. Use it to render the saved theme into a page, or to build a Qt stylesheet.
The list between the markers is written by the skill's scripts/build.py from themes.json.
"""

# THEMES:BEGIN
DEFAULT = "nimble"
THEMES = [
  {"id":"nimble","name":"Nimble","mode":"dark","vars":{"--bg":"#191c24","--bg-panel":"#13161e","--bg-card":"#1d2030","--bg-input":"#0e1018","--bg-hi":"#242840","--border":"#262b3c","--border-hi":"#333a54","--accent":"#f59e0b","--accent-hi":"#fbbf24","--accent-text":"#fbbf24","--accent-soft":"#fcd34d","--text":"#f2f4fc","--text-dim":"#c4cde4","--text-muted":"#8a96b8","--accent-rgb":"245,158,11","--accent-dim":"rgba(245,158,11,.09)","--accent-glow":"rgba(245,158,11,.22)","--on-accent":"#000","--green":"#4ade80","--red":"#f87171","--blue":"#60a5fa","--purple":"#c084fc","--backdrop":"rgba(8,9,13,.66)","--shadow":"rgba(0,0,0,.5)"}},
  {"id":"cream","name":"Cream","mode":"light","vars":{"--bg":"#f5f1e8","--bg-panel":"#eee7d8","--bg-card":"#f9f8f6","--bg-input":"#fcfbfa","--bg-hi":"#e9ddc6","--border":"#e2d8c2","--border-hi":"#cebe9f","--accent":"#d97706","--accent-hi":"#f59e0b","--accent-text":"#b45309","--accent-soft":"#a16207","--text":"#241f14","--text-dim":"#5a4f3a","--text-muted":"#81745a","--accent-rgb":"217,119,6","--accent-dim":"rgba(217,119,6,.16)","--accent-glow":"rgba(217,119,6,.22)","--on-accent":"#000","--green":"#16a34a","--red":"#dc2626","--blue":"#2563eb","--purple":"#9333ea","--backdrop":"rgba(30,34,46,.42)","--shadow":"rgba(30,34,46,.22)"}},
  {"id":"fog","name":"Fog","mode":"light","vars":{"--bg":"#d7dbe4","--bg-panel":"#c9cfdb","--bg-card":"#e4e6ea","--bg-input":"#e9eaed","--bg-hi":"#bbc2d3","--border":"#b7bdcd","--border-hi":"#97a0b4","--accent":"#d97706","--accent-hi":"#f59e0b","--accent-text":"#b45309","--accent-soft":"#a16207","--text":"#141924","--text-dim":"#3a435a","--text-muted":"#5a6681","--accent-rgb":"217,119,6","--accent-dim":"rgba(217,119,6,.16)","--accent-glow":"rgba(217,119,6,.22)","--on-accent":"#000","--green":"#16a34a","--red":"#dc2626","--blue":"#2563eb","--purple":"#9333ea","--backdrop":"rgba(30,34,46,.42)","--shadow":"rgba(30,34,46,.22)"}},
  {"id":"deep-sea","name":"Deep Sea","mode":"dark","vars":{"--bg":"#0d141e","--bg-panel":"#080e16","--bg-card":"#0d182e","--bg-input":"#040810","--bg-hi":"#102042","--border":"#15243a","--border-hi":"#1b335a","--accent":"#38bdf8","--accent-hi":"#7dd3fc","--accent-text":"#7dd3fc","--accent-soft":"#7dd3fc","--text":"#f3f7fc","--text-dim":"#c4d1e3","--text-muted":"#8a9db7","--accent-rgb":"56,189,248","--accent-dim":"rgba(56,189,248,.09)","--accent-glow":"rgba(56,189,248,.22)","--on-accent":"#000","--green":"#4ade80","--red":"#f87171","--blue":"#60a5fa","--purple":"#c084fc","--backdrop":"rgba(8,9,13,.66)","--shadow":"rgba(0,0,0,.5)"}},
  {"id":"furnace","name":"Furnace","mode":"dark","vars":{"--bg":"#1e1715","--bg-panel":"#16100f","--bg-card":"#291d1a","--bg-input":"#110c0b","--bg-hi":"#382722","--border":"#342623","--border-hi":"#4c3631","--accent":"#ff7a59","--accent-hi":"#ff9d85","--accent-text":"#ff9d85","--accent-soft":"#ff9d85","--text":"#fbf5f4","--text-dim":"#e2c9c6","--text-muted":"#b4928d","--accent-rgb":"255,122,89","--accent-dim":"rgba(255,122,89,.09)","--accent-glow":"rgba(255,122,89,.22)","--on-accent":"#000","--green":"#4ade80","--red":"#f87171","--blue":"#60a5fa","--purple":"#c084fc","--backdrop":"rgba(8,9,13,.66)","--shadow":"rgba(0,0,0,.5)"}},
  {"id":"coal","name":"Coal","mode":"dark","vars":{"--bg":"#181716","--bg-panel":"#11100f","--bg-card":"#211f1c","--bg-input":"#0c0b0a","--bg-hi":"#2e2b26","--border":"#2c2926","--border-hi":"#413c37","--accent":"#f59e0b","--accent-hi":"#fbbf24","--accent-text":"#fbbf24","--accent-soft":"#fcd34d","--text":"#f9f7f6","--text-dim":"#d9d4ce","--text-muted":"#a8a199","--accent-rgb":"245,158,11","--accent-dim":"rgba(245,158,11,.09)","--accent-glow":"rgba(245,158,11,.22)","--on-accent":"#000","--green":"#4ade80","--red":"#f87171","--blue":"#60a5fa","--purple":"#c084fc","--backdrop":"rgba(8,9,13,.66)","--shadow":"rgba(0,0,0,.5)"}},
  {"id":"forest","name":"Forest","mode":"dark","vars":{"--bg":"#16201b","--bg-panel":"#101814","--bg-card":"#1a2b24","--bg-input":"#0b130f","--bg-hi":"#213b30","--border":"#23362d","--border-hi":"#304f41","--accent":"#4ade80","--accent-hi":"#86efac","--accent-text":"#86efac","--accent-soft":"#86efac","--text":"#f3fbf7","--text-dim":"#c4e3d4","--text-muted":"#8bb7a1","--accent-rgb":"74,222,128","--accent-dim":"rgba(74,222,128,.09)","--accent-glow":"rgba(74,222,128,.22)","--on-accent":"#000","--green":"#4ade80","--red":"#f87171","--blue":"#60a5fa","--purple":"#c084fc","--backdrop":"rgba(8,9,13,.66)","--shadow":"rgba(0,0,0,.5)"}},
  {"id":"moss","name":"Moss","mode":"dark","vars":{"--bg":"#1d2119","--bg-panel":"#161b13","--bg-card":"#232c1e","--bg-input":"#11150e","--bg-hi":"#2d3b26","--border":"#2e3727","--border-hi":"#3f4f36","--accent":"#a3e635","--accent-hi":"#bef264","--accent-text":"#bef264","--accent-soft":"#bef264","--text":"#f7fbf4","--text-dim":"#d2e0c8","--text-muted":"#9eb28f","--accent-rgb":"163,230,53","--accent-dim":"rgba(163,230,53,.09)","--accent-glow":"rgba(163,230,53,.22)","--on-accent":"#000","--green":"#4ade80","--red":"#f87171","--blue":"#60a5fa","--purple":"#c084fc","--backdrop":"rgba(8,9,13,.66)","--shadow":"rgba(0,0,0,.5)"}},
  {"id":"orchid","name":"Orchid","mode":"dark","vars":{"--bg":"#1d1825","--bg-panel":"#17121e","--bg-card":"#261a32","--bg-input":"#120d19","--bg-hi":"#322143","--border":"#2f243d","--border-hi":"#423057","--accent":"#c084fc","--accent-hi":"#d8b4fe","--accent-text":"#d8b4fe","--accent-soft":"#d8b4fe","--text":"#f7f3fc","--text-dim":"#d1c4e3","--text-muted":"#9d8ab7","--accent-rgb":"192,132,252","--accent-dim":"rgba(192,132,252,.09)","--accent-glow":"rgba(192,132,252,.22)","--on-accent":"#000","--green":"#4ade80","--red":"#f87171","--blue":"#60a5fa","--purple":"#c084fc","--backdrop":"rgba(8,9,13,.66)","--shadow":"rgba(0,0,0,.5)"}},
  {"id":"blush","name":"Blush","mode":"dark","vars":{"--bg":"#261d23","--bg-panel":"#1f161c","--bg-card":"#31212a","--bg-input":"#1a1116","--bg-hi":"#402936","--border":"#3c2a36","--border-hi":"#53394a","--accent":"#f472b6","--accent-hi":"#f9a8d4","--accent-text":"#f9a8d4","--accent-soft":"#f9a8d4","--text":"#fbf4f8","--text-dim":"#e0c8d8","--text-muted":"#b28fa6","--accent-rgb":"244,114,182","--accent-dim":"rgba(244,114,182,.09)","--accent-glow":"rgba(244,114,182,.22)","--on-accent":"#000","--green":"#4ade80","--red":"#f87171","--blue":"#60a5fa","--purple":"#c084fc","--backdrop":"rgba(8,9,13,.66)","--shadow":"rgba(0,0,0,.5)"}},
  {"id":"graphite","name":"Graphite","mode":"dark","vars":{"--bg":"#1f1f21","--bg-panel":"#18191a","--bg-card":"#25262a","--bg-input":"#131415","--bg-hi":"#303136","--border":"#2f3134","--border-hi":"#414349","--accent":"#f59e0b","--accent-hi":"#fbbf24","--accent-text":"#fbbf24","--accent-soft":"#fcd34d","--text":"#f6f7f8","--text-dim":"#d0d2d7","--text-muted":"#9c9fa6","--accent-rgb":"245,158,11","--accent-dim":"rgba(245,158,11,.09)","--accent-glow":"rgba(245,158,11,.22)","--on-accent":"#000","--green":"#4ade80","--red":"#f87171","--blue":"#60a5fa","--purple":"#c084fc","--backdrop":"rgba(8,9,13,.66)","--shadow":"rgba(0,0,0,.5)"}},
  {"id":"carbon","name":"Carbon","mode":"dark","vars":{"--bg":"#0e0e0e","--bg-panel":"#070707","--bg-card":"#161616","--bg-input":"#020202","--bg-hi":"#212121","--border":"#202020","--border-hi":"#333333","--accent":"#f5f5f5","--accent-hi":"#ffffff","--accent-text":"#ffffff","--accent-soft":"#ffffff","--text":"#f7f7f7","--text-dim":"#d4d4d4","--text-muted":"#a1a1a1","--accent-rgb":"245,245,245","--accent-dim":"rgba(245,245,245,.09)","--accent-glow":"rgba(245,245,245,.22)","--on-accent":"#000","--green":"#4ade80","--red":"#f87171","--blue":"#60a5fa","--purple":"#c084fc","--backdrop":"rgba(8,9,13,.66)","--shadow":"rgba(0,0,0,.5)"}},
  {"id":"steel","name":"Steel","mode":"dark","vars":{"--bg":"#23262a","--bg-panel":"#1c1f23","--bg-card":"#282c34","--bg-input":"#171a1e","--bg-hi":"#313641","--border":"#32373e","--border-hi":"#424954","--accent":"#60a5fa","--accent-hi":"#93c5fd","--accent-text":"#93c5fd","--accent-soft":"#93c5fd","--text":"#f5f7f9","--text-dim":"#ccd2db","--text-muted":"#969fac","--accent-rgb":"96,165,250","--accent-dim":"rgba(96,165,250,.09)","--accent-glow":"rgba(96,165,250,.22)","--on-accent":"#000","--green":"#4ade80","--red":"#f87171","--blue":"#60a5fa","--purple":"#c084fc","--backdrop":"rgba(8,9,13,.66)","--shadow":"rgba(0,0,0,.5)"}},
  {"id":"espresso","name":"Espresso","mode":"dark","vars":{"--bg":"#1a1411","--bg-panel":"#130d0b","--bg-card":"#261b14","--bg-input":"#0d0907","--bg-hi":"#37261b","--border":"#32241d","--border-hi":"#4c3529","--accent":"#f2c14e","--accent-hi":"#f7d77e","--accent-text":"#f7d77e","--accent-soft":"#f7d77e","--text":"#fcf6f3","--text-dim":"#e3cdc4","--text-muted":"#b7988a","--accent-rgb":"242,193,78","--accent-dim":"rgba(242,193,78,.09)","--accent-glow":"rgba(242,193,78,.22)","--on-accent":"#000","--green":"#4ade80","--red":"#f87171","--blue":"#60a5fa","--purple":"#c084fc","--backdrop":"rgba(8,9,13,.66)","--shadow":"rgba(0,0,0,.5)"}}
]
# THEMES:END


def get(theme_id=None):
    """The theme with this id, or the default one when the id is missing or unknown."""
    for t in THEMES:
        if t["id"] == theme_id:
            return t
    return next(t for t in THEMES if t["id"] == DEFAULT)


def valid(theme_id):
    return any(t["id"] == theme_id for t in THEMES)


def tokens(theme_id=None):
    """Python-style names for one theme: BG, BG_PANEL, ACCENT, TEXT_DIM and so on, each a '#rrggbb'
    string, plus ACCENT_RGB as an (r, g, b) tuple for colors that need their own alpha."""
    t = get(theme_id)
    out = {"ID": t["id"], "NAME": t["name"], "MODE": t["mode"]}
    for k, v in t["vars"].items():
        out[k[2:].replace("-", "_").upper()] = v
    out["ACCENT_RGB"] = tuple(int(n) for n in t["vars"]["--accent-rgb"].split(","))
    return out


def css_vars(theme_id=None):
    """The theme as one inline style string, for <html style="..."> rendered by the server."""
    return "".join(f"{k}:{v};" for k, v in get(theme_id)["vars"].items())
