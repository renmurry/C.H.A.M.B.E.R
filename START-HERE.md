# C.H.A.M.B.E.R - start here

Hi! This whole folder is the tool. Copy it anywhere, build it once on a PC, and
you've got both a clicky app and a command-line version. Here's everything you
need, top to bottom.

## What it does (10-second version)
You give it georeferenced PDF map sheets. It traces the white
outline off each one and saves it as proper GIS files (GeoJSON, KML, Shapefile, and more)
in your coordinate system. There's an accuracy checker too.

---

## Do the other PCs need Python? No.

Important, because it's the usual worry: you only need Python on the **one PC
where you build**. The finished `CHAMBER.exe` has Python and everything
else baked inside it, so on every *other* Windows PC it just runs - no Python,
no installing anything. Build once, then copy the exe (or the installer) around.

So: build on a machine that has Python, carry the exe to the ones that don't.

---

## Step 1 - build it (you only do this on a build machine)

First you need Python 3.12 (only here, only once). Get it here:
https://www.python.org/downloads/release/python-3129/
On the very first installer screen, **tick "Add python.exe to PATH"**, then
install. (You only need this to build. After that the app runs on its own.)

Now double-click **`build_all.bat`** in this folder. It works for a few minutes
(grabbing the pieces and packing them), then drops two files into a new **`dist`**
folder:

- **`CHAMBER.exe`** - the app
- **`CHAMBER-CLI.exe`** - the command-line one

Done. You won't need Python again to run either of them.

---

## Step 2a - using the app

Double-click **`dist\CHAMBER.exe`**. Then:

1. On the **Run** tab, **Browse** to the folder with your PDFs. (It looks inside every subfolder too, so you can point it at a big parent folder and it finds them all.)
2. **Browse** to where you want the results.
3. Optional, once: open the **Settings** tab to pick the coordinate system (or leave it on **Auto**), the **export formats** (Shapefile, GeoPackage, etc.), the merged file for Google Earth Engine, or **OCR** to read the sheet number off each map. Your choices are remembered.
4. Back on **Run**, hit **Run**. A man and his dog play fetch while it works, the neon bar shows the progress, and a summary pops up at the end with a button to open the results.

First time you open it, Windows might show a blue "Windows protected your PC"
box. Click **More info**, then **Run anyway**. It's just unsigned, not dodgy.

---

## Step 2b - using the command line

Open a Command Prompt and run something like:

```
dist\CHAMBER-CLI.exe  C:\my\pdfs  -o  C:\my\results  --epsg auto
```

Lazy tip: don't type the paths. Drag a folder into the window and it fills the
path in for you.

Flags worth knowing:

- `--epsg auto` - the coordinate system: `auto` picks the UTM zone per sheet, or give a code like `32643`
- `--jobs 4` - chew through several PDFs at once
- `--tif` - also save a georeferenced GeoTIFF of each sheet (off by default; slower)
- `--debug-images all` - a debug picture for every sheet (default: only flagged ones)
- `--simplify 0.001` - smaller number means more detail on the outline
- `--formats shp,gpkg,dxf` - which file types to save (any of geojson, kml, shp, gpkg, dxf)

---

## Try it right now on the samples

There are three pretend sample maps in the **`samples`** folder. Point either
version at it to watch it work:

```
dist\CHAMBER-CLI.exe  samples  -o  samples\out  --epsg auto
```

Each PDF gives you the outline as GeoJSON and KML (plus a GeoTIFF or a "debug"
image with the trace drawn on top, if you ask for them - see the flags above).

---

## Carrying it to another PC (two easy ways)

- **Just the app:** copy **`CHAMBER.exe`** (and/or the CLI one) from `dist`
  onto a USB stick or wherever. They're self-contained, no Python needed.
  Double-click and go.
- **The whole kit:** copy this entire folder. On the new PC, run `build_all.bat`
  once and you're set.

---

## Install it like a normal program (optional)

Want Start-menu and desktop shortcuts plus an uninstaller? See **`INSTALLER.md`**.
Short version: install the free Inno Setup, then double-click
**`build_installer.bat`**. You get one Setup file you can run on any PC.

---

## Is it safe for confidential data?

Yes. It runs entirely on your computer - no internet, no accounts, nothing gets
uploaded. The fuller write-up is in **`SECURITY.md`**.

---

## The rest of the files (so nothing looks mysterious)

- `README.md` - the deeper reference, including the accuracy checker
- `SECURITY.md` - the data-safety brief you can show people
- `samples\` - three test PDFs you can practise on
- `sheet_profile.example.json` - a template for your private sheet profile
  (see the README). Your real one lives in `%APPDATA%\CHAMBER\`, never in here.
- `src\`, `tests\`, `*.spec`, `pyproject.toml` - the actual code and build recipe
- the other `build_*.bat` files - build just the app, or just the CLI, on their own

Stuck on anything? The README has the long version. Have fun.

## If something ever breaks
Don't panic - see **IF-SOMETHING-BREAKS.md**. Plain-English fixes, no coding needed.
