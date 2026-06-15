from __future__ import annotations

from dataclasses import dataclass, field

from n2t.core.compiler.analyzer import (
    KEYWORD_CONSTANTS,
    OPERATORS,
    STATEMENT_KEYWORDS,
    UNARY_OPERATORS,
)
from n2t.core.compiler.cursor import TokenCursor
from n2t.core.compiler.symbol_table import SymbolTable
from n2t.core.compiler.tokenizer import JackTokenizer, TokenType
from n2t.core.compiler.vm_writer import VMWriter


@dataclass
class CompilationEngine:
    """Project 11: walks the token stream and emits VM code for one class."""

    cursor: TokenCursor
    symbols: SymbolTable = field(default_factory=SymbolTable)
    writer: VMWriter = field(default_factory=VMWriter)
    _class_name: str = ""
    _label_id: int = 0

    @classmethod
    def from_source(cls, source: str) -> CompilationEngine:
        return cls(TokenCursor(JackTokenizer(source).tokenize()))

    def compile(self) -> list[str]:
        self._compile_class()
        return self.writer.output

    def _new_label(self, prefix: str) -> str:
        label = f"{prefix}_{self._label_id}"
        self._label_id += 1
        return label

    # program structure ---------------------------------------------------

    def _compile_class(self) -> None:
        self.cursor.expect("class")
        self._class_name = self.cursor.advance().value
        self.cursor.expect("{")
        while self.cursor.value_is("static", "field"):
            self._compile_class_var_dec()
        while self.cursor.value_is("constructor", "function", "method"):
            self._compile_subroutine()
        self.cursor.expect("}")

    def _compile_class_var_dec(self) -> None:
        kind = self.cursor.advance().value  # 'static' | 'field'
        self._define_variables(kind)

    def _define_variables(self, kind: str) -> None:
        # Shared by classVarDec and varDec: 'type name (, name)* ;'.
        var_type = self.cursor.advance().value
        self.symbols.define(self.cursor.advance().value, var_type, kind)
        while self.cursor.value_is(","):
            self.cursor.advance()  # ','
            self.symbols.define(self.cursor.advance().value, var_type, kind)
        self.cursor.expect(";")

    def _compile_subroutine(self) -> None:
        self.symbols.start_subroutine()
        kind = self.cursor.advance().value  # constructor | function | method
        self.cursor.advance()  # return type
        name = self.cursor.advance().value
        if kind == "method":
            # A method's hidden first argument is the object it runs on.
            self.symbols.define("this", self._class_name, "arg")
        self.cursor.expect("(")
        self._compile_parameter_list()
        self.cursor.expect(")")
        self._compile_subroutine_body(kind, name)

    def _compile_parameter_list(self) -> None:
        while not self.cursor.value_is(")"):
            var_type = self.cursor.advance().value
            self.symbols.define(self.cursor.advance().value, var_type, "arg")
            if self.cursor.value_is(","):
                self.cursor.advance()  # ','

    def _compile_subroutine_body(self, kind: str, name: str) -> None:
        self.cursor.expect("{")
        while self.cursor.value_is("var"):
            self._compile_var_dec()
        self.writer.function(f"{self._class_name}.{name}", self.symbols.count("var"))
        self._write_subroutine_setup(kind)
        self._compile_statements()
        self.cursor.expect("}")

    def _write_subroutine_setup(self, kind: str) -> None:
        if kind == "constructor":
            # Allocate room for the object's fields and make THIS point at it.
            self.writer.push("constant", self.symbols.count("field"))
            self.writer.call("Memory.alloc", 1)
            self.writer.pop("pointer", 0)
        elif kind == "method":
            # Bind THIS to the object passed as the hidden argument 0.
            self.writer.push("argument", 0)
            self.writer.pop("pointer", 0)

    def _compile_var_dec(self) -> None:
        self.cursor.advance()  # 'var'
        self._define_variables("var")

    # statements ----------------------------------------------------------

    def _compile_statements(self) -> None:
        dispatch = {
            "let": self._compile_let,
            "if": self._compile_if,
            "while": self._compile_while,
            "do": self._compile_do,
            "return": self._compile_return,
        }
        while self.cursor.value_is(*STATEMENT_KEYWORDS):
            dispatch[self.cursor.current.value]()

    def _compile_let(self) -> None:
        self.cursor.advance()  # 'let'
        name = self.cursor.advance().value
        if self.cursor.value_is("["):
            self._compile_let_array(name)
            return
        self.cursor.expect("=")
        self._compile_expression()
        self.cursor.expect(";")
        self.writer.pop(self.symbols.segment_of(name), self.symbols.index_of(name))

    def _compile_let_array(self, name: str) -> None:
        # Compute the target address (base + index) before evaluating the
        # right side, then route the store through THAT via a temp slot so a
        # nested array access on the right cannot clobber the pointer.
        self.writer.push(self.symbols.segment_of(name), self.symbols.index_of(name))
        self.cursor.expect("[")
        self._compile_expression()
        self.cursor.expect("]")
        self.writer.binary_op("+")
        self.cursor.expect("=")
        self._compile_expression()
        self.cursor.expect(";")
        self.writer.pop("temp", 0)
        self.writer.pop("pointer", 1)
        self.writer.push("temp", 0)
        self.writer.pop("that", 0)

    def _compile_if(self) -> None:
        else_label = self._new_label("IF_ELSE")
        end_label = self._new_label("IF_END")
        self.cursor.advance()  # 'if'
        self._compile_condition()
        self.writer.if_goto(else_label)  # condition was negated
        self._compile_block()
        self.writer.goto(end_label)
        self.writer.label(else_label)
        if self.cursor.value_is("else"):
            self.cursor.advance()  # 'else'
            self._compile_block()
        self.writer.label(end_label)

    def _compile_while(self) -> None:
        top_label = self._new_label("WHILE_TOP")
        end_label = self._new_label("WHILE_END")
        self.writer.label(top_label)
        self.cursor.advance()  # 'while'
        self._compile_condition()
        self.writer.if_goto(end_label)  # condition was negated
        self._compile_block()
        self.writer.goto(top_label)
        self.writer.label(end_label)

    def _compile_condition(self) -> None:
        # '( expression )' with the result negated, so a single if-goto can
        # branch past the body when the condition is false.
        self.cursor.expect("(")
        self._compile_expression()
        self.cursor.expect(")")
        self.writer.unary_op("~")

    def _compile_block(self) -> None:
        self.cursor.expect("{")
        self._compile_statements()
        self.cursor.expect("}")

    def _compile_do(self) -> None:
        self.cursor.advance()  # 'do'
        self._compile_subroutine_call(self.cursor.advance().value)
        self.cursor.expect(";")
        self.writer.pop("temp", 0)  # discard the unused return value

    def _compile_return(self) -> None:
        self.cursor.advance()  # 'return'
        if self.cursor.value_is(";"):
            self.writer.push("constant", 0)  # void subroutines return 0
        else:
            self._compile_expression()
        self.cursor.expect(";")
        self.writer.do_return()

    # expressions ---------------------------------------------------------

    def _compile_expression(self) -> None:
        self._compile_term()
        while self.cursor.value_is(*OPERATORS):
            operator = self.cursor.advance().value
            self._compile_term()
            self.writer.binary_op(operator)

    def _compile_term(self) -> None:
        token = self.cursor.current
        if token.type == TokenType.INTEGER:
            self.writer.push("constant", int(self.cursor.advance().value))
        elif token.type == TokenType.STRING:
            self._compile_string(self.cursor.advance().value)
        elif token.value in KEYWORD_CONSTANTS:
            self._compile_keyword_constant(self.cursor.advance().value)
        elif token.value == "(":
            self.cursor.advance()  # '('
            self._compile_expression()
            self.cursor.expect(")")
        elif token.value in UNARY_OPERATORS:
            self.cursor.advance()  # unary operator
            self._compile_term()
            self.writer.unary_op(token.value)
        else:
            self._compile_identifier_term()

    def _compile_string(self, text: str) -> None:
        # Build the String object one character at a time; appendChar returns
        # the same object, so it stays on the stack for the next call.
        self.writer.push("constant", len(text))
        self.writer.call("String.new", 1)
        for char in text:
            self.writer.push("constant", ord(char))
            self.writer.call("String.appendChar", 2)

    def _compile_keyword_constant(self, value: str) -> None:
        if value == "this":
            self.writer.push("pointer", 0)
            return
        self.writer.push("constant", 0)
        if value == "true":
            self.writer.unary_op("~")  # true is -1, i.e. ~0

    def _compile_identifier_term(self) -> None:
        name = self.cursor.advance().value
        if self.cursor.value_is("["):
            self._compile_array_access(name)
        elif self.cursor.value_is(".", "("):
            self._compile_subroutine_call(name)
        else:
            self.writer.push(self.symbols.segment_of(name), self.symbols.index_of(name))

    def _compile_array_access(self, name: str) -> None:
        self.writer.push(self.symbols.segment_of(name), self.symbols.index_of(name))
        self.cursor.expect("[")
        self._compile_expression()
        self.cursor.expect("]")
        self.writer.binary_op("+")
        self.writer.pop("pointer", 1)  # THAT = base + index
        self.writer.push("that", 0)

    def _compile_subroutine_call(self, name: str) -> None:
        if self.cursor.value_is("."):
            self.cursor.advance()  # '.'
            method = self.cursor.advance().value
            self._compile_dotted_call(name, method)
        else:
            # An undotted call is a method on the current object.
            self.writer.push("pointer", 0)
            n_args = self._compile_call_arguments() + 1
            self.writer.call(f"{self._class_name}.{name}", n_args)

    def _compile_dotted_call(self, target: str, method: str) -> None:
        if self.symbols.has(target):
            # 'object.method(...)': push the object as the hidden argument.
            self.writer.push(
                self.symbols.segment_of(target), self.symbols.index_of(target)
            )
            n_args = self._compile_call_arguments() + 1
            self.writer.call(f"{self.symbols.type_of(target)}.{method}", n_args)
        else:
            # 'Class.function(...)': a plain function or constructor call.
            n_args = self._compile_call_arguments()
            self.writer.call(f"{target}.{method}", n_args)

    def _compile_call_arguments(self) -> int:
        self.cursor.expect("(")
        n_args = self._compile_expression_list()
        self.cursor.expect(")")
        return n_args

    def _compile_expression_list(self) -> int:
        if self.cursor.value_is(")"):
            return 0
        count = 1
        self._compile_expression()
        while self.cursor.value_is(","):
            self.cursor.advance()  # ','
            self._compile_expression()
            count += 1
        return count
