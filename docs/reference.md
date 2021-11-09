# API Reference

### Scraper

::: scrapelib.Scraper
    rendering:
      heading_level: 4

## Caching

Assign a `MemoryCache`, `FileCache`, or `SQLiteCache` to
the `cache_storage` property of a `scrapelib.Scraper` to cache responses:

``` python

from scrapelib import Scraper
from scrapelib.cache import FileCache
cache = FileCache('cache-directory')
scraper = Scraper()
scraper.cache_storage = cache
scraper.cache_write_only = False
```

### MemoryCache

::: scrapelib.MemoryCache
    rendering:
      heading_level: 4
    selection:
      members: False

### FileCache

::: scrapelib.FileCache
    rendering:
      heading_level: 4
    selection:
      members: False

### SQLiteCache

::: scrapelib.SQLiteCache
    rendering:
      heading_level: 4
    selection:
      members: False

## Exceptions

### HTTPError

::: scrapelib.HTTPError
    rendering:
      heading_level: 4

### HTTPMethodUnavailableError

::: scrapelib.HTTPMethodUnavailableError
    rendering:
      heading_level: 4

### FTPError

::: scrapelib.FTPError
    rendering:
      heading_level: 4
