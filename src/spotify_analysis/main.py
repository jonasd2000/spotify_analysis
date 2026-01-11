import os

from nicegui import ui
from dotenv import load_dotenv

from spotify_analysis.logging_config import configure_logging
from spotify_analysis.data.data_manager import DataManager
from spotify_analysis.ui.analysis_home import AnalysisHome

load_dotenv()

is_production_env_variable = os.getenv("IS_PRODUCTION")
IS_PRODUCTION = is_production_env_variable is not None and int(is_production_env_variable) == 1

data_manager = DataManager()

@ui.page("/")
async def analysis_page() -> None:
    analysis_home = AnalysisHome(data_manager=data_manager)
    await analysis_home.create_widget()

def main() -> None:
    reload = not IS_PRODUCTION
    configure_logging()
    ui.run(reload=reload)

if __name__ in {"__main__", "__mp_main__"}:
    main()