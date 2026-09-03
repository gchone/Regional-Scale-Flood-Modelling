from __future__ import annotations

from typing import Any, Iterable

from .RiverNetwork import PointsCollection, Reach, RiverNetwork, _SavedVariablesMixin
from .TreeTools import create_full_tree_table_from_features
from .geometry import FullTopologyLink, LineFeature, ensure_line_feature


class FullReach(Reach):
    def get_upstream_next_points(self, collection: PointsCollection):
        return self._get_next_points(collection, direction="upstream", visited=set())

    def get_downstream_next_points(self, collection: PointsCollection):
        return self._get_next_points(collection, direction="downstream", visited=set())

    def get_upstreamnextpts(self, collection: PointsCollection):
        return self.get_upstream_next_points(collection)

    def get_downstreamnextpts(self, collection: PointsCollection):
        return self.get_downstream_next_points(collection)

    def _get_next_points(
        self,
        collection: PointsCollection,
        direction: str,
        visited: set[tuple[str, int]],
    ):
        state = (direction, self.id)
        if state in visited:
            return []
        visited.add(state)
        results = []
        network = self.rivernetwork

        for link in network._links_by_first.get(self.id, []):
            connected = network.get_reach(link.reach_id_2)
            if direction == "upstream":
                if link.orientation == "END-TO-START":
                    point = connected.get_first_point(collection)
                    if point is not None:
                        results.append(point)
                    else:
                        results.extend(connected._get_next_points(collection, "upstream", visited))
                elif link.orientation == "END-TO-END":
                    point = connected.get_last_point(collection)
                    if point is not None:
                        results.append(point)
                    else:
                        results.extend(connected._get_next_points(collection, "downstream", visited))
            else:
                if link.orientation == "START-TO-START":
                    point = connected.get_first_point(collection)
                    if point is not None:
                        results.append(point)
                    else:
                        results.extend(connected._get_next_points(collection, "upstream", visited))
                elif link.orientation == "START-TO-END":
                    point = connected.get_last_point(collection)
                    if point is not None:
                        results.append(point)
                    else:
                        results.extend(connected._get_next_points(collection, "downstream", visited))

        for link in network._links_by_second.get(self.id, []):
            connected = network.get_reach(link.reach_id_1)
            if direction == "upstream":
                if link.orientation == "START-TO-END":
                    point = connected.get_first_point(collection)
                    if point is not None:
                        results.append(point)
                    else:
                        results.extend(connected._get_next_points(collection, "upstream", visited))
                elif link.orientation == "END-TO-END":
                    point = connected.get_last_point(collection)
                    if point is not None:
                        results.append(point)
                    else:
                        results.extend(connected._get_next_points(collection, "downstream", visited))
            else:
                if link.orientation == "START-TO-START":
                    point = connected.get_first_point(collection)
                    if point is not None:
                        results.append(point)
                    else:
                        results.extend(connected._get_next_points(collection, "upstream", visited))
                elif link.orientation == "END-TO-START":
                    point = connected.get_last_point(collection)
                    if point is not None:
                        results.append(point)
                    else:
                        results.extend(connected._get_next_points(collection, "downstream", visited))
        return results


class FullRiverNetwork(_SavedVariablesMixin):
    IDlink1name = "RID1"
    IDlink2name = "RID2"
    IDlink_orientationname = "Orientation"

    dict_attr_fields = {
        "id": "RID",
        "length": "length",
        "main": "Main",
    }

    def __init__(self) -> None:
        super().__init__()
        self.points_collections: dict[str, PointsCollection] = {}
        self.points_collection = self.points_collections
        self.dict_attr_fields = FullRiverNetwork.dict_attr_fields.copy()
        self._reaches: dict[int, FullReach] = {}
        self._links: list[FullTopologyLink] = []
        self._links_by_first: dict[int, list[FullTopologyLink]] = {}
        self._links_by_second: dict[int, list[FullTopologyLink]] = {}
        self.reaches: list[FullReach] = []

    def load_data(self, reaches: Iterable[LineFeature | dict[str, Any]]) -> None:
        features = [ensure_line_feature(feature) for feature in reaches]
        self._reaches = {}
        self.reaches = []
        for feature in features:
            rid = int(feature.attributes[self.dict_attr_fields["id"]])
            reach = FullReach(self, feature, rid)
            self._reaches[rid] = reach
            self.reaches.append(reach)
        self._links = create_full_tree_table_from_features(features, self.dict_attr_fields["id"])
        self._links_by_first = {}
        self._links_by_second = {}
        for link in self._links:
            self._links_by_first.setdefault(link.reach_id_1, []).append(link)
            self._links_by_second.setdefault(link.reach_id_2, []).append(link)

    def get_reach(self, reach_id: int) -> FullReach:
        return self._reaches[int(reach_id)]
