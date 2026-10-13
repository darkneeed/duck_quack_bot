from __future__ import annotations
from collections import OrderedDict
from typing import Any, Generic, Iterable, Iterator, TypeVar

T = TypeVar("T")


class BoundedSet(Generic[T]):
    """A bounded set with FIFO/LRU eviction semantics based on OrderedDict."""

    def __init__(self, maxsize: int = 10_000, iterable: Iterable[T] | None = None) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self._maxsize = maxsize
        self._data: OrderedDict[T, None] = OrderedDict()
        if iterable is not None:
            self.update(iterable)

    def add(self, item: T) -> None:
        if item in self._data:
            self._data.move_to_end(item)
            return
        self._data[item] = None
        if len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def update(self, *iterables: Iterable[T]) -> None:
        for it in iterables:
            for item in it:
                self.add(item)

    def discard(self, item: T) -> None:
        self._data.pop(item, None)

    def remove(self, item: T) -> None:
        del self._data[item]

    def clear(self) -> None:
        self._data.clear()

    def copy(self) -> BoundedSet[T]:
        new_set = BoundedSet[T](maxsize=self._maxsize)
        new_set._data = self._data.copy()
        return new_set

    def __contains__(self, item: Any) -> bool:
        return item in self._data

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[T]:
        return iter(self._data)

    def __repr__(self) -> str:
        return f"BoundedSet({list(self._data.keys())}, maxsize={self._maxsize})"
