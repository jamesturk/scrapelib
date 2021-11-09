# scrapeshell

Many times, especially during development, it is useful to open an
interactive shell to tinker with a page. Often the HTML being returned
is slightly out of sync with what is being seen in the browser, and it
can be difficult to detect these differences without firing up an
interactive python shell and inspecting what the request is returning.

If scrapelib is installed on your path it provides the `scrapeshell` command.

`scrapeshell <URL>` will
open an [IPython](http://ipython.scipy.org/moin/) shell and present
you with an instance of requests.Response with the contents of the
scraped page and if [lxml](http://lxml.de) is installed, an
`lxml.html.HtmlElement` instance as well.

## `scrapeshell`

## scrapeshell arguments

### url

scrapeshell requires a URL, which will then be retrieved via a
`scrapelib.Scraper.get` call.

### `--ua user_agent`

Set a custom user agent (useful for seeing if a site is returning
different results based on UA).

### `--noredirect`

Don't follow redirects.

