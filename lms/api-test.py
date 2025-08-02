import http.client, json
from urllib.parse import urlparse

url = "https://www.sofascore.com/api/v1/unique-tournament/17/season/76986/standings/total"
parsed_url = urlparse(url)

conn = http.client.HTTPSConnection(parsed_url.netloc)
headers = {
    "User-Agent": "Mozilla/5.0"
}
conn.request("GET", parsed_url.path, headers=headers)
res = conn.getresponse()
data = res.read()
jsondata = json.loads(data.decode("utf-8"))

print(jsondata)

