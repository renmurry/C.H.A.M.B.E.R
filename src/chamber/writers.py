"""Output writers: GeoJSON (target CRS), KML (WGS84), GeoTIFF (target CRS)."""
from __future__ import annotations
import json
from pathlib import Path
from shapely.geometry import mapping


def write_geojson(path, poly, epsg, props):
    fc = {"type": "FeatureCollection",
          "crs": {"type": "name", "properties": {"name": f"urn:ogc:def:crs:EPSG::{epsg}"}},
          "features": [{"type": "Feature", "properties": props, "geometry": mapping(poly)}]}
    Path(path).write_text(json.dumps(fc, indent=2), encoding="utf-8")


def _xml_escape(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _extended_data(props):
    """KML ExtendedData table (shows in the Google Earth balloon)."""
    if not props:
        return ""
    skip = {"source_crs_wkt", "geometry"}
    rows = []
    for k, v in props.items():
        if k in skip or v in ("", None):
            continue
        rows.append(f'<Data name="{_xml_escape(k)}"><value>{_xml_escape(v)}</value></Data>')
    return "<ExtendedData>" + "".join(rows) + "</ExtendedData>" if rows else ""


def write_kml(path, lonlat, name, props=None):
    ring = list(lonlat) + [lonlat[0]]
    coords = " ".join(f"{lo},{la},0" for lo, la in ring)
    kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>{_xml_escape(name)}</name>
<Style><LineStyle><color>ff00aaff</color><width>2</width></LineStyle>
<PolyStyle><fill>0</fill></PolyStyle></Style>
{_extended_data(props)}
<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords}</coordinates>
</LinearRing></outerBoundaryIs></Polygon></Placemark>
</Document></kml>"""
    # always UTF-8: Windows would otherwise use cp1252 and crash on any
    # non-Latin character (the KML header already promises UTF-8)
    Path(path).write_text(kml, encoding="utf-8")


def write_geotiff(path, img, bbox, affine, epsg):
    import rasterio
    from rasterio.transform import from_gcps
    from rasterio.control import GroundControlPoint as GCP
    from pyproj import Transformer
    H, W = img.shape[:2]
    bx0, by0, bx1, by1 = bbox
    tr = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    gcps = []
    for col, row, xp, yp in [(0, 0, bx0, by1), (W, 0, bx1, by1),
                             (W, H, bx1, by0), (0, H, bx0, by0)]:
        lo, la = affine(xp, yp)
        x, y = tr.transform(lo, la)
        gcps.append(GCP(row, col, x, y))
    transform = from_gcps(gcps)
    profile = dict(driver="GTiff", height=H, width=W, count=3, dtype=img.dtype,
                   crs=f"EPSG:{epsg}", transform=transform, compress="deflate")
    with rasterio.open(path, "w", **profile) as dst:
        for i in range(3):
            dst.write(img[:, :, i], i + 1)


def write_debug(path, img, pixel_pts):
    import cv2
    ov = img.copy()
    cv2.drawContours(ov, [pixel_pts.reshape(-1, 1, 2)], -1, (255, 0, 0), 3)
    cv2.imwrite(str(path), ov)


# --- extra vector formats via pyogrio (Shapefile, GeoPackage, DXF) ---

# format key -> (OGR driver, file extension). geojson/kml stay on the custom
# writers above; these three go through OGR.
OGR_FORMATS = {
    "shp":  ("ESRI Shapefile", ".shp"),
    "gpkg": ("GPKG", ".gpkg"),
    "dxf":  ("DXF", ".dxf"),
}

# shapefile field names cap at 10 chars, so keep these short
def _attr_arrays(props_list):
    import numpy as np
    cols = [("sheet_id", object), ("method", object), ("crs", object),
            ("vertices", "i4"), ("area_m2", "f8"), ("area_ha", "f8"),
            ("perim_m", "f8"), ("qc", object)]
    src = {"perim_m": "perimeter_m"}
    if props_list and "block_label" in props_list[0]:      # OCR fields present
        from . import ocr as OCR
        for key in OCR.OCR_FIELDS:
            short = OCR.SHP_NAMES[key]
            dt = "f8" if key == "label_conf" else ("i4" if key == "id_match" else object)
            cols.append((short, dt)); src[short] = key
    fields, data = [], []
    for name, dt in cols:
        key = src.get(name, name)
        if dt is object:
            data.append(np.array([str(p.get(key, "")) for p in props_list], dtype=object))
        else:
            data.append(np.array([p.get(key, 0) for p in props_list], dtype=dt))
        fields.append(name)
    return fields, data


def write_vector(path, polys, props_list, epsg, driver):
    """Write one or more polygons to an OGR format (Shapefile/GeoPackage/DXF)."""
    import numpy as np, shapely
    from pyogrio.raw import write
    geometry = np.array([shapely.to_wkb(g) for g in polys], dtype=object)
    crs = f"EPSG:{epsg}"
    if driver == "DXF":
        # the DXF driver has a fixed schema and rejects custom fields
        write(str(path), geometry=geometry, field_data=[], fields=[],
              driver="DXF", geometry_type="Polygon", crs=crs)
        return
    fields, field_data = _attr_arrays(props_list)
    write(str(path), geometry=geometry, field_data=field_data, fields=fields,
          driver=driver, geometry_type="MultiPolygon", crs=crs, promote_to_multi=True)
