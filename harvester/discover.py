"""
discover.py — строит «фронтир» клиник Казахстана из sitemap портала 103.kz.

103.kz агрегирует прайс-листы тысяч клиник РК, каждая на поддомене
<slug>.103.kz, а её прайс — на <slug>.103.kz/pricing/ по единому HTML-шаблону.
Sitemap (sitemap-personals.xml.gz) перечисляет все клиники — это и есть
полный список того, у кого вообще есть онлайн-прайс.

Результат: harvester/frontier.txt — по одному хосту на строку.
"""
import gzip
import os
import re
import ssl
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
SITEMAP_INDEX = "https://103.kz/sitemap.xml"
UA = {"User-Agent": "Mozilla/5.0 (compatible; MedPriceBot/1.0; research)"}

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=60, context=_ctx).read()


def _locs(xml: str):
    return re.findall(r"<loc>(.*?)</loc>", xml)


def discover() -> list[str]:
    index = _fetch(SITEMAP_INDEX).decode("utf-8", "ignore")
    hosts: list[str] = []
    seen: set[str] = set()
    for sub in _locs(index):
        if "personals" not in sub.lower():
            continue
        raw = _fetch(sub)
        try:
            xml = gzip.decompress(raw).decode("utf-8", "ignore")
        except OSError:
            xml = raw.decode("utf-8", "ignore")
        for loc in _locs(xml):
            host = re.sub(r"https?://", "", loc).split("/")[0].strip().lower()
            # только клиники-поддомены *.103.kz (не www/основной портал)
            if host.endswith(".103.kz") and host not in ("www.103.kz", "103.kz") and host not in seen:
                seen.add(host)
                hosts.append(host)
    return hosts


def main():
    hosts = discover()
    out = os.path.join(ROOT, "frontier.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(hosts) + "\n")
    print(f"frontier: {len(hosts)} clinics -> {out}")


if __name__ == "__main__":
    main()
