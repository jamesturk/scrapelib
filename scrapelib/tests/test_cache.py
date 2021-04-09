from typing import cast
import requests
from .. import CachingSession
from ..cache import MemoryCache, FileCache, SQLiteCache, CacheStorageBase

DUMMY_URL = "http://dummy/"
HTTPBIN = "http://httpbin.org/"


def test_default_key_for_request() -> None:
    cs = CachingSession()

    # non-get methods
    for method in ("post", "head", "put", "delete", "patch"):
        assert cs.key_for_request(method, DUMMY_URL) is None

    # simple get method
    assert cs.key_for_request("get", DUMMY_URL) == DUMMY_URL
    # now with params
    assert (
        cs.key_for_request("get", DUMMY_URL, params={"foo": "bar"})
        == DUMMY_URL + "?foo=bar"
    )
    # params in both places
    assert (
        cs.key_for_request("get", DUMMY_URL + "?abc=def", params={"foo": "bar"})
        == DUMMY_URL + "?abc=def&foo=bar"
    )


def test_default_should_cache_response() -> None:
    cs = CachingSession()
    resp = requests.Response()
    # only 200 should return True
    resp.status_code = 200
    assert cs.should_cache_response(resp) is True
    for code in (203, 301, 302, 400, 403, 404, 500):
        resp.status_code = code
        assert cs.should_cache_response(resp) is False


def test_no_cache_request() -> None:
    cs = CachingSession()
    # call twice, to prime cache (if it were enabled)
    resp = cs.request("get", HTTPBIN + "status/200")
    resp = cs.request("get", HTTPBIN + "status/200")
    assert resp.status_code == 200
    assert resp.fromcache is False


def test_simple_cache_request() -> None:
    cs = CachingSession(cache_storage=MemoryCache())
    url = HTTPBIN + "get"

    # first response not from cache
    resp = cs.request("get", url)
    assert resp.fromcache is False

    assert url in cast(MemoryCache, cs.cache_storage).cache

    # second response comes from cache
    cached_resp = cs.request("get", url)
    assert resp.text == cached_resp.text
    assert cached_resp.fromcache is True


def test_cache_write_only() -> None:
    cs = CachingSession(cache_storage=MemoryCache())
    cs.cache_write_only = True
    url = HTTPBIN + "get"

    # first response not from cache
    resp = cs.request("get", url)
    assert resp.fromcache is False

    # response was written to cache
    assert url in cast(MemoryCache, cs.cache_storage).cache

    # but second response doesn't come from cache
    cached_resp = cs.request("get", url)
    assert cached_resp.fromcache is False


# test storages #####


def _test_cache_storage(storage_obj: CacheStorageBase) -> None:
    # unknown key returns None
    assert storage_obj.get("one") is None

    _content_as_bytes = b"here's unicode: \xe2\x98\x83"
    _content_as_unicode = "here's unicode: \u2603"

    # set 'one'
    resp = requests.Response()
    resp.headers["x-num"] = "one"
    resp.status_code = 200
    resp._content = _content_as_bytes
    storage_obj.set("one", resp)
    cached_resp = storage_obj.get("one")
    assert cached_resp is not None
    if cached_resp is not None:
        assert cached_resp.headers == {"x-num": "one"}
        assert cached_resp.status_code == 200
        cached_resp.encoding = "utf8"
        assert cached_resp.text == _content_as_unicode


def test_memory_cache() -> None:
    _test_cache_storage(MemoryCache())


def test_file_cache() -> None:
    fc = FileCache("cache")
    fc.clear()
    _test_cache_storage(fc)
    fc.clear()


def test_sqlite_cache() -> None:
    sc = SQLiteCache("cache.db")
    sc.clear()
    _test_cache_storage(sc)
    sc.clear()
