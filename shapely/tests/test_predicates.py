from functools import partial

import numpy as np
import pytest

import shapely
from shapely import Geometry

from .common import (
    all_types,
    empty,
    geometry_collection,
    ignore_invalid,
    line_string,
    linear_ring,
    point,
    polygon,
)

UNARY_PREDICATES = (
    shapely.is_empty,
    shapely.is_simple,
    shapely.is_ring,
    shapely.is_closed,
    shapely.is_valid,
    shapely.is_missing,
    shapely.is_geometry,
    shapely.is_valid_input,
    shapely.is_prepared,
    pytest.param(
        shapely.is_ccw,
        marks=pytest.mark.skipif(shapely.geos_version < (3, 7, 0), reason="GEOS < 3.7"),
    ),
)

BINARY_PREDICATES = (
    shapely.disjoint,
    shapely.touches,
    shapely.intersects,
    shapely.crosses,
    shapely.within,
    shapely.contains,
    shapely.contains_properly,
    shapely.overlaps,
    shapely.covers,
    shapely.covered_by,
    pytest.param(
        partial(shapely.dwithin, distance=1.0),
        marks=pytest.mark.skipif(
            shapely.geos_version < (3, 10, 0), reason="GEOS < 3.10"
        ),
    ),
    shapely.equals,
    shapely.equals_exact,
)

BINARY_PREPARED_PREDICATES = BINARY_PREDICATES[:-2]


@pytest.mark.parametrize("geometry", all_types)
@pytest.mark.parametrize("func", UNARY_PREDICATES)
def test_unary_array(geometry, func):
    actual = func([geometry, geometry])
    assert actual.shape == (2,)
    assert actual.dtype == np.bool_


@pytest.mark.parametrize("func", UNARY_PREDICATES)
def test_unary_with_kwargs(func):
    out = np.empty((), dtype=np.uint8)
    actual = func(point, out=out)
    assert actual is out
    assert actual.dtype == np.uint8


@pytest.mark.parametrize("func", UNARY_PREDICATES)
def test_unary_missing(func):
    if func in (shapely.is_valid_input, shapely.is_missing):
        assert func(None)
    else:
        assert not func(None)


@pytest.mark.parametrize("a", all_types)
@pytest.mark.parametrize("func", BINARY_PREDICATES)
def test_binary_array(a, func):
    with ignore_invalid(shapely.is_empty(a)):
        # Empty geometries give 'invalid value encountered' in all predicates
        # (see https://github.com/libgeos/geos/issues/515)
        actual = func([a, a], point)
    assert actual.shape == (2,)
    assert actual.dtype == np.bool_


@pytest.mark.parametrize("func", BINARY_PREDICATES)
def test_binary_with_kwargs(func):
    out = np.empty((), dtype=np.uint8)
    actual = func(point, point, out=out)
    assert actual is out
    assert actual.dtype == np.uint8


@pytest.mark.parametrize("func", BINARY_PREDICATES)
def test_binary_missing(func):
    actual = func(np.array([point, None, None]), np.array([None, point, None]))
    assert (~actual).all()


def test_equals_exact_tolerance():
    # specifying tolerance
    p1 = shapely.points(50, 4)
    p2 = shapely.points(50.1, 4.1)
    actual = shapely.equals_exact([p1, p2, None], p1, tolerance=0.05)
    np.testing.assert_allclose(actual, [True, False, False])
    assert actual.dtype == np.bool_
    actual = shapely.equals_exact([p1, p2, None], p1, tolerance=0.2)
    np.testing.assert_allclose(actual, [True, True, False])
    assert actual.dtype == np.bool_

    # default value for tolerance
    assert shapely.equals_exact(p1, p1).item() is True
    assert shapely.equals_exact(p1, p2).item() is False

    # an array of tolerances
    actual = shapely.equals_exact(p1, p2, tolerance=[0.05, 0.2, np.nan])
    np.testing.assert_allclose(actual, [False, True, False])


@pytest.mark.skipif(shapely.geos_version < (3, 10, 0), reason="GEOS < 3.10")
def test_dwithin():
    p1 = shapely.points(50, 4)
    p2 = shapely.points(50.1, 4.1)
    actual = shapely.dwithin([p1, p2, None], p1, distance=0.05)
    np.testing.assert_equal(actual, [True, False, False])
    assert actual.dtype == np.bool_
    actual = shapely.dwithin([p1, p2, None], p1, distance=0.2)
    np.testing.assert_allclose(actual, [True, True, False])
    assert actual.dtype == np.bool_

    # an array of distances
    actual = shapely.dwithin(p1, p2, distance=[0.05, 0.2, np.nan])
    np.testing.assert_allclose(actual, [False, True, False])


@pytest.mark.parametrize(
    "geometry,expected",
    [
        (point, False),
        (line_string, False),
        (linear_ring, True),
        (empty, False),
    ],
)
def test_is_closed(geometry, expected):
    assert shapely.is_closed(geometry) == expected


def test_relate():
    p1 = shapely.points(0, 0)
    p2 = shapely.points(1, 1)
    actual = shapely.relate(p1, p2)
    assert isinstance(actual, str)
    assert actual == "FF0FFF0F2"


@pytest.mark.parametrize("g1, g2", [(point, None), (None, point), (None, None)])
def test_relate_none(g1, g2):
    assert shapely.relate(g1, g2) is None


def test_relate_pattern():
    g = shapely.linestrings([(0, 0), (1, 0), (1, 1)])
    polygon = shapely.box(0, 0, 2, 2)
    assert shapely.relate(g, polygon) == "11F00F212"
    assert shapely.relate_pattern(g, polygon, "11F00F212")
    assert shapely.relate_pattern(g, polygon, "*********")
    assert not shapely.relate_pattern(g, polygon, "F********")


def test_relate_pattern_empty():
    with ignore_invalid():
        # Empty geometries give 'invalid value encountered' in all predicates
        # (see https://github.com/libgeos/geos/issues/515)
        assert shapely.relate_pattern(empty, empty, "*" * 9).item() is True


@pytest.mark.parametrize("g1, g2", [(point, None), (None, point), (None, None)])
def test_relate_pattern_none(g1, g2):
    assert shapely.relate_pattern(g1, g2, "*" * 9).item() is False


def test_relate_pattern_incorrect_length():
    with pytest.raises(shapely.GEOSException, match="Should be length 9"):
        shapely.relate_pattern(point, polygon, "**")

    with pytest.raises(shapely.GEOSException, match="Should be length 9"):
        shapely.relate_pattern(point, polygon, "**********")


@pytest.mark.parametrize("pattern", [b"*********", 10, None])
def test_relate_pattern_non_string(pattern):
    with pytest.raises(TypeError, match="expected string"):
        shapely.relate_pattern(point, polygon, pattern)


def test_relate_pattern_non_scalar():
    with pytest.raises(ValueError, match="only supports scalar"):
        shapely.relate_pattern([point] * 2, polygon, ["*********"] * 2)


@pytest.mark.skipif(shapely.geos_version < (3, 7, 0), reason="GEOS < 3.7")
@pytest.mark.parametrize(
    "geom, expected",
    [
        (Geometry("LINEARRING (0 0, 0 1, 1 1, 0 0)"), False),
        (Geometry("LINEARRING (0 0, 1 1, 0 1, 0 0)"), True),
        (Geometry("LINESTRING (0 0, 0 1, 1 1, 0 0)"), False),
        (Geometry("LINESTRING (0 0, 1 1, 0 1, 0 0)"), True),
        (Geometry("LINESTRING (0 0, 1 1, 0 1)"), False),
        (Geometry("LINESTRING (0 0, 0 1, 1 1)"), False),
        (point, False),
        (polygon, False),
        (geometry_collection, False),
        (None, False),
    ],
)
def test_is_ccw(geom, expected):
    assert shapely.is_ccw(geom) == expected


def _prepare_with_copy(geometry):
    """Prepare without modifying inplace"""
    geometry = shapely.transform(geometry, lambda x: x)  # makes a copy
    shapely.prepare(geometry)
    return geometry


@pytest.mark.parametrize("a", all_types)
@pytest.mark.parametrize("func", BINARY_PREPARED_PREDICATES)
def test_binary_prepared(a, func):
    with ignore_invalid(shapely.is_empty(a)):
        # Empty geometries give 'invalid value encountered' in all predicates
        # (see https://github.com/libgeos/geos/issues/515)
        actual = func(a, point)
        result = func(_prepare_with_copy(a), point)
    assert actual == result


@pytest.mark.parametrize("geometry", all_types + (empty,))
def test_is_prepared_true(geometry):
    assert shapely.is_prepared(_prepare_with_copy(geometry))


@pytest.mark.parametrize("geometry", all_types + (empty, None))
def test_is_prepared_false(geometry):
    assert not shapely.is_prepared(geometry)


def test_contains_properly():
    # polygon contains itself, but does not properly contains itself
    assert shapely.contains(polygon, polygon).item() is True
    assert shapely.contains_properly(polygon, polygon).item() is False
