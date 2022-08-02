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
import json
import logging
import sys
import os
from pathlib import Path, PureWindowsPath
import requests
import click
import click_log
from typing import Union
from platformdirs import user_config_dir
import jinja2

__author__ = "Robert Lieback"
__version__ = '1.0-beta.1'


logger = logging.getLogger(__name__)
click_log.basic_config(logger)


class MbsException(Exception):
    def __init__(self, msg):
        logger.error(msg)
        sys.exit()


class Metabase:
    appname = "mbs"
    author = "mbs"
    user_config_dir = user_config_dir(appname, author)
    remotes_config_file = os.path.join(user_config_dir, "remotes.json")
    include_default_folder = "include"

    def __init__(self, include_folder=include_default_folder, init_url=None):
        self.mbs_tag = "## mbs_controlled ##"

        self.include_folder = include_folder

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel("INFO")

        if init_url:
            if not os.path.isfile(".mbs"):
                init_url = init_url.strip("/")  # strip trailing slashes
                with open(".mbs", "w") as f:
                    config = {"url": init_url}
                    json.dump(config, f)
                    logger.info(f"Created \".mbs\" file with url \"{init_url}\" in the current directory.")
            else:
                raise MbsException("There is already an mbs repo in this folder.")
        else:
            if os.path.isfile(".mbs"):
                with open(".mbs") as f:
                    self.config = json.load(f)
            else:
                raise MbsException("This folder is not a valid mbs repo. Use 'mbs init <url>' to create a new repo first.")

            if os.path.isfile(self.user_config_dir):
                with open(self.remotes_config_file) as f:
                    credentials = json.load(f)

    @property
    def remotes(self):
        if os.path.isfile(self.remotes_config_file):
            with open(self.remotes_config_file) as f:
                return json.load(f)
        else:
            raise MbsException("You are currently not logged in. Use \"mbs login\" with your credentials")

    @property
    def session(self):
        if self.remotes:
            return self.remotes[self.config["url"]]["session"]
        else:
            return False

    @property
    def username(self):
        if self.remotes:
            return self.remotes[self.config["url"]]["username"]
        else:
            return False

    @property
    def password(self):
        if self.remotes:
            return self.remotes[self.config["url"]]["password"]
        else:
            return False

    def _get(self, path):
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "X-Metabase-Session": self.session,
            'User-Agent': 'MetaBaseSync'
        }
        req = requests.get(self.config["url"] + path, headers=headers)
        if req.status_code not in [200]:
            if req.text == "Unauthenticated":
                self.renew_session()
                return self._get(path)
            else:
                raise MbsException("Error: " + req.text)
        return req.json()

    def _put(self, path, data):
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "X-Metabase-Session": self.session,
            'User-Agent': 'MetaBaseSync'
        }
        req = requests.put(self.config["url"] + path, headers=headers, json=data)
        if req.status_code not in [200, 202]:
            if req.text == "Unauthenticated":
                self.renew_session()
                return self._put(path, data)
            else:
                raise MbsException("Error: " + req.text)

        return req.json()

    def renew_session(self):
        if self.username and self.password:
            self.login(self.username, self.password)
        else:
            raise MbsException("Can't renew session, because you haven't saved your credentials. "
                            "Please use \"mbs login --dont-save-credentials <username> <password>\" again.")

    def login(self, username: str, password: str, dont_save_credentials: bool = False):
        url = self.config["url"]

        if os.path.isfile(self.remotes_config_file):  # we have credentials
            with open(self.remotes_config_file) as f:
                credentials = json.load(f)
        else:
            credentials = {}

        session_req = requests.post(url + "/api/session", json={"username": username, "password": password})

        if session_req.status_code == 200 and "id" in session_req.json():  # success, lets save that

            credentials[url] = {}

            credentials[url]["session"] = session_req.json()["id"]
            if not dont_save_credentials:
                credentials[url]["username"] = username
                credentials[url]["password"] = password

            if not os.path.exists(self.user_config_dir):
                os.makedirs(self.user_config_dir)

            if os.path.isfile(self.remotes_config_file):
                os.unlink(self.remotes_config_file)

            with open(self.remotes_config_file, "w") as f:
                json.dump(credentials, f, sort_keys=True, indent=4)
                f.truncate()
            return True
        else:
            raise MbsException(session_req.text)

    def pull(self, card_id=False, overwrite=False):
        if card_id:
            card = self._get("/api/card/" + str(card_id))
            self.write_card(card, overwrite)
        else:
            cards = self._get("/api/card")
            c = 0
            for card in cards:
                if card["dataset_query"]["type"] == "native":  # we only manage native sql for now
                    if self.mbs_tag in card["dataset_query"]["native"]["query"]:
                        self.write_card(card, overwrite)
                        c += 1
            logger.info(f"Found {c} native sql cards/questions with the mbs tag \"{self.mbs_tag}\".")

    def write_card(self, card, overwrite=False):
        if self.mbs_tag in card["dataset_query"]["native"]["query"]:
            self.logger.info(f"Found mbs tag on native sql with id: {card['id']} ({card['name']})")
            title = "".join(c for c in card["name"] if c.isalnum() or c in (' ', '.', '_')).rstrip()[:256]
            filename = f"{card['id']}-{title}"
            if not os.path.isfile(f"{filename}.json") or overwrite:
                with open(f"{filename}.json", "w") as f:
                    json.dump(card, f, sort_keys=True, indent=4)
                    f.truncate()
                    self.logger.info(f"Created \"{filename}.json\".")
            else:
                self.logger.warning(f"File \"{filename}.json\" already exists. You can force to overwrite with the \"-o\" flag.")
        else:
            logger.info(f"The card/question with this id has no mbs tag. Please add \"{self.mbs_tag}\" in the query as a comment.")

    def push(self, filename: str = "all", render_only=False):
        if filename:
            if render_only:
                self.logger.info(f"Rendering file: {filename}")
                output = self.render(filename)
                logger.info(f"Rended \"{filename}\" to:")
                print(output)
                self.check(output)
            else:
                self.logger.info(f"Rendering and uploading file: {filename}")
                output = self.render(filename)
                if self.check(output):
                    card = json.loads(output)
                    self._put(f"/api/card/{card['id']}", card)
        else:
            for file in list(Path.cwd().rglob("*.json")):  # gets files also in subdirectories
                if self.include_folder not in os.path.dirname(file):
                    # print(file, os.path.basename(file), os.path.dirname(file), os.path.relpath(file, os.getcwd()))
                    self.logger.info(f"Rendering and uploading file: {file}")
                    output = self.render(file)
                    if render_only:
                        print(output)
                    else:
                        if self.check(output):
                            card = json.loads(output)
                            self._put(f"/api/card/{card['id']}", card)

    def render(self, filename):
        def escape_json(data: str):
            return json.dumps(data).strip("\"")

        jenv = jinja2.Environment(
            loader=jinja2.FileSystemLoader([os.getcwd(), self.include_folder], followlinks=True),
            autoescape=False
        )
        jenv.filters['json'] = escape_json
        if sys.platform == "win32":
            template_path = PureWindowsPath(os.path.relpath(filename, os.getcwd())).as_posix()
        else:
            template_path = os.path.relpath(filename, os.getcwd())
        output = jenv .get_template(
            template_path
        ).render(
            is_mbs=True,
            mbs_url=self.config["url"],
            mbs_file=template_path,
            mbs_file_abs=filename
        )
        if self.mbs_tag not in output:
            raise MbsException(f"MBS tag (\"{self.mbs_tag}\") not found in the output! "
                            f"Mark this question/card as controlled by MBS, to avoid confusions with online "
                            f"editors.")
        return output

    def check(self, data: Union[str, dict]):
        """
        Validate data before uploading to metabase.
        """
        try:
            if isinstance(data, str):
                card = json.loads(data)
            else:
                card = data
        except json.JSONDecodeError as e:
            logger.error("JSON decode error while checking this output:")
            print(data)
            raise
        error = False
        if "id" not in card:
            logger.error("There is no id set in your data.")
            error = True
        if "name" not in card:
            logger.error("There is no name set in your data.")
            error = True
        if error:
            raise MbsException("Data invalid.")
        else:
            return True


@click.group()
@click_log.simple_verbosity_option(logger)
@click.version_option(version=__version__, prog_name="MetaBaseSync - MBS")
@click.pass_context
def cli(ctx):
    # ensure that ctx.obj exists and is a dict (in case `cli()` is called
    # by means other than the `if` block below)
    sys.tracebacklimit = 0  # Hide the traceback
    ctx.ensure_object(dict)
    # ctx.obj["mb"] = Metabase(include_folder=include_folder)


@cli.command()
@click.argument('card_id', default=0)
@click.option("-o", "--overwrite",
              is_flag=True,
              help=f"Overwrite existing files"
              )
@click_log.simple_verbosity_option(logger)
def pull(card_id, overwrite):
    Metabase().pull(card_id, overwrite)


@cli.command()
@click.option("--include_folder", default=Metabase.include_default_folder, help=f"The folder where jinja2 looks for include files.", show_default=True)
@click.option("-ro",
              "--render_only",
              is_flag=True,
              help="Render to the console without uploading to metabase. Useful for debugging."
              )
@click.argument('filename', default="")
@click_log.simple_verbosity_option(logger)
def push(filename, include_folder, render_only):
    Metabase(include_folder=include_folder).push(filename, render_only)


@cli.command()
@click.argument('url')
@click_log.simple_verbosity_option(logger)
def init(url):
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
    mb = Metabase()
    if mb.login(username, password, dont_save_credentials):
        logger.info("Login successful.")


if __name__ == "__main__":
    cli(obj={})
