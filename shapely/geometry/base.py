"""Base geometry class and utilities

Note: a third, z, coordinate value may be used when constructing
geometry objects, but has no effect on geometric analysis. All
operations are performed in the x-y plane. Thus, geometries with
different z values may intersect or be equal.
"""
import math
from itertools import islice
from warnings import warn

import shapely
from shapely.affinity import affine_transform
from shapely.coords import CoordinateSequence
from shapely.errors import GeometryTypeError, GEOSException, ShapelyDeprecationWarning

try:
    import numpy as np

    integer_types = (int, np.integer)
except ImportError:
    integer_types = (int,)


GEOMETRY_TYPES = [
    "Point",
    "LineString",
    "LinearRing",
    "Polygon",
    "MultiPoint",
    "MultiLineString",
    "MultiPolygon",
    "GeometryCollection",
]


def dump_coords(geom):
    """Dump coordinates of a geometry in the same order as data packing"""
    if not isinstance(geom, BaseGeometry):
        raise ValueError(
            "Must be instance of a geometry class; found " + geom.__class__.__name__
        )
    elif geom.type in ("Point", "LineString", "LinearRing"):
        return geom.coords[:]
    elif geom.type == "Polygon":
        return geom.exterior.coords[:] + [i.coords[:] for i in geom.interiors]
    elif geom.type.startswith("Multi") or geom.type == "GeometryCollection":
        # Recursive call
        return [dump_coords(part) for part in geom.geoms]
    else:
        raise GeometryTypeError("Unhandled geometry type: " + repr(geom.type))


class CAP_STYLE:
    round = 1
    flat = 2
    square = 3


class JOIN_STYLE:
    round = 1
    mitre = 2
    bevel = 3


class BaseGeometry(shapely.Geometry):
    """
    Provides GEOS spatial predicates and topological operations.

    """

    __slots__ = []

    def __new__(self):
        warn(
            "Directly calling the base class 'BaseGeometry()' is deprecated, and "
            "will raise an error in the future. To create an empty geometry, "
            "use one of the subclasses instead, for example 'GeometryCollection()'.",
            ShapelyDeprecationWarning,
            stacklevel=2,
        )
        return shapely.from_wkt("GEOMETRYCOLLECTION EMPTY")

    @property
    def _ndim(self):
        return shapely.get_coordinate_dimension(self)

    def __bool__(self):
        return self.is_empty is False

    def __nonzero__(self):
        return self.__bool__()

    def __repr__(self):
        try:
            wkt = super().__str__()
        except (GEOSException, ValueError):
            # we never want a repr() to fail; that can be very confusing
            return "<shapely.{} Exception in WKT writer>".format(
                self.__class__.__name__
            )

        # the total length is limited to 80 characters including brackets
        max_length = 78
        if len(wkt) > max_length:
            return "<{}...>".format(wkt[: max_length - 3])

        return "<{}>".format(wkt)

    def __str__(self):
        return self.wkt

    def __reduce__(self):
        return (shapely.from_wkb, (shapely.to_wkb(self, include_srid=True),))

    # Operators
    # ---------

    def __and__(self, other):
        return self.intersection(other)

    def __or__(self, other):
        return self.union(other)

    def __sub__(self, other):
        return self.difference(other)

    def __xor__(self, other):
        return self.symmetric_difference(other)

    # Coordinate access
    # -----------------

    @property
    def coords(self):
        """Access to geometry's coordinates (CoordinateSequence)"""
        coords_array = shapely.get_coordinates(self, include_z=self.has_z)
        return CoordinateSequence(coords_array)

    @property
    def xy(self):
        """Separate arrays of X and Y coordinate values"""
        raise NotImplementedError

    # Python feature protocol

    @property
    def __geo_interface__(self):
        """Dictionary representation of the geometry"""
        raise NotImplementedError

    # Type of geometry and its representations
    # ----------------------------------------

    def geometryType(self):
        warn(
            "The 'GeometryType()' method is deprecated, and will be removed in "
            "the future. You can use the 'geom_type' attribute instead.",
            ShapelyDeprecationWarning,
            stacklevel=2,
        )
        return self.geom_type

    @property
    def type(self):
        return self.geom_type

    @property
    def wkt(self):
        """WKT representation of the geometry"""
        # TODO(shapely-2.0) keep default of not trimming?
        return shapely.to_wkt(self, rounding_precision=-1)

    @property
    def wkb(self):
        """WKB representation of the geometry"""
        return shapely.to_wkb(self)

    @property
    def wkb_hex(self):
        """WKB hex representation of the geometry"""
        return shapely.to_wkb(self, hex=True)

    def svg(self, scale_factor=1.0, **kwargs):
        """Raises NotImplementedError"""
        raise NotImplementedError

    def _repr_svg_(self):
        """SVG representation for iPython notebook"""
        svg_top = (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink" '
        )
        if self.is_empty:
            return svg_top + "/>"
        else:
            # Establish SVG canvas that will fit all the data + small space
            xmin, ymin, xmax, ymax = self.bounds
            if xmin == xmax and ymin == ymax:
                # This is a point; buffer using an arbitrary size
                xmin, ymin, xmax, ymax = self.buffer(1).bounds
            else:
                # Expand bounds by a fraction of the data ranges
                expand = 0.04  # or 4%, same as R plots
                widest_part = max([xmax - xmin, ymax - ymin])
                expand_amount = widest_part * expand
                xmin -= expand_amount
                ymin -= expand_amount
                xmax += expand_amount
                ymax += expand_amount
            dx = xmax - xmin
            dy = ymax - ymin
            width = min([max([100.0, dx]), 300])
            height = min([max([100.0, dy]), 300])
            try:
                scale_factor = max([dx, dy]) / max([width, height])
            except ZeroDivisionError:
                scale_factor = 1.0
            view_box = "{} {} {} {}".format(xmin, ymin, dx, dy)
            transform = "matrix(1,0,0,-1,0,{})".format(ymax + ymin)
            return svg_top + (
                'width="{1}" height="{2}" viewBox="{0}" '
                'preserveAspectRatio="xMinYMin meet">'
                '<g transform="{3}">{4}</g></svg>'
            ).format(view_box, width, height, transform, self.svg(scale_factor))

    @property
    def geom_type(self):
        """Name of the geometry's type, such as 'Point'"""
        return GEOMETRY_TYPES[shapely.get_type_id(self)]

    # Real-valued properties and methods
    # ----------------------------------

    @property
    def area(self):
        """Unitless area of the geometry (float)"""
        return float(shapely.area(self))

    def distance(self, other):
        """Unitless distance to other geometry (float)"""
        return float(shapely.distance(self, other))

    def hausdorff_distance(self, other):
        """Unitless hausdorff distance to other geometry (float)"""
        return float(shapely.hausdorff_distance(self, other))

    @property
    def length(self):
        """Unitless length of the geometry (float)"""
        return float(shapely.length(self))

    @property
    def minimum_clearance(self):
        """Unitless distance by which a node could be moved to produce an invalid geometry (float)"""
        return float(shapely.minimum_clearance(self))

    # Topological properties
    # ----------------------

    @property
    def boundary(self):
        """Returns a lower dimension geometry that bounds the object

        The boundary of a polygon is a line, the boundary of a line is a
        collection of points. The boundary of a point is an empty (null)
        collection.
        """
        return shapely.boundary(self)

    @property
    def bounds(self):
        """Returns minimum bounding region (minx, miny, maxx, maxy)"""
        return tuple(shapely.bounds(self).tolist())

    @property
    def centroid(self):
        """Returns the geometric center of the object"""
        return shapely.centroid(self)

    def point_on_surface(self):
        """Returns a point guaranteed to be within the object, cheaply.

        Alias of `representative_point`.
        """
        return shapely.point_on_surface(self)

    def representative_point(self):
        """Returns a point guaranteed to be within the object, cheaply.

        Alias of `point_on_surface`.
        """
        return shapely.point_on_surface(self)

    @property
    def convex_hull(self):
        """Imagine an elastic band stretched around the geometry: that's a
        convex hull, more or less

        The convex hull of a three member multipoint, for example, is a
        triangular polygon.
        """
        return shapely.convex_hull(self)

    @property
    def envelope(self):
        """A figure that envelopes the geometry"""
        return shapely.envelope(self)

    @property
    def minimum_rotated_rectangle(self):
        """Returns the general minimum bounding rectangle of
        the geometry. Can possibly be rotated. If the convex hull
        of the object is a degenerate (line or point) this same degenerate
        is returned.
        """
        # first compute the convex hull
        hull = self.convex_hull
        try:
            coords = hull.exterior.coords
        except AttributeError:  # may be a Point or a LineString
            return hull
        # generate the edge vectors between the convex hull's coords
        edges = (
            (pt2[0] - pt1[0], pt2[1] - pt1[1])
            for pt1, pt2 in zip(coords, islice(coords, 1, None))
        )

        def _transformed_rects():
            for dx, dy in edges:
                # compute the normalized direction vector of the edge
                # vector.
                length = math.sqrt(dx**2 + dy**2)
                ux, uy = dx / length, dy / length
                # compute the normalized perpendicular vector
                vx, vy = -uy, ux
                # transform hull from the original coordinate system to
                # the coordinate system defined by the edge and compute
                # the axes-parallel bounding rectangle.
                transf_rect = affine_transform(hull, (ux, uy, vx, vy, 0, 0)).envelope
                # yield the transformed rectangle and a matrix to
                # transform it back to the original coordinate system.
                yield (transf_rect, (ux, vx, uy, vy, 0, 0))

        # check for the minimum area rectangle and return it
        transf_rect, inv_matrix = min(_transformed_rects(), key=lambda r: r[0].area)
        return affine_transform(transf_rect, inv_matrix)

    def buffer(
        self,
        distance,
        resolution=16,
        quadsegs=None,
        cap_style=CAP_STYLE.round,
        join_style=JOIN_STYLE.round,
        mitre_limit=5.0,
        single_sided=False,
    ):
        """Get a geometry that represents all points within a distance
        of this geometry.

        A positive distance produces a dilation, a negative distance an
        erosion. A very small or zero distance may sometimes be used to
        "tidy" a polygon.

        Parameters
        ----------
        distance : float
            The distance to buffer around the object.
        resolution : int, optional
            The resolution of the buffer around each vertex of the
            object.
        quadsegs : int, optional
            Sets the number of line segments used to approximate an
            angle fillet.  Note: the use of a `quadsegs` parameter is
            deprecated and will be gone from the next major release.
        cap_style : int, optional
            The styles of caps are: CAP_STYLE.round (1), CAP_STYLE.flat
            (2), and CAP_STYLE.square (3).
        join_style : int, optional
            The styles of joins between offset segments are:
            JOIN_STYLE.round (1), JOIN_STYLE.mitre (2), and
            JOIN_STYLE.bevel (3).
        mitre_limit : float, optional
            The mitre limit ratio is used for very sharp corners. The
            mitre ratio is the ratio of the distance from the corner to
            the end of the mitred offset corner. When two line segments
            meet at a sharp angle, a miter join will extend the original
            geometry. To prevent unreasonable geometry, the mitre limit
            allows controlling the maximum length of the join corner.
            Corners with a ratio which exceed the limit will be beveled.
        single_side : bool, optional
            The side used is determined by the sign of the buffer
            distance:

                a positive distance indicates the left-hand side
                a negative distance indicates the right-hand side

            The single-sided buffer of point geometries is the same as
            the regular buffer.  The End Cap Style for single-sided
            buffers is always ignored, and forced to the equivalent of
            CAP_FLAT.

        Returns
        -------
        Geometry

        Notes
        -----
        The return value is a strictly two-dimensional geometry. All
        Z coordinates of the original geometry will be ignored.

        Examples
        --------
        >>> from shapely.wkt import loads
        >>> g = loads('POINT (0.0 0.0)')
        >>> g.buffer(1.0).area        # 16-gon approx of a unit radius circle
        3.1365484905459...
        >>> g.buffer(1.0, 128).area   # 128-gon approximation
        3.141513801144...
        >>> g.buffer(1.0, 3).area     # triangle approximation
        3.0
        >>> list(g.buffer(1.0, cap_style=CAP_STYLE.square).exterior.coords)
        [(1.0, 1.0), (1.0, -1.0), (-1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)]
        >>> g.buffer(1.0, cap_style=CAP_STYLE.square).area
        4.0

        """
        if quadsegs is not None:
            warn(
                "The `quadsegs` argument is deprecated. Use `resolution`.",
                DeprecationWarning,
            )
            resolution = quadsegs

        if mitre_limit == 0.0:
            raise ValueError("Cannot compute offset from zero-length line segment")

        return shapely.buffer(
            self,
            distance,
            quadsegs=resolution,
            cap_style=cap_style,
            join_style=join_style,
            mitre_limit=mitre_limit,
            single_sided=single_sided,
        )

    def simplify(self, tolerance, preserve_topology=True):
        """Returns a simplified geometry produced by the Douglas-Peucker
        algorithm

        Coordinates of the simplified geometry will be no more than the
        tolerance distance from the original. Unless the topology preserving
        option is used, the algorithm may produce self-intersecting or
        otherwise invalid geometries.
        """
        return shapely.simplify(self, tolerance, preserve_topology=preserve_topology)

    def normalize(self):
        """Converts geometry to normal form (or canonical form).

        This method orders the coordinates, rings of a polygon and parts of
        multi geometries consistently. Typically useful for testing purposes
        (for example in combination with `equals_exact`).

        Examples
        --------
        >>> from shapely.wkt import loads
        >>> p = loads("MULTILINESTRING((0 0, 1 1), (3 3, 2 2))")
        >>> p.normalize().wkt
        'MULTILINESTRING ((2 2, 3 3), (0 0, 1 1))'
        """
        return shapely.normalize(self)

    # Binary operations
    # -----------------

    def difference(self, other):
        """Returns the difference of the geometries"""
        return shapely.difference(self, other)

    def intersection(self, other):
        """Returns the intersection of the geometries"""
        return shapely.intersection(self, other)

    def symmetric_difference(self, other):
        """Returns the symmetric difference of the geometries
        (Shapely geometry)"""
        return shapely.symmetric_difference(self, other)

    def union(self, other):
        """Returns the union of the geometries (Shapely geometry)"""
        return shapely.union(self, other)

    # Unary predicates
    # ----------------

    @property
    def has_z(self):
        """True if the geometry's coordinate sequence(s) have z values (are
        3-dimensional)"""
        return bool(shapely.has_z(self))

    @property
    def is_empty(self):
        """True if the set of points in this geometry is empty, else False"""
        return bool(shapely.is_empty(self))

    @property
    def is_ring(self):
        """True if the geometry is a closed ring, else False"""
        return bool(shapely.is_ring(self))

    @property
    def is_closed(self):
        """True if the geometry is closed, else False

        Applicable only to 1-D geometries."""
        if self.geom_type == "LinearRing":
            return True
        return bool(shapely.is_closed(self))

    @property
    def is_simple(self):
        """True if the geometry is simple, meaning that any self-intersections
        are only at boundary points, else False"""
        return bool(shapely.is_simple(self))

    @property
    def is_valid(self):
        """True if the geometry is valid (definition depends on sub-class),
        else False"""
        return bool(shapely.is_valid(self))

    # Binary predicates
    # -----------------

    def relate(self, other):
        """Returns the DE-9IM intersection matrix for the two geometries
        (string)"""
        return shapely.relate(self, other)

    def covers(self, other):
        """Returns True if the geometry covers the other, else False"""
        return bool(shapely.covers(self, other))

    def covered_by(self, other):
        """Returns True if the geometry is covered by the other, else False"""
        return bool(shapely.covered_by(self, other))

    def contains(self, other):
        """Returns True if the geometry contains the other, else False"""
        return bool(shapely.contains(self, other))

    def crosses(self, other):
        """Returns True if the geometries cross, else False"""
        return bool(shapely.crosses(self, other))

    def disjoint(self, other):
        """Returns True if geometries are disjoint, else False"""
        return bool(shapely.disjoint(self, other))

    def equals(self, other):
        """Returns True if geometries are equal, else False.

        This method considers point-set equality (or topological
        equality), and is equivalent to (self.within(other) &
        self.contains(other)).

        Examples
        --------
        >>> LineString(
        ...     [(0, 0), (2, 2)]
        ... ).equals(
        ...     LineString([(0, 0), (1, 1), (2, 2)])
        ... )
        True

        Returns
        -------
        bool

        """
        return bool(shapely.equals(self, other))

    def intersects(self, other):
        """Returns True if geometries intersect, else False"""
        return bool(shapely.intersects(self, other))

    def overlaps(self, other):
        """Returns True if geometries overlap, else False"""
        return bool(shapely.overlaps(self, other))

    def touches(self, other):
        """Returns True if geometries touch, else False"""
        return bool(shapely.touches(self, other))

    def within(self, other):
        """Returns True if geometry is within the other, else False"""
        return bool(shapely.within(self, other))

    def equals_exact(self, other, tolerance):
        """True if geometries are equal to within a specified
        tolerance.

        Parameters
        ----------
        other : BaseGeometry
            The other geometry object in this comparison.
        tolerance : float
            Absolute tolerance in the same units as coordinates.

        This method considers coordinate equality, which requires
        coordinates to be equal and in the same order for all components
        of a geometry.

        Because of this it is possible for "equals()" to be True for two
        geometries and "equals_exact()" to be False.

        Examples
        --------
        >>> LineString(
        ...     [(0, 0), (2, 2)]
        ... ).equals_exact(
        ...     LineString([(0, 0), (1, 1), (2, 2)]),
        ...     1e-6
        ... )
        False

        Returns
        -------
        bool

        """
        return bool(shapely.equals_exact(self, other, tolerance))

    def almost_equals(self, other, decimal=6):
        """True if geometries are equal at all coordinates to a
        specified decimal place.

        .. deprecated:: 1.8.0 The 'almost_equals()' method is deprecated
            and will be removed in Shapely 2.0 because the name is
            confusing. The 'equals_exact()' method should be used
            instead.

        Refers to approximate coordinate equality, which requires
        coordinates to be approximately equal and in the same order for
        all components of a geometry.

        Because of this it is possible for "equals()" to be True for two
        geometries and "almost_equals()" to be False.

        Examples
        --------
        >>> LineString(
        ...     [(0, 0), (2, 2)]
        ... ).equals_exact(
        ...     LineString([(0, 0), (1, 1), (2, 2)]),
        ...     1e-6
        ... )
        False

        Returns
        -------
        bool

        """
        warn(
            "The 'almost_equals()' method is deprecated and will be removed in Shapely 2.0",
            ShapelyDeprecationWarning,
            stacklevel=2,
        )
        return self.equals_exact(other, 0.5 * 10 ** (-decimal))

    def relate_pattern(self, other, pattern):
        """Returns True if the DE-9IM string code for the relationship between
        the geometries satisfies the pattern, else False"""
        return bool(shapely.relate_pattern(self, other, pattern))

    # Linear referencing
    # ------------------

    def line_locate_point(self, other, normalized=False):
        """Returns the distance along this geometry to a point nearest the
        specified point

        If the normalized arg is True, return the distance normalized to the
        length of the linear geometry.

        Alias of `project`.
        """
        return shapely.line_locate_point(self, other, normalized=normalized)

    def project(self, other, normalized=False):
        """Returns the distance along this geometry to a point nearest the
        specified point

        If the normalized arg is True, return the distance normalized to the
        length of the linear geometry.

        Alias of `line_locate_point`.
        """
        return shapely.line_locate_point(self, other, normalized=normalized)

    def line_interpolate_point(self, distance, normalized=False):
        """Return a point at the specified distance along a linear geometry

        Negative length values are taken as measured in the reverse
        direction from the end of the geometry. Out-of-range index
        values are handled by clamping them to the valid range of values.
        If the normalized arg is True, the distance will be interpreted as a
        fraction of the geometry's length.

        Alias of `interpolate`.
        """
        return shapely.line_interpolate_point(self, distance, normalized=normalized)

    def interpolate(self, distance, normalized=False):
        """Return a point at the specified distance along a linear geometry

        Negative length values are taken as measured in the reverse
        direction from the end of the geometry. Out-of-range index
        values are handled by clamping them to the valid range of values.
        If the normalized arg is True, the distance will be interpreted as a
        fraction of the geometry's length.

        Alias of `line_interpolate_point`.
        """
        return shapely.line_interpolate_point(self, distance, normalized=normalized)


class BaseMultipartGeometry(BaseGeometry):

    __slots__ = []

    @property
    def coords(self):
        raise NotImplementedError(
            "Sub-geometries may have coordinate sequences, "
            "but multi-part geometries do not"
        )

    @property
    def geoms(self):
        return GeometrySequence(self)

    def __bool__(self):
        return self.is_empty is False

    def svg(self, scale_factor=1.0, color=None):
        """Returns a group of SVG elements for the multipart geometry.

        Parameters
        ==========
        scale_factor : float
            Multiplication factor for the SVG stroke-width.  Default is 1.
        color : str, optional
            Hex string for stroke or fill color. Default is to use "#66cc99"
            if geometry is valid, and "#ff3333" if invalid.
        """
        if self.is_empty:
            return "<g />"
        if color is None:
            color = "#66cc99" if self.is_valid else "#ff3333"
        return "<g>" + "".join(p.svg(scale_factor, color) for p in self.geoms) + "</g>"


class GeometrySequence:
    """
    Iterative access to members of a homogeneous multipart geometry.
    """

    # Attributes
    # ----------
    # __p__ : object
    #     Parent (Shapely) geometry
    __p__ = None

    def __init__(self, parent):
        self.__p__ = parent

    def _get_geom_item(self, i):
        return shapely.get_geometry(self.__p__, i)

    def __iter__(self):
        for i in range(self.__len__()):
            yield self._get_geom_item(i)

    def __len__(self):
        return shapely.get_num_geometries(self.__p__)

    def __getitem__(self, key):
        m = self.__len__()
        if isinstance(key, integer_types):
            if key + m < 0 or key >= m:
                raise IndexError("index out of range")
            if key < 0:
                i = m + key
            else:
                i = key
            return self._get_geom_item(i)
        elif isinstance(key, slice):
            res = []
            start, stop, stride = key.indices(m)
            for i in range(start, stop, stride):
                res.append(self._get_geom_item(i))
            return type(self.__p__)(res or None)
        else:
            raise TypeError("key must be an index or slice")


class EmptyGeometry(BaseGeometry):
    def __new__(self):
        """Create an empty geometry."""
        warn(
            "The 'EmptyGeometry()' constructor to create an empty geometry is "
            "deprecated, and will raise an error in the future. Use one of the "
            "geometry subclasses instead, for example 'GeometryCollection()'.",
            ShapelyDeprecationWarning,
            stacklevel=2,
        )
        return shapely.from_wkt("GEOMETRYCOLLECTION EMPTY")
