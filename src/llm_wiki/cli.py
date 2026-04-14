"""Command-line interface for llm-wiki."""

import click
from llm_wiki import __version__


@click.group()
@click.version_option(version=__version__)
def main():
    """Federated LLM wiki system with daemon governance."""
    pass


@main.command()
def init():
    """Initialize a new wiki instance."""
    click.echo("Initializing wiki...")
    click.echo("Not yet implemented - coming in later issues")


@main.command()
def daemon():
    """Start the wiki daemon."""
    click.echo("Starting daemon...")
    click.echo("Not yet implemented - coming in Epic 4")


if __name__ == "__main__":
    main()
