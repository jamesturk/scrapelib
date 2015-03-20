Migrating from 0.x to 1.x
=========================

Scrapelib 1.x drops some of the deprecated interfaces from early versions of scrapelib that did
not depend upon requests.

The most noticable of these is the absence of ``urlopen()``.  Because scrapelib is implemented as
a wrapper around ``requests.Session`` it is recommended people use ``get()``,  ``post()`` and the 
`other request methods <http://docs.python-requests.org/en/latest/api/>`_.

The return type of ``urlopen`` was a ``ResultStr``, which is no longer returned, instead a standard `requests.Response <http://docs.python-requests.org/en/latest/api/#requests.Response>`_ will be returned.


Notable Changes to Responses
----------------------------

To migrate code using urlopen from an old-style ``scrapelib.ResultStr`` to a ``requests.Response``:

    * It is no longer possible to treat a response like a string.  Instead use ``resp.text``, ``resp.bytes`` or ``resp.json()`` as needed.
    * ``resp.bytes`` is now ``resp.content``
    * ``resp.response`` is now just ``resp``
    * ``resp.response.code`` is now ``resp.status_code``
    * ``resp.response.requested_url`` is no longer available, you can use the idiom ``resp.history[0].url if resp.history else resp.url``
    * ``resp.encoding`` is still available as ``resp.encoding``
    * ``resp._scraper`` is no longer available (was an internal API and hopefully not relied upon)

If you were already using ``get()``, ``post()`` , and similar the response format has not changed.


Examples
--------

A GET request
~~~~~~~~~~~~~

With urlopen::

    s = Scraper()
    resp = s.urlopen('http://example.com/json')
    assert resp.response.code == 200
    data = json.loads(resp)

    # or for a non-JSON response
    print(resp)

With get::

    s = Scraper()
    resp = s.get('http://example.com/json')
    assert resp.status_code == 200
    data = resp.json()      # uses requests built-in JSON support

    # or for a non-JSON request
    print(resp.text)


A POST request
~~~~~~~~~~~~~~~

With urlopen::

    s = Scraper()
    resp = s.urlopen('http://example.com/form', 'POST', {'param': 'abc'})

With get::

    s = Scraper()
    resp = s.post('http://example.com/form', {'param': 'abc'})

