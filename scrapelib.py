import time
import urllib2
import urlparse
import functools
import robotparser

try:
    import httplib2
    USE_HTTPLIB2 = True
except ImportError:
    USE_HTTPLIB2 = False


class RobotExclusionError(Exception):

    def __init__(self, message, url, user_agent):
        super(RobotExclusionError, self).__init__(message)
        self.url = url
        self.user_agent = user_agent


class Scraper(object):

    def __init__(self, user_agent='scrapelib 0.1',
                 cache_dir=None, headers={},
                 requests_per_minute=60,
                 follow_robots=True):
        self.headers = headers
        self.user_agent = user_agent

        self.follow_robots = follow_robots
        if self.follow_robots:
            self._robot_parsers = {}

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

    def _robot_allowed(self, user_agent, parsed_url):
        robots_url = urlparse.urljoin(parsed_url.scheme + "://" +
                                      parsed_url.netloc, "robots.txt")

        try:
            parser = self._robot_parsers[robots_url]
        except KeyError:
            parser = robotparser.RobotFileParser()
            parser.set_url(robots_url)
            parser.read()
            self._robot_parsers[robots_url] = parser

        return parser.can_fetch(user_agent, parsed_url.geturl())

    def urlopen(self, url):
        if self.throttled:
            self._throttle()

        parsed_url = urlparse.urlparse(url)

        if callable(self.headers):
            headers = self.headers(url)
        else:
            headers = self.headers

        if 'User-Agent' not in headers:
            headers['User-Agent'] = self.user_agent
        user_agent = headers['User-Agent']

        if parsed_url.scheme in ['http', 'https']:
            if self.follow_robots and not self._robot_allowed(user_agent,
                                                              parsed_url):
                raise RobotExclusionError(
                    "User-Agent '%s' not allowed at '%s'" % (
                        user_agent, url), url, user_agent)

            if USE_HTTPLIB2:
                resp, content = self._http.request(url, 'GET',
                                                   headers=headers)
                return content

        req = urllib2.Request(url, headers=headers)
        resp = urllib2.urlopen(req)
        return resp.read()
