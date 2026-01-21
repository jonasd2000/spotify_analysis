import polars as pl
import pytest

from spotify_analysis.data.transformer import (
    SchemaTransformer,
    DataValidationError,
)

def test_schema_transformer_transform_data():
    test_schema = pl.Schema({"a": pl.Int64, "b": pl.Int64, "c": pl.Utf8})
    test_df = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": ["i", "j", "k"]})
    
    new_schema = pl.Schema({"a_new": pl.Float64, "b_new": pl.Utf8, "c_new": pl.Utf8})
    
    schema_transformer = SchemaTransformer(old_schema=test_schema, new_schema=new_schema)
    new_df = schema_transformer.transform_data(test_df, additional_data=None)
    
    assert new_df.schema == new_schema
    assert new_df["a_new"].to_list() == [1.0, 2.0, 3.0]
    assert new_df["b_new"].to_list() == ["4", "5", "6"]
    assert new_df["c_new"].to_list() == ["i", "j", "k"]
    
def test_schema_transformer_validate_data():
    test_schema = pl.Schema({"a": pl.Int64, "b": pl.Int64, "c": pl.Utf8})
    test_df = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": ["i", "j", "k"]})
    
    new_schema = pl.Schema({"a_new": pl.Float64, "b_new": pl.Utf8, "c_new": pl.Utf8})
    
    schema_transformer = SchemaTransformer(old_schema=test_schema, new_schema=new_schema)
    schema_transformer.validate_input_data(test_df)
    
def test_schema_transformer_invalid_schema():
    # type of column b, c in schema does not match the type of the data
    test_schema = pl.Schema({"a": pl.Int64, "b": pl.Float64, "c": pl.Int64})
    test_df = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": ["i", "j", "k"]})
    
    schema_transformer = SchemaTransformer(old_schema=test_schema, new_schema={})
    with pytest.raises(DataValidationError):
        schema_transformer.validate_input_data(test_df)