from __future__ import annotations

from collections.abc import Iterator
from typing import Generic, TypeVar


T = TypeVar("T")


class RegistryError(LookupError):
    """A registry key is missing or was registered more than once."""


class Registry(Generic[T]):
    def __init__(self, name: str) -> None:
        self.name = name
        self._items: dict[str, T] = {}

    def register(self, key: str, value: T) -> None:
        if not key or key in self._items:
            raise RegistryError(f"{self.name} registry key is empty or duplicated: {key!r}")
        self._items[key] = value

    def require(self, key: str) -> T:
        try:
            return self._items[key]
        except KeyError as exc:
            raise RegistryError(f"Unknown {self.name} registry key: {key!r}") from exc

    def supports(self, key: str) -> bool:
        return key in self._items

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._items))

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

