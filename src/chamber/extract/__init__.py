"""Interactive feature extraction: open a sheet, image or GeoTIFF, click
features, get GIS layers.

source   - opens any input and works out where its pixels sit on the ground
gridref  - places a sheet from the grid labels printed around its map frame
pdfvec   - the lines and shapes drawn inside a PDF, grouped by style
labels   - text printed on the map, as points
sam      - click / box / +- points -> outline (MobileSAM, run with onnxruntime)
shapes   - outlines to clean polygons, squaring up buildings, snapping lines
similar  - "find similar": more features that look like the ones you kept
session  - the layers you are building, undo, and export
"""
