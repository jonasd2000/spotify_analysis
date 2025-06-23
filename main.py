from data_manager import DataManager
from ui.analysis_home import AnalysisHome
from nicegui import ui

data_manager = DataManager()
    
@ui.page("/")
def analysis_page() -> None:
    AnalysisHome(data_manager=data_manager).create_widget()

ui.run()
