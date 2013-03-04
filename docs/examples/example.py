#!/usr/bin/python

# This program will demonstrate the use of the scrapelib library to
# load pages linked from a particular web page.

# This program is Copyright 2013 (c) Olivier Berger + Institutl Mines-Telecom
# This program is provided under the terms of the same license as the
# scrapelib library (see accompanying LICENSE file)


import sys, os
from HTMLParser import HTMLParser
import re
from urlparse import urljoin
from BeautifulSoup import BeautifulSoup
import requests.exceptions
import scrapelib


# Setup a file cache in the .cache subdir. When run twice, data will
# be reloaded from the cache instead of performing network requests.
filecache = scrapelib.FileCache('.cache')

# config's 'verbose' is passed to the Requests library, to trace
# network requests, which will appear like :
# 2013-03-04T13:47:50.943934   GET   http://sunlightfoundation.com/
s = scrapelib.Scraper(requests_per_minute=10, accept_cookies=True,
                      follow_robots=True, cache_obj=filecache, cache_write_only=False, 
                      config={'verbose':sys.stderr}, raise_errors=False, follow_redirects=False)

# We will load the following page and all <a href> links starting from it
index_url = 'http://sunlightfoundation.com/'

tempfilename, response = s.urlretrieve(index_url)

if response.status_code != 200:
    os.remove(tempfilename)
    sys.stderr.write('Warning: Could not load ' + index_url + ' error ' + response.status_code + '.\n')
    sys.exit(1)

# Parser for <a href> links
# an alternative is to use BeautifulSoup (see below)
class LinksExtractor(HTMLParser):
   def __init__(self):
       HTMLParser.__init__(self)
       self.links = []
       
   def handle_starttag(self, tag, attrs):
       if tag == 'a':
           if len(attrs) > 0 :
               for attr in attrs :
                   if attr[0] == "href":
                       self.links.append(attr[1])

   def get_links(self):
      return self.links


htmlparser = LinksExtractor()

tempfile = open(tempfilename)
htmlparser.feed(tempfile.read())
htmlparser.close()

links = htmlparser.get_links()

r = re.compile('http://')

# Iterate over links
for link in links:
    if not r.match(link):
        # render links absolute URLs
        link = urljoin(index_url, link)
        # if not a HTTP/HTTPS URL (mailto or other), skip it
        if not r.match(link):
            sys.stderr.write('Warning: Skipping non-HTTP URI ' + link + '.\n')
            continue
    try:
        contents = s.urlopen(link)
    except (scrapelib.RobotExclusionError, requests.exceptions.ConnectionError) as e:
        sys.stderr.write('Warning: Could not scrape ' + link + ': ' + str(e.message) + '.\n')
        continue

    # Extract title of page
    title = 'NO TITLE'
    html = BeautifulSoup(contents)
    titles = html.find('title')

    if titles:
        title = titles.contents[0]
    print link, '-', title


tempfile.close()
os.remove(tempfilename)
