from spotify_analysis.api.spotify import SpotifyClient
from dotenv import load_dotenv

load_dotenv()


async def main():
    client = SpotifyClient()
    resp = await client.tracks(["spotify:track:2takcwOaAZWiXQijPHIx7B"])
    print(resp.json())
    

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())