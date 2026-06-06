# -*- coding: utf-8 -*-
"""
Created on Mon Mar 17 17:05:18 2025

@author: Brian Peltonen
Copyright: Parcosm.ai, Inc.
"""
from __future__ import annotations

import ast
import datetime
import os
import re
import sys
from pathlib import Path
from string import Template
from typing import Any, Dict, Optional, Union


def _find_conf_file(file_path: str) -> Path | None:
    """Resolve a conf file: absolute/cwd path first, then each ``sys.path`` entry."""
    p = Path(file_path).expanduser()
    if p.is_file():
        return p.resolve()
    if p.is_absolute():
        return None
    for entry in sys.path:
        if not entry:
            entry = os.getcwd()
        candidate = Path(entry).expanduser() / file_path
        if candidate.is_file():
            return candidate.resolve()
    return None


class CastedDict:
    def __init__(self, file_path: Optional[str] = None):
        """
        Initialize the TypedDict, optionally loading data from a conf file.

        Expected line format: ``key value type`` (whitespace-separated).
        """
        self._data: Dict[str, Dict[str, str]] = {}

        if file_path:
            self.load_from_conf_with_local_override(file_path)

        for i in range(1, len(sys.argv)):
            if sys.argv[i] == "-c":
                arg = sys.argv[i + 1]
                k, v = arg.split("=", 1)
                if k not in self._data:
                    self._data[k] = {"type": "str", "value": v}
                else:
                    self._data[k]["value"] = v

    def load_from_conf_with_local_override(self, file_path: str) -> None:
        found = False
        resolved = _find_conf_file(file_path)
        if resolved is not None:
            self.load_from_conf(str(resolved))
            found = True

        resolved_local = _find_conf_file(file_path + ".local")
        if resolved_local is not None:
            self.load_from_conf(str(resolved_local))
            found = True
        if not found:
            raise FileNotFoundError(
                f"Configuration file {file_path} not found (cwd, absolute, or sys.path), "
                f"nor {file_path}.local"
            )

    def load_from_conf(self, file_path: str) -> None:
        """Load data from a conf file into the CastedDict."""
        with open(file_path, "r") as conf_file:
            lines = conf_file.read().replace(",\n", ",").split("\n")

            for line in lines:
                key_rest = re.split(r"\s+", line.strip(), maxsplit=1)
                if len(key_rest) != 2:
                    continue

                key, rest = key_rest

                if rest.startswith("[") and rest.endswith("]"):
                    value = rest
                    datum_type = "list"
                else:
                    dq_match = re.match(r'^"([^"]*)"\s*(\w+)?$', rest)
                    if dq_match:
                        value_with_type = [dq_match.group(1)]
                        if dq_match.group(2):
                            value_with_type.append(dq_match.group(2))
                    else:
                        value_with_type = re.split(r"\s+", rest)

                    if len(value_with_type) == 1:
                        value = value_with_type[0]
                        datum_type = "str"
                    elif len(value_with_type) == 2:
                        value, datum_type = value_with_type
                    else:
                        continue

                self._data[key] = {
                    "value": value,
                    "type": datum_type.lower() if datum_type else "str",
                }

    def get(self, key: str, default=None):
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def __getitem__(self, key: str) -> Any:
        """Get an item, casting it to the specified type."""
        if key not in self._data:
            raise KeyError(f"Key '{key}' not found")

        item = self._data[key]
        type_str = item["type"]

        value = item["value"]
        if value.startswith("[") and value.endswith("]"):
            try:
                parsed_list = ast.literal_eval(value)
                if not isinstance(parsed_list, list):
                    raise ValueError
                if type_str == "int":
                    return [int(v) for v in parsed_list]
                elif type_str == "float":
                    return [float(v) for v in parsed_list]
                elif type_str == "str":
                    return [str(v) for v in parsed_list]
                else:
                    return parsed_list

            except (ValueError, SyntaxError):
                raise ValueError(f"Invalid list format: {item}")

        value = item["value"].strip()
        value = Template(value).substitute(os.environ)
        type_str = item["type"]

        try:
            if value == "True":
                return True
            elif value == "False":
                return False
            elif type_str == "str":
                return value
            elif type_str == "int":
                return int(value)
            elif type_str == "float":
                return float(value)
            elif type_str in ["path", "filepath"]:
                return Path(os.path.expanduser(os.path.normpath(value)))
            elif type_str == "date":
                for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y"]:
                    try:
                        return datetime.datetime.strptime(value, fmt).date()
                    except ValueError:
                        continue
                raise ValueError(f"Unable to parse date: {value}")
            elif type_str == "timestamp":
                for fmt in [
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M:%S.%f",
                    "%Y-%m-%dT%H:%M:%S.%f",
                ]:
                    try:
                        return datetime.datetime.strptime(value, fmt)
                    except ValueError:
                        continue
                raise ValueError(f"Unable to parse timestamp: {value}")
            else:
                return value
        except (ValueError, TypeError):
            return value

    def __setitem__(self, key: str, value: Union[str, tuple]):
        if isinstance(value, tuple):
            val, type_str = value
            self._data[key] = {
                "value": str(val),
                "type": type_str.lower(),
            }
        else:
            self._data[key] = {
                "value": str(value),
                "type": "str",
            }

    def keys(self):
        return self._data.keys()
