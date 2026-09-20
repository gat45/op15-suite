import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
p = os.path.join(tempfile.gettempdir(), "t_fix3.db")
if os.path.exists(p):
    os.remove(p)
from jarvix_memory.router import MemoryRouter
from jarvix_memory.core.models import Memory
from datetime import datetime, timedelta

r = MemoryRouter(db_path=p)

# [1] whole-word post-rank: junk comune affleure pas en top
junk = r.db.recall_cost_aware("existe pas xyz123 bulldog volant")
top = junk[0]
print("[1] junk abstain:", top.get("abstain"), "| top est partial:", not top.get("_value", 1) == 1 and word := None)
real = r.db.search_fts("MBUF 3500", limit=3)
print("[1] fts top pour MBUF:", (real[0]["content"] or "").replace("\n", " ")[:60])

# [2] scheduler
ok = r.consolidation.start_scheduler(interval_hours=6)
print("[2] scheduler demarre:", ok, "| thread:", r.consolidation._scheduler_thread.is_alive())
r.consolidation.stop_scheduler()
print("[2] stop:", r.consolidation._stop)

# [3] warm
if r.db.vector is not None:
    r.db.vector.warm()
    import time
    time.sleep(12)
    print("[3] warm model precharge:", r.db.vector._model is not None)
