"""Inventaire complet : classes et fonctions publiques du paquet jarvix_memory."""
import sys, inspect, pkgutil, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import jarvix_memory

pkg = __import__("jarvix_memory", fromlist=["x"])
count_cls = count_fn = 0
seen = set()
mods = sorted(m.name for m in pkgutil.walk_packages(pkg.__path__, prefix="jarvix_memory."))
out = []
for mn in mods:
    try:
        mod = __import__(mn, fromlist=["*"])
    except Exception:
        continue
    for name, obj in inspect.getmembers(mod):
        if name in seen:
            continue
        if inspect.isclass(obj) and obj.__module__ == mn:
            seen.add(name)
            out.append(f"CLASS {name}  ({mn})")
            count_cls += 1
            placed = False
            for mname, mobj in inspect.getmembers(obj, inspect.isfunction):
                if not (mname.startswith("_")) or mname in ("_init_db", "_connect", "_request"):
                    if not placed:
                        out.append(f"    (module {mn})"); placed = True
                    try:
                        out.append(f"    def {mname}{inspect.signature(mobj)}")
                        count_fn += 1
                    except (ValueError, TypeError):
                        pass
        elif inspect.isfunction(obj) and obj.__module__ == mn and not name.startswith("_"):
            seen.add(name)
            out.append(f"FN    {name}  ({mn})")
            count_fn += 1
with open(os.path.join(os.path.dirname(__file__), "..", "docs", "FONCTIONS.md"), "w", encoding="utf-8") as f:
    f.write("# Inventaire complet (auto-genere)\n\n" + "\n".join(out)
            + f"\n\n---\n**Classes: {count_cls} | Fonctions/modes publics: {count_fn}**\n")
print(f"CLASSES: {count_cls} | FONCTIONS PUBLICS: {count_fn}")
