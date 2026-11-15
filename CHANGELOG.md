# Changelog

## Unreleased
- **Read (Extract tab)**: `T` now names your features from the map. A label
  running along a road names the road; a label inside an area names the area;
  a label beside a pin names the pin. A road named twice takes the name most
  labels agree on, and names printed on two lines are joined. Used labels leave
  Landmarks; the rest stay there. Features kept later are named as you keep
  them.
- Every exported layer has a new **name** column. Click a feature to see or
  type its name (one undo step undoes it). Names show on the map.
- Fixed: opening a PDF without a large embedded image (a vector-only map) in
  the Extract tab failed with newer PyMuPDF versions.
- The "fitz is deprecated" warning on start is gone.

## 2.0.1
- First downloadable release of 2.0: `CHAMBER.exe` and `CHAMBER-CLI.exe`
  are attached to the GitHub Release. No feature changes from 2.0.0.

## 2.0.0 - "Shape Shifter"
- New **Extract** tab: open a PDF, GeoTIFF, JPG or PNG (several at once) and
  click features off it.
  - **Area click / Box**: a roof, tree or pond outlined from one click or a box;
    Shift+click adds, Ctrl+click cuts, Tab shows another size. Runs offline on
    the CPU (MobileSAM, converted to ONNX).
  - **Snap line**: roads and streams that follow the image between your clicks.
  - **Road Brush** and **Paint the Map Red**: paint roads (and, in red, what
    isn't road; a closed red loop fills) and it learns what roads look like on
    that image, then **Find roads** traces a network: centrelines joined at
    junctions plus road surfaces, with width measured from the image or fixed
    to the brush (`width_m`).
  - **Find similar**: keep a few of a kind and it looks for more, in one area,
    the whole image or every open file; each one comes up for keep or drop.
  - **Drawn in this PDF**: lines and shapes drawn inside a PDF, grouped by colour
    and width, taken in one go (exact).
  - **Read text**: map text as points.
  - **Square up outlines** for buildings; undo / redo; area and length shown.
  - **Remove / Remove all** to take files off the list (never deletes from disk),
    with a check for unexported work.
  - **Export**: GeoPackage, Shapefile, GeoJSON, KML (with attributes), DXF.
- **Placing a map** now also works without GeoPDF tags: from a GeoTIFF or world
  file, or from the **grid labels printed around the map** (with the fit error
  shown). Maps that can't be placed are worked in pixel units.
- **Six looks**: click the title. Frost, Midnight and Atlas, each with side
  panels or floating ones (Focus). The layout waits while a feature is waiting
  for keep / drop. Midnight is the v1.9 look.
- **Sound** (off by default; speaker button at the top): effects for keep, drop,
  combos, look-alikes and badges, and five original music loops, *Paper
  Lanterns*, *Static Hearts*, *Ember Hours* (lofi piano), *Pocket Sunshine*
  (lively stride piano) and *Contours* (three minutes, seven parts), synthesised
  from code, with track and volume in Settings.
- **Livelier Extract screen**: kept features pulse, a combo counter for keeps in
  a row, a scan line over the area the model is reading, and an animated
  contour-line welcome screen.
- New badges: First Outline, Tree Hugger, Road Runner, Copycat, Gridlock, Paint
  the Town Red and Shape Shifter.

## 1.9.0 - "Fetch"
- New desktop app, rebuilt with Qt: frosted-glass panels (real blur behind the
  window on Windows, a dark glass look elsewhere), neon highlights, and three
  tabs: **Run**, **Settings** and **Badges**. Every setting is remembered between
  runs. The glass blur can be switched off in Settings.
- New progress animation, in 3D: a man throws a frisbee, his dog chases and
  catches it, brings it back and sits; he kneels, pets the dog, takes the
  frisbee and throws again - short, medium or long, picked at random each
  round, for as long as the run lasts. When the run ends the dog sits beside
  him for a last pat. A neon progress bar shows the real progress underneath.
- Only the files you ask for: GeoTIFF is now off by default (`--tif` to turn it
  on), and debug images are made only for flagged sheets by default
  (`--debug-images flagged|all|none`; also in Settings).
- Parallel jobs now default to up to 4 in the app.

## 1.8.0 - "Good dog"
- New name: **C.H.A.M.B.E.R**. The apps are now `CHAMBER.exe` and
  `CHAMBER-CLI.exe`, the commands `chamber` and `chamber-validate`.
- Sheet-specific details (how a file name splits into codes, and extra label
  words printed on your sheets) now live in a private `sheet_profile.json`
  instead of the code. See `sheet_profile.example.json`.
- Each result is now identified by `sheet_id` (the PDF's file name).
- The default coordinate system is now `auto` (the UTM zone of each sheet).
- Fix: a sheet name containing `&` or `<` no longer breaks the KML file.
- Samples and tests now use made-up sheets only.
- New progress bar: a pixel-art dog runs along a grassy path (leaving paw prints)
  toward a bone at the finish line. When the run ends it grabs the bone and hops,
  with hearts if every sheet came out clean. Also: bold Run button, a status line
  with a time-left estimate, and a colour-coded log (green ok, amber flagged,
  red failed).
- OCR is now much more accurate (tested on a batch of 317 sheets):
  - The header panel is read in sharp overlapping tiles. Before, the whole tall
    panel was shrunk to fit the OCR engine and small things vanished (the District
    name was blank on every sheet, thin "1" digits went missing: 0013 read as 003).
  - If a boxed number or a date comes back incomplete, that one row gets a
    zoomed second look.
  - With a sheet profile, all codes now come from the file name, which is exact.
    OCR double-checks the sheet number.
  - ID_MISMATCH now only fires when BOTH the panel and the map number disagree
    with the file name, i.e. a sheet that is really misnamed. No more false alarms.
  - Multi-word names are kept whole ("North Ridge").
  - If a sheet has two numbers printed inside (its own plus a stray one), the
    one matching the file name is used as the map label.
  - Dates: a day like "01" whose 0 melts into the dotted line is recovered, and
    if the "Map generated on" label itself is missed (it sits at the very bottom
    edge), the tool still finds the date where that line should be.
  - Result on the 317-sheet batch: 317 ok (was 18 flagged), 0 wrong codes (was
    167), District filled on 317 (was 0), no blank Town/Village (was 15), no
    blank "generated on" (was 100). Areas unchanged. "Modified on" is only
    blank where the sheet itself leaves it blank.

## 1.7.0
- Reads the header panel off the sheet with offline OCR: State, District,
  Sub-district, Town/Village names and codes, Ward, sheet number, and the
  created / modified / generated timestamps, plus the sheet ID painted on the
  map itself. Tick "Read sheet IDs from the map (OCR)" or use --ocr. It reads the
  number that sits INSIDE the traced outline (ignoring neighbours), adds
  label / place / confidence as attributes, and checks the ID against the
  file name (flags ID_MISMATCH if they disagree). Every field lands in the
  attribute table (GeoJSON, Shapefile, GeoPackage) AND in the KML as
  ExtendedData (visible in the Google Earth balloon). Blank fields are listed in
  meta_missing. No internet.
- Fix: some sheets failed with "UnicodeEncodeError: 'charmap' codec". OCR had
  misread a smudge as a Chinese character (川) and Windows couldn't save it in
  the KML. Every output file is now written as UTF-8, and OCR text is cleaned
  to plain Latin letters/digits so those phantom characters never appear.

## 1.6.0
- Optional "merge + zip for GEE": tick it (or use --merge-zip) and the run also
  produces ONE merged shapefile plus a WGS84 copy, each zipped the way Google
  Earth Engine wants. Your individual per-sheet files are left untouched.

## 1.5.0
- Now scans subfolders: point it at a parent folder and it finds every PDF inside,
  however deeply nested. All results go into the one output folder you pick.

## 1.4.0
- Achievements! A celebratory completion dialog with a confetti burst on clean
  runs, plus unlockable badges (First Light, Centurion, Spotless, Polyglot...).
  Progress saves to your Windows AppData. New "Badges" button shows them all.
- The finish popup now adapts to the result (calm if some sheets failed).

## 1.3.0
- Choose your export formats: added Shapefile (.shp), GeoPackage (.gpkg) and DXF
  alongside GeoJSON and KML. Tick them in the app, or use `--formats` on the
  command line. GeoPackage/Shapefile also get a combined all-sheets index file.

## 1.2.0
- You now get both an app and a command-line version side by side.
  `build_all.bat` builds both, and the installer ships both.
- Trace now centres itself on the outline instead of hugging the inside
  edge (it measures how thick the line is). Cut the area error roughly in half,
  from about 2.4% to about 1.2% on the test sheets.
- New validate tool that checks the output: area, an uncertainty range,
  a coordinate-math sanity check, and a real error number if you give it known
  areas to compare against.
- Added a plain-English security write-up (`SECURITY.md`).

## 1.1.0
- Added the desktop app: folder pickers, a CRS dropdown with an Auto option,
  GeoTIFF and parallel-jobs toggles, a progress bar, a live log, and an "open the
  results folder" button.
- Moved the batch loop into one shared engine so the app and the command line
  behave identically.
- New windowed build that produces the clickable app.

## 1.0.0
- First proper version.
- Outline extraction: use a real vector outline if the PDF has one, otherwise
  trace it off the image with the flood-fill trick.
- Reads the exact georeferencing out of the PDF; can auto-pick the UTM zone.
- Outputs GeoJSON, KML and GeoTIFF, a combined index, a CSV report and a log.
- Command line with logging, parallel jobs, a progress bar, QC flags and proper
  exit codes.
- Test suite and pinned dependencies.
- Build kit for a standalone Windows exe.
