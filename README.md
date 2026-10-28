# C.H.A.M.B.E.R

**C**artographic **H**arvester for **A**utomated **M**ap **B**atch **E**xport & **R**eprojection

Turns georeferenced PDF map sheets into real GIS files.

It opens a georeferenced PDF, grabs the coordinates baked into it, traces the
thick white outline off the map, and hands you GeoJSON, KML, Shapefile,
GeoPackage, DXF and GeoTIFF in whatever coordinate system you want (by default
it picks the right UTM zone for each sheet).

It scans **every subfolder** too, so you can point it at one big parent folder
and it finds all the PDFs inside, however they're organised. Results all land in
the single output folder you choose.

## The catch (please read this one)
The outline is *painted onto the image*, not stored as real vector lines. So
the trace is a really good guess, not gospel. It lands within about 1-2% on
area, and every sheet comes with an uncertainty number and a little QC flag so
you know which ones to actually eyeball.

It also assumes the outline is one solid, bright-white, closed loop. Broken,
dashed or faint lines, or an outline that runs off the edge of the page, can
trip it up. When that happens it flags the sheet instead of quietly lying to
you. And the PDF has to genuinely carry georeferencing inside it; a plain scan
with no coordinates can't be dropped onto a map.

## Two ways to run it (you get both)
- `CHAMBER.exe` is the clicky app. Browse, pick a folder, hit go.
- `CHAMBER-CLI.exe` is the command-line one, for scripting and big batches.

Build both in one shot: double-click `build_all.bat`. They land in `dist\`.
(Or build them one at a time with `build_app.bat` and `build_exe.bat`.)

## Using the app
Three tabs:
- **Run**: Browse to your folder of PDFs and to where you want the results, then
  hit **Run**. While it works, a man and his dog play fetch on the stage (a new
  random throw each round), the neon bar shows the real progress, and the log
  scrolls. When it's done you get a summary with a button to open the results.
- **Settings**: coordinate system (leave it on Auto and it picks the UTM zone per
  sheet), export formats, GeoTIFF, merged GEE zip, parallel jobs, debug images,
  OCR, and the glass blur. Everything is remembered for next time.
- **Badges**: your achievements.

## Using the command line
```
CHAMBER-CLI.exe  C:\my\pdfs  -o  C:\my\results  --epsg auto
```
Handy flags: `--epsg` (a code, or `auto`), `--dpi`, `--simplify` (smaller number
= more points on the outline), `--jobs` (chew through several at once),
`--tif` (also write a GeoTIFF of each sheet; off by default because it's slower),
`--debug-images flagged|all|none` (default: only for flagged sheets),
`--formats shp,gpkg,dxf`, `--merge-zip` (one merged, zipped shapefile, ready for
Google Earth Engine) and `--ocr` (read text off the sheet, see below).

## What lands in the output folder
For each PDF: the outline in whichever formats you picked (GeoJSON, KML,
Shapefile, GeoPackage, DXF). If you ask for them: a georeferenced GeoTIFF, and a
debug image with the trace drawn on top (made for flagged sheets by default -
glance at those). Once per run you also
get one combined file with every sheet in it, a CSV report, and a log of what
happened. Each result is identified by its `sheet_id`, which is the PDF's file
name.

## Reading text off the sheet (optional OCR)
Tick "Read sheet IDs from the map (OCR)" or use `--ocr`. Fully offline. It reads
the number printed inside the traced outline (ignoring neighbours), and the header
panel in the left margin if the sheet has one (names, codes, ward, sheet number
and dates), and adds them all as attributes. Blank fields are listed in
`meta_missing` so you know what to double-check.

### Your private sheet profile
Details that are specific to *your* sheets are kept out of the code, in a small
file of your own: `sheet_profile.json`. It can tell the tool:
- how a numeric file name splits into codes (`id_layout`), so codes come from
  the file name, which is exact, and OCR only double-checks the sheet number.
  A sheet whose printed number disagrees with its file name is flagged
  `ID_MISMATCH`.
- extra words printed on your sheets that are labels, not place names
  (`label_words`, `label_prefixes`).

Put it at `%APPDATA%\CHAMBER\sheet_profile.json`, or point the `CHAMBER_PROFILE`
environment variable at it. Start from `sheet_profile.example.json`. Without a
profile everything still works; codes then come from OCR alone. Never commit
your real profile (it's in `.gitignore`).

## Did it actually work? (the validation tool)
```
chamber-validate  C:\my\pdfs  -o  C:\my\results
```
Spits out a little report: each sheet's area, an uncertainty range, and a sanity
check on the coordinate math. Drop a `ground_truth.csv` (just
`sheet_id,true_area_ha`) next to your PDFs and it'll tell you the real error
against known areas. On the test sheets that's about 1.2% off.

## Installing it like a normal program
See `INSTALLER.md`. Builds a proper Windows installer with Start-menu and desktop
shortcuts and an uninstaller.

## Running the tests
```
pip install -e ".[dev]"
pytest
```
The samples and test sheets are made up: invented names, invented codes,
invented places.

## Security, quickly
It all runs on your machine. No internet, no logins, nothing phones home. Full
story in `SECURITY.md`.

## Credits
The stage animation is rendered (in Blender) from two 3D models, both under the
Creative Commons Attribution 4.0 licence
([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)):
- "Geoffrey Frisbee Throw - Disc Golf" by
  [LasquetiSpice](https://sketchfab.com/LasquetiSpice) -
  [model page](https://sketchfab.com/3d-models/geoffrey-frisbee-throw-disc-golf-60b257e448df4cb0b55d4670026d4e6a)
- "Stylized Low Poly German Shepherd" by
  [DreamNoms](https://sketchfab.com/DreamNoms) -
  [model page](https://sketchfab.com/3d-models/stylized-low-poly-german-shepherd-18d8fbe184c5448283762893b6ea9752)

Changes made: posed and animated (relaxed stance, kneeling, petting, catching),
combined into one scene with a frisbee, lit, and rendered as image sequences.
Only the rendered frames ship with the app, not the models.

## Someday-maybe list
- pull out more than just the outline (roads, labels, points)
- a one-page QA sheet with every trace thumbnail so you can scan a whole batch
