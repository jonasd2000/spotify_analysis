import argparse
from pathlib import Path

from nicegui import ui

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
    
    def __init__(self) -> None:
        pass
    
    def parse_arguments(self) -> None:
        parser = Parser()
        args = parser.parse_args()
        self.path = Path(args.path)
        
    def run(self) -> None:
        ui.label(str(self.path))
        ui.button('BUTTON', on_click=lambda: ui.notify('button was pressed'))

        ui.run()
