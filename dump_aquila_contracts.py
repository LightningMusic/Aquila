# save as dump_aquila_contracts.py

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable


FILES = (
    Path("src/bios/models.py"),
    Path("src/bios/providers/base.py"),
    Path("src/bios/providers/default.py"),
)

# Bodies of these methods are useful because DellProvider must interact with
# their state and fallback behavior correctly.
FULL_METHODS = {
    "__init__",
    "connect",
    "disconnect",
    "close",
    "refresh",
    "is_connected",
    "boot_order",
    "set_boot_order",
    "add_boot_device",
    "remove_boot_device",
    "current_boot_device",
    "next_boot_device",
    "set_next_boot_device",
    "clear_next_boot_device",
}


def render_arguments(arguments: ast.arguments) -> str:
    positional = list(arguments.posonlyargs) + list(arguments.args)
    positional_defaults = [None] * (
        len(positional) - len(arguments.defaults)
    ) + list(arguments.defaults)

    rendered: list[str] = []

    posonly_count = len(arguments.posonlyargs)
    for index, (argument, default) in enumerate(
        zip(positional, positional_defaults)
    ):
        text = argument.arg
        if argument.annotation is not None:
            text += f": {ast.unparse(argument.annotation)}"
        if default is not None:
            text += f" = {ast.unparse(default)}"
        rendered.append(text)

        if posonly_count and index + 1 == posonly_count:
            rendered.append("/")

    if arguments.vararg is not None:
        text = f"*{arguments.vararg.arg}"
        if arguments.vararg.annotation is not None:
            text += f": {ast.unparse(arguments.vararg.annotation)}"
        rendered.append(text)
    elif arguments.kwonlyargs:
        rendered.append("*")

    for argument, default in zip(
        arguments.kwonlyargs,
        arguments.kw_defaults,
    ):
        text = argument.arg
        if argument.annotation is not None:
            text += f": {ast.unparse(argument.annotation)}"
        if default is not None:
            text += f" = {ast.unparse(default)}"
        rendered.append(text)

    if arguments.kwarg is not None:
        text = f"**{arguments.kwarg.arg}"
        if arguments.kwarg.annotation is not None:
            text += f": {ast.unparse(arguments.kwarg.annotation)}"
        rendered.append(text)

    return ", ".join(rendered)


def render_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    signature = (
        f"{prefix} {node.name}({render_arguments(node.args)})"
    )
    if node.returns is not None:
        signature += f" -> {ast.unparse(node.returns)}"
    return signature + ":"


def decorators(node: ast.AST) -> Iterable[str]:
    for decorator in getattr(node, "decorator_list", ()):
        yield f"@{ast.unparse(decorator)}"


def print_imports(tree: ast.Module) -> None:
    print("\n# IMPORTS")
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            print(ast.unparse(node))


def print_assignment(node: ast.Assign | ast.AnnAssign) -> None:
    try:
        print("    " + ast.unparse(node).replace("\n", "\n    "))
    except Exception:
        pass


def print_class(
    source: str,
    node: ast.ClassDef,
    *,
    model_file: bool,
) -> None:
    print()
    for decorator in decorators(node):
        print(decorator)

    bases = [ast.unparse(base) for base in node.bases]
    keywords = [
        f"{keyword.arg}={ast.unparse(keyword.value)}"
        for keyword in node.keywords
    ]
    inheritance = ", ".join(bases + keywords)

    if inheritance:
        print(f"class {node.name}({inheritance}):")
    else:
        print(f"class {node.name}:")

    docstring = ast.get_docstring(node)
    if docstring:
        first_line = docstring.strip().splitlines()[0]
        print(f'    """{first_line}"""')

    for child in node.body:
        if isinstance(child, (ast.Assign, ast.AnnAssign)):
            print_assignment(child)
            continue

        if not isinstance(
            child,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue

        print()
        for decorator in decorators(child):
            print(f"    {decorator}")

        # Model constructors/properties and selected provider methods need
        # their implementations. Other methods only need signatures.
        include_body = (
            child.name in FULL_METHODS
            or (
                model_file
                and child.name in {
                    "__init__",
                    "__post_init__",
                    "value",
                    "name",
                    "to_dict",
                    "model_dump",
                }
            )
        )

        if include_body:
            segment = ast.get_source_segment(source, child)
            if segment:
                print(
                    "\n".join(
                        f"    {line}" if line else ""
                        for line in segment.splitlines()
                    )
                )
                continue

        print(f"    {render_signature(child)} ...")


def dump_file(path: Path) -> None:
    print("\n" + "=" * 78)
    print(path.as_posix())
    print("=" * 78)

    if not path.is_file():
        print("FILE NOT FOUND")
        return

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    print_imports(tree)

    print("\n# MODULE CONSTANTS AND TYPE ALIASES")
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            try:
                print(ast.unparse(node))
            except Exception:
                pass

    print("\n# CLASSES")
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            print_class(
                source,
                node,
                model_file=path.name == "models.py",
            )


def main() -> None:
    for path in FILES:
        dump_file(path)


if __name__ == "__main__":
    main()
