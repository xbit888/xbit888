"""Сетевая регрессия на токенах с известным ответом (Robinhood Chain).

Не для CI — ходит в публичный RPC и обозреватель. Запуск перед релизом:
    python tests/live_regression.py
"""
import importlib.util
import os
import sys
import tempfile
import threading

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="xbit888-live-")
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("xbit", os.path.join(os.path.dirname(HERE), "xbit888-boundless.pyw"))
xb = importlib.util.module_from_spec(spec)
sys.modules["xbit"] = xb
spec.loader.exec_module(xb)

CASES = [
    # (токен, описание, проверка итогового результата)
    ("0x95f68c34b9260eaba5464a0fd0560a543e35ff4a", "PU-X: бандл через промежуточные кошельки",
     lambda d: len(d["bundle_clusters"]) >= 1 and d["bundle_pct"] > 50),
    ("0xfeaf46c2661002dd1402221b08468b276a8e0863", "чистый запуск",
     lambda d: not d["bundle_clusters"]),
    ("0xd111d37ba471fbe1c038976c8c51560bb0ee2335", "KERMIT: чистый запуск",
     lambda d: not d["bundle_clusters"]),
]


def run(token):
    out, done = {}, threading.Event()

    def emit(kind, payload):
        if kind == "bundle_result" and payload.get("error"):
            out["error"] = payload["error"]; done.set()
        elif kind == "bundle_funders":
            out["data"] = payload; done.set()
    threading.Thread(target=lambda: xb.run_bundle_check(token, emit, xb.Translator("en"), threading.Event()),
                     daemon=True).start()
    done.wait(240)
    return out


failed = 0
for token, label, check in CASES:
    result = run(token)
    data = result.get("data")
    if not data:
        print(f"??   {label}: нет результата ({result.get('error', 'таймаут')})")
        failed += 1
        continue
    if xb.links_unverified(data):
        print(f"??   {label}: обозреватель не ответил по {data['links_failed']} кошелькам — повторите позже")
        failed += 1
        continue
    ok = check(data)
    failed += 0 if ok else 1
    print(f"{'OK ' if ok else 'FAIL'} {label}: групп {len(data['bundle_clusters'])}, бандл {data['bundle_pct']:.1f}%")
sys.exit(1 if failed else 0)
