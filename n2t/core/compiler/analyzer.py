from __future__ import annotations

from dataclasses import dataclass, field

from n2t.core.compiler.cursor import TokenCursor
from n2t.core.compiler.tokenizer import JackTokenizer, Token, TokenType

STATEMENT_KEYWORDS = {"let", "if", "while", "do", "return"}
KEYWORD_CONSTANTS = {"true", "false", "null", "this"}
UNARY_OPERATORS = {"-", "~"}
OPERATORS = set("+-*/&|<>=")


@dataclass
class JackAnalyzer:
    """Project 10: turns a token stream into the grammar's XML parse tree."""

    cursor: TokenCursor
    _lines: list[str] = field(default_factory=list)
    _indent: int = 0

    @classmethod
    def from_source(cls, source: str) -> JackAnalyzer:
        return cls(TokenCursor(JackTokenizer(source).tokenize()))

    def tokens_xml(self) -> list[str]:
        # The "T.xml" output is just the flat token list, no grammar structure.
        return ["<tokens>", *(t.xml() for t in self.cursor.tokens), "</tokens>"]

    def parse_xml(self) -> list[str]:
        self.compile_class()
        return self._lines

    # output helpers ------------------------------------------------------

    def _emit(self, text: str) -> None:
        self._lines.append("  " * self._indent + text)

    def _emit_token(self) -> Token:
        token = self.cursor.advance()
        self._emit(token.xml())
        return token

    def _open(self, tag: str) -> None:
        self._emit(f"<{tag}>")
        self._indent += 1

    def _close(self, tag: str) -> None:
        self._indent -= 1
        self._emit(f"</{tag}>")

    # program structure ---------------------------------------------------

    def compile_class(self) -> None:
        self._open("class")
        self._emit_token()  # 'class'
        self._emit_token()  # className
        self._emit_token()  # '{'
        while self.cursor.value_is("static", "field"):
            self.compile_class_var_dec()
        while self.cursor.value_is("constructor", "function", "method"):
            self.compile_subroutine()
        self._emit_token()  # '}'
        self._close("class")

    def compile_class_var_dec(self) -> None:
        self._open("classVarDec")
        self._emit_until_semicolon()
        self._close("classVarDec")

    def compile_subroutine(self) -> None:
        self._open("subroutineDec")
        self._emit_token()  # constructor | function | method
        self._emit_token()  # return type
        self._emit_token()  # subroutine name
        self._emit_token()  # '('
        self.compile_parameter_list()
        self._emit_token()  # ')'
        self.compile_subroutine_body()
        self._close("subroutineDec")

    def compile_parameter_list(self) -> None:
        # The wrapper is always emitted, even when there are no parameters.
        self._open("parameterList")
        while not self.cursor.value_is(")"):
            self._emit_token()
        self._close("parameterList")

    def compile_subroutine_body(self) -> None:
        self._open("subroutineBody")
        self._emit_token()  # '{'
        while self.cursor.value_is("var"):
            self.compile_var_dec()
        self.compile_statements()
        self._emit_token()  # '}'
        self._close("subroutineBody")

    def compile_var_dec(self) -> None:
        self._open("varDec")
        self._emit_until_semicolon()
        self._close("varDec")

    def _emit_until_semicolon(self) -> None:
        # classVarDec and varDec share the same shape: a run of tokens that
        # always ends at the first ';'.
        while not self.cursor.value_is(";"):
            self._emit_token()
        self._emit_token()  # ';'

    # statements ----------------------------------------------------------

    def compile_statements(self) -> None:
        self._open("statements")
        while self.cursor.value_is(*STATEMENT_KEYWORDS):
            self._compile_statement()
        self._close("statements")

    def _compile_statement(self) -> None:
        dispatch = {
            "let": self.compile_let,
            "if": self.compile_if,
            "while": self.compile_while,
            "do": self.compile_do,
            "return": self.compile_return,
        }
        dispatch[self.cursor.current.value]()

    def compile_let(self) -> None:
        self._open("letStatement")
        self._emit_token()  # 'let'
        self._emit_token()  # varName
        if self.cursor.value_is("["):
            self._emit_token()  # '['
            self.compile_expression()
            self._emit_token()  # ']'
        self._emit_token()  # '='
        self.compile_expression()
        self._emit_token()  # ';'
        self._close("letStatement")

    def compile_if(self) -> None:
        self._open("ifStatement")
        self._emit_conditioned_block()  # 'if' '(' expr ')' '{' stmts '}'
        if self.cursor.value_is("else"):
            self._emit_token()  # 'else'
            self._emit_token()  # '{'
            self.compile_statements()
            self._emit_token()  # '}'
        self._close("ifStatement")

    def compile_while(self) -> None:
        self._open("whileStatement")
        self._emit_conditioned_block()
        self._close("whileStatement")

    def _emit_conditioned_block(self) -> None:
        # Shared 'keyword (expression) { statements }' shape of if/while.
        self._emit_token()  # 'if' | 'while'
        self._emit_token()  # '('
        self.compile_expression()
        self._emit_token()  # ')'
        self._emit_token()  # '{'
        self.compile_statements()
        self._emit_token()  # '}'

    def compile_do(self) -> None:
        self._open("doStatement")
        self._emit_token()  # 'do'
        self._compile_subroutine_call()
        self._emit_token()  # ';'
        self._close("doStatement")

    def compile_return(self) -> None:
        self._open("returnStatement")
        self._emit_token()  # 'return'
        if not self.cursor.value_is(";"):
            self.compile_expression()
        self._emit_token()  # ';'
        self._close("returnStatement")

    # expressions ---------------------------------------------------------

    def compile_expression(self) -> None:
        self._open("expression")
        self.compile_term()
        while self.cursor.value_is(*OPERATORS):
            self._emit_token()  # op
            self.compile_term()
        self._close("expression")

    def compile_term(self) -> None:
        self._open("term")
        if self.cursor.value_is("("):
            self._emit_token()  # '('
            self.compile_expression()
            self._emit_token()  # ')'
        elif self.cursor.value_is(*UNARY_OPERATORS):
            self._emit_token()  # unaryOp
            self.compile_term()
        elif self.cursor.type_is(TokenType.IDENTIFIER):
            self._compile_identifier_term()
        else:
            self._emit_token()  # integer/string/keyword constant
        self._close("term")

    def _compile_identifier_term(self) -> None:
        # An identifier term is an array access, a subroutine call, or a plain
        # variable, told apart by the symbol that follows it.
        following = self.cursor.peek().value
        if following == "[":
            self._emit_token()  # varName
            self._emit_token()  # '['
            self.compile_expression()
            self._emit_token()  # ']'
        elif following in (".", "("):
            self._compile_subroutine_call()
        else:
            self._emit_token()  # varName

    def _compile_subroutine_call(self) -> None:
        # Emitted inline (no wrapper tag), matching the reference XML.
        self._emit_token()  # subroutine or class/var name
        if self.cursor.value_is("."):
            self._emit_token()  # '.'
            self._emit_token()  # method name
        self._emit_token()  # '('
        self.compile_expression_list()
        self._emit_token()  # ')'

    def compile_expression_list(self) -> None:
        self._open("expressionList")
        if not self.cursor.value_is(")"):
            self.compile_expression()
            while self.cursor.value_is(","):
                self._emit_token()  # ','
                self.compile_expression()
        self._close("expressionList")
