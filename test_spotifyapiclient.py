from spotify_analysis.api.spotify import SpotifyClient
from dotenv import load_dotenv

load_dotenv()


async def main():
    client = SpotifyClient()
    resp = await client.get("https://api.spotify.com/v1/tracks?ids=7ouMYWpwJ422jRcDASZB7P%2C4VqPOruhp5EdPBeR92t6lQ%2C2takcwOaAZWiXQijPHIx7B")
    print(resp.json())
    

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())