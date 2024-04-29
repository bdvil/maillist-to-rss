import click

from .aliases import alias_group
from .email import email_group
from .server import serve_command


@click.group()
def root():
    pass


root.add_command(serve_command)
root.add_command(alias_group)
root.add_command(email_group)
