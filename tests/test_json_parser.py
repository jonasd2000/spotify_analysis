import asyncio
import json
import io
import pytest
import polars as pl

from spotify_analysis.data.data_pipeline.parser import JsonParser

test_json = [
    {"a": 1, "b": 2, "c": 3},
    {"a": 4, "b": 5, "c": 6},
    {"a": 7, "b": 8, "c": 9},
]

@pytest.mark.asyncio
async def test_json_parser():
    parser = JsonParser()
    parser.schema = {"a": pl.Int64, "b": pl.Int64, "c": pl.Int64}
    
    input_queue = asyncio.Queue()
    output_queue = asyncio.Queue()
    
    parsing_task = asyncio.create_task(parser.parse_data(input_queue, output_queue))
    
    buffer = io.StringIO()
    buffer.write(json.dumps(test_json))
    buffer.seek(0)
    
    await input_queue.put(buffer)
    input_queue.shutdown()
    
    await parsing_task
    assert output_queue.qsize() == 1