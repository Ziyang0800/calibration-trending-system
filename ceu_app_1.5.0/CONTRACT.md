# Product pack contract 1

Every product, including 3458A OGC (`packs/ogc`), is a **pack**: a folder that the shell loads at start-up. A pack can be
changed and released on its own, without a new exe. Copy `packs/_template`, rename it, and run `python tests/run_all.py`.

## Folder
```
packs/<id>/
  product.json      manifest (below)
  pack.py           class Pack  (entry; any name via "entry")
  <data files>      catalogs, default setups ... read from the pack folder
  ui/<id>.js        screen logic      ui/job.html  job card markup      ui/<id>.css  styles
  vendor/           optional: pure-Python libraries the pack needs (added to sys.path)
```
Where the shell looks: `packs/` inside the exe (baseline), then `%APPDATA%\CEUTool\packs\<id>\<version>\` (downloaded). The pinned or newest
compatible version wins; if it fails to load, the previous version is tried and the banner says so.

## product.json
| key | meaning |
|---|---|
| id | lower-case letters/digits/_ , unique, never changes |
| name, tag, desc, detail, keywords | start-screen tile and search; `detail` is the line on the product card |
| version | this pack's version (x.y.z). Raise it for every release |
| contract | must be 1 |
| needs_shell | oldest CEU Tool version that can run this pack |
| entry | python file with `class Pack` (default pack.py) |
| ui | `{"html","js","css"}` paths relative to the folder |
| order | optional, tile order |

## Python: class Pack(svc, folder, manifest)
`svc` is the shell. Stable parts: `svc.dir` (data folder), `svc.lock` (RLock), `svc._eval(equipment_id)` (MARS status dict),
`svc.cache`, `svc.refresh()`, `svc._do_refresh()`, `svc.refreshing`, `svc.fetch_error`, `svc.last_report`, `svc.mode()`, `svc.no_login_msg()`.
Shell modules a pack may import: `logic`, `store`, `masterlist`, `report`. Pack-private files go in `svc.dir` (e.g. `setup_<id>.json`; OGC uses `setup_ogc.json`, created from the old `setup.json` on the first start). `setup.json` is only for shell settings (update_path, refresh_minutes, greeting_name).

Optional methods: `close()` (back to the start screen; default `new_session`), `reminder_ids()` (ETEs for the daily 30-day reminder; default `ids()`), `diag()` (extra lines for Copy diagnostics). Optional state key `station` ("B-2" turns the accent colour purple).

Required methods (see `packs/_template/pack.py` for working stubs):

| method | returns / does |
|---|---|
| publish() | `{"models":[], "modules":[{"id","model","desc"}], "mdesc":{model:text}}` extra start-screen search terms |
| health() | `(needing attention, total)` for the tile status |
| ids(), master_ids(), demo_models() | ETE IDs the shell fetches from MARS (active, masterlist), demo names |
| problems() | list of texts for the red banner (broken data files); never raise |
| open(model, module), recent_item() | start screen opened the pack; `{"model","module","label"}` or None |
| rpc(name, *args) | calls from the screen: `shell.call(name, ...)` |
| set_job(so, serial, result), state(), scan(code) | job fields, screen state, scan result `{"kind","message"}` (kinds: verified, dup, invalid, not_in_station, need_job, no_login, ignore) |
| new_session(), reset(), reuse_session() | clear everything; clear scans; same setup next DUT |
| table() | `[(model, serial, equipment id, cal due text)]` in report order; raise ValueError if not all verified |
| unit_model(), procedure(), file_tag() | report header values and file name tag |
| get_setup(), save_setup(data), ete_list(), current_masterlist(), active_ids(), apply_masterlist(rows) | Setup page and ETE manager |

`state()` must contain: `product, job{so,serial,result,ok,errors}, rows[...], verified, total, need_scan, scanned, all_verified, reuse, kpi{...}`.
Each row: MARS status dict plus `slot, no_scan, hint, verified`.
Block scanning and the report when `svc.mode() == "nologin"` (no demo data in real reports).

## Screen (ui)
The js file calls `CEU.register("<id>", function(shell){ ... return {hooks} })`. Element ids must be unique in the app: use a prefix.
`shell` offers `$ esc api poll call(name,...) card openModal closeModal fmtDate dueHtml rerender`.
Optional hooks: `header(S, el)` (draws into the header, e.g. OGC's Station switch; the shell clears it on the start screen), `sessionLabel(S)` (text of the "same setup" question), `focusJob()` (focus the first job field), `shell.busy()` (a dialog or countdown is open).
Hooks: `render(S) started(S) progress(S) hasWork(S) notReady(S) pcard(S, detail) summary(S) kpis(S)->{n,html}` and optional `setup()`.

## Rules for contributors
1. Do not edit the shell (`service.py`, `plugins.py`, `ui/index.html`, `app.py`) from a pack change. Ask the shell owner.
2. New Python libraries: a pack can only use libraries already in the exe. Pure-Python library: put it in `vendor/`. Compiled library: ask the shell owner to add it to the exe and raise `needs_shell` in your manifest.
3. Never change `contract` yourself. A contract change is made by the shell owner and gets a migration note here.
4. Every release raises `version`. Released zips are never overwritten.
5. A pack that raises while loading shows an error on its own tile; do not catch errors to hide them.

## Releasing (pack owner)
```
python tests/run_all.py
python release_pack.py packs\<id> --notes "what changed" --pilot-pcs PC1,PC2   # pilot ring first
python release_pack.py <id> --promote                                           # everyone
python release_pack.py <id> --rollback 1.0.0                                    # back to an older released version
python release_pack.py <id> --list
```
PCs download at start-up and every 45 minutes, verify the sha256 in `latest.json`, and run the new version after the app is restarted.
Only the shell owner and pack owners may have write access to the release folder: code in it runs on every PC.
