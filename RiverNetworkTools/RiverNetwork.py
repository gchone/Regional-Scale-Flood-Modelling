from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from .geometry import Coordinate, LineFeature, PointFeature, TopologyLink, ensure_line_feature, ensure_links


class BrowsingStopper:
    def __init__(self) -> None:
        self.break_generator = False


@dataclass(frozen=True)
class SavedVariable:
    name: str
    dtype: str
    field_name: str
    max_length: int | None = None


class _SavedVariablesMixin:
    def __init__(self) -> None:
        self._saved_variables: dict[str, SavedVariable] = {}

    def get_saved_variables(self) -> set[str]:
        return set(self._saved_variables.keys())

    def add_saved_variable(
        self,
        name: str,
        dtype: str,
        max_length: int | None = None,
        field_name: str | None = None,
    ) -> None:
        if field_name is None:
            field_name = name
        if dtype not in {"int", "float", "str"}:
            raise TypeError("dtype must be 'int', 'float', or 'str'.")
        if dtype == "str" and max_length is None:
            raise TypeError("max_length is required for string saved variables.")
        self._saved_variables[name] = SavedVariable(name, dtype, field_name, max_length)

    def delete_saved_variable(self, name: str) -> None:
        del self._saved_variables[name]

    def get_SavedVariables(self) -> set[str]:
        return self.get_saved_variables()

    def add_SavedVariable(
        self,
        name: str,
        dtype: str,
        maxlength: int | None = None,
        fieldname: str | None = None,
    ) -> None:
        self.add_saved_variable(name, dtype, maxlength, fieldname)

    def delete_SavedVariable(self, name: str) -> None:
        self.delete_saved_variable(name)


class RiverNetwork(_SavedVariablesMixin):
    LINKS_UP_FIELD = "UpID"
    LINKS_DOWN_FIELD = "DownID"
    reaches_linkfieldup = LINKS_UP_FIELD
    reaches_linkfielddown = LINKS_DOWN_FIELD

    dict_attr_fields = {
        "id": "RID",
        "length": "length",
    }

    def __init__(self) -> None:
        super().__init__()
        self.points_collections: dict[str, PointsCollection] = {}
        self.points_collection = self.points_collections
        self.dict_attr_fields = RiverNetwork.dict_attr_fields.copy()
        self._reaches: dict[int, Reach] = {}
        self._links_down: dict[int, int] = {}
        self._links_up: dict[int, list[int]] = defaultdict(list)
        self.reaches: list[Reach] = []

    def load_data(
        self,
        reaches: Iterable[LineFeature | dict[str, Any]],
        reaches_linktable: Iterable[TopologyLink | tuple[int, int] | dict[str, Any]],
        load_secondary_channel: bool = False,
    ) -> None:
        self._reaches = {}
        self._links_down = {}
        self._links_up = defaultdict(list)
        self.reaches = []

        main_field = self.dict_attr_fields.get("main")
        valid_ids: set[int] = set()
        for raw_feature in reaches:
            feature = ensure_line_feature(raw_feature)
            rid = int(feature.attributes[self.dict_attr_fields["id"]])
            if main_field is not None and not load_secondary_channel:
                if int(feature.attributes.get(main_field, 0)) == 0:
                    continue
            reach = Reach(self, feature, rid)
            self._reaches[rid] = reach
            self.reaches.append(reach)
            valid_ids.add(rid)

        for link in ensure_links(
            reaches_linktable,
            down_field=self.reaches_linkfielddown,
            up_field=self.reaches_linkfieldup,
        ):
            down_id = int(link.downstream_id)
            up_id = int(link.upstream_id)
            if up_id not in valid_ids or down_id not in valid_ids:
                continue
            self._links_down[up_id] = down_id
            self._links_up[down_id].append(up_id)

    def get_downstream_ends(self):
        for reach in self.reaches:
            if reach.id not in self._links_down:
                yield reach

    def get_upstream_ends(self):
        for reach in self.reaches:
            if not self._links_up.get(reach.id):
                yield reach

    def browse_reaches_down_to_up(
        self,
        prioritize_points_collection: "PointsCollection | None" = None,
        prioritize_points_attribute: str | None = None,
        prioritize_reach_attribute: str | None = None,
        reverse: bool = False,
    ):
        for downstream_end in self.get_downstream_ends():
            for item in self._browse_reaches_down_to_up_recursive(
                downstream_end,
                prioritize_points_collection,
                prioritize_points_attribute,
                prioritize_reach_attribute,
                reverse,
            ):
                yield item

    def _browse_reaches_down_to_up_recursive(
        self,
        current_reach: "Reach",
        prioritize_points_collection: "PointsCollection | None",
        prioritize_points_attribute: str | None,
        prioritize_reach_attribute: str | None,
        reverse: bool,
    ):
        yield current_reach
        upstream_list = list(current_reach.get_upstream_reaches())
        if prioritize_points_collection is not None and prioritize_points_attribute is not None:
            upstream_list.sort(
                key=lambda reach: getattr(
                    reach.get_first_point(prioritize_points_collection),
                    prioritize_points_attribute,
                ),
                reverse=reverse,
            )
        elif prioritize_reach_attribute is not None:
            upstream_list.sort(
                key=lambda reach: getattr(reach, prioritize_reach_attribute),
                reverse=reverse,
            )
        for reach in upstream_list:
            for item in self._browse_reaches_down_to_up_recursive(
                reach,
                prioritize_points_collection,
                prioritize_points_attribute,
                prioritize_reach_attribute,
                reverse,
            ):
                yield item

    def browse_reaches_up_to_down(
        self,
        stopper: BrowsingStopper | None = None,
        prioritize_reach_attribute: str | None = None,
        reverse: bool = False,
    ):
        if stopper is None:
            stopper = BrowsingStopper()
        upstream_ends = list(self.get_upstream_ends())
        if prioritize_reach_attribute is not None:
            upstream_ends.sort(
                key=lambda reach: getattr(reach, prioritize_reach_attribute),
                reverse=reverse,
            )
        for upstream_end in upstream_ends:
            stopper.break_generator = False
            current_reach = upstream_end
            while current_reach is not None:
                if stopper.break_generator:
                    break
                yield current_reach
                current_reach = current_reach.get_downstream_reach()

    def get_reach(self, reach_id: int) -> "Reach":
        return self._reaches[int(reach_id)]

    def order_reaches_by_discharge(self, collection: "PointsCollection", discharge_name: str) -> None:
        order = 0
        for reach in self.browse_reaches_down_to_up(
            prioritize_points_collection=collection,
            prioritize_points_attribute=discharge_name,
            reverse=True,
        ):
            reach.order = order
            order += 1

    def place_points_at_regular_interval(self, interval: float, collection: "PointsCollection") -> None:
        if interval <= 0:
            raise ValueError("interval must be strictly positive.")
        if collection._points:
            raise ValueError("collection must be empty before placing points.")
        point_id = 1
        for reach in self.browse_reaches_down_to_up():
            distance = 0.0
            while distance < reach.length:
                point = DataPoint(collection, reach, point_id, distance)
                collection._register_point(point)
                point_id += 1
                distance += interval

    def placePointsAtRegularInterval(self, interval: float, collection: "PointsCollection") -> None:
        self.place_points_at_regular_interval(interval, collection)

    def __str__(self) -> str:
        for downstream_end in self.get_downstream_ends():
            return downstream_end._recursive_print("")
        return ""


class Reach:
    def __init__(self, river_network: RiverNetwork, feature: LineFeature, rid: int) -> None:
        self.river_network = river_network
        self.rivernetwork = river_network
        self.feature = feature
        self.shape = feature
        self.id = int(rid)
        self.order = None
        self.length = float(feature.length())
        for attr, field_name in river_network.dict_attr_fields.items():
            if attr == "length":
                setattr(self, attr, self.length)
            elif field_name in feature.attributes:
                setattr(self, attr, feature.attributes[field_name])

    def get_downstream_reach(self) -> "Reach | None":
        down_id = self.river_network._links_down.get(self.id)
        if down_id is None:
            return None
        return self.river_network.get_reach(down_id)

    def get_upstream_reaches(self):
        for reach_id in self.river_network._links_up.get(self.id, []):
            yield self.river_network.get_reach(reach_id)

    def get_uptream_reaches(self):
        for reach in self.get_upstream_reaches():
            yield reach

    def is_downstream_end(self) -> bool:
        return self.get_downstream_reach() is None

    def is_upstream_end(self) -> bool:
        return len(list(self.get_upstream_reaches())) == 0

    def browse_points(
        self,
        collection: "PointsCollection",
        orientation: str = "DOWN_TO_UP",
        stopper: BrowsingStopper | None = None,
    ):
        if stopper is not None and stopper.break_generator:
            return
        points = sorted(
            collection._points_by_reach.get(self.id, []),
            key=lambda point: point.dist,
            reverse=(orientation == "UP_TO_DOWN"),
        )
        for point in points:
            yield point

    def get_last_point(self, collection: "PointsCollection") -> "DataPoint | None":
        points = collection._points_by_reach.get(self.id, [])
        if not points:
            return None
        return max(points, key=lambda point: point.dist)

    def get_first_point(self, collection: "PointsCollection") -> "DataPoint | None":
        points = collection._points_by_reach.get(self.id, [])
        if not points:
            return None
        return min(points, key=lambda point: point.dist)

    def get_point(
        self,
        distance: float,
        collection: "PointsCollection",
        tolerance: float = 0.01,
    ) -> "DataPoint | None":
        for point in collection._points_by_reach.get(self.id, []):
            if abs(point.dist - distance) < tolerance:
                return point
        return None

    def add_point(self, distance: float, collection: "PointsCollection") -> "DataPoint":
        new_id = max(collection._points.keys(), default=0) + 1
        point = DataPoint(collection, self, new_id, distance)
        collection._register_point(point)
        return point

    def is_upstream(self, reach: "Reach") -> bool:
        for upstream_reach in self.get_upstream_reaches():
            if upstream_reach._recursive_is_upstream(reach):
                return True
        return False

    def _recursive_is_upstream(self, reach: "Reach") -> bool:
        if self.id == reach.id:
            return True
        for upstream_reach in self.get_upstream_reaches():
            if upstream_reach._recursive_is_upstream(reach):
                return True
        return False

    def is_downstream(self, reach: "Reach") -> bool:
        downstream_reach = self.get_downstream_reach()
        if downstream_reach is None:
            return False
        return downstream_reach._recursive_is_downstream(reach)

    def _recursive_is_downstream(self, reach: "Reach") -> bool:
        if self.id == reach.id:
            return True
        downstream_reach = self.get_downstream_reach()
        if downstream_reach is None:
            return False
        return downstream_reach._recursive_is_downstream(reach)

    def _recursive_print(self, prefix: str) -> str:
        string_value = prefix + str(self) + "\n"
        for child in self.get_upstream_reaches():
            string_value += child._recursive_print(prefix + "- ")
        return string_value

    def __str__(self) -> str:
        return str(self.id)


class PointsCollection(_SavedVariablesMixin):
    dict_attr_fields = {
        "id": "id",
        "reach_id": "RID",
        "dist": "MEAS",
    }

    def __init__(self, river_network: RiverNetwork, name: str) -> None:
        super().__init__()
        self.river_network = river_network
        self.rivernetwork = river_network
        self.name = name
        self.dict_attr_fields = PointsCollection.dict_attr_fields.copy()
        self._points: dict[int, DataPoint] = {}
        self._points_by_reach: dict[int, list[DataPoint]] = defaultdict(list)
        river_network.points_collections[name] = self

    def _register_point(self, point: "DataPoint") -> None:
        self._points[point.id] = point
        self._points_by_reach[point.reach.id].append(point)

    def load_table(self, points_table: Iterable[PointFeature | dict[str, Any]]) -> None:
        self._points = {}
        self._points_by_reach = defaultdict(list)
        for row in points_table:
            if isinstance(row, PointFeature):
                values = dict(row.attributes)
            else:
                values = dict(row)
            point_id = int(values[self.dict_attr_fields["id"]])
            reach_id = int(values[self.dict_attr_fields["reach_id"]])
            distance = float(values[self.dict_attr_fields["dist"]])
            reach = self.river_network.get_reach(reach_id)
            extra = {}
            for attr, field_name in self.dict_attr_fields.items():
                if attr in {"id", "reach_id", "dist"}:
                    continue
                if field_name in values:
                    extra[attr] = values[field_name]
            point = DataPoint(self, reach, point_id, distance, **extra)
            self._register_point(point)

    def delete_point(self, datapoint: "DataPoint") -> None:
        self._points.pop(datapoint.id, None)
        self._points_by_reach[datapoint.reach.id] = [
            point
            for point in self._points_by_reach.get(datapoint.reach.id, [])
            if point.id != datapoint.id
        ]

    def to_table_rows(self, dict_attr_output_fields: dict[str, str] | None = None) -> list[dict[str, Any]]:
        if dict_attr_output_fields is None:
            dict_attr_output_fields = self.dict_attr_fields.copy()
            for name, saved_variable in self._saved_variables.items():
                dict_attr_output_fields[name] = saved_variable.field_name
        if "id" not in dict_attr_output_fields:
            raise RuntimeError("'id' field is required")
        rows: list[dict[str, Any]] = []
        for point in sorted(self._points.values(), key=lambda item: item.id):
            row: dict[str, Any] = {}
            for attr, field_name in dict_attr_output_fields.items():
                if attr == "reach_id":
                    row[field_name] = point.reach.id
                else:
                    row[field_name] = getattr(point, attr)
            rows.append(row)
        return rows

    def save_points(
        self,
        target: Any = None,
        dict_attr_output_fields: dict[str, str] | None = None,
        writer: Any = None,
    ):
        rows = self.to_table_rows(dict_attr_output_fields)
        if writer is None:
            if target is not None:
                raise ValueError("writer is required when target is provided.")
            return rows
        writer.write_rows(target, rows)
        return target


class Points_collection(PointsCollection):
    pass


class DataPoint:
    def __init__(
        self,
        points_collection: PointsCollection,
        reach: Reach,
        pt_id: int,
        dist: float,
        **kwargs: Any,
    ) -> None:
        self.points_collection = points_collection
        self.reach = reach
        self.id = int(pt_id)
        self.dist = float(dist)
        for key, value in kwargs.items():
            setattr(self, key, value)

    @property
    def X(self) -> float | None:
        value = self.__dict__.get("_X")
        if value is not None:
            return value
        coordinate = self.reach.feature.interpolate(self.dist)
        return coordinate.x

    @X.setter
    def X(self, value: float) -> None:
        self.__dict__["_X"] = value

    @property
    def Y(self) -> float | None:
        value = self.__dict__.get("_Y")
        if value is not None:
            return value
        coordinate = self.reach.feature.interpolate(self.dist)
        return coordinate.y

    @Y.setter
    def Y(self, value: float) -> None:
        self.__dict__["_Y"] = value

    def as_feature(self, attribute_names: Iterable[str] | None = None) -> PointFeature:
        if attribute_names is None:
            attribute_names = []
        attributes = {"id": self.id}
        for name in attribute_names:
            attributes[name] = getattr(self, name)
        return PointFeature(attributes=attributes, point=Coordinate(self.X, self.Y))

    def __str__(self) -> str:
        return f"DataPoint(id={self.id}, reach={self.reach.id}, dist={self.dist})"
