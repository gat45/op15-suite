"""validate_doctor_report.py — valide le schéma du rapport JSON de mcp_doctor.

Usage :
    python3 tools/validate_doctor_report.py doctor-report.json

Sans dépendance externe. Exit 0 = rapport conforme, exit 1 = violation
(détail de chaque erreur sur stderr). Utilisé par la CI pour garantir que
le rapport reste consommable (rapports de session, dashboards, alertes).
"""
import json
import sys
from pathlib import Path

REQUIRED_TOP = {
    "tool": str, "date": str, "registry": str, "servers": list,
    "ok_count": int, "fail_count": int, "all_green": bool,
}
REQUIRED_SERVER = {
    "name": str, "ok": bool, "server": (str, type(None)),
    "version": (str, type(None)), "tools": int, "probe": (dict, type(None)),
    "duration_s": (int, float), "detail": str,
}
REQUIRED_PROBE = {"tool": str, "ok": bool, "msg": str}


def check(cond: bool, errors: list, msg: str) -> None:
    if not cond:
        errors.append(msg)


def type_ok(value, expected) -> bool:
    types = expected if isinstance(expected, tuple) else (expected,)
    return isinstance(value, types) and not (isinstance(value, bool)
                                             and bool not in [bool] + list(types))


def validate(report: dict) -> list:
    errors: list[str] = []
    for key, typ in REQUIRED_TOP.items():
        check(key in report, errors, f"clé top-level manquante: {key}")
        if key in report:
            check(type_ok(report[key], typ), errors,
                  f"{key}: type {type(report[key]).__name__}, attendu {typ}")
    check(report.get("tool") == "mcp_doctor", errors,
          f"tool != 'mcp_doctor': {report.get('tool')!r}")

    servers = report.get("servers", [])
    check(isinstance(servers, list) and len(servers) > 0, errors,
          "servers: liste non vide attendue")
    names = set()
    for i, s in enumerate(servers):
        if not isinstance(s, dict):
            errors.append(f"servers[{i}]: objet attendu")
            continue
        for key, typ in REQUIRED_SERVER.items():
            check(key in s, errors, f"servers[{i}]: clé manquante: {key}")
            if key in s:
                check(type_ok(s[key], typ), errors,
                      f"servers[{i}].{key}: type invalide")
        name = s.get("name")
        check(name and name not in names, errors,
              f"servers[{i}]: name absent ou dupliqué ({name!r})")
        names.add(name)
        # durée cohérente (>= 0) et tools non négatif
        check(s.get("duration_s", -1) >= 0, errors,
              f"servers[{i}].duration_s négatif")
        check(s.get("tools", -1) >= 0, errors, f"servers[{i}].tools négatif")
        # si ok=True : pas de sonde en échec ; si sonde présente : schéma probe
        probe = s.get("probe")
        if probe is not None:
            check(isinstance(probe, dict), errors, f"servers[{i}].probe: dict attendu")
            if isinstance(probe, dict):
                for key, typ in REQUIRED_PROBE.items():
                    check(key in probe, errors,
                          f"servers[{i}].probe: clé manquante: {key}")
                if probe.get("ok") is False:
                    check(s.get("ok") is False, errors,
                          f"servers[{i}]: sonde en échec mais ok=True")
        if s.get("ok") is True and s.get("detail", "") == "":
            errors.append(f"servers[{i}]: ok=True sans detail")

    # cohérence des compteurs
    n = len(servers)
    check(report.get("ok_count", -1) == sum(1 for s in servers
                                            if isinstance(s, dict) and s.get("ok")),
          errors, "ok_count incohérent avec servers[]")
    check(report.get("fail_count", -1) == sum(1 for s in servers
                                              if isinstance(s, dict) and not s.get("ok")),
          errors, "fail_count incohérent avec servers[]")
    check(report.get("ok_count", 0) + report.get("fail_count", 0) == n, errors,
          "ok_count + fail_count != len(servers)")
    check(report.get("all_green") == (report.get("fail_count") == 0), errors,
          "all_green incohérent avec fail_count")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_doctor_report.py <doctor-report.json>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"INVALID: rapport illisible ({e})", file=sys.stderr)
        return 1
    if not isinstance(report, dict):
        print("INVALID: racine JSON non-objet", file=sys.stderr)
        return 1
    errors = validate(report)
    if errors:
        print(f"INVALID: {len(errors)} violation(s) de schéma:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"VALID: rapport conforme ({len(report.get('servers', []))} serveurs, "
          f"all_green={report.get('all_green')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
