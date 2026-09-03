from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable


@dataclass(frozen=True)
class Coordinate:
    x: float
    y: float
    m: float | None = None


@dataclass
class PointFeature:
    attributes: dict[str, Any]
    point: Coordinate

    @property
    def x(self) -> float:
        return self.point.x

    @property
    def y(self) -> float:
        return self.point.y


@dataclass
class LineFeature:
    attributes: dict[str, Any]
    vertices: list[Coordinate] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.vertices = list(self.vertices)
        if len(self.vertices) < 2:
            raise ValueError("LineFeature requires at least two vertices.")

    @property
    def start_point(self) -> Coordinate:
        return self.vertices[0]

    @property
    def end_point(self) -> Coordinate:
        return self.vertices[-1]

    def reversed(self) -> "LineFeature":
        return LineFeature(
            attributes=dict(self.attributes),
            vertices=list(reversed(self.vertices)),
        )

    def length(self) -> float:
        total = 0.0
        for start, end in zip(self.vertices[:-1], self.vertices[1:]):
            total += math.hypot(end.x - start.x, end.y - start.y)
        return total

    def with_m_values(self, start_m: float = 0.0) -> "LineFeature":
        m_value = float(start_m)
        vertices: list[Coordinate] = []
        for index, point in enumerate(self.vertices):
            if index > 0:
                previous = self.vertices[index - 1]
                m_value += math.hypot(point.x - previous.x, point.y - previous.y)
            vertices.append(Coordinate(point.x, point.y, m_value))
        return LineFeature(attributes=dict(self.attributes), vertices=vertices)

    def interpolate(self, distance: float) -> Coordinate:
        if distance <= 0:
            first = self.vertices[0]
            return Coordinate(first.x, first.y, first.m)
        remaining = float(distance)
        for start, end in zip(self.vertices[:-1], self.vertices[1:]):
            segment_length = math.hypot(end.x - start.x, end.y - start.y)
            if segment_length == 0:
                continue
            if remaining <= segment_length:
                ratio = remaining / segment_length
                x_value = start.x + ratio * (end.x - start.x)
                y_value = start.y + ratio * (end.y - start.y)
                return Coordinate(x_value, y_value)
            remaining -= segment_length
        last = self.vertices[-1]
        return Coordinate(last.x, last.y, last.m)

    def centroid(self) -> Coordinate:
        x_values = [point.x for point in self.vertices]
        y_values = [point.y for point in self.vertices]
        return Coordinate(sum(x_values) / len(x_values), sum(y_values) / len(y_values))


@dataclass(frozen=True)
class TopologyLink:
    downstream_id: int
    upstream_id: int


@dataclass(frozen=True)
class FullTopologyLink:
    reach_id_1: int
    reach_id_2: int
    orientation: str


@dataclass(frozen=True)
class FlowPathPoint:
    id: int
    rid: int
    dist: float
    offset: float
    x: float
    y: float
    row: int
    col: int


def ensure_line_feature(value: LineFeature | dict[str, Any]) -> LineFeature:
    if isinstance(value, LineFeature):
        return value
    attributes = dict(value.get("attributes", {}))
    raw_vertices = value.get("vertices", [])
    vertices = [
        point if isinstance(point, Coordinate) else Coordinate(*point)
        for point in raw_vertices
    ]
    return LineFeature(attributes=attributes, vertices=vertices)


def ensure_point_feature(value: PointFeature | dict[str, Any]) -> PointFeature:
    if isinstance(value, PointFeature):
        return value
    attributes = dict(value.get("attributes", {}))
    raw_point = value.get("point")
    if isinstance(raw_point, Coordinate):
        point = raw_point
    else:
        point = Coordinate(*raw_point)
    return PointFeature(attributes=attributes, point=point)


def ensure_links(
    links: Iterable[TopologyLink | tuple[int, int] | dict[str, Any]],
    down_field: str = "DownID",
    up_field: str = "UpID",
) -> list[TopologyLink]:
    result: list[TopologyLink] = []
    for link in links:
        if isinstance(link, TopologyLink):
            result.append(link)
        elif isinstance(link, dict):
            result.append(TopologyLink(int(link[down_field]), int(link[up_field])))
        else:
            result.append(TopologyLink(int(link[0]), int(link[1])))
    return result
