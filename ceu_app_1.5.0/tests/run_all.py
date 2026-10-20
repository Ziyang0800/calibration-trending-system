"""Run every check:  python tests/run_all.py   (exit code 1 if anything fails)."""
import asyncio, os, sys, traceback
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import test_rules, test_packs, test_ui

fails = 0
for name in sorted(n for n in dir(test_rules) if n.startswith("test_")):
    try:
        getattr(test_rules, name)(); print("ok   ", name)
    except Exception:
        fails += 1; print("FAIL ", name); traceback.print_exc()
for name in sorted(n for n in dir(test_packs) if n.startswith("test_")):
    try:
        getattr(test_packs, name)(); print("ok   ", name)
    except Exception:
        fails += 1; print("FAIL ", name); traceback.print_exc()
for t in test_ui.TESTS:
    try:
        asyncio.run(t()); print("ok   ", t.__name__)
    except Exception:
        fails += 1; print("FAIL ", t.__name__); traceback.print_exc()
print("\n%s" % ("ALL PASSED" if not fails else "%d FAILED" % fails))
sys.exit(1 if fails else 0)
