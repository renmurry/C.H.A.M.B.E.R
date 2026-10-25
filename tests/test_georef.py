import numpy as np
from chamber.georef import utm_epsg, _affine_from_corners, pixel_to_page


def test_utm_epsg_north_zone36():
    assert utm_epsg(31.24, 26.66) == 32636        # sample_A

def test_utm_epsg_other_zones():
    assert utm_epsg(-122.4, 37.8) == 32610         # San Francisco
    assert utm_epsg(151.2, -33.9) == 32756         # Sydney (southern)

def test_affine_recovers_linear_map():
    # page corners and a known linear page->lonlat mapping
    page = [(0, 0), (0, 100), (100, 100), (100, 0)]
    geo = [(10 + 0.001 * x, 50 + 0.002 * y) for x, y in page]
    aff = _affine_from_corners(page, geo)
    for (x, y), (lo, la) in zip(page, geo):
        glo, gla = aff(x, y)
        assert abs(glo - lo) < 1e-9 and abs(gla - la) < 1e-9

def test_pixel_to_page_orientation():
    bbox = [100, 200, 300, 600]      # x0,y0,x1,y1
    # image top row (py=0) maps to high y (north); bottom to low y
    assert pixel_to_page(0, 0, 100, 100, bbox) == (100, 600)
    assert pixel_to_page(100, 100, 100, 100, bbox) == (300, 200)
