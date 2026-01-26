import asyncio

import pytest

from spotify_analysis.data.data_pipeline.getter import IdentityGetter
from spotify_analysis.data.data_pipeline.parser import IdentityParser
from spotify_analysis.data.data_pipeline.transformer import IdentityTransformer
from spotify_analysis.data.data_pipeline.loader import NullLoader
from spotify_analysis.data.data_pipeline.pipelines import DataPipeline


def test_create_hooks():
    dp = DataPipeline(None, None, None, None)
    
    getter_hook_queue = asyncio.Queue()
    parser_hook_queue = asyncio.Queue()
    transformer_hook_queue = asyncio.Queue()
    
    dp.register_hook("getter", getter_hook_queue)
    dp.register_hook("parser", parser_hook_queue)
    dp.register_hook("transformer", transformer_hook_queue)
    
    assert dp.hooks == {"getter": [getter_hook_queue], "parser": [parser_hook_queue], "transformer": [transformer_hook_queue]}
    
async def print_active_tasks():
    while True:
        print(asyncio.all_tasks())
        await asyncio.sleep(1)
    
@pytest.mark.asyncio
async def test_hooks():
    dp = DataPipeline(IdentityGetter(), IdentityParser(), IdentityTransformer(), NullLoader())
    
    input_queue = asyncio.Queue()
    
    getter_hook_queue1 = asyncio.Queue()
    getter_hook_queue2 = asyncio.Queue()
    dp.register_hook("getter", getter_hook_queue1)
    dp.register_hook("getter", getter_hook_queue2)
    
    pipeline_task = asyncio.create_task(dp.run(input_queue))
    
    num_items = 5
    for i in range(num_items):
        await input_queue.put(f"foo-{i}")
    input_queue.shutdown()
    
    await pipeline_task
    
    assert getter_hook_queue1.qsize() == num_items
    assert getter_hook_queue2.qsize() == num_items