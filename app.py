import argparse
from pathlib import Path

from data_manager import DataManager
from ui_manager import UIManager

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
    ui_manager: UIManager
    
    def __init__(self) -> None:
        self.data_manager = DataManager()
        self.ui_manager = UIManager(self.data_manager)
    
    def parse_arguments(self) -> None:
        args = Parser().parse_args()
        self.path = Path(args.path)

    def run(self) -> None:
        self.parse_arguments()
        self.data_manager.load_data(self.path)
        self.ui_manager.run()
