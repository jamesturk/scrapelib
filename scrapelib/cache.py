"""
    module includes some basic caching support for requests

    use CachingSession in place of requests.Session
"""
import re
import os
import hashlib
import requests

class CachingSession(requests.Session):
    def __init__(self,
                 headers=None,
                 cookies=None,
                 auth=None,
                 timeout=None,
                 proxies=None,
                 hooks=None,
                 params=None,
                 config=None,
                 prefetch=False,
                 verify=True,
                 cert=None):
        super(CachingSession, self).__init__(headers, cookies, auth, timeout,
                                             proxies, hooks, params, config,
                                             prefetch, verify, cert)
        self.cache = MemoryCache()


    def request_to_key(self, method, url, **kwargs):
        """ Return a cache key from a given set of request parameters.

            Default behavior is to return a complete URL for all GET
            requests, and None otherwise.

            Can be overriden if caching of non-get requests is desired.
        """
        if method != 'get':
            return None

        return requests.Request(url=url,
                                params=kwargs.get('params', {})).full_url


    def should_cache_response(self, response):
        """ Check if a given Response object should be cached.

            Default behavior is to only cache responses with a 200
            status code.
        """
        return response.status_code == 200

    def request(self, method, url, **kwargs):
        """ Override, wraps Session.request in caching.

            Cache is only used if request_to_key returns a valid key
            and should_cache_response was true as well.
        """
        resp = None

        request_key = self.request_to_key(method, url, **kwargs)

        if request_key:
            resp = self.cache.get(request_key)

        if resp:
            resp.fromcache = True
        else:
            resp = super(CachingSession, self).request(method, url, **kwargs)
            # save to cache if request and response meet criteria
            if request_key and self.should_cache_response(resp):
                self.cache.set(method, url, resp)

        return resp


class MemoryCache(object):
    def __init__(self):
        self.cache = {}

    def get(self, key):
        return self.cache.get(url, None)

    def set(self, key, response):
        self.cache[key] = response


class FileCache(object):
    # file name escaping inspired by httplib2
    _prefix = re.compile(r'^\w+://')
    _illegal = re.compile(r'[?/:|]+')
    _header_re = re.compile(r'([-\w]+): (.*)')
    _maxlen = 200

    def _clean_key(self, key):
        # strip scheme
        md5 = hashlib.md5(key).hexdigest()
        key = self._prefix.sub('', key)
        key = self._illegal.sub(',', key)
        return ','.join((key[:self._maxlen], md5))

    def __init__(self, cache_dir):
        self.cache_dir = cache_dir

    def get(self, orig_key):
        resp = requests.Response()

        key = self._clean_key(orig_key)
        path = os.path.join(self.cache_dir, key)

        with open(path) as f:
            lines = f.readlines()
            for num, line in enumerate(lines):
                # set headers
                header = self._header_re.match(line)
                if header:
                    resp.headers[header.group(1)] = header.group(2).strip('\r')
                else:
                    break
            # skip a line, everything after that is good
            resp._content = '\n'.join(lines[num+1:])

        resp.status_code = int(headers['status'])
        resp.url = headers['content-location'] or orig_key
        #TODO: resp.request = request
        return resp

    def set(self, key, response):
        if method == 'get':
            self.cache[key] = response
