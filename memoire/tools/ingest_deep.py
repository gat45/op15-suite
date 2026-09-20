import sys
sys.path.insert(0, "src")
from jarvix_memory.core.database import Database
from jarvix_memory.core.ingest import ingest_directory, _human

db = Database("jarvix_memory.db")
for r in [r"D:\oneplus", r"D:\archive_16tps_20260902",
          r"D:\snapdragon_profiling", r"D:\runtime_v2", r"D:\profil_40tokens"]:
    res = ingest_directory(db, r, note="scan COMPLET sans cap (deep)", max_files=200000)
    tag = "OK " if "semantic_id" in res else "ERR"
    print(tag, r, "->", res.get("files"), "fichiers |", _human(res.get("size", 0)),
          "| skipped:", res.get("skipped", 0))
