# How the CEU Tool is organised now (plain version)

**One exe = the shell + one folder per product.** The shell is the window, start screen, MARS fetch, updater, report and
theme. A product (3458A OGC, ECal, a future one) is a folder under `packs\`. Nothing else.

```
CEUTool.exe            shell (changes rarely)
  packs\ogc\           3458A OGC   - owner: Jacky
  packs\ecal\          ECal        - owner: colleague A
  packs\<new>\         next product - copy packs\_template
```

## Who does what
| You are | You change | You never touch | You release with |
|---|---|---|---|
| Pack owner (OGC, ECal ...) | only `packs\<your id>\` | shell files, other packs | `release_pack.py` (no exe) |
| Shell owner (Jacky) | `service.py`, `plugins.py`, `ui\index.html`, `app.py` | pack folders | `build_exe.bat` + `release.py` |

## Pack owner: change a product (no exe, others not disturbed)
1. Edit files in `packs\<id>\` (rules in `pack.py`, screen in `ui\`, data json).
2. Raise `"version"` in `product.json` (1.0.0 -> 1.0.1).
3. `python tests\run_all.py` must say ALL PASSED.
4. Pilot: `python release_pack.py packs\<id> --notes "what changed" --pilot-pcs BENCH-PC1,BENCH-PC2`
   Only those PCs get it. Restart the app there and test for a few days.
5. Everyone: `python release_pack.py <id> --promote`
6. Problem? `python release_pack.py <id> --rollback 1.0.0` (PCs go back at next start). `--list` shows what is released.
PCs fetch it at start-up and every 45 min; it runs after the next app restart. If the new pack is broken, only that
product's tile shows an error (the app tries the older version first); other products keep working.

## Pack owner: new product
Copy `packs\_template` to `packs\<newid>`, edit `product.json` (id, name, tags), `pack.py`, `ui\`. Test, then release the
first version as above. Read `CONTRACT.md` for the methods. The release also needs the shell to be new enough (`needs_shell`).

## New Python library?
- Pure Python: put it in `packs\<id>\vendor\` (works without a new exe).
- Compiled (numpy, pandas ...) or anything needing install: Jacky adds it to the exe, builds a new shell, and the pack sets `needs_shell` to that version.

## Shell owner: new exe
Change shell code -> raise `version.py` -> `build_exe.bat` -> `release.py` (publishes the exe). Packs inside the exe are the baseline for new PCs.
When a pack on the share is newer than the exe's copy, the share wins.

## Rules
- Only shell owner + pack owners get write access to the release folder (code in it runs on every PC).
- Never overwrite a released zip; always a new version. Never edit `latest.json` by hand.
- Back up the release folder (`packs\` + exe) before big changes.
