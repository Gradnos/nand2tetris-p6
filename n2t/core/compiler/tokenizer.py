from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

KEYWORDS = {
    "class",
    "constructor",
    "function",
    "method",
    "field",
    "static",
    "var",
    "int",
    "char",
    "boolean",
    "void",
    "true",
    "false",
    "null",
    "this",
    "let",
    "do",
    "if",
    "else",
    "while",
    "return",
}

SYMBOLS = set("{}()[].,;+-*/&|<>=~")

# These symbols collide with XML markup, so they are escaped when printed.
XML_ESCAPES = {
    "<": "&lt;",
    ">": "&gt;",
    "&": "&amp;",
}


class TokenType(Enum):
    KEYWORD = "keyword"
    SYMBOL = "symbol"
    INTEGER = "integerConstant"
    STRING = "stringConstant"
    IDENTIFIER = "identifier"


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str

    def xml(self) -> str:
        # String constants are stored without their surrounding quotes, and the
        # markup-sensitive symbols are escaped here so the parser never has to.
        text = XML_ESCAPES.get(self.value, self.value)
        return f"<{self.type.value}> {text} </{self.type.value}>"


@dataclass
class JackTokenizer:
    source: str
    _tokens: list[Token] = field(default_factory=list)

    def tokenize(self) -> list[Token]:
        code = self._strip_comments(self.source)
        i = 0
        n = len(code)
        while i < n:
            char = code[i]
            if char.isspace():
                i += 1
            elif char == '"':
                i = self._read_string(code, i)
            elif char in SYMBOLS:
                self._tokens.append(Token(TokenType.SYMBOL, char))
                i += 1
            elif char.isdigit():
                i = self._read_integer(code, i)
            else:
                i = self._read_word(code, i)
        return self._tokens

    def _read_string(self, code: str, start: int) -> int:
        # start points at the opening quote; read up to the closing one.
        end = code.index('"', start + 1)
        self._tokens.append(Token(TokenType.STRING, code[start + 1 : end]))
        return end + 1

    def _read_integer(self, code: str, start: int) -> int:
        end = start
        while end < len(code) and code[end].isdigit():
            end += 1
        self._tokens.append(Token(TokenType.INTEGER, code[start:end]))
        return end

    def _read_word(self, code: str, start: int) -> int:
        # An identifier (or keyword) runs until the next symbol or whitespace.
        end = start
        while end < len(code) and (code[end].isalnum() or code[end] == "_"):
            end += 1
        word = code[start:end]
        kind = TokenType.KEYWORD if word in KEYWORDS else TokenType.IDENTIFIER
        self._tokens.append(Token(kind, word))
        return end

    @staticmethod
    def _strip_comments(source: str) -> str:
        # Walk the source once, copying everything that is not inside a comment.
        # String literals are copied verbatim so a "//" inside a string survives.
        result: list[str] = []
        i = 0
        n = len(source)
        while i < n:
            two = source[i : i + 2]
            if source[i] == '"':
                end = source.index('"', i + 1)
                result.append(source[i : end + 1])
                i = end + 1
            elif two == "//":
                i = source.find("\n", i)
                i = n if i == -1 else i
            elif two == "/*":
                i = source.index("*/", i + 2) + 2
            else:
                result.append(source[i])
                i += 1
        return "".join(result)
