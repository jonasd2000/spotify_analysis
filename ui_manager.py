from nicegui import ui, element
import polars as pl

from data_manager import DataManager

class UIManager:
    data_manager: DataManager
    
    data_table: element.Element
    
    def __init__(self, data_manager: DataManager) -> None:
        self.data_manager = data_manager
        self.data_table = None
    
    def create_data_table(self, dataframe: pl.DataFrame) -> None:
        columns = [
            {'name': column, 'label': column.capitalize(), 'field': column, 'sortable': True}
            for column in dataframe.columns
        ]
        rows = dataframe.to_dicts()
        return ui.table(columns=columns, rows=rows, pagination=100)
    
    def create_ui(self) -> None:
        ui.label(str(self.data_manager.path))
        
        with ui.row():
            ui.select(self.data_manager.streaming_data.columns, label="Group by", multiple=True, clearable=True, on_change=self.data_manager.group_by_aggregate_parser.process_group_by_change_event)
            ui.select(self.data_manager.group_by_aggregate_parser.aggregate_choices, clearable=True, label="Aggregate function", on_change=self.data_manager.group_by_aggregate_parser.process_aggregate_function_change_event)
            ui.select(self.data_manager.streaming_data.columns, label="Aggregate by", clearable=True, on_change=self.data_manager.group_by_aggregate_parser.process_aggregate_by_change_event)
            min_date, max_date = self.data_manager.get_min_max_date()
            ui.date(value=min_date, on_change=self.data_manager.group_by_aggregate_parser.process_start_date_change_event)
            ui.date(value=max_date, on_change=self.data_manager.group_by_aggregate_parser.process_end_date_change_event)
            
        def on_submit():
            if self.data_table is not None:
                self.data_table.delete()
            self.data_table = self.create_data_table(self.data_manager.get_data())
        
        ui.button("Submit", on_click=on_submit)
        
