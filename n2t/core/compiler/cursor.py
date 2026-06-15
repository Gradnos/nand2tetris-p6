from __future__ import annotations

from dataclasses import dataclass, field

from n2t.core.compiler.tokenizer import Token, TokenType


@dataclass
class TokenCursor:
    tokens: list[Token]
    _pos: int = field(default=0)

    @property
    def current(self) -> Token:
        return self.tokens[self._pos]

    @property
    def has_more(self) -> bool:
        return self._pos < len(self.tokens)

    def peek(self, ahead: int = 1) -> Token:
        # Lets a parser look at the next token to decide between grammar rules
        # (e.g. telling an array access apart from a plain variable).
        return self.tokens[self._pos + ahead]

    def advance(self) -> Token:
        token = self.current
        self._pos += 1
        return token

    def expect(self, value: str) -> Token:
        # Consume a token we already know must be there from the grammar; the
        # assertion turns a malformed program into a clear failure instead of a
        # confusing one further down.
        token = self.current
        assert token.value == value, f"expected '{value}', got '{token.value}'"
        return self.advance()

    def value_is(self, *values: str) -> bool:
        return self.has_more and self.current.value in values

    def type_is(self, *types: TokenType) -> bool:
        return self.has_more and self.current.type in types
