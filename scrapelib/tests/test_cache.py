import sys

import requests
from ..cache import CachingSession, MemoryCache, FileCache

DUMMY_URL = 'http://dummy/'
HTTPBIN = 'http://httpbin.org/'


def test_default_key_for_request():
    cs = CachingSession()

    # non-get methods
    for method in ('post', 'head', 'put', 'delete', 'patch'):
        assert cs.key_for_request(method, DUMMY_URL) is None

    # simple get method
    assert cs.key_for_request('get', DUMMY_URL) == DUMMY_URL
    # now with params
    assert cs.key_for_request('get', DUMMY_URL, params={'foo': 'bar'}) == DUMMY_URL + '?foo=bar'
    # params in both places
    assert (cs.key_for_request('get', DUMMY_URL + '?abc=def', params={'foo': 'bar'}) ==
            DUMMY_URL + '?abc=def&foo=bar')


def test_key_param_ordering():
    '''Verifies that two differently ordered but otherwise equivalent
    query strings recieve the same cache key.
    '''
    cs = CachingSession()
    params1 = '?a=1&b=2&c=3'
    params2 = '?c=3&a=1&b=2'

    key1 = cs.key_for_request('get', DUMMY_URL + params1)
    key2 = cs.key_for_request('get', DUMMY_URL + params2)
    assert key1 == key2


def test_key_param_ordering_with_array():
    '''Verifies that that two differently ordered but otherwise equivalent
    query strings continaing array parameters result in the same cache key.
    This should just work, because python's sorted function sorts a list of
    sequences by their first item, then second, etc.
    '''
    cs = CachingSession()
    params1 = '?a[]=jamesturk&a[]=thomnasty&a[]=tags'
    params2 = '?a[]=tags&a[]=jamesturk&a[]=thomnasty'
    params3 = '?a[]=tags&a[]=jamesturk&a[]=thomnasty&intern=cspencer'

    key1 = cs.key_for_request('get', DUMMY_URL + params1)
    key2 = cs.key_for_request('get', DUMMY_URL + params2)
    key3 = cs.key_for_request('get', DUMMY_URL + params3)
    assert key1 == key2
    assert key1 != key3
    assert key2 != key3


def test_default_should_cache_response():
    cs = CachingSession()
    resp = requests.Response()
    # only 200 should return True
    resp.status_code = 200
    assert cs.should_cache_response(resp) is True
    for code in (203, 301, 302, 400, 403, 404, 500):
        resp.status_code = code
        assert cs.should_cache_response(resp) is False


def test_no_cache_request():
    cs = CachingSession()
    # call twice, to prime cache (if it were enabled)
    resp = cs.request('get', HTTPBIN + 'status/200')
    resp = cs.request('get', HTTPBIN + 'status/200')
    assert resp.status_code == 200
    assert resp.fromcache is False


def test_simple_cache_request():
    cs = CachingSession(cache_storage=MemoryCache())
    url = HTTPBIN + 'get'

    # first response not from cache
    resp = cs.request('get', url)
    assert resp.fromcache is False

    assert url in cs.cache_storage.cache

    # second response comes from cache
    cached_resp = cs.request('get', url)
    assert resp.text == cached_resp.text
    assert cached_resp.fromcache is True


def test_cache_write_only():
    cs = CachingSession(cache_storage=MemoryCache())
    cs.cache_write_only = True
    url = HTTPBIN + 'get'

    # first response not from cache
    resp = cs.request('get', url)
    assert resp.fromcache is False

    # response was written to cache
    assert url in cs.cache_storage.cache

    # but second response doesn't come from cache
    cached_resp = cs.request('get', url)
    assert cached_resp.fromcache is False


# test storages #####

def _test_cache_storage(storage_obj):
    # unknown key returns None
    assert storage_obj.get('one') is None

    _content_as_bytes = b"here's unicode: \xe2\x98\x83"
    if sys.version_info[0] < 3:
        _content_as_unicode = unicode("here's unicode: \u2603",
                                      'unicode_escape')
    else:
        _content_as_unicode = "here's unicode: \u2603"

    # set 'one'
    resp = requests.Response()
    resp.headers['x-num'] = 'one'
    resp.status_code = 200
    resp._content = _content_as_bytes
    storage_obj.set('one', resp)
    cached_resp = storage_obj.get('one')
    assert cached_resp.headers == {'x-num': 'one'}
    assert cached_resp.status_code == 200
    cached_resp.encoding = 'utf8'
    assert cached_resp.text == _content_as_unicode


def test_memory_cache():
    _test_cache_storage(MemoryCache())


def test_file_cache():
    fc = FileCache('cache')
    fc.clear()
    _test_cache_storage(fc)
    fc.clear()
