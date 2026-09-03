from __future__ import annotations

from typing import Protocol


class FeedbackProtocol(Protocol):
    def pushInfo(self, message: str) -> None:
        ...

    def pushWarning(self, message: str) -> None:
        ...

    def isCanceled(self) -> bool:
        ...

    def setProgress(self, progress: int) -> None:
        ...


class FlowDirectionRasterProtocol(Protocol):
    VALID_DIRS: set[int]

    def x_to_col(self, x: float) -> int:
        ...

    def y_to_row(self, y: float) -> int:
        ...

    def col_to_x(self, col: int) -> float:
        ...

    def row_to_y(self, row: int) -> float:
        ...

    def in_bounds(self, row: int, col: int) -> bool:
        ...

    def get_value(self, row: int, col: int) -> int:
        ...

    def step(self, row: int, col: int) -> tuple[int, int, float] | None:
        ...
