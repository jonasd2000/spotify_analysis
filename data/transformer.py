from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional

import polars as pl
import pydantic

class DataTransformer(ABC):
    @abstractmethod
    def _transform_data(self, data: pl.DataFrame) -> pl.DataFrame:
        pass
    
    def validate_data(self, data: pl.DataFrame) -> None:
        pass
    
    def transform_data(self, data: pl.DataFrame) -> pl.DataFrame:
        try:
            self.validate_data(data)
        except Exception as e:
            raise e        
        return self._transform_data(data)
    
class DataTransformerPipeline(DataTransformer):
    def __init__(self, transformers: list[DataTransformer]) -> None:
        self.transformers = transformers
        
    def _transform_data(self, data: pl.DataFrame) -> pl.DataFrame:
        for transformer in self.transformers:
            data = transformer.transform_data(data)
        return data
    
class SchemaTransformer(DataTransformer):
    old_schema: pl.Schema
    new_schema: pl.Schema
        
    def __init__(self, old_schema: dict[str, pl.DataType], new_schema: dict[str, pl.DataType]) -> None:
        self.old_schema = old_schema
        self.new_schema = new_schema
        self.schema_mapping = {
            (old_name, old_type): (new_name, new_type) 
            for (old_name, old_type), (new_name, new_type) in zip(old_schema.items(), new_schema.items())
        }
        
    def validate_data(self, data):
        if data.schema != self.old_schema:
            raise pl.exceptions.SchemaError("Data schema does not match expected schema")
        
    def _transform_data(self, data: pl.DataFrame) -> pl.DataFrame:
        for current_column_name, current_column_dtype in data.schema.items():
            new_column_name, new_column_dtype = self.schema_mapping[(current_column_name, current_column_dtype)]
            
            data = data.with_columns(
                pl.col(current_column_name).cast(new_column_dtype).alias(new_column_name)
            )
            
            if new_column_name != current_column_name:
                data = data.drop(current_column_name)
        return data
        
        