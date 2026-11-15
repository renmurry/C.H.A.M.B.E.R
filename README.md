# C.H.A.M.B.E.R

**C**artographic **H**arvester for **A**utomated **M**ap **B**atch **E**xport & **R**eprojection

Turns map sheets, GeoPDFs and images into real GIS files.

Two jobs, one app:
- **Run** (batch): point it at a folder of georeferenced PDF sheets and it traces
  the boundary on every one.
- **Extract** (hands-on): open a PDF, GeoTIFF or photo, click roofs, trees,
  ponds and roads, and keep what's right. See [The Extract screen](#the-extract-screen).

For the batch job: it opens a georeferenced PDF, grabs the coordinates baked into it, traces the
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
Four tabs:
- **Run**: Browse to your folder of PDFs and to where you want the results, then
  hit **Run**. While it works, a man and his dog play fetch on the stage (a new
  random throw each round), the neon bar shows the real progress, and the log
  scrolls. When it's done you get a summary with a button to open the results.
- **Extract**: click features off a map or image, see below.
- **Settings**: coordinate system (leave it on Auto and it picks the UTM zone per
  sheet), export formats, GeoTIFF, merged GEE zip, parallel jobs, debug images,
  OCR, and the glass blur. Everything is remembered for next time.
- **Badges**: your achievements.

**Sound**: the speaker button at the top cycles *off → effects → effects +
music*. Off by default. Effects: a note on every kept feature that climbs as your
combo grows, a soft thud on a drop, a ping when look-alikes are found, a chime for
badges. Music: four original loops written for this app, *Paper Lanterns* (bright
synth-pop), *Static Hearts* (piano and heavy guitars), *Ember Hours* (lofi
piano: a rolling piano over a dusty beat, a choir swell, a quiet guitar part) and
*Pocket Sunshine* (lively stride piano with brushes and a glockenspiel) and
*Contours*, the long one: about three minutes in seven parts (a single point,
contour lines, the ride, friction, the campfire, the overview, home), its theme
spelled from letters; or shuffle all five; pick
one and set the volumes in Settings. The music is synthesised from code
(`src/chamber/music.py`) the first time you turn it on (a few seconds), then
kept in `%APPDATA%\CHAMBER\music`.

**Click the C.H.A.M.B.E.R title** to change the look. There are six: three
styles (Frost, Midnight, Atlas), each with the panels at the sides or floating
over the map (Focus). Each click picks a different one at random; the app
remembers the last. If something is waiting for Keep / Drop, the colours change
straight away and the layout waits until you've decided, so a switch never costs
you a feature.

## The Extract screen
Open (or drag in) a PDF, GeoTIFF, JPG or PNG. Several at once is fine.
To take one off the list, select it in Files and press **Remove** (or **Ctrl+W**,
or **Delete** in the list); right-click the list for **Remove all**. The file on
disk is never touched. If a file has kept features you haven't exported, it asks
first.

**Where is it on the ground?** The app works it out, best source first:
1. GeoPDF tags inside the PDF (exact).
2. A GeoTIFF, or an image with a world file (`.jgw`, `.pgw`, `.tfw`, `.wld`).
3. The grid labels printed around the map frame (`410000 E`, `1350000 N`, or
   degree labels). The coordinate system is read from the page if it's printed
   there (`EPSG:…` or `UTM Zone 36N`); if not, type the EPSG code in the Files
   panel. The fit error is shown, so you can see when the labels agree.
4. Nothing: you can still extract, in pixel units, and place it later in your GIS.

A photo with a single GPS point (a geotagged drone shot) can't be placed from that
one point; the app tells you so and works in pixels.

**Tools** (key in brackets):

| Tool | What it does |
|---|---|
| Area click `A` | Click a roof, tree or pond: its outline appears. **Shift+click** adds a point, **Ctrl+click** cuts a part away, **Tab** shows another size. |
| Box `B` | Drag a box around one feature. Best for packed roofs. |
| Snap line `L` | Click along a road or stream; the line follows it between your clicks. **Enter** or double-click finishes, **Backspace** takes back a click. Add a click wherever it bends sharply. |
| Road Brush `R` | Paint along a road (or stream, footpath) with a brush about as wide as it. Each stroke teaches the tool what a road looks like here; a soft overlay shows what it has learned. **Ctrl+wheel** or **[ ]** changes the brush size, **Backspace** takes back a stroke. |
| Paint the Map Red `X` | Paint over things that are *not* road (yards, roofs, river beds). Close a red stroke into a loop, any shape, and everything inside counts as not road too. |
| Find roads `Enter` | With either brush active: traces the roads as a network: centrelines that meet exactly at junctions (split there, small gaps bridged, stubs removed), each with its road surface. *From my strokes* follows what's joined to your paint; *Whole image* takes every road-shaped area. Each piece comes up for keep / drop, longest first. |
| Point `P` | Drop a point (a landmark, pole, well). |
| Pick `V` | Select a feature (**Delete** removes it), or click a line drawn in the PDF to select every line drawn the same way. |
| Find similar `F` | After you keep one or more of a kind, it looks for more that look the same, in this area, the whole image, or every open file. Each one comes up for **Enter** (keep) or **Esc** (drop). The Looser / Stricter slider sets how alike they must be. |
| Read text `T` | Text printed on the map is read (exact for PDFs with real text, offline OCR for images) and **names your features**: a label running along a road names the road, a label inside an area names the area, a label beside a pin names the pin. Labels that fit nothing stay as points in Landmarks. Click any feature to fix its name. |

**Enter** keeps, **Esc** drops, clicking somewhere new keeps the last one and
starts the next. Keep several in a row for a **combo** (a drop resets it). While
the model reads a new part of the map, that area is outlined with a scan line. **Ctrl+Z / Ctrl+Y** undo and redo. Wheel zooms; middle- or
right-drag pans; **0** fits the map.

**Lines and shapes drawn in a PDF** (boundaries, roads, rivers drawn by whoever
made the map) are listed under *Drawn in this PDF*, grouped by colour and width.
Pick one and press *Take into layer*: these are exact, no tracing involved.

**Road width**: per line layer, either *Measured* (taken from the image along
each road, stored as `width_m`) or *Brush width* (a fixed buffer). Kept roads go
into the line layer (e.g. Roads) and their surfaces into a matching polygon layer
(e.g. *Roads surface*). The Looser / Stricter slider also sets how sure the tool
must be before something counts as road.

**Square up outlines** (on for Buildings) turns a ragged roof outline into a
rectangle, or straight walls at right angles, without changing its area by more
than a fifth.

**Layers**: Buildings, Roads, Water, Streams, Trees, Landmarks, plus any you add
with **+ Layer**. Click a layer to draw into it, Ctrl+click to hide it. Areas and
lengths are shown in m² / ha / m / km when the map is placed.

**Export** writes every layer with its attributes (layer, name, method, confidence,
text, area or length, source file): GeoPackage (one file, all layers),
Shapefile, GeoJSON, KML (attributes show in the Google Earth balloon) or DXF.

**How the outlines work**: a small segmentation model (MobileSAM) runs on your
computer's CPU. The first click in a new part of the map takes a second or two
while it reads that area; every click after that, nearby, takes a fraction of a
second. Nothing is sent anywhere.

**The honest part**: it's very good at things with a clear edge (trees, separate
roofs, ponds). Roofs that touch each other in a dense row may merge into one, or
one roof may split along its sheets: use a box, Shift/Ctrl+clicks, or Tab. A road
under trees or crowded with parked cars needs a few more clicks. Always glance at
what you keep.

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
The Extract screen's outline model is MobileSAM
([github.com/ChaoningZhang/MobileSAM](https://github.com/ChaoningZhang/MobileSAM)),
Apache License 2.0, converted to ONNX (see `assets/models/NOTICE.md`).

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
- place an image with no coordinates by matching the place names on it to
  OpenStreetMap (opt-in, the only part that would need the internet)
- train the outline model on local roofs for dense rows of buildings
- a one-page QA sheet with every trace thumbnail so you can scan a whole batch
