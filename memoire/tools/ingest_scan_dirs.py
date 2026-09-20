import sys
sys.path.insert(0, "src")
from pathlib import Path
from jarvix_memory.core.database import Database
from jarvix_memory.core.ingest import ingest_directory, get_scan_roots

db = Database("jarvix_memory.db")
roots = get_scan_roots(Path("config.json"))
print("racines:", len(roots))
for r in roots:
    res = ingest_directory(db, r)
    if "error" in res:
        print("ERR ", r, "->", res["error"])
    else:
        print("OK ", r)
        print("    ->", res["files"], "fichiers |", res["size"], "octets | sem:", res["semantic_id"][:8])
