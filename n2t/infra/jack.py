from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from n2t.core.compiler import CompilationEngine, JackAnalyzer

# The reference .xml files ship with Windows line endings, so the analyzer
# output is written the same way to stay byte-for-byte comparable.
XML_NEWLINE = "\r\n"


@dataclass
class JackProgram:  # Projects 10 and 11: the Jack compiler entry point.
    files: list[Path] = field(default_factory=list)

    @classmethod
    def load_from(cls, file_or_directory_name: str) -> JackProgram:
        path = Path(file_or_directory_name)
        if path.is_dir():
            files = sorted(path.glob("*.jack"))
            if not files:
                raise ValueError(f"No .jack files found in directory: {path}")
            return cls(files)
        if path.suffix != ".jack":
            raise ValueError(f"Expected a .jack file or directory, got: {path}")
        return cls([path])

    def compile(self) -> None:
        for jack_file in self.files:
            self._compile_file(jack_file)

    def _compile_file(self, jack_file: Path) -> None:
        source = jack_file.read_text()

        # Project 10: the flat token list and the grammar parse tree.
        analyzer = JackAnalyzer.from_source(source)
        tokens_path = jack_file.with_name(jack_file.stem + "T.xml")
        self._write_xml(tokens_path, analyzer.tokens_xml())
        self._write_xml(jack_file.with_suffix(".xml"), analyzer.parse_xml())

        # Project 11: the executable VM code.
        vm_code = CompilationEngine.from_source(source).compile()
        jack_file.with_suffix(".vm").write_text("\n".join(vm_code) + "\n")

    @staticmethod
    def _write_xml(path: Path, lines: list[str]) -> None:
        path.write_text(XML_NEWLINE.join(lines) + XML_NEWLINE, newline="")
