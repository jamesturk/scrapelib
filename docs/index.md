# Overview

**scrapelib** is a library for making requests for less-than-reliable websites.

Source: [https://github.com/jamesturk/scrapelib](https://github.com/jamesturk/scrapelib)

Documentation: [https://jamesturk.github.io/scrapelib/](https://jamesturk.github.io/scrapelib/)

Issues: [https://github.com/jamesturk/scrapelib/issues](https://github.com/jamesturk/scrapelib/issues)

[![PyPI badge](https://badge.fury.io/py/scrapelib.svg)](https://badge.fury.io/py/scrapelib)
[![Test badge](https://github.com/jamesturk/scrapelib/workflows/Test%20&%20Lint/badge.svg)](https://github.com/jamesturk/scrapelib/actions?query=workflow%3A%22Test+%26+Lint%22)

## Features

**scrapelib** originated as part of the [Open States](http://openstates.org/)
project to scrape the websites of all 50 state legislatures and as a result
was therefore designed with features desirable when dealing with sites that
have intermittent errors or require rate-limiting.

Advantages of using scrapelib over using requests as-is:

- HTTP(S) and FTP requests via an identical API
- support for simple caching with pluggable cache backends
- highly-configurable request throtting
- configurable retries for non-permanent site failures
- All of the power of the suberb [requests](http://python-requests.org) library.

## Installation

*scrapelib* is on [PyPI](https://pypi.org/project/scrapelib/), and can be installed via any standard package management tool:

    poetry add scrapelib

or:

    pip install scrapelib
