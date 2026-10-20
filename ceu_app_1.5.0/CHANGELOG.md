# Changelog
## 1.5.0 (branch feature/plugin-products)
- Products load as plug-in packs from folders (packs/<id>, see CONTRACT.md). ECal moved out of the shell into packs/ecal (own code, data, screen, tests).
- A pack is released on its own with release_pack.py (zip + sha256 + latest.json on the release folder); PCs download it at start-up / every 45 min and use it after a restart. Pilot ring (--pilot-pcs / --pilot-users), --promote, --rollback, --list.
- A pack that fails to load, or is not compatible, shows its error on its own tile; the other products keep working; an older version of the same pack is tried first.
- Start screen: tiles for failed packs; a banner tells when a new pack version was downloaded.
- packs/_template: copy to start a new product. 3458A OGC is a pack too (packs/ogc): station rules, B-1/B-2, Setup editor and screen moved out of the shell; its setup now lives in setup_ogc.json (made from the old setup.json automatically). The shell has no product code left.
- tests/test_packs.py: release, sync, pilot, rollback, checksum, zip safety, broken pack fallback.
## 1.4.1
- Product card is bigger (larger name, teal tint). 
- "Model ID" (e.g. N4431B) and "Module ID" (e.g. N4431-60008) wording everywhere. Entering a Module ID on the start screen fills the Model ID and locks it when the module belongs to one model; when it belongs to several (N4431A/B) the job card offers them as buttons.
- Messages say "the developer" (no name); the sign-in button is "MARS login".
- ETE checks only look at what is in use: the Expiring/Expired/Sent-for-cal cards count the ETEs of the current station (OGC) or the ones the chosen module needs (ECal), not every spare Set; start-screen tile status counts the active B-1 setup; the daily reminder covers B-1, the chosen B-2 Set and ECal active units.
- Arrow keys move through start-screen search hits; scan feedback is announced to screen readers.
## 1.4.0
- No MARS login on a PC: no demo data any more. A red bar says "This PC has no MARS login. Please inform <dev> to sign in", scanning and report creation are blocked, and tiles show "No MARS login". Once a login works the "Dev sign-in" button disappears. Developer name: "dev_name" in setup.json (default Jacky). Demo data only with the environment variable CEU_DEMO=1 (tests).
- A broken ecal_catalog.json (or setup_ecal.json / names.json) now shows the red banner and falls back to the built-in catalog, instead of failing silently. The catalog is validated.
- Cancel button (and Esc) during the 2-second report countdown; "Create report" stays available when all ETEs are verified.
- OGC rows now name a valid unit of the same model when the active one is not valid (as ECal does).
- Start screen: tiles show status ("All ETEs valid" / "N need attention"), plus a Recent row.
- Setup pages show each unit's cal due date.
- Masterlist import shows a preview (+new / removed / changed, warns when a removed ETE is active in Setup) before replacing.
- Colour roles: teal = selection/focus/actions, red = logo and critical errors, green = success, amber = warning. Dialog headers are neutral unless it is an error/warning; buttons are teal.
- Job card collapses to a one-line summary (Edit/Hide) once scanning starts; the B-2 card appears only after a Set is chosen; visible keyboard focus rings.
- Options (... button): Reduce motion switch, Copy diagnostics (version, log tail, setup summary; no passwords). Progress bar under the header while MARS refreshes.
- tests/ folder: python tests/run_all.py (rules tests + headless screen tests). CONTRIBUTING.md added.
## 1.3.2
- Greeting uses a short name looked up from the Windows login name in names.json ({"ziyanang": "Jacky"}); no match shows "Hello, Cal AE". The key can also be the e-mail/UPN (Windows user principal name), and "greeting_name" in setup.json overrides everything on that PC. Lookup order: %APPDATA%\\CEUTool\\names.json, then names.json in the shared release folder (copied to the PC at start-up and every 45 min, so edits reach every PC without a rebuild), then the bundled default_names.json.
## 1.3.1
- Title bar is teal (dark: deep teal with teal edge; light: soft teal tint). Colours in winchrome.py.
- Start screen: "Hello, Cal AE / What are you calibrating today?", teal accents instead of red.
- Slide/fade transition between the start screen and a product page, and back.
- Smaller KPI cards plus a wide product card (e.g. "HP/Agilent 3458A 8.5-digit multimeter"; for ECal it shows the chosen module).
- ECal torque tester: one at a time. Torque wrench is Yes/No on the job card; the tester itself (model, then ID) is set in Setup.
- Everything resets when you start a new session ("No, start a new session") and when you go back to the start screen (a "Leave and clear?" prompt appears only if there are scans or job fields). Module, connectors, torque, job fields, scans, B-2 Set and station are all cleared.
## 1.3.0
- New product: ECal (ECal modules + torque testers). Search a model (N4431B) or module ID (N4431-60008) on the start screen.
- Job: module model, then module ID (filtered by model; typing suggests matches), connector types for Mixed modules (up to 3 on 4-port, 2 on 2-port), unit serial, Service Order, result type, torque wrench Yes/No (+ which tester).
- Required ETEs follow from the module: VNA + the cal kit of each connector type (+ torque testers). They are the ACTIVE units chosen in Setup (ECal Setup page: VNA, 6 kits, 3 torque testers); a scan can only confirm them, anything else is blocked. When an active unit is not valid and another unit of the same model is, the row says which one to switch to.
- Torque testers are listed on the report but never scanned (they are in the mech-lab); they must still be valid in MARS.
- Report identical to OGC (ETE rows only). Unit: model (serial). Procedure: Orion, ECAL (5959-9575), ECAL.CAL.N882 (override with "procedure" in setup_ecal.json).
- Data files: ecal_catalog.json (modules, options, connector-to-kit map; copy to %APPDATA%\CEUTool to override without rebuilding), default_ecal_setup.json -> %APPDATA%\CEUTool\setup_ecal.json (active units + masterlist; masterlist import also accepts a 'Model ID' column).
- Next DUT on the same setup keeps the verified ETEs: change the module and only the kits that differ need scanning.
## 1.2.0
- Product framework: the app now opens on a start screen. Type a model (e.g. 3458A) or pick a product tile; the matching application loads. A Products button (house icon, top left) returns to the start screen. 3458A OGC is unchanged and is product #1; more products plug in as packs (products.py).
- Windows title bar is coloured to match the theme (dark: deep red-black with Keysight-red edge; light: soft red tint). Windows 11 gets the full colours, Windows 10 gets a dark/light bar. Colours are in winchrome.py (PALETTE).
## 1.1.4
- build_exe.bat warns (and stops) when mars_account.json is missing, instead of silently building an exe with no MARS login; it records this in dist\\build_info.txt and release.py refuses such a build unless --allow-no-account is given.
## 1.1.3
- New app icon: barcode with viewfinder corners and scan line (make_icon.py, app.ico).
- Alignment pass: header grid (station switch centred, status buttons flush to the right edge), table text now lines up with the cards above it, tick column right-aligned, Verified divider and job card spacing evened out, scan row shows "Ready to scan".
## 1.1.2
- Save and Import dialogs now open as native Windows dialogs on their own thread (fix for the mouse pointer missing / dialog not clickable). Falls back to the old dialog if that fails; the reason is written to app.log.
## 1.1.1
- Built-in shared release folder (\\romulus\v4\PGLab\Callab\Software\CEU_Reporting_Tool): update checks and release.py use it without any setup.json edit. An update_path in setup.json still overrides it.
- B-2 warning wording: "I acknowledge, do not show again until next launch".
## 1.1.0
- Polish, same layout: shorter KPI cards with a status edge, step badges 1/2, icons on the header buttons, count badge on the Verified divider.
- Animation: scanned row blinks green (0.4 s) then slides to Verified; KPI and progress numbers count smoothly; scan box shakes on an invalid, unknown or duplicate ETE;
  pop-ups fade in; Refresh icon spins; animated tick on "Report saved"; smooth theme switch. Respects Windows "reduce animations".
## 1.0.4
- A scanned ETE blinks green in its place for a moment, then moves to the bottom of the list.
## 1.0.3
- B-2 warning is shown once each time the app is started (no longer once a day).
- After a report is saved: "Do you have another DUT using the same setup?" Yes re-uses the session: MARS is fetched again
  and every ETE is re-checked automatically; only Service Order, Serial # and Result Type are entered, then "Create report"
  (2-second countdown as before). Ends when the app closes, on a new day, a station or B-2 Set switch, Setup save, Clear scans.
- An ETE that is no longer valid loses its tick automatically; the report cannot be created until it is fixed.
- Countdown and save steps show a progress bar; scan box wording: "Scan the Equipment ID Sticker with barcode scanner".
- Setup editor: row numbers removed. Tooltips on the ETEs, Setup, Refresh and MARS login buttons.
## 1.0.2
- Light theme redesigned: cooler blue-grey look, same teal (B-1) and purple (B-2) as the dark theme.
- build_exe.bat stops early with a clear message if dist\CEUTool.exe is still running.
## 1.0.1
- Service Order accepts WO-######### or SO#########; label/placeholder wording: "Serial #".
- Main list: first column renamed "Equipment"; scanned ETEs move to the bottom (switchable).
- Light / dark theme switch (remembered).
- The CEU report is saved where the user chooses (Save dialog).
## 1.0.0
- First versioned build: includes everything from v1-v6 (fixed-slot Setup with model/ID dropdowns, group-set rule,
  ETE manager, once-a-day B-2 warning, 45-minute MARS refresh, SO/WO service orders) plus the update check.
