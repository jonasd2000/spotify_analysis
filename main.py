from data_manager import DataManager
from ui.analysis_home import AnalysisHome
from nicegui import ui


data_manager = DataManager()

@ui.page("/")
async def analysis_page() -> None:
    analysis_home = AnalysisHome(data_manager=data_manager)
    await analysis_home.create_widget()

if __name__ in ["__main__", "__mp_main__"]:
    ui.run()