import click

from .server import serve_command


@click.group()
def root():
    pass


root.add_command(serve_command)
