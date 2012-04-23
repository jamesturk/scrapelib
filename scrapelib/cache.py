"""
    module providing caching support for requests

    use CachingSession in place of requests.Session to take advantage
"""
import re
import os
import glob
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
                 cert=None,
                 cache_storage=None,
                ):
        super(CachingSession, self).__init__(headers, cookies, auth, timeout,
                                             proxies, hooks, params, config,
                                             prefetch, verify, cert)
        self.cache_storage = cache_storage

    def key_for_request(self, method, url, **kwargs):
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

            Cache is only used if key_for_request returns a valid key
            and should_cache_response was true as well.
        """
        # short circuit if cache isn't configured
        if not self.cache_storage:
            resp = super(CachingSession, self).request(method, url, **kwargs)
            resp.fromcache = False
            return resp

        resp = None
        method = method.lower()

        request_key = self.key_for_request(method, url, **kwargs)

        if request_key and not self.config.get('cache_write_only'):
            resp = self.cache_storage.get(request_key)

        if resp:
            resp.fromcache = True
        else:
            resp = super(CachingSession, self).request(method, url, **kwargs)
            # save to cache if request and response meet criteria
            if request_key and self.should_cache_response(resp):
                self.cache_storage.set(request_key, resp)
            resp.fromcache = False

        return resp


class MemoryCache(object):
    def __init__(self):
        self.cache = {}

    def get(self, key):
        return self.cache.get(key, None)

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
        md5 = hashlib.md5(key.encode('utf8')).hexdigest()
        key = self._prefix.sub('', key)
        key = self._illegal.sub(',', key)
        return ','.join((key[:self._maxlen], md5))

    def __init__(self, cache_dir):
        # normalize path
        self.cache_dir = os.path.join(os.getcwd(), cache_dir)
        # create directory
        os.path.isdir(self.cache_dir) or os.makedirs(self.cache_dir)

    def get(self, orig_key):
        resp = requests.Response()

        key = self._clean_key(orig_key)
        path = os.path.join(self.cache_dir, key)

        try:
            with open(path) as f:
                lines = f.readlines()
                for num, line in enumerate(lines):
                    # set headers
                    header = self._header_re.match(line)
                    if header:
                        resp.headers[header.group(1)] = \
                                header.group(2).strip('\r')
                    else:
                        break
                # skip a line, everything after that is good
                resp._content = ('\n'.join(lines[num + 1:])).encode('utf8')

            # status will be in headers but isn't a real header
            resp.status_code = int(resp.headers.pop('status'))
            resp.url = resp.headers['content-location'] or orig_key
            #TODO: resp.request = request
            return resp
        except IOError:
            return None

    def set(self, key, response):
        key = self._clean_key(key)
        path = os.path.join(self.cache_dir, key)

        with open(path, 'wb') as f:
            status_str = 'status: {0}\n'.format(response.status_code)
            f.write(status_str.encode('utf8'))
            for h, v in response.headers.items():
                # header: value\n
                f.write(h.encode('utf8'))
                f.write(b': ')
                f.write(v.encode('utf8'))
                f.write(b'\n')
            # one blank line
            f.write(b'\n')
            f.write(response.content)

    def clear(self):
        # only delete things that end w/ a md5, less dangerous this way
        cache_glob = '*,' + ('[0-9a-f]' * 32)
        for fname in glob.glob(os.path.join(self.cache_dir, cache_glob)):
            os.remove(fname)
