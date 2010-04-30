#!/usr/bin/env python
import os
import time
import unittest
import scrapelib
import threading
import BaseHTTPServer
import SimpleHTTPServer

try:
    import json
except ImportError:
    import simplejson as json


class SilentRequestHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class TestServerThread(threading.Thread):
    def __init__(self, test_object):
        super(TestServerThread, self).__init__()
        self.test_object = test_object
        self.test_object.lock.acquire()

    def run(self):
        try:
            self.server = BaseHTTPServer.HTTPServer(
                ('', 8000), SilentRequestHandler)
        finally:
            self.test_object.lock.release()

        try:
            self.server.serve_forever()
        finally:
            self.server.server_close()

    def stop(self):
        self.server.shutdown()


class ScraperTest(unittest.TestCase):
    def setUp(self):
        self.lock = threading.Lock()
        self.thread = TestServerThread(self)
        self.thread.start()
        self.lock.acquire()

    def tearDown(self):
        self.lock.release()
        self.thread.stop()

    def test_get(self):
        s = scrapelib.Scraper(requests_per_minute=0)
        self.assertEqual('this is a test.',
                         s.urlopen("http://localhost:8000/index.html")[1])

    def test_request_throttling(self):
        requests = 0
        s = scrapelib.Scraper(requests_per_minute=30)

        begin = time.time()
        while time.time() <= (begin + 2):
            s.urlopen("http://localhost:8000/index.html")
            requests += 1

        self.assert_(requests <= 2)

        # We should be able to make many more requests with throttling
        # disabled
        s.throttled = False
        requests = 0
        begin = time.time()
        while time.time() <= (begin + 2):
            s.urlopen("http://localhost:8000/index.html")
            requests += 1

        self.assert_(requests > 10)

    def test_follow_robots(self):
        s = scrapelib.Scraper(follow_robots=True, requests_per_minute=0)
        self.assertRaises(scrapelib.RobotExclusionError, s.urlopen,
                          "http://localhost:8000/private/secret.html")
        self.assertEqual("this is a test.",
                         s.urlopen("http://localhost:8000/index.html")[1])

        s.follow_robots = False
        self.assertEqual("this is a secret.", s.urlopen(
                "http://localhost:8000/private/secret.html")[1])

    def test_urllib2_methods(self):
        old = scrapelib.USE_HTTPLIB2
        scrapelib.USE_HTTPLIB2 = False

        s = scrapelib.Scraper(requests_per_minute=0)

        self.assertRaises(scrapelib.HTTPMethodUnavailableError, s.urlopen,
                          "http://localhost:8000", 'HEAD')

        self.assertRaises(scrapelib.HTTPMethodUnavailableError, s.urlopen,
                          "ftp://example.com", "POST")

        scrapelib.USE_HTTPLIB2 = old

    def test_headers(self):
        s = scrapelib.Scraper(user_agent='test_agent')

        self.assertEqual('test_agent', s._make_headers(
                'http://localhost:8000')['user-agent'])

        # override user_agent
        s.headers = {'user-agent': 'other_agent'}
        self.assertEqual('other_agent', s._make_headers(
                'http://localhost:8000')['user-agent'])

        # callable headers
        s.headers = lambda url: {'req-url': url}
        self.assertEqual('http://localhost:8000', s._make_headers(
                'http://localhost:8000')['req-url'])

        s.disable_compression = True
        self.assertEqual('text/*', s._make_headers(
                'http://localhost:8000')['Accept-Encoding'])

        # override accept-encoding
        s.headers = {'accept-encoding': '*'}
        self.assertEqual('*', s._make_headers(
                'http://localhost:8000')['Accept-encoding'])

if __name__ == '__main__':
    os.chdir(os.path.abspath('./test_root'))
    unittest.main()
