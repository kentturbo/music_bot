import asyncio
import sys
import os

# Add root folder to sys.path so we can import from bot
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.config import settings
from bot.services.types import Track, Source
import aiohttp
from bot.services.audio_source import AudioResolver

async def main():
    async with aiohttp.ClientSession() as session:
        resolver = AudioResolver(session)
        
        # Mock track
        track = Track(
            source=Source.DEEZER,
            source_id="1578898442",
            artist="44neverluv",
            title="wanna sleep",
            album="melancholia",
            duration=128,  # approximate duration in seconds
            cover_url="",
            preview_url=""
        )
        
        print(f"Resolving track: {track.artist} - {track.title}")
        result = await resolver.resolve(track)
        if result:
            print("Successfully resolved!")
            print("Is Preview:", result.is_preview)
            print("Ext:", result.ext)
            print("URL:", result.url)
            print("Data length:", len(result.data) if result.data else "None")
        else:
            print("Failed to resolve track.")

if __name__ == "__main__":
    asyncio.run(main())
