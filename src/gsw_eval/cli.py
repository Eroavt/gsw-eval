"""Command line entry point. Owner: Erik."""

import typer

app = typer.Typer(help="Benchmark LLMs on written Swiss German.")


@app.command()
def tax() -> None:
    """Compute the token tax table."""
    typer.echo("not implemented yet")


@app.command()
def run(model: str = typer.Option(..., help="Model name")) -> None:
    """Run normalization for one model on all conditions."""
    typer.echo(f"not implemented yet: {model}")


if __name__ == "__main__":
    app()
