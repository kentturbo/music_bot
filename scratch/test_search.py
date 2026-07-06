import asyncio
import time
import aiohttp
import structlog
from bot.services.search_aggregator import SearchAggregator

# Configure logging to stdout
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)

# Mock Redis class to avoid needing a real Redis server
class MockRedis:
    async def get(self, key):
        return None
    async def set(self, key, val, ex=None):
        pass

async def test_search():
    async with aiohttp.ClientSession() as session:
        redis = MockRedis()
        aggregator = SearchAggregator(session, redis)
        
        query = "44neverluv sleep"
        print(f"Starting search for: '{query}'...")
        
        # Test Deezer
        start = time.time()
        try:
            print("Testing Deezer...")
            deezer_res = await aggregator._search_deezer(query)
            print(f"Deezer returned {len(deezer_res)} results in {time.time() - start:.2f}s")
        except Exception as e:
            print(f"Deezer failed after {time.time() - start:.2f}s: {e}")
            
        # Test YT Music
        start = time.time()
        try:
            print("Testing YT Music...")
            yt_res = await aggregator._search_ytmusic(query)
            print(f"YT Music returned {len(yt_res)} results in {time.time() - start:.2f}s")
        except Exception as e:
            print(f"YT Music failed after {time.time() - start:.2f}s: {e}")
            
        # Test Last.fm
        start = time.time()
        try:
            print("Testing Last.fm...")
            last_res = await aggregator._search_lastfm(query)
            print(f"Last.fm returned {len(last_res)} results in {time.time() - start:.2f}s")
        except Exception as e:
            print(f"Last.fm failed after {time.time() - start:.2f}s: {e}")

        # Test combined search
        print("\nTesting full search method...")
        start = time.time()
        tracks = await aggregator.search(query)
        print(f"Full search returned {len(tracks)} tracks in {time.time() - start:.2f}s")
        for i, t in enumerate(tracks[:3]):
            print(f"  {i+1}. {t.artist} - {t.title} (Source: {t.source})")

if __name__ == "__main__":
    asyncio.run(test_search())
