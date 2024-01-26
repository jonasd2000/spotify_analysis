import argparse
from pathlib import Path

from nicegui import ui

from data_manager import DataManager

class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, 
                         prog="spotify_analysis")
        self.add_arguments()
        
    def add_arguments(self) -> None:
        self.add_argument(
            "--path",
            help="The path to the unzipped Spotify Extended Streaming History folder.",
            type=str,
            required=True
        )

class App:
    path: Path
    data_manager: DataManager
    
    def __init__(self) -> None:
        self.data_manager = DataManager()
    
    def parse_arguments(self) -> None:
        args = Parser().parse_args()
        self.path = Path(args.path)

    def run(self) -> None:
        self.parse_arguments()
        self.data_manager.load_data(self.path)
        
        ui.label(str(self.path))
        ui.button('BUTTON', on_click=lambda: ui.notify('button was pressed'))

        ui.run()
