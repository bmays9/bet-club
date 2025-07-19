import requests

url = "https://golf-leaderboard-data.p.rapidapi.com/scorecard/220/101017"

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": RAPIDAPI_GOLF_HOST
}

response = requests.get(url, headers=headers)

print(response.json())