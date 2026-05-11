from __future__ import annotations

import os
from dataclasses import dataclass, field


SEGMENT_POINTERS = {
    "local":    "LCL",
    "argument": "ARG",
    "this":     "THIS",
    "that":     "THAT",
}

BINARY_OPS = {
    "add": "M=D+M",
    "sub": "M=M-D",
    "and": "M=D&M",
    "or":  "M=D|M",
}

UNARY_OPS = {
    "neg": "M=-M",
    "not": "M=!M",
}

COMPARISONS = {
    "eq": "JEQ",
    "gt": "JGT",
    "lt": "JLT",
}


@dataclass
class VmProgram:
    files: list[tuple[str, list[str]]] = field(default_factory=list)
    output_path: str = ""
    bootstrap: bool = False

    _asm: list[str] = field(default_factory=list)
    _current_file: str = ""
    _current_function: str = ""
    _cmp_id: int = 0
    _ret_id: int = 0

    @classmethod
    def load_from(cls, file_or_directory_name: str) -> VmProgram:
        path = file_or_directory_name

        if os.path.isdir(path):
            return cls._load_directory(path)

        if not path.endswith(".vm"):
            raise ValueError(f"Expected a .vm file or directory, got: {path}")

        name = os.path.basename(path)[:-3]
        return cls(
            files=[(name, read_source(path))],
            output_path=path[:-3] + ".asm",
            bootstrap=False,
        )

    @classmethod
    def _load_directory(cls, path: str) -> VmProgram:
        names = sorted(f for f in os.listdir(path) if f.endswith(".vm"))
        if not names:
            raise ValueError(f"No .vm files found in directory: {path}")

        files = [(n[:-3], read_source(os.path.join(path, n))) for n in names]
        dir_name = os.path.basename(os.path.normpath(path))

        # The ProgramFlow tests are directory-shaped but set up their own
        # stack frame from the .tst, so we only bootstrap when Sys.init is
        # actually there to be called.
        needs_bootstrap = any(defines_sys_init(lines) for _, lines in files)

        return cls(
            files=files,
            output_path=os.path.join(path, dir_name + ".asm"),
            bootstrap=needs_bootstrap,
        )

    def translate(self) -> None:
        self._asm = []
        self._cmp_id = 0

        if self.bootstrap:
            self._write_bootstrap()

        for name, lines in self.files:
            self._current_file = name
            self._current_function = ""
            self._ret_id = 0
            for raw in lines:
                cmd = strip_line(raw)
                if cmd:
                    self._dispatch(cmd)

        # Trap PC at the end so it can't wander into uninitialized memory
        # after the program finishes (CPUEmulator decodes zeros as @0/no-op,
        # but the .tst can still observe whatever side effects happen along
        # the way).
        self._asm += [
            "// terminate",
            "(__END__)",
            "@__END__",
            "0;JMP",
        ]

        with open(self.output_path, "w") as f:
            f.write("\n".join(self._asm) + "\n")

    def _dispatch(self, cmd: str) -> None:
        self._asm.append(f"// {cmd}")

        parts = cmd.split()
        op = parts[0]

        if op in BINARY_OPS:
            self._binary(BINARY_OPS[op])
        elif op in UNARY_OPS:
            self._unary(UNARY_OPS[op])
        elif op in COMPARISONS:
            self._compare(COMPARISONS[op])
        elif op == "push":
            self._push(parts[1], int(parts[2]))
        elif op == "pop":
            self._pop(parts[1], int(parts[2]))
        elif op == "label":
            self._asm.append(f"({self._scoped(parts[1])})")
        elif op == "goto":
            self._asm += [f"@{self._scoped(parts[1])}", "0;JMP"]
        elif op == "if-goto":
            self._if_goto(parts[1])
        elif op == "function":
            self._function(parts[1], int(parts[2]))
        elif op == "call":
            self._call(parts[1], int(parts[2]))
        elif op == "return":
            self._return()
        else:
            raise ValueError(f"Unknown VM command: {cmd}")

    # arithmetic and logic ------------------------------------------------

    def _binary(self, op: str) -> None:
        # SP--, then operate at SP-1 in place. Top operand goes into D first.
        self._asm += [
            "@SP", "AM=M-1",
            "D=M",
            "A=A-1",
            op,
        ]

    def _unary(self, op: str) -> None:
        self._asm += ["@SP", "A=M-1", op]

    def _compare(self, jump: str) -> None:
        n = self._cmp_id
        self._cmp_id += 1
        true_lbl = f"CMP_TRUE_{n}"
        end_lbl  = f"CMP_END_{n}"
        self._asm += [
            "@SP", "AM=M-1",
            "D=M",
            "A=A-1",
            "D=M-D",
            f"@{true_lbl}",
            f"D;{jump}",
            "@SP", "A=M-1",
            "M=0",
            f"@{end_lbl}",
            "0;JMP",
            f"({true_lbl})",
            "@SP", "A=M-1",
            "M=-1",
            f"({end_lbl})",
        ]

    # memory access -------------------------------------------------------

    def _push(self, segment: str, i: int) -> None:
        if segment == "constant":
            self._asm += [f"@{i}", "D=A"]
        elif segment in SEGMENT_POINTERS:
            self._asm += [
                f"@{i}", "D=A",
                f"@{SEGMENT_POINTERS[segment]}", "A=M+D",
                "D=M",
            ]
        elif segment == "temp":
            self._asm += [f"@{5 + i}", "D=M"]
        elif segment == "pointer":
            self._asm += [f"@{'THIS' if i == 0 else 'THAT'}", "D=M"]
        elif segment == "static":
            self._asm += [f"@{self._current_file}.{i}", "D=M"]
        else:
            raise ValueError(f"Unknown segment: {segment}")

        self._asm += [
            "@SP", "A=M", "M=D",
            "@SP", "M=M+1",
        ]

    def _pop(self, segment: str, i: int) -> None:
        if segment == "constant":
            self._asm += ["@SP", "M=M-1"]
            return

        if segment in SEGMENT_POINTERS:
            # Stash target address in R13 so we don't need to keep recomputing
            # it after clobbering A to read the stack top.
            self._asm += [
                f"@{i}", "D=A",
                f"@{SEGMENT_POINTERS[segment]}", "D=M+D",
                "@R13", "M=D",
                "@SP", "AM=M-1",
                "D=M",
                "@R13", "A=M",
                "M=D",
            ]
            return

        if segment == "temp":
            dest = f"@{5 + i}"
        elif segment == "pointer":
            dest = "@THIS" if i == 0 else "@THAT"
        elif segment == "static":
            dest = f"@{self._current_file}.{i}"
        else:
            raise ValueError(f"Unknown segment: {segment}")

        self._asm += [
            "@SP", "AM=M-1",
            "D=M",
            dest,
            "M=D",
        ]

    # branching -----------------------------------------------------------

    def _scoped(self, label: str) -> str:
        if self._current_function:
            return f"{self._current_function}${label}"
        return label

    def _if_goto(self, label: str) -> None:
        self._asm += [
            "@SP", "AM=M-1",
            "D=M",
            f"@{self._scoped(label)}",
            "D;JNE",
        ]

    # functions -----------------------------------------------------------

    def _function(self, name: str, n_locals: int) -> None:
        self._current_function = name
        self._ret_id = 0
        self._asm.append(f"({name})")
        for _ in range(n_locals):
            self._asm += [
                "@SP", "A=M", "M=0",
                "@SP", "M=M+1",
            ]

    def _call(self, name: str, n_args: int) -> None:
        caller = self._current_function or "Bootstrap"
        ret_lbl = f"{caller}$ret.{self._ret_id}"
        self._ret_id += 1

        # push return address
        self._asm += [
            f"@{ret_lbl}", "D=A",
            "@SP", "A=M", "M=D",
            "@SP", "M=M+1",
        ]
        # save caller's frame
        for ptr in ("LCL", "ARG", "THIS", "THAT"):
            self._asm += [
                f"@{ptr}", "D=M",
                "@SP", "A=M", "M=D",
                "@SP", "M=M+1",
            ]
        # ARG = SP - n_args - 5; LCL = SP
        self._asm += [
            "@SP", "D=M",
            f"@{n_args + 5}", "D=D-A",
            "@ARG", "M=D",
            "@SP", "D=M",
            "@LCL", "M=D",
            f"@{name}", "0;JMP",
            f"({ret_lbl})",
        ]

    def _return(self) -> None:
        # endFrame in R13, retAddr in R14. R13-R15 are the spec's scratch
        # registers and are free to clobber here.
        self._asm += [
            "@LCL", "D=M",
            "@R13", "M=D",

            # Stash retAddr *before* writing *ARG -- when n_args==0 the two
            # locations alias and the next write would otherwise destroy it.
            "@5", "A=D-A", "D=M",
            "@R14", "M=D",

            # *ARG = pop()
            "@SP", "AM=M-1", "D=M",
            "@ARG", "A=M", "M=D",

            # SP = ARG + 1
            "@ARG", "D=M+1",
            "@SP", "M=D",

            # restore caller's THAT, THIS, ARG, LCL by walking back from endFrame
            "@R13", "AM=M-1", "D=M", "@THAT", "M=D",
            "@R13", "AM=M-1", "D=M", "@THIS", "M=D",
            "@R13", "AM=M-1", "D=M", "@ARG",  "M=D",
            "@R13", "AM=M-1", "D=M", "@LCL",  "M=D",

            "@R14", "A=M", "0;JMP",
        ]

    def _write_bootstrap(self) -> None:
        self._asm += [
            "// bootstrap",
            "@256", "D=A",
            "@SP", "M=D",
        ]
        self._current_function = ""
        self._call("Sys.init", 0)


def read_source(path: str) -> list[str]:
    with open(path) as f:
        return f.readlines()


def defines_sys_init(lines: list[str]) -> bool:
    for raw in lines:
        s = strip_line(raw)
        if s.startswith("function ") and s.split()[1:2] == ["Sys.init"]:
            return True
    return False


def strip_line(line: str) -> str:
    i = line.find("//")
    if i != -1:
        line = line[:i]
    return line.strip()