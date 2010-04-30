import time
import urllib2
import urlparse
import functools

try:
    import httplib2
    USE_HTTPLIB2 = True
except ImportError:
    USE_HTTPLIB2 = False


class Scraper(object):

    def __init__(self, user_agent='scrapelib 0.1',
                 cache_dir=None, headers={},
                 requests_per_minute=60):
        self.headers = headers

        if requests_per_minute > 0:
            self.throttled = True
            self.request_frequency = 60.0 / requests_per_minute
            self.last_request = 0
        else:
            self.throttled = False

        if cache_dir and not USE_HTTPLIB2:
            print "httplib2 not available, caching will be disabled."

        if USE_HTTPLIB2:
              self._http = httplib2.Http(cache_dir)

    def _throttle(self):
        now = time.time()
        diff = self.request_frequency - (now - self.last_request)
        if diff > 0:
            print "sleeping for %fs" % diff
            time.sleep(diff)
            self.last_request = time.time()
        else:
            self.last_request = now

    def urlopen(self, url):
        if self.throttled:
            self._throttle()

        parsed_url = urlparse.urlparse(url)

        if callable(self.headers):
            headers = self.headers(url)
        else:
            headers = self.headers

        if parsed_url.scheme in ['http', 'https'] and USE_HTTPLIB2:
            resp, content = self._http.request(url, 'GET', headers=headers)

            return content
        else:
            req = urllib2.Request(url, headers=headers)
            resp = urllib2.urlopen(req)

            return resp.read()
