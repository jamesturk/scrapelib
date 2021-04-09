"""
    module providing caching support for requests

    use CachingSession in place of requests.Session to take advantage
"""
import re
import os
import glob
import hashlib
import requests
import sqlite3
import json
from typing import Optional, Dict
from ._types import Response


class CacheResponse(Response):
    fromcache: bool


class CacheStorageBase:
    def get(self, key: str) -> Optional[Response]:
        raise NotImplementedError()

    def set(self, key: str, response: Response) -> None:
        raise NotImplementedError()


class MemoryCache(CacheStorageBase):
    """In memory cache for request responses."""

    def __init__(self) -> None:
        self.cache: Dict[str, Response] = {}

    def get(self, key: str) -> Optional[Response]:
        """Get cache entry for key, or return None."""
        return self.cache.get(key, None)

    def set(self, key: str, response: Response) -> None:
        """Set cache entry for key with contents of response."""
        self.cache[key] = response


class FileCache(CacheStorageBase):
    """
    File-based cache for request responses.

    :param cache_dir: directory for storing responses
    :param check_last_modified:  set to True to compare last-modified
        timestamp in cached response with value from HEAD request
    """

    # file name escaping inspired by httplib2
    _prefix = re.compile(r"^\w+://")
    _illegal = re.compile(r"[?/:|]+")
    _header_re = re.compile(r"([-\w]+): (.*)")
    _maxlen = 200

    def _clean_key(self, key: str) -> str:
        # strip scheme
        md5 = hashlib.md5(key.encode("utf8")).hexdigest()
        key = self._prefix.sub("", key)
        key = self._illegal.sub(",", key)
        return ",".join((key[: self._maxlen], md5))

    def __init__(self, cache_dir: str, check_last_modified: bool = False):
        # normalize path
        self.cache_dir = os.path.join(os.getcwd(), cache_dir)
        self.check_last_modified = check_last_modified
        # create directory
        if not os.path.isdir(self.cache_dir):
            os.makedirs(self.cache_dir)

    def get(self, orig_key: str) -> Optional[Response]:
        """Get cache entry for key, or return None."""
        resp = requests.Response()

        key = self._clean_key(orig_key)
        path = os.path.join(self.cache_dir, key)

        try:
            with open(path, "rb") as f:
                # read lines one at a time
                while True:
                    line = f.readline().decode("utf8").strip("\r\n")
                    # set headers

                    if self.check_last_modified and re.search(
                        "last-modified", line, flags=re.I
                    ):
                        # line contains last modified header
                        head_resp = requests.head(orig_key)

                        try:
                            new_lm = head_resp.headers["last-modified"]
                            old_lm = line[line.find(":") + 1:].strip()
                            if old_lm != new_lm:
                                # last modified timestamps don't match, need to download again
                                return None
                        except KeyError:
                            # no last modified header present, so redownload
                            return None

                    header = self._header_re.match(line)
                    if header:
                        resp.headers[header.group(1)] = header.group(2)
                    else:
                        break
                # everything left is the real content
                resp._content = f.read()

            # status & encoding will be in headers, but are faked
            # need to split spaces out of status to get code (e.g. '200 OK')
            resp.status_code = int(resp.headers.pop("status").split(" ")[0])
            resp.encoding = resp.headers.pop("encoding")
            resp.url = resp.headers.get("content-location", orig_key)
            # TODO: resp.request = request
            return resp
        except IOError:
            return None

    def set(self, key: str, response: Response) -> None:
        """Set cache entry for key with contents of response."""
        key = self._clean_key(key)
        path = os.path.join(self.cache_dir, key)

        with open(path, "wb") as f:
            status_str = "status: {0}\n".format(response.status_code)
            f.write(status_str.encode("utf8"))
            encoding_str = "encoding: {0}\n".format(response.encoding)
            f.write(encoding_str.encode("utf8"))
            for h, v in response.headers.items():
                # header: value\n
                f.write(h.encode("utf8"))
                f.write(b": ")
                f.write(v.encode("utf8"))
                f.write(b"\n")
            # one blank line
            f.write(b"\n")
            f.write(response.content)

    def clear(self) -> None:
        # only delete things that end w/ a md5, less dangerous this way
        cache_glob = "*," + ("[0-9a-f]" * 32)
        for fname in glob.glob(os.path.join(self.cache_dir, cache_glob)):
            os.remove(fname)


class SQLiteCache(CacheStorageBase):
    """SQLite cache for request responses.

    :param cache_path: path for SQLite database file
    :param check_last_modified: set to True to compare last-modified
        timestamp in cached response with value from HEAD request

    """

    _columns = ["key", "status", "modified", "encoding", "data", "headers"]

    def __init__(self, cache_path: str, check_last_modified: bool = False):
        self.cache_path = cache_path
        self.check_last_modified = check_last_modified
        self._conn = sqlite3.connect(cache_path)
        self._conn.text_factory = str
        self._build_table()

    def _build_table(self) -> None:
        """Create table for storing request information and response."""
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS cache
                (key text UNIQUE, status integer, modified text,
                 encoding text, data blob, headers blob)"""
        )

    def set(self, key: str, response: Response) -> None:
        """Set cache entry for key with contents of response."""
        mod = response.headers.pop("last-modified", None)
        status = int(response.status_code)
        rec = (
            key,
            status,
            mod,
            response.encoding,
            response.content,
            json.dumps(dict(response.headers)),
        )
        with self._conn:
            self._conn.execute("DELETE FROM cache WHERE key=?", (key,))
            self._conn.execute("INSERT INTO cache VALUES (?,?,?,?,?,?)", rec)

    def get(self, key: str) -> Optional[Response]:
        """Get cache entry for key, or return None."""
        query = self._conn.execute("SELECT * FROM cache WHERE key=?", (key,))
        rec = query.fetchone()
        if rec is None:
            return None
        rec = dict(zip(self._columns, rec))

        if self.check_last_modified:
            if rec["modified"] is None:
                return None  # no last modified header present, so redownload

            head_resp = requests.head(key)
            new_lm = head_resp.headers.get("last-modified", None)
            if rec["modified"] != new_lm:
                return None

        resp = Response()
        resp._content = rec["data"]
        resp.status_code = rec["status"]
        resp.encoding = rec["encoding"]
        resp.headers = json.loads(rec["headers"])
        resp.url = key
        return resp

    def clear(self) -> None:
        """Remove all records from cache."""
        with self._conn:
            self._conn.execute("DELETE FROM cache")

    def __del__(self) -> None:
        self._conn.close()
