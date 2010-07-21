import os
import sys
import glob
import time
import unittest
import tempfile
from multiprocessing import Process

import flask
import scrapelib

app = flask.Flask(__name__)


@app.route('/')
def index():
    resp = app.make_response("Hello world!")
    return resp


@app.route('/ua')
def ua():
    resp = app.make_response(flask.request.headers['user-agent'])
    resp.headers['cache-control'] = 'no-cache'
    return resp


@app.route('/p/s.html')
def secret():
    return "secret"


@app.route('/redirect')
def redirect():
    return flask.redirect(flask.url_for('index'))


@app.route('/500')
def fivehundred():
    flask.abort(500)


@app.route('/robots.txt')
def robots():
    return """
    User-agent: *
    Disallow: /p/
    Allow: /
    """


def run_server():
    class NullFile(object):
        def write(self, s):
            pass

    sys.stdout = NullFile()
    sys.stderr = NullFile()

    app.run()


class ScraperTest(unittest.TestCase):
    def setUp(self):
        self.cache_dir = tempfile.mkdtemp()
        self.error_dir = tempfile.mkdtemp()
        self.s = scrapelib.Scraper(requests_per_minute=0,
                                   error_dir=self.error_dir,
                                   cache_dir=self.cache_dir,
                                   use_cache_first=True)

    def tearDown(self):
        for path in glob.iglob(os.path.join(self.cache_dir, "*")):
            os.remove(path)
        os.rmdir(self.cache_dir)
        for path in glob.iglob(os.path.join(self.error_dir, "*")):
            os.remove(path)
        os.rmdir(self.error_dir)

    def test_get(self):
        self.assertEqual('Hello world!',
                         self.s.urlopen("http://localhost:5000/"))

    def test_request_throttling(self):
        requests = 0
        s = scrapelib.Scraper(requests_per_minute=30)

        begin = time.time()
        while time.time() <= (begin + 2):
            s.urlopen("http://localhost:5000/")
            requests += 1

        self.assert_(requests <= 2)

        # We should be able to make many more requests with throttling
        # disabled
        s.throttled = False
        requests = 0
        begin = time.time()
        while time.time() <= (begin + 2):
            s.urlopen("http://localhost:5000/")
            requests += 1

        self.assert_(requests > 10)

    def test_user_agent(self):
        resp = self.s.urlopen("http://localhost:5000/ua")
        self.assertEqual(resp, scrapelib._user_agent)

        self.s.user_agent = 'a different agent'
        resp = self.s.urlopen("http://localhost:5000/ua")
        self.assertEqual(resp, 'a different agent')

    def test_default_to_http(self):
        self.assertEqual('Hello world!',
                         self.s.urlopen("localhost:5000/"))

    def test_follow_robots(self):
        self.assertRaises(scrapelib.RobotExclusionError, self.s.urlopen,
                          "http://localhost:5000/p/s.html")
        self.assertRaises(scrapelib.RobotExclusionError, self.s.urlopen,
                          "http://localhost:5000/p/a/t/h/")

        self.s.follow_robots = False
        self.assertEqual("secret",
                         self.s.urlopen("http://localhost:5000/p/s.html"))
        self.assertRaises(scrapelib.HTTPError, self.s.urlopen,
                          "http://localhost:5000/p/a/t/h/")

    def test_error_context(self):
        def raises():
            with self.s.urlopen("http://localhost:5000/"):
                raise Exception('test')

        self.assertRaises(Exception, raises)
        self.assertTrue(os.path.isfile(os.path.join(
            self.error_dir, "http:,,localhost:5000,")))

    def test_404(self):
        self.assertRaises(scrapelib.HTTPError, self.s.urlopen,
                          "http://localhost:5000/does/not/exist")

        self.s.raise_errors = False
        resp = self.s.urlopen("http://localhost:5000/does/not/exist")
        self.assertEqual(404, resp.response.code)

    def test_500(self):
        self.assertRaises(scrapelib.HTTPError, self.s.urlopen,
                          "http://localhost:5000/500")

        self.s.raise_errors = False
        resp = self.s.urlopen("http://localhost:5000/500")
        self.assertEqual(resp.response.code, 500)

    def test_follow_redirect(self):
        resp = self.s.urlopen("http://localhost:5000/redirect")
        self.assertEqual("http://localhost:5000/", resp.response.url)
        self.assertEqual("http://localhost:5000/redirect",
                         resp.response.requested_url)
        self.assertEqual(200, resp.response.code)

        self.s.follow_redirects = False
        resp = self.s.urlopen("http://localhost:5000/redirect")
        self.assertEqual("http://localhost:5000/redirect",
                         resp.response.url)
        self.assertEqual("http://localhost:5000/redirect",
                         resp.response.requested_url)
        self.assertEqual(302, resp.response.code)

    def test_caching(self):
        resp = self.s.urlopen("http://localhost:5000/")
        self.assertFalse(resp.response.fromcache)
        resp = self.s.urlopen("http://localhost:5000/")
        self.assert_(resp.response.fromcache)

        self.s.use_cache_first = False
        resp = self.s.urlopen("http://localhost:5000/")
        self.assertFalse(resp.response.fromcache)

    def test_urlretrieve(self):
        fname, resp = self.s.urlretrieve("http://localhost:5000/")
        with open(fname) as f:
            self.assertEqual(f.read(), "Hello world!")
            self.assertEqual(200, resp.code)
        os.remove(fname)

        (fh, set_fname) = tempfile.mkstemp()
        fname, resp = self.s.urlretrieve("http://localhost:5000/",
                                         set_fname)
        self.assertEqual(fname, set_fname)
        with open(set_fname) as f:
            self.assertEqual(f.read(), "Hello world!")
            self.assertEqual(200, resp.code)
        os.remove(set_fname)


if __name__ == '__main__':
    process = Process(target=run_server)
    process.start()
    time.sleep(0.1)
    unittest.main(exit=False)
    process.terminate()
