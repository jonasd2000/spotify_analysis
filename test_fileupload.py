import asyncio
import logging
import sys
from dotenv import load_dotenv

from nicegui.events import MultiUploadEventArguments

from spotify_analysis.ui.widgets.data_loader_widget import DataLoaderWidget
from spotify_analysis.data.data_manager import DataManager


load_dotenv()

async def main():
    logging.basicConfig(level=logging.DEBUG)
    file_path = sys.argv[1]
    
    data_manager = DataManager(":memory:")
    await data_manager.setup()
    widget = DataLoaderWidget(data_manager)

    with open(file_path, "rb") as file:
        await widget.handle_multi_upload(MultiUploadEventArguments(contents=[file], names=[file_path], sender=None, client=None, types=[None]))
        
if __name__ == "__main__":
    asyncio.run(main())