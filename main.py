from logging_config import configure_logging
from data_manager import DataManager
from ui.analysis_home import AnalysisHome
from nicegui import ui


data_manager = DataManager()

@ui.page("/")
async def analysis_page() -> None:
    analysis_home = AnalysisHome(data_manager=data_manager)
    await analysis_home.create_widget()

def main() -> None:
    configure_logging()
    ui.run()

if __name__ in ["__main__", "__mp_main__"]:
    main()