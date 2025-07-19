import requests

url = "https://golf-leaderboard-data.p.rapidapi.com/scorecard/220/101017"

headers = {
	"x-rapidapi-key": "cee5b032bcmshed81897ec3a5096p1804b9jsn74aec3308aaf",
	"x-rapidapi-host": "golf-leaderboard-data.p.rapidapi.com"
}

response = requests.get(url, headers=headers)

print(response.json())