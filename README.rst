Features:
  * HTTP, HTTPS, FTP requests
  * HTTP caching, compression, cookies
  * redirect following
  * request throttling
  * robots.txt compliance (optional)
  * robust error handling

Example: ::

  import scrapelib
  s = scrapelib.Scraper(requests_per_minute=10, allow_cookies=True,
                        follow_robots=True)

  # Grab Google front page
  s.urlopen('http://google.com')

  # Will raise RobotExclusionError
  s.urlopen('http://google.com/search')

  # Will be throttled to 10 HTTP requests per minute
  while True:
      s.urlopen('http://example.com')