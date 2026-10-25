# C.H.A.M.B.E.R

Turns georeferenced PDF map sheets into real GIS files.

It opens a georeferenced PDF, grabs the coordinates baked into it, traces the
thick white block outline off the map, and hands you GeoJSON, KML, Shapefile,
GeoPackage, DXF and GeoTIFF in whatever coordinate system you want (by default
it picks the right UTM zone for each sheet).

It scans **every subfolder** too, so you can point it at one big parent folder
and it finds all the PDFs inside, however they're organised. Results all land in
the single output folder you choose.

## The catch (please read this one)
The boundary is *painted onto the image*, not stored as real vector lines. So
the trace is a really good guess, not gospel. It lands within about 1-2% on
area, and every sheet comes with an uncertainty number and a little QC flag so
you know which ones to actually eyeball.

It also assumes the boundary is one solid, bright-white, closed loop. Broken,
dashed or faint lines, or a boundary that runs off the edge of the page, can
trip it up. When that happens it flags the sheet instead of quietly lying to
you. And the PDF has to genuinely carry georeferencing inside it; a plain scan
with no coordinates can't be dropped onto a map.

## Two ways to run it (you get both)
- `CHAMBER.exe` is the clicky app. Browse, pick a folder, hit go.
- `CHAMBER-CLI.exe` is the command-line one, for scripting and big batches.

Build both in one shot: double-click `build_all.bat`. They land in `dist\`.
(Or build them one at a time with `build_app.bat` and `build_exe.bat`.)

## Using the app
Open it, Browse to your folder of PDFs, Browse to where you want the results,
pick a CRS (or just leave it on "Auto" and it works out the UTM zone per sheet),
and hit Run. The bar fills, the log scrolls, and you get a popup when it's done
with a button to open the results folder.

## Using the command line
```
CHAMBER-CLI.exe  C:\my\pdfs  -o  C:\my\results  --epsg auto
```
Handy flags: `--epsg` (a code, or `auto`), `--dpi`, `--simplify` (smaller number
= more points on the outline), `--jobs` (chew through several at once),
`--no-tif` (skip the GeoTIFFs if you just want the shapes, much faster),
`--formats shp,gpkg,dxf`, `--merge-zip` (one merged, zipped shapefile, ready for
Google Earth Engine) and `--ocr` (read text off the sheet, see below).

## What lands in the output folder
For each PDF: the boundary in whichever formats you picked (GeoJSON, KML,
Shapefile, GeoPackage, DXF), a georeferenced GeoTIFF, and a debug image with the
trace drawn on top (seriously, glance at a few of these). Once per run you also
get one combined file with every block in it, a CSV report, and a log of what
happened. Each block is identified by its `sheet_id`, which is the PDF's file
name.

## Reading text off the sheet (optional OCR)
Tick "Read block IDs from the map (OCR)" or use `--ocr`. Fully offline. It reads
the number printed inside the traced block (ignoring neighbours), and the header
panel in the left margin if the sheet has one (names, codes, ward, block number
and dates), and adds them all as attributes. Blank fields are listed in
`meta_missing` so you know what to double-check.

### Your private sheet profile
Details that are specific to *your* sheets are kept out of the code, in a small
file of your own: `sheet_profile.json`. It can tell the tool:
- how a numeric file name splits into codes (`id_layout`), so codes come from
  the file name, which is exact, and OCR only double-checks the block number.
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
Spits out a little report: each block's area, an uncertainty range, and a sanity
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

## Someday-maybe list
- pull out more than just the boundary (roads, labels, points)
- a one-page QA sheet with every trace thumbnail so you can scan a whole batch
