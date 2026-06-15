from __future__ import annotations

from dataclasses import dataclass, field

# Jack operators that map straight onto a single VM command.
ARITHMETIC_COMMANDS = {
    "+": "add",
    "-": "sub",
    "&": "and",
    "|": "or",
    "<": "lt",
    ">": "gt",
    "=": "eq",
}

# Unary operators and the two operators with no VM primitive go through the OS.
UNARY_COMMANDS = {"-": "neg", "~": "not"}
OS_CALLS = {"*": "Math.multiply", "/": "Math.divide"}


@dataclass
class VMWriter:
    """Collects the VM commands emitted while compiling one Jack class."""

    _lines: list[str] = field(default_factory=list)

    @property
    def output(self) -> list[str]:
        return self._lines

    def push(self, segment: str, index: int) -> None:
        self._lines.append(f"push {segment} {index}")

    def pop(self, segment: str, index: int) -> None:
        self._lines.append(f"pop {segment} {index}")

    def binary_op(self, operator: str) -> None:
        if operator in OS_CALLS:
            self.call(OS_CALLS[operator], 2)
        else:
            self._lines.append(ARITHMETIC_COMMANDS[operator])

    def unary_op(self, operator: str) -> None:
        self._lines.append(UNARY_COMMANDS[operator])

    def label(self, name: str) -> None:
        self._lines.append(f"label {name}")

    def goto(self, name: str) -> None:
        self._lines.append(f"goto {name}")

    def if_goto(self, name: str) -> None:
        self._lines.append(f"if-goto {name}")

    def call(self, name: str, n_args: int) -> None:
        self._lines.append(f"call {name} {n_args}")

    def function(self, name: str, n_locals: int) -> None:
        self._lines.append(f"function {name} {n_locals}")

    def do_return(self) -> None:
        self._lines.append("return")
