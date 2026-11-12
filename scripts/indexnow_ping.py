#!/usr/bin/env python3
"""Tell Bing (and every IndexNow engine) about new or changed pages. No account needed.
Usage: python3 -I scripts/indexnow_ping.py <url> [<url> ...]   (no args = every URL in the live sitemap)"""
import json, sys, urllib.request, xml.dom.minidom as m

KEY = "8068a5bff68d9412c326870f56a85978"   # also served at https://www.healthymoneydaily.com/8068a5bff68d9412c326870f56a85978.txt; keep that file
HOST = "www.healthymoneydaily.com"

urls = sys.argv[1:] or [l.firstChild.data for l in m.parseString(
    urllib.request.urlopen(f"https://{HOST}/sitemap.xml", timeout=30).read()).getElementsByTagName("loc")]
body = json.dumps({"host": HOST, "key": KEY, "keyLocation": f"https://{HOST}/{KEY}.txt", "urlList": urls}).encode()
req = urllib.request.Request("https://api.indexnow.org/indexnow", body, {"Content-Type": "application/json; charset=utf-8"})
try:
    print("IndexNow", urllib.request.urlopen(req, timeout=30).status, len(urls), "urls")
except urllib.error.HTTPError as e:
    print("IndexNow failed", e.code, e.read()[:200].decode(errors="replace")); sys.exit(1)
