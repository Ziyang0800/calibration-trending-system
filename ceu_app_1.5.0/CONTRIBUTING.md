# Contributing
One app, one exe, one updater. Each product is a pack (packs/<id>) that is released on its own: read CONTRACT.md first.

- A product = a pack module (like ecal.py: state, scan, table, setup, ete_list ...) + its data files (catalog / default setup JSON) + tests. Register it in products.py and the dispatch hooks in service.py.
- Do not edit another product's module or the shared shell (ui/index.html, service.py dispatch) without telling the maintainer; keep shell changes small.
- Rules live in logic.py (pure functions). Add a test in tests/test_rules.py for every rule change.
- Before a pull request: `pip install playwright openpyxl` then `python tests/run_all.py` must say ALL PASSED.
- Version bump, CHANGELOG entry, build and release.py are done by the maintainer only. Test builds: release to a local folder and point CEU_UPDATE_PATH at it (never the shared drive).
- Never commit mars_account.json.
