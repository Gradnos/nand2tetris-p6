from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass
class Assembler:
    @classmethod
    def create(cls) -> Assembler:
        return cls()

    def assemble(self, _assembly: Iterable[str]) -> Iterable[str]:
        lines = self._clean_lines(_assembly)
        symbol_table = self._first_pass(lines)
        return self._second_pass(lines, symbol_table)

    # ---------------- CLEANING ----------------

    def _clean_lines(self, assembly: Iterable[str]) -> list[str]:
        result: list[str] = []
        for line in assembly:
            line = line.split("//")[0].strip()
            if line:
                result.append(line)
        return result

    # ---------------- FIRST PASS ----------------

    def _first_pass(self, lines: list[str]) -> dict[str, int]:
        symbol_table = self._init_symbol_table()
        rom_address = 0

        for line in lines:
            if self._is_label(line):
                label = line[1:-1]
                symbol_table[label] = rom_address
            else:
                rom_address += 1

        return symbol_table

    def _init_symbol_table(self) -> dict[str, int]:
        table = {
            "SP": 0,
            "LCL": 1,
            "ARG": 2,
            "THIS": 3,
            "THAT": 4,
            "SCREEN": 16384,
            "KBD": 24576,
        }

        for i in range(16):
            table[f"R{i}"] = i

        return table

    # ---------------- SECOND PASS ----------------

    def _second_pass(
        self,
        lines: list[str],
        symbol_table: dict[str, int],
    ) -> list[str]:
        result: list[str] = []
        next_free_ram = 16

        for line in lines:
            if self._is_label(line):
                continue

            if self._is_a_instruction(line):
                value, next_free_ram = self._resolve_a_instruction(
                    line, symbol_table, next_free_ram
                )
                result.append(f"{value:016b}")
            else:
                result.append(self._translate_c_instruction(line))

        return result

    # ---------------- HELPERS ----------------

    def _is_label(self, line: str) -> bool:
        return line.startswith("(") and line.endswith(")")

    # ---------------- C-INSTRUCTION ----------------

    def _is_a_instruction(self, line: str) -> bool:
        return line.startswith("@")

    def _resolve_a_instruction(
        self,
        line: str,
        symbol_table: dict[str, int],
        next_free_ram: int,
    ) -> tuple[int, int]:
        symbol = line[1:]

        if symbol.isdigit():
            return int(symbol), next_free_ram

        if symbol not in symbol_table:
            symbol_table[symbol] = next_free_ram
            next_free_ram += 1

        return symbol_table[symbol], next_free_ram

    # ---------------- C-INSTRUCTION ----------------

    def _translate_c_instruction(self, line: str) -> str:
        dest, comp, jump = self._parse_c(line)
        return "111" + self._comp_bits(comp) + self._dest_bits(dest) + self._jump_bits(jump)

    def _parse_c(self, line: str) -> tuple[str | None, str, str | None]:
        dest: str | None = None
        jump: str | None = None

        if "=" in line:
            dest, line = line.split("=")

        if ";" in line:
            comp, jump = line.split(";")
        else:
            comp = line

        return dest, comp, jump

    def _dest_bits(self, dest: str | None) -> str:
        table = {
            None: "000",
            "M": "001",
            "D": "010",
            "MD": "011",
            "A": "100",
            "AM": "101",
            "AD": "110",
            "AMD": "111",
        }
        return table[dest]

    def _jump_bits(self, jump: str | None) -> str:
        table = {
            None: "000",
            "JGT": "001",
            "JEQ": "010",
            "JGE": "011",
            "JLT": "100",
            "JNE": "101",
            "JLE": "110",
            "JMP": "111",
        }
        return table[jump]

    def _comp_bits(self, comp: str) -> str:
        table = {
            "0": "0101010",
            "1": "0111111",
            "-1": "0111010",
            "D": "0001100",
            "A": "0110000",
            "M": "1110000",
            "!D": "0001101",
            "!A": "0110001",
            "!M": "1110001",
            "-D": "0001111",
            "-A": "0110011",
            "-M": "1110011",
            "D+1": "0011111",
            "A+1": "0110111",
            "M+1": "1110111",
            "D-1": "0001110",
            "A-1": "0110010",
            "M-1": "1110010",
            "D+A": "0000010",
            "D+M": "1000010",
            "D-A": "0010011",
            "D-M": "1010011",
            "A-D": "0000111",
            "M-D": "1000111",
            "D&A": "0000000",
            "D&M": "1000000",
            "D|A": "0010101",
            "D|M": "1010101",
        }
        return table[comp]
