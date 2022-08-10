#!/usr/bin/env python3
#
# Copyright (C) 2022  Robert Lieback
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
import logging
import sys
import click
import click_log
from mbs.metabase import Metabase, MbsException, MbsFatalException
logger = logging.getLogger()
click_log.basic_config(logger)


__author__ = "Robert Lieback"
__version__ = '1.0-beta.3'


@click.group()
@click_log.simple_verbosity_option(logger)
@click.version_option(version=__version__, prog_name="MetaBaseSync - MBS")
@click.pass_context
def cli(ctx):
    # ensure that ctx.obj exists and is a dict (in case `cli()` is called
    # by means other than the `if` block below)
    ctx.ensure_object(dict)


@cli.command()
@click.argument('card_id', default=0)
@click.option("-o", "--overwrite",
              is_flag=True,
              help="Overwrite existing files"
              )
@click_log.simple_verbosity_option(logger)
def pull(card_id, overwrite):
    """
    Use this to download new questions in your local repo folder.
    Optional you can pass a CARD_ID to only pull this card/question.
    """
    Metabase().pull(card_id, overwrite)


@cli.command()
@click.argument('filename', default="")
@click_log.simple_verbosity_option(logger)
def merge(filename):
    """
    Updates your local files with some data from metabase. This is useful to get e.g. update the
    visualisation settings only from metabase, because they are better to edit in the metabase frontend.
    It currently works only for native queries by keeping the native query while updating all other data.
    Without FILENAME all files are updated, so be carefull.
    """
    Metabase().merge(filename=filename)


@cli.command()
@click.option("--include_folder",
              default=Metabase.include_default_folder,
              help=f"Adds an additional folder where jinja2 looks for include files.",
              show_default=True)
@click.option("-ro",
              "--render_only",
              is_flag=True,
              help="Render to the console without uploading to metabase. Useful for debugging."
              )
@click.argument('filename', default="")
@click_log.simple_verbosity_option(logger)
def push(filename, include_folder, render_only):
    """
    Push all or a single file to Metabase. Your JSON files will be rendered as a jinja2 template file.
    """
    Metabase(include_folder=include_folder).push(filename, render_only)


@cli.command()
@click.argument('url')
@click_log.simple_verbosity_option(logger)
def init(url):
    """
    Initialise a new repository in this directory.
    """
    Metabase(init_url=url)


@cli.command()
@click.argument('username')
@click.argument('password')
@click_log.simple_verbosity_option(logger)
@click.option("-s", "--dont-save-credentials",
              is_flag=True,
              help=f"Save only the session cookie, not username/password to '{Metabase.user_config_dir}'."
              )
def login(username, password, dont_save_credentials):
    """
    Login to the Metabase instance of the current repository.
    """
    mb = Metabase()
    if mb.login(username, password, dont_save_credentials):
        logger.info("Login successful.")


def entrypoint():
    """
    Handle exceptions and click
    """
    try:
        cli(obj={})
    except MbsException as ex:
        logger.error(ex)
        sys.exit(-1)
    except MbsFatalException as ex:
        logger.critical(ex)
        sys.exit(-2)
    except Exception as ex:
        logger.error(f"{type(ex).__name__}: {ex}")


if __name__ == "__main__":
    entrypoint()
