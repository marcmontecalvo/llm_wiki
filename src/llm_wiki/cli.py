"""Command-line interface for llm-wiki."""

from pathlib import Path

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
@click.option(
    "--config-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="config",
    help="Path to configuration directory",
)
def daemon(config_dir: Path):
    """Start the wiki daemon."""
    from llm_wiki.daemon.main import run_daemon

    click.echo(f"Starting daemon with config from {config_dir}...")
    run_daemon(config_dir)


if __name__ == "__main__":
    main()
