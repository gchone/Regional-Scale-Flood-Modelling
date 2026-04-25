from pathlib import Path
import sys
from collections import defaultdict

sys.path.append(str(Path(__file__).resolve().parents[1]))


# =============================================================================
# Helpers
# =============================================================================

class BrowsingStopper:
    """
    Passed as an argument to generators when browsing points from upstream to
    downstream. Setting break_generator = True stops the current path traversal.
    """

    def __init__(self):
        self.break_generator = False


# =============================================================================
# RiverNetwork
# =============================================================================

class RiverNetwork:
    """
    Lightweight port of the ArcGIS RiverNetwork class.

    Replaces numpy structured arrays with plain Python dicts and lists.
    Accepts QgsVectorLayer objects instead of ArcGIS feature classes.

    Orientation convention: reaches are oriented downstream→upstream
    (first vertex = outlet end, last vertex = headwater end).
    Links table uses DownID / UpID field names.
    """

    LINKS_DOWN_FIELD = "DownID"
    LINKS_UP_FIELD   = "UpID"

    def __init__(self):
        self._reaches            = {}                  # RID (int) -> Reach
        self._links_down         = {}                  # upRID -> downRID
        self._links_up           = defaultdict(list)   # downRID -> [upRID, ...]
        self.points_collections  = {}                  # name -> PointsCollection
        self.rid_field           = "RID"
        self.crs                 = None

    def load_data(self, routes, links, rid_field="RID"):
        """
        Build network topology from a QgsVectorLayer (routes) and a
        QgsFeatureSource (links table).

        Args:
            routes    : QgsVectorLayer (lines) — oriented route network
            links     : QgsVectorLayer or QgsFeatureSource — DownID/UpID link table
            rid_field : str — RouteID field name (default "RID")
        """
        self.rid_field = rid_field
        self.crs       = routes.sourceCrs()

        for f in routes.getFeatures():
            rid = f[rid_field]
            if rid is None:
                continue
            self._reaches[int(rid)] = Reach(self, f, int(rid))

        for f in links.getFeatures():
            down_id = f[self.LINKS_DOWN_FIELD]
            up_id   = f[self.LINKS_UP_FIELD]
            if down_id is None or up_id is None:
                continue
            down_id = int(down_id)
            up_id   = int(up_id)
            self._links_down[up_id] = down_id
            self._links_up[down_id].append(up_id)

    def get_reach(self, rid):
        """Return the Reach object for a given RID."""
        return self._reaches.get(int(rid))

    def get_downstream_ends(self):
        """
        Generator. Yields reaches that have no downstream neighbour
        (not present as an UpID in the links table).
        """
        for rid, reach in self._reaches.items():
            if rid not in self._links_down:
                yield reach

    def get_upstream_ends(self):
        """
        Generator. Yields reaches that have no upstream neighbours
        (not present as a DownID in the links table).
        """
        for rid, reach in self._reaches.items():
            if not self._links_up.get(rid):
                yield reach

    def browse_reaches_down_to_up(
        self,
        prioritize_points_collection=None,
        prioritize_points_attribute=None,
        prioritize_reach_attribute=None,
        reverse=False,
    ):
        """
        Generator. Yields reaches from downstream to upstream using an
        iterative stack to avoid Python recursion limits on large watersheds.

        At confluences, if prioritize_points_collection is provided, upstream
        reaches are sorted by the value of prioritize_points_attribute on their
        most downstream point in that collection (highest first if reverse=True).

        Args:
            prioritize_points_collection : PointsCollection or None
            prioritize_points_attribute  : str — DataPoint attribute name
            prioritize_reach_attribute   : str — Reach attribute name
            reverse                      : bool — if True, highest value first
        """
        for downstream_end in self.get_downstream_ends():
            stack = [downstream_end]
            while stack:
                current = stack.pop()
                yield current

                upstream_list = list(current.get_upstream_reaches())

                if prioritize_points_collection is not None:
                    def sort_key(r, col=prioritize_points_collection,
                                 attr=prioritize_points_attribute):
                        pt = r.get_first_point(col)
                        if pt is None:
                            return float('-inf') if reverse else float('inf')
                        return getattr(pt, attr)
                    upstream_list.sort(key=sort_key, reverse=not reverse)

                elif prioritize_reach_attribute is not None:
                    upstream_list.sort(
                        key=lambda r: getattr(r, prioritize_reach_attribute),
                        reverse=not reverse,
                    )

                else:
                    upstream_list.reverse()

                stack.extend(upstream_list)

    def browse_reaches_up_to_down(
        self,
        stopper=None,
        prioritize_reach_attribute=None,
        reverse=False,
    ):
        """
        Generator. Yields reaches from upstream to downstream using an
        iterative stack.

        Args:
            stopper                    : BrowsingStopper or None
            prioritize_reach_attribute : str — Reach attribute to sort upstream ends by
            reverse                    : bool
        """
        if stopper is None:
            stopper = BrowsingStopper()

        upstream_ends = list(self.get_upstream_ends())
        if prioritize_reach_attribute is not None:
            upstream_ends.sort(
                key=lambda r: getattr(r, prioritize_reach_attribute),
                reverse=reverse,
            )

        for upstream_end in upstream_ends:
            stopper.break_generator = False
            stack = [upstream_end]
            while stack:
                if stopper.break_generator:
                    break
                current = stack.pop()
                yield current
                down = current.get_downstream_reach()
                if down is not None:
                    stack.append(down)

    def order_reaches_by_discharge(self, collection, discharge_attribute):
        """
        Traverse the network downstream→upstream, visiting tributaries in
        descending order of flow accumulation at their most downstream point.
        Assigns an incrementing integer 'order' attribute to each reach.

        Mirrors ArcGIS RiverNetwork.order_reaches_by_discharge().

        Args:
            collection           : PointsCollection — flow accumulation points
            discharge_attribute  : str — DataPoint attribute holding the
                                   flow accumulation value
        """
        order = 0
        for reach in self.browse_reaches_down_to_up(
            prioritize_points_collection=collection,
            prioritize_points_attribute=discharge_attribute,
            reverse=True,
        ):
            reach.order = order
            order += 1

    def place_points_at_regular_interval(self, interval, collection):
        """
        Place DataPoints at a regular interval along each reach.
        The collection must already exist but must be empty.

        Args:
            interval   : float — spacing between points in CRS units
            collection : PointsCollection — target collection (must be empty)
        """
        pt_id = 0
        for reach in self.browse_reaches_down_to_up():
            geom   = reach.feature.geometry()
            length = geom.length()
            dist   = 0.0
            while dist < length:
                pt_id += 1
                pt = DataPoint(
                    points_collection=collection,
                    reach=reach,
                    pt_id=pt_id,
                    dist=dist,
                )
                collection._points[pt_id] = pt
                collection._points_by_reach[reach.id].append(pt)
                dist += interval


# =============================================================================
# Reach
# =============================================================================

class Reach:
    """
    Represents a single reach in the river network.

    Mirrors the ArcGIS Reach class but stores attributes as plain Python
    instance variables rather than numpy array rows.
    """

    def __init__(self, river_network, feature, rid):
        """
        Args:
            river_network : RiverNetwork — parent network
            feature       : QgsFeature — the reach feature
            rid           : int — RouteID
        """
        self.river_network = river_network
        self.feature       = feature
        self.id            = rid
        self.order         = None  # set by order_reaches_by_discharge()

        for field in feature.fields():
            name = field.name()
            setattr(self, name, feature[name])

    def get_downstream_reach(self):
        """Return the downstream Reach, or None if this is the outlet."""
        down_rid = self.river_network._links_down.get(self.id)
        if down_rid is None:
            return None
        return self.river_network._reaches.get(down_rid)

    def get_upstream_reaches(self):
        """Generator. Yields all directly upstream Reach objects."""
        for up_rid in self.river_network._links_up.get(self.id, []):
            reach = self.river_network._reaches.get(up_rid)
            if reach is not None:
                yield reach

    def is_downstream_end(self):
        """True if this reach has no downstream neighbour."""
        return self.get_downstream_reach() is None

    def is_upstream_end(self):
        """True if this reach has no upstream neighbours."""
        return not bool(self.river_network._links_up.get(self.id))

    def browse_points(self, collection, orientation="DOWN_TO_UP", stopper=None):
        """
        Generator. Yields DataPoints on this reach sorted by dist.

        Args:
            collection  : PointsCollection
            orientation : "DOWN_TO_UP" (ascending dist) or "UP_TO_DOWN" (descending)
            stopper     : BrowsingStopper or None
        """
        if stopper is not None and stopper.break_generator:
            return

        pts = sorted(
            collection._points_by_reach.get(self.id, []),
            key=lambda p: p.dist,
            reverse=(orientation == "UP_TO_DOWN"),
        )
        for pt in pts:
            yield pt

    def get_first_point(self, collection):
        """
        Return the DataPoint with the smallest dist on this reach
        (most downstream point), or None if no points exist.
        """
        pts = collection._points_by_reach.get(self.id, [])
        if not pts:
            return None
        return min(pts, key=lambda p: p.dist)

    def get_last_point(self, collection):
        """
        Return the DataPoint with the largest dist on this reach
        (most upstream point), or None if no points exist.
        """
        pts = collection._points_by_reach.get(self.id, [])
        if not pts:
            return None
        return max(pts, key=lambda p: p.dist)

    def get_point(self, distance, collection, tolerance=0.01):
        """Return the DataPoint closest to distance within tolerance, or None."""
        for pt in collection._points_by_reach.get(self.id, []):
            if abs(pt.dist - distance) < tolerance:
                return pt
        return None

    def add_point(self, distance, collection):
        """
        Add a new DataPoint at the given distance along this reach.
        Returns the new DataPoint.
        """
        new_id = max(collection._points.keys(), default=0) + 1
        pt = DataPoint(
            points_collection=collection,
            reach=self,
            pt_id=new_id,
            dist=distance,
        )
        collection._points[new_id] = pt
        collection._points_by_reach[self.id].append(pt)
        return pt

    def is_upstream(self, reach):
        """True if reach is upstream of self."""
        visited = set()
        stack   = list(self.get_upstream_reaches())
        while stack:
            current = stack.pop()
            if current.id in visited:
                continue
            visited.add(current.id)
            if current.id == reach.id:
                return True
            stack.extend(current.get_upstream_reaches())
        return False

    def is_downstream(self, reach):
        """True if reach is downstream of self."""
        current = self.get_downstream_reach()
        visited = set()
        while current is not None:
            if current.id in visited:
                break
            visited.add(current.id)
            if current.id == reach.id:
                return True
            current = current.get_downstream_reach()
        return False

    def __str__(self):
        return str(self.id)


# =============================================================================
# PointsCollection
# =============================================================================

class PointsCollection:
    """
    A collection of DataPoints associated with a RiverNetwork.

    Mirrors the ArcGIS Points_collection class but uses plain Python dicts
    instead of numpy structured arrays.

    dict_attr_fields maps logical attribute names to the field names used
    when loading from a QgsFeatureSource:
        'id'       -> point ID field name
        'reach_id' -> RID field name
        'dist'     -> distance field name

    Additional entries (e.g. 'X', 'Y', 'discharge') can be added before
    calling load_table().
    """

    def __init__(self, river_network, name):
        """
        Args:
            river_network : RiverNetwork — parent network
            name          : str — collection name
        """
        self.river_network    = river_network
        self.name             = name
        self._points          = {}                   # pt_id (int) -> DataPoint
        self._points_by_reach = defaultdict(list)    # rid -> [DataPoint, ...]
        self.dict_attr_fields = {
            "id":       "id",
            "reach_id": "RID",
            "dist":     "dist",
        }
        river_network.points_collections[name] = self

    def load_table(self, source):
        """
        Load points from a QgsFeatureSource.

        All fields listed in dict_attr_fields must exist in the source.

        Args:
            source : QgsVectorLayer or QgsFeatureSource
        """
        id_field       = self.dict_attr_fields["id"]
        reach_id_field = self.dict_attr_fields["reach_id"]
        dist_field     = self.dict_attr_fields["dist"]

        for f in source.getFeatures():
            pt_id = int(f[id_field])
            rid   = int(f[reach_id_field])
            dist  = float(f[dist_field])

            reach = self.river_network._reaches.get(rid)
            if reach is None:
                continue

            extra = {}
            for attr, field in self.dict_attr_fields.items():
                if attr in ("id", "reach_id", "dist"):
                    continue
                val = f[field]
                extra[attr] = float(val) if val is not None else None

            pt = DataPoint(
                points_collection=self,
                reach=reach,
                pt_id=pt_id,
                dist=dist,
                **extra,
            )
            self._points[pt_id] = pt
            self._points_by_reach[rid].append(pt)

    def delete_point(self, datapoint):
        """Remove a DataPoint from the collection."""
        self._points.pop(datapoint.id, None)
        self._points_by_reach[datapoint.reach.id] = [
            p for p in self._points_by_reach.get(datapoint.reach.id, [])
            if p.id != datapoint.id
        ]

    def save_points(self, target_layer, dict_attr_output_fields=None):
        """
        Save points to a QgsVectorLayer (memory layer).

        Args:
            target_layer            : QgsVectorLayer (memory, writable)
            dict_attr_output_fields : dict mapping attr name -> field name,
                                      or None to save all fields in
                                      dict_attr_fields
        """
        if dict_attr_output_fields is None:
            dict_attr_output_fields = self.dict_attr_fields.copy()

        pr = target_layer.dataProvider()
        for pt in self._points.values():
            f = QgsFeature(target_layer.fields())
            for attr, field in dict_attr_output_fields.items():
                val = getattr(pt, attr, None)
                if val is not None:
                    f.setAttribute(field, val)
            pr.addFeature(f)


# =============================================================================
# DataPoint
# =============================================================================

class DataPoint:
    """
    A point located along a reach at a given distance.

    Mirrors the ArcGIS DataPoint class but stores attributes as plain
    Python instance variables.

    Any extra keyword arguments passed to __init__ are set as attributes,
    allowing flexible attribute storage (e.g. X, Y, discharge, flowacc).
    """

    def __init__(self, points_collection, reach, pt_id, dist, **kwargs):
        """
        Args:
            points_collection : PointsCollection — parent collection
            reach             : Reach — the reach this point lies on
            pt_id             : int — unique point ID
            dist              : float — distance along reach from downstream end
            **kwargs          : any additional attributes (e.g. X=, Y=, discharge=)
        """
        self.points_collection = points_collection
        self.reach             = reach
        self.id                = pt_id
        self.dist              = dist

        for key, val in kwargs.items():
            setattr(self, key, val)

    def __str__(self):
        return f"DataPoint(id={self.id}, reach={self.reach.id}, dist={self.dist:.2f})"