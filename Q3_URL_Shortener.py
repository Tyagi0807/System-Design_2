"""Q3 - URL Shortener: Base62 counter-based codes, redirect with cache, click tracking.
Run: python q3_url_shortener.py
"""
import itertools
from collections import OrderedDict
from datetime import datetime
from urllib.parse import urlparse

BASE62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
MASK = (1 << 42) - 1  # keep scrambled id inside 42 bits (< 62^7)


def to_base62(n):
    if n == 0:
        return BASE62[0]
    out = []
    while n:
        n, r = divmod(n, 62)
        out.append(BASE62[r])
    return "".join(reversed(out))


def scramble(n):
    """Reversible (bijective) mixing so consecutive IDs do not give guessable codes."""
    return ((n * 2654435761) ^ 0x2A5A5A5A) & MASK


class LRUCache:
    def __init__(self, capacity=1000):
        self.cap, self.data = capacity, OrderedDict()

    def get(self, key):
        if key in self.data:
            self.data.move_to_end(key)
            return self.data[key]

    def put(self, key, value):
        self.data[key] = value
        self.data.move_to_end(key)
        if len(self.data) > self.cap:
            self.data.popitem(last=False)


class URLShortener:
    def __init__(self, domain="https://sho.rt", cache_size=1000):
        self.domain = domain
        self.db = {}                     # short_code -> {long_url, created_at, expires_at}
        self.clicks = {}                 # short_code -> count (analytics store)
        self.cache = LRUCache(cache_size)
        self.counter = itertools.count(1)  # stands in for the Key Generation Service
        self.cache_hits = self.cache_misses = 0

    def shorten(self, long_url, alias=None, expires_at=None):
        p = urlparse(long_url)
        if p.scheme not in ("http", "https") or not p.netloc:
            raise ValueError("Invalid URL")
        if alias:
            if alias in self.db:
                raise ValueError("Alias already taken")
            code = alias
        else:
            code = to_base62(scramble(next(self.counter)))
        self.db[code] = {"long_url": long_url, "created_at": datetime.now(),
                         "expires_at": expires_at}
        self.clicks[code] = 0
        return f"{self.domain}/{code}"

    def redirect(self, code):
        """Returns (status_code, location). 302 so that every click reaches us."""
        record = self.cache.get(code)
        if record:
            self.cache_hits += 1
        else:
            self.cache_misses += 1
            record = self.db.get(code)
            if record is None:
                return 404, None
            self.cache.put(code, record)
        if record["expires_at"] and datetime.now() > record["expires_at"]:
            return 410, None
        self.clicks[code] += 1  # production: publish event to Kafka, count asynchronously
        return 302, record["long_url"]

    def stats(self, code):
        return {"short_code": code, "long_url": self.db[code]["long_url"],
                "total_clicks": self.clicks[code]}


if __name__ == "__main__":
    s = URLShortener()
    u1 = s.shorten("https://www.example.com/some/very/long/path?x=1&y=2")
    u2 = s.shorten("https://docs.python.org/3/", alias="pydocs")
    print("Short URLs:", u1, u2)

    code1 = u1.rsplit("/", 1)[1]
    for _ in range(3):
        print("Redirect:", s.redirect(code1))
    print("Redirect pydocs:", s.redirect("pydocs"))
    print("Unknown code:", s.redirect("nope123"))
    print("Stats:", s.stats(code1))
    print("Cache hits/misses:", s.cache_hits, s.cache_misses)

    codes = {s.shorten(f"https://example.com/{i}") for i in range(10000)}
    print("10,000 URLs -> unique codes:", len(codes))
