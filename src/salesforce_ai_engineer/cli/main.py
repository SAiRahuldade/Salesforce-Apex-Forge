"""Typer CLI bootstrap."""

import typer

from salesforce_ai_engineer.core.bootstrap import get_container

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    get_container().resolve("logger").debug("CLI initialized")
