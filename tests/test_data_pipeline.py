import asyncio

import pytest

from spotify_analysis.data.data_pipeline.getter import IdentityGetter
from spotify_analysis.data.data_pipeline.parser import IdentityParser
from spotify_analysis.data.data_pipeline.transformer import IdentityTransformer
from spotify_analysis.data.data_pipeline.loader import NullLoader
from spotify_analysis.data.data_pipeline.pipelines import DataPipeline


def test_register_hooks():
    getter = IdentityGetter(1, 1, True)
    parser = IdentityParser(1, 1, True)
    transformer = IdentityTransformer(1, 1, True)
    loader = NullLoader(1, 1, True)
    dp = DataPipeline(getter, parser, transformer, loader)
    
    getter_hook_queue = asyncio.Queue()
    parser_hook_queue = asyncio.Queue()
    transformer_hook_queue = asyncio.Queue()
    
    dp.register_hook("getter", getter_hook_queue)
    dp.register_hook("parser", parser_hook_queue)
    dp.register_hook("transformer", transformer_hook_queue)
    
    assert dp.hooks == {getter: [getter_hook_queue], parser: [parser_hook_queue], transformer: [transformer_hook_queue]}
    
@pytest.mark.asyncio
async def test_hooks():
    dp = DataPipeline(
        IdentityGetter(1, 1 , True), 
        IdentityParser(1, 1, True), 
        IdentityTransformer(1, 1, True), 
        NullLoader(1, 1, True)
    )
    
    input_queue = asyncio.Queue()
    
    getter_hook_queue1 = asyncio.Queue()
    getter_hook_queue2 = asyncio.Queue()
    parser_hook_queue1 = asyncio.Queue()
    dp.register_hook("getter", getter_hook_queue1)
    dp.register_hook("getter", getter_hook_queue2)
    dp.register_hook("parser", parser_hook_queue1)
    
    pipeline_task = asyncio.create_task(dp.run(input_queue))
    
    num_items = 50
    for i in range(num_items):
        await input_queue.put(f"foo-{i}")
    input_queue.shutdown()
    
    await pipeline_task
    
    assert getter_hook_queue1.qsize() == num_items
    assert getter_hook_queue2.qsize() == num_items
    assert parser_hook_queue1.qsize() == num_items
    
@pytest.mark.asyncio
async def test_hook_forwards():
    dp = DataPipeline(
        IdentityGetter(1, 1 , True), 
        IdentityParser(1, 1, True), 
        IdentityTransformer(1, 1, True), 
        NullLoader(1, 1, True)
    )
    
    input_queue = asyncio.Queue()
    
    transformer_hook_queue1 = asyncio.Queue()
    transformer_hook_forwards = lambda x: 4 * x
    dp.register_hook("transformer", transformer_hook_queue1, transformer_hook_forwards)
    
    assert dp.hook_forwards == {(dp.transformer, transformer_hook_queue1): transformer_hook_forwards}
    
    pipeline_task = asyncio.create_task(dp.run(input_queue))
    
    num_items = 50
    input_items = []
    for i in range(num_items):
        item = f"foo-{i}"
        input_items.append(item)
        await input_queue.put(item)
    input_queue.shutdown()
    
    await pipeline_task
    
    assert transformer_hook_queue1.qsize() == num_items
    for item in input_items:
        assert transformer_hook_queue1.get_nowait() == transformer_hook_forwards(item)