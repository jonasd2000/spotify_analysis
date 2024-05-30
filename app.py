import argparse

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
        self.add_argument(
            "--audio_features",
            help="Wether or not to retrieve audio features from Spotify.",
            action="store_true"
        )

class App:
    data_manager: DataManager
    ui_manager: UIManager
    
    def __init__(self) -> None:
        args = Parser().parse_args()
        self.data_manager = DataManager()
        self.ui_manager = UIManager(self.data_manager)
        
        self.data_manager.load_data(args.path, args.audio_features)
        self.ui_manager.create_ui()
