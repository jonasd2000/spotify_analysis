import asyncio
import sqlite3
import polars as pl
from spotify_analysis.data.enricher import MusicbrainzAPIEnricher

conn = sqlite3.connect("listening_history.db")

isrcs = conn.execute(
    """
    SELECT international_standard_recording_code FROM track WHERE international_standard_recording_code IS NOT NULL LIMIT 100
    """
).fetchall()
    
isrcs = [isrc[0] for isrc in isrcs]

df = pl.DataFrame({"isrc": isrcs})

async def main():
    enricher = MusicbrainzAPIEnricher()
    enriched = await enricher.enrich_data(df)
    print(enriched)

asyncio.run(main())