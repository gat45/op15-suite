"""Stress-test live JARVIX sur le vrai projet D:\oneplus — observer les angles morts."""
import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from jarvix_memory.router import MemoryRouter

r = MemoryRouter()  # vraie DB jarvix_memory.db
print("=" * 60)
print("LANCEMENT LIVE SUR D:\\oneplus")
print("=" * 60)

# 1. Stats réelles
st = r.stats()
total = st.pop("total_memories")
print(f"[1] memoire: {total} souvenirs |", ", ".join(f"{k}:{v}" for k, v in st.items() if v))

# 2. Performance LIKE vs Vector vs cost-aware
def bench(fn, n=10):
    t0 = time.time()
    for _ in range(n):
        fn()
    return (time.time() - t0) / n * 1000

q = "MBUF 3500 throughput"
t_like = bench(lambda: r.db.search_fts(q, limit=5))
t_vec = bench(lambda: r.db.search_vector(q, limit=5))
t_cost = bench(lambda: r.db.recall_cost_aware(q, limit=5))
print(f"[2] perf: LIKE {t_like*1000:.0f}ms | vector {t_vec*1000:.0f}ms | cost-aware {t_cost*1000:.0f}ms")

# 3. Qualite de recall sur sujets reels
for probe in ["MBUF 3500", "root invisible", "unbrick EDL 9008", "profiler_v3 MoE", "existe pas xyz123"]:
    res = r.db.recall_cost_aware(probe, limit=3)
    print(f"[3] recall '{probe}': {len(res)} res | top:", (res[0]["content"] or "")[:70].replace("\n", " ") if res else "RIEN")

# 4. Perception d'un vrai artefact du projet
art = None
for cand in ["op15-forensics/op15_report.json", "op15-forensics/README.md", "memoire/pyproject.toml", "README.md"]:
    if os.path.exists(os.path.join(r"D:\oneplus", cand)):
        art = os.path.join(r"D:\oneplus", cand)
        break
if art:
    per = r.perception.perceive(art, note="probe live")
    print(f"[4] perception {os.path.basename(art)}: signals={per.get('signals')} top={(per.get('top_severity') or {}).get('tag')}")
else:
    print("[4] perception: aucun artefact trouve")

# 5. Verifier un claim reel (allowlist git/python)
c = r.verification.claim("git repo memoire sain", source="live-test")
av = r.auto_verify.verify_auto(c.id, [
    {"type": "file_exists", "path": r"D:\oneplus\memoire\pyproject.toml"},
    {"type": "file_contains", "path": r"D:\oneplus\memoire\pyproject.toml", "needle": "jarvix-memory"},
    {"type": "command", "cmd": ["git", "-C", r"D:\oneplus\memoire", "status", "--porcelain"], "expect_rc": 0},
])
print(f"[5] verify_auto live: {av['verdict']} ({av['passed']}p/{av['failed']}f)")

# 6. Gardes experimentaux/existants - re-test d'une piste connue
guard = r.experiment.repeat_guard("MBUF 4000")
g2 = r.experiment.repeat_guard("engie probe totally unknown")
print(f"[6] repeat_guard MBUF: blocked={guard['blocked']} | piste inconnue: blocked={g2['blocked']}")

# 7. JEV sur une vraie decision
jt = r.jev.route("besoin de lancer benchmark NPU sur le device", log=False)
jg = r.jev.gate("flash le bootloader du device", log=False)
print(f"[7] jev: route={jt['choice']} | gate flash: {jg['decision']} (p={jg['destructive_prob']})")

# 8. Angles morts cibles
env = r.proactive.monitor("lancement bench MBUF sur device", experiment_tracker=r.experiment, recovery_layer=r.recovery)
print(f"[8] proactive: silent={env['silent']} | fail_actifs={len(env['active_failures'])} | refutes={len(env['refuted_path_warning'])}")

# 9. Densite DB / doublons connus
conn = r.db._connect()
n_inconnu = conn.execute("SELECT COUNT(*) FROM memories WHERE type='action' AND status='provisional'").fetchone()[0]
print(f"[9] actions provisionales jamais resolues: {n_inconnu} (angle mort: proposees, jamais approuvees/archived)")

# 10. Consolidation inutile?
cs = r.consolidation.stats()
print(f"[10] consolidation: {cs}")

print("=" * 60)
