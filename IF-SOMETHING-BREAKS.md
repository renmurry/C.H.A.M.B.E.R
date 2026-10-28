# If something breaks (don't panic)

Hi. If you're reading this, something probably looked scary. Take a breath. You
almost certainly did NOT break anything important, and you do NOT need to know
any code to fix it. This page walks you through it like a friend sitting next
to you.

## The two golden rules

**Rule 1: You're never stuck alone.**
Whatever the screen says, you can copy that text, send it to whoever helps you
with the tool (or open an issue on the GitHub page), and say "this happened, help." Describing the problem in plain words is
all the skill you need. The fixing part is not yours to carry.

**Rule 2: Your backup is your undo button.**
Keep a spare copy of the whole `C.H.A.M.B.E.R` folder somewhere safe (a USB
stick, OneDrive, Google Drive). If anything ever gets truly messed up, you
delete the broken one and copy the backup back. Done. Instant fresh start, zero
knowledge required. If you haven't made that backup yet, do it now and the rest
of this page becomes "just in case."

## A calming fact

This tool does not change on its own. No internet, no auto-updates, nothing
reaching in to mess with it. If it worked yesterday, it will work today. Most
"breaks" are really just a file that got moved or renamed, which is easy to undo.

---

## The usual suspects (and their easy fixes)

### "Windows protected your PC" (blue box)
Not a break. Windows is just being cautious because the app isn't signed.
Click **More info**, then **Run anyway**. Safe to do.

### The app won't open, or opens and instantly closes
First try: just build it again. Double-click **`build_all.bat`**, wait for DONE,
then open `dist\CHAMBER.exe` again. A fresh build cures most things.

### A rebuild (build_all.bat) fails partway
1. Delete the folder named **`.venv_build`** inside `C.H.A.M.B.E.R`
   (it's just temporary build stuff, totally safe to delete).
2. Double-click **`build_all.bat`** again.
That clears out a half-finished build and starts clean.

### "Python was not found" during a build
You only need Python on the computer where you BUILD. Reinstall Python 3.12 from
python.org and tick **"Add python.exe to PATH"** on the first screen. Then build
again. (Computers that only RUN the finished .exe never need Python.)

### One PDF failed but the others worked
That's normal, not a break. The tool flags the odd sheet and keeps going. Open
the `_report.csv` in the output folder and look at the `qc` column to see which
one and why. The good sheets are all fine.

### My Shapefile / GeoPackage files didn't appear
Make sure those boxes were ticked before you hit Run. If they were ticked and
still nothing showed up, check the log for `SHP_FAILED` or `GPKG_FAILED` and
report that line (open an issue on the GitHub page). It's an easy fix.

### The window looks odd, laggy or see-through in a strange way
That's the glass blur not agreeing with this PC's graphics. Open the
**Settings** tab, untick **"Glass blur behind the window"**, close the app and
open it again. It switches to a plain dark glass look that works everywhere.

### The app looks frozen during a big batch
Give it a moment. Big folders or high `--jobs` take time, and the window can
look still while it's working hard. The progress bar and the log will catch up.

### Something lost track of my folder / files look "gone"
Almost always a rename or move. Your files are still on the disk. In the app,
just Browse to where they actually are now. (This exact thing happened once
during setup and everything was fine.)

---

## The nuclear option (when in doubt)

If you ever feel like it's all gone sideways:
1. Delete the messy `C.H.A.M.B.E.R` folder.
2. Copy your backup `C.H.A.M.B.E.R` folder back in its place.
3. Double-click `build_all.bat` once.
You're back to a known-good tool. This works no matter what went wrong.

---

## How to ask for help (the magic move)

When something shows an error:
1. Select the text (or take a screenshot, or even snap a photo of the screen).
2. Send it to whoever helps you with the tool (or open an issue on GitHub) with a sentence like: "I ran X, then this showed up."
3. That's it. You'll get a plain steps-to-fix back.

You do not need to understand the error. You just need to pass it along.

---

## One last thing

You built this. It's yours, it's offline, it's safe, and it's backed up. Breaking
it in a way that can't be undone is genuinely hard to do. So go use it without
fear, and if it ever hiccups, this page (and a quick message for help) has you.

You've got this.
