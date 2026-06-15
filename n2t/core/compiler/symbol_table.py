from __future__ import annotations

from dataclasses import dataclass, field

# Each variable kind lives in a fixed VM memory segment.
KIND_SEGMENTS = {
    "static": "static",
    "field": "this",
    "arg": "argument",
    "var": "local",
}


@dataclass
class Symbol:
    type: str
    kind: str
    index: int


@dataclass
class SymbolTable:
    """Two-level scope: class-wide symbols plus the current subroutine's."""

    _class_scope: dict[str, Symbol] = field(default_factory=dict)
    _subroutine_scope: dict[str, Symbol] = field(default_factory=dict)
    _counts: dict[str, int] = field(default_factory=dict)

    def start_subroutine(self) -> None:
        # Subroutine-level names (args and locals) are forgotten between
        # subroutines; class-level names (statics and fields) persist.
        self._subroutine_scope = {}
        self._counts["arg"] = 0
        self._counts["var"] = 0

    def define(self, name: str, var_type: str, kind: str) -> None:
        index = self._counts.get(kind, 0)
        self._counts[kind] = index + 1
        scope = self._scope_for(kind)
        scope[name] = Symbol(var_type, kind, index)

    def count(self, kind: str) -> int:
        return self._counts.get(kind, 0)

    def has(self, name: str) -> bool:
        return name in self._subroutine_scope or name in self._class_scope

    def _lookup(self, name: str) -> Symbol:
        # A local name shadows a class name of the same identifier.
        return self._subroutine_scope.get(name) or self._class_scope[name]

    def segment_of(self, name: str) -> str:
        return KIND_SEGMENTS[self._lookup(name).kind]

    def index_of(self, name: str) -> int:
        return self._lookup(name).index

    def type_of(self, name: str) -> str:
        return self._lookup(name).type

    def _scope_for(self, kind: str) -> dict[str, Symbol]:
        if kind in ("static", "field"):
            return self._class_scope
        return self._subroutine_scope
