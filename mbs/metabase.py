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
from typing import Union
from platformdirs import user_config_dir
import jinja2


logger = logging.getLogger()


class MbsException(Exception):
    """
    Non critical errors.
    """


class MbsFatalException(Exception):
    """
    Critical errors.
    """


class Metabase:
    appname = "mbs"
    author = "mbs"
    user_config_dir = user_config_dir(appname, author)
    remotes_config_file = os.path.join(user_config_dir, "remotes.json")
    include_default_folder = "include"

    def __init__(self, include_folder=include_default_folder, init_url=None):
        self.mbs_tag = "## mbs_controlled ##"

        self.include_folder = include_folder

        if init_url:
            if not os.path.isfile(".mbs"):
                init_url = init_url.strip("/")  # strip trailing slashes
                with open(".mbs", "w") as f:
                    config = {"url": init_url}
                    json.dump(config, f)
                    logger.info(f"Created \".mbs\" file with url \"{init_url}\" in the current directory.")
            else:
                raise MbsFatalException("There is already an mbs repo in this folder.")
        else:
            if os.path.isfile(".mbs"):
                with open(".mbs") as f:
                    self.config = json.load(f)
            else:
                raise MbsFatalException("This folder is not a valid mbs repo. Use 'mbs init <url>' "
                                        "to create a new repo first.")

            if os.path.isfile(self.user_config_dir):
                with open(self.remotes_config_file) as f:
                    credentials = json.load(f)

    @property
    def remotes(self):
        if os.path.isfile(self.remotes_config_file):
            with open(self.remotes_config_file) as f:
                return json.load(f)
        else:
            raise MbsFatalException("You are currently not logged in. Use \"mbs login\" with your credentials")

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
                raise MbsFatalException("Error: " + req.text)
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
                raise MbsFatalException("Error: " + req.text)

        return req.json()

    def renew_session(self):
        if self.username and self.password:
            self.login(self.username, self.password)
        else:
            raise MbsFatalException("Can't renew session, because you haven't saved your credentials. "
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
            raise MbsFatalException(session_req.text)

    def pull(self, card_id=False, overwrite=False):
        existing_ids = []
        for file in list(Path.cwd().rglob("*.json")):  # gets files also in subdirectories
            with open(file) as f:
                card = json.load(f)
                if "id" in card:
                    existing_ids.append(card["id"])

        if card_id:
            card = self._get("/api/card/" + str(card_id))
            self.__write_card(card, overwrite)
        else:
            cards = self._get("/api/card")
            c = 0
            for card in cards:
                if card["id"] in existing_ids:
                    logger.info(f"Skipping already existing id {card['id']}.")
                    continue
                if ("native" in card["dataset_query"] and self.mbs_tag in card["dataset_query"]["native"]["query"]) or \
                        (isinstance(card["description"], str) and self.mbs_tag in card["description"]):
                    self.__write_card(card, overwrite)
                    c += 1
            logger.info(f"Found {c} new cards/questions with the mbs tag \"{self.mbs_tag}\".")

    def merge(self, filename=""):
        if filename:
            self.__merge_file(filename)
        else:
            for file in list(Path.cwd().rglob("*.json")):  # gets files also in subdirectories
                self.__merge_file(file)

    def __merge_file(self, filename):
        if os.path.isfile(filename):
            with open(filename) as f:
                card = json.load(f)
                if "id" in card:
                    updated_card = self._get("/api/card/" + str(card["id"]))
                    if card["query_type"] == "native" and updated_card["query_type"] == "native":
                        updated_card["dataset_query"]["native"]["query"] = card["dataset_query"]["native"]["query"]
                        self.__write_card(updated_card, overwrite=True, filename=filename)
                    else:
                        logger.warning(f"{filename}: \"merge\" currently supports only native sql queries.")
                else:
                    logger.error(f"{filename}: There is no card/question id this file.")
        else:
            logger.error(f"File \"{filename}\" wasn't found.")

    def __write_card(self, card, overwrite=False, filename=""):
        logger.info(f"Found mbs tag on cards/questions: {card['id']} ({card['name']})")
        title = "".join(c for c in card["name"] if c.isalnum() or c in (' ', '.', '_', '-')).rstrip()[:256]
        if not filename:
            filename = f"{card['id']} - {title}.json"
        if not os.path.isfile(f"{filename}") or overwrite:
            # filter out some unnecessary values, that metabase will manage himself
            try:
                del card["created_at"]
                del card["creator"]
                del card["creator_id"]
                del card["last-edit-info"]
                del card["made_public_by_id"]
                del card["public_uuid"]
                del card["updated_at"]
                del card["embedding_params"]
                del card["enable_embedding"]
                del card["average_query_time"]
                del card["last_query_start"]
                del card["moderation_reviews"]
            except KeyError:
                pass

            with open(f"{filename}", "w") as f:
                json.dump(card, f, sort_keys=True, indent=4)
                f.truncate()
                logger.info(f"Wrote \"{filename}\".")
        else:
            logger.warning(f"File \"{filename}\" already exists. You can force to overwrite "
                                f"with the \"-o\" flag.")

    def push(self, filename: str = "all", render_only=False):
        if filename:
            if render_only:
                logger.info(f"Rendering file: {filename}")
                output = self.render(filename)
                logger.info(f"Rended \"{filename}\" to:")
                print(output)
                self.check(output)
            else:
                logger.info(f"Rendering and uploading file: {filename}")
                output = self.render(filename)
                if self.check(output):
                    card = json.loads(output)
                    self._put(f"/api/card/{card['id']}", card)
        else:
            for file in list(Path.cwd().rglob("*.json")):  # gets files also in subdirectories
                if self.include_folder not in os.path.dirname(file):
                    logger.info(f"Rendering and uploading file: {file}")
                    output = self.render(file)
                    if render_only:
                        print(output)
                    else:
                        if self.check(output):
                            card = json.loads(output)
                            self._put(f"/api/card/{card['id']}", card)

    def render(self, filename):
        jenv = jinja2.Environment(
            loader=jinja2.FileSystemLoader([os.getcwd(), self.include_folder], followlinks=True),
            autoescape=False
        )
        jenv.filters['json'] = lambda a: json.dumps(a)[1:-1]
        if sys.platform == "win32":
            template_path = PureWindowsPath(os.path.relpath(filename, os.getcwd())).as_posix()
        else:
            template_path = os.path.relpath(filename, os.getcwd())
        try:
            output = jenv .get_template(
                template_path
            ).render(
                is_mbs=True,
                mbs_url=self.config["url"],
                mbs_file=template_path,
                mbs_file_abs=filename
            )
        except jinja2.TemplateSyntaxError as t:
            logger.error(f"Render error: {t.filename} - Line {t.lineno} - {t.message}")
            logger.error(f"Line with the error > {t.source.splitlines()[t.lineno-1]}")
            raise MbsFatalException("Couldn't render template.")
        if self.mbs_tag not in output:
            raise MbsException(f"MBS tag (\"{self.mbs_tag}\") not found in the output! "
                            f"Mark this question/card as controlled by MBS, to avoid confusions with online "
                            f"editors.")
        return output

    def check(self, data: Union[str, dict]):
        """
        Validate data before uploading to metabase.
        """
        error = False
        try:
            if isinstance(data, str):
                card = json.loads(data)
            else:
                card = data
        except json.JSONDecodeError as e:
            logger.error("JSON decode error while checking this output:")
            # print(data, "\nError:", e)
            logger.error(f"Render error: Line {e.lineno} - {e.msg}")
            logger.error(f"Line with the error > {data.splitlines()[e.lineno - 1]}")
            raise MbsException("JSON invalid.")
        if "id" not in card:
            logger.error("There is no id set in your data.")
            error = True
        if "name" not in card:
            logger.error("There is no name set in your data.")
            error = True
        if error:
            raise MbsFatalException("Data invalid.")
        else:
            return True
