//! High-performance Parquet writer plugin for Dativo ETL
//!
//! This Rust plugin demonstrates:
//! - Fast Parquet writing using Arrow
//! - Schema inference and validation
//! - Columnar data processing
//! - Compression and optimization
//!
//! Build with: cargo build --release
//! Output: target/release/libparquet_writer_plugin.so (or .dylib/.dll)

use arrow::array::{ArrayRef, Float64Array, Int64Array, StringArray};
use arrow::datatypes::{DataType, Field, Schema};
use arrow::record_batch::RecordBatch;
use parquet::arrow::ArrowWriter;
use parquet::basic::Compression;
use parquet::file::properties::WriterProperties;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::ffi::{CStr, CString};
use std::fs::File;
use std::os::raw::c_char;
use std::path::PathBuf;
use std::sync::Arc;

/// Configuration passed from Python
#[derive(Debug, Deserialize)]
struct WriterConfig {
    asset_name: String,
    schema: Vec<SchemaField>,
    output_base: String,
    target_type: String,
    connection: HashMap<String, serde_json::Value>,
    #[serde(default)]
    engine: EngineConfig,
}

#[derive(Debug, Deserialize)]
struct SchemaField {
    name: String,
    #[serde(rename = "type")]
    field_type: String,
}

#[derive(Debug, Deserialize, Default)]
struct EngineConfig {
    #[serde(default)]
    options: EngineOptions,
}

#[derive(Debug, Deserialize, Default)]
struct EngineOptions {
    #[serde(default = "default_compression")]
    compression: String,
    #[serde(default = "default_row_group_size")]
    row_group_size: usize,
}

fn default_compression() -> String {
    "snappy".to_string()
}

fn default_row_group_size() -> usize {
    100_000
}

#[derive(Debug, Serialize)]
struct FileMetadata {
    path: String,
    size_bytes: u64,
    record_count: usize,
}

/// Parquet Writer state
pub struct ParquetWriter {
    config: WriterConfig,
    schema: Arc<Schema>,
}

impl ParquetWriter {
    /// Create new Parquet writer from configuration
    fn new(config: WriterConfig) -> Result<Self, String> {
        // Build Arrow schema from config
        let fields: Vec<Field> = config
            .schema
            .iter()
            .map(|f| {
                let data_type = match f.field_type.as_str() {
                    "string" => DataType::Utf8,
                    "integer" => DataType::Int64,
                    "number" | "float" => DataType::Float64,
                    _ => DataType::Utf8,
                };
                Field::new(&f.name, data_type, true)
            })
            .collect();

        let schema = Arc::new(Schema::new(fields));

        Ok(Self { config, schema })
    }

    /// Write batch of records to Parquet file
    fn write_batch(
        &self,
        records: Vec<HashMap<String, serde_json::Value>>,
        file_counter: usize,
    ) -> Result<FileMetadata, String> {
        if records.is_empty() {
            return Err("No records to write".to_string());
        }

        // Build output path
        let output_dir = PathBuf::from(&self.config.output_base);
        std::fs::create_dir_all(&output_dir)
            .map_err(|e| format!("Failed to create output directory: {}", e))?;

        let output_file = output_dir.join(format!("part-{:05}.parquet", file_counter));

        // Create Parquet writer
        let file = File::create(&output_file)
            .map_err(|e| format!("Failed to create output file: {}", e))?;

        let compression = match self.config.engine.options.compression.as_str() {
            "snappy" => Compression::SNAPPY,
            "gzip" => Compression::GZIP,
            "lz4" => Compression::LZ4,
            "zstd" => Compression::ZSTD,
            "none" => Compression::UNCOMPRESSED,
            _ => Compression::SNAPPY,
        };

        let props = WriterProperties::builder()
            .set_compression(compression)
            .set_max_row_group_size(self.config.engine.options.row_group_size)
            .build();

        let mut writer = ArrowWriter::try_new(file, self.schema.clone(), Some(props))
            .map_err(|e| format!("Failed to create Arrow writer: {}", e))?;

        // Convert records to Arrow RecordBatch
        let batch = self.records_to_batch(records)?;

        // Write batch
        writer
            .write(&batch)
            .map_err(|e| format!("Failed to write batch: {}", e))?;

        writer
            .close()
            .map_err(|e| format!("Failed to close writer: {}", e))?;

        // Get file size
        let file_size = std::fs::metadata(&output_file)
            .map(|m| m.len())
            .unwrap_or(0);

        Ok(FileMetadata {
            path: output_file.to_string_lossy().to_string(),
            size_bytes: file_size,
            record_count: batch.num_rows(),
        })
    }

    /// Convert records to Arrow RecordBatch
    fn records_to_batch(
        &self,
        records: Vec<HashMap<String, serde_json::Value>>,
    ) -> Result<RecordBatch, String> {
        let mut columns: Vec<ArrayRef> = Vec::new();

        for field in self.schema.fields() {
            let column_name = field.name();

            match field.data_type() {
                DataType::Utf8 => {
                    let values: Vec<Option<String>> = records
                        .iter()
                        .map(|r| {
                            r.get(column_name)
                                .and_then(|v| v.as_str())
                                .map(|s| s.to_string())
                        })
                        .collect();
                    columns.push(Arc::new(StringArray::from(values)) as ArrayRef);
                }
                DataType::Int64 => {
                    let values: Vec<Option<i64>> = records
                        .iter()
                        .map(|r| {
                            r.get(column_name).and_then(|v| {
                                if let Some(num) = v.as_i64() {
                                    Some(num)
                                } else if let Some(s) = v.as_str() {
                                    s.parse::<i64>().ok()
                                } else {
                                    None
                                }
                            })
                        })
                        .collect();
                    columns.push(Arc::new(Int64Array::from(values)) as ArrayRef);
                }
                DataType::Float64 => {
                    let values: Vec<Option<f64>> = records
                        .iter()
                        .map(|r| {
                            r.get(column_name).and_then(|v| {
                                if let Some(num) = v.as_f64() {
                                    Some(num)
                                } else if let Some(s) = v.as_str() {
                                    s.parse::<f64>().ok()
                                } else {
                                    None
                                }
                            })
                        })
                        .collect();
                    columns.push(Arc::new(Float64Array::from(values)) as ArrayRef);
                }
                _ => {
                    return Err(format!(
                        "Unsupported data type for column {}: {:?}",
                        column_name,
                        field.data_type()
                    ))
                }
            }
        }

        RecordBatch::try_new(self.schema.clone(), columns)
            .map_err(|e| format!("Failed to create RecordBatch: {}", e))
    }
}

/// Create Parquet writer from JSON config
///
/// # Safety
/// config_json must be a valid null-terminated C string
#[no_mangle]
pub unsafe extern "C" fn create_writer(config_json: *const c_char) -> *mut ParquetWriter {
    if config_json.is_null() {
        return std::ptr::null_mut();
    }

    // Convert C string to Rust string
    let c_str = match CStr::from_ptr(config_json).to_str() {
        Ok(s) => s,
        Err(_) => return std::ptr::null_mut(),
    };

    // Parse JSON config
    let config: WriterConfig = match serde_json::from_str(c_str) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Failed to parse config: {}", e);
            return std::ptr::null_mut();
        }
    };

    // Create writer
    match ParquetWriter::new(config) {
        Ok(writer) => Box::into_raw(Box::new(writer)),
        Err(e) => {
            eprintln!("Failed to create writer: {}", e);
            std::ptr::null_mut()
        }
    }
}

/// Write batch of records
///
/// Returns JSON metadata that must be freed with free_string
///
/// # Safety
/// writer must be a valid pointer from create_writer
/// records_json must be a valid null-terminated C string
#[no_mangle]
pub unsafe extern "C" fn write_batch(
    writer: *mut ParquetWriter,
    records_json: *const c_char,
) -> *const c_char {
    if writer.is_null() || records_json.is_null() {
        return std::ptr::null();
    }

    let writer = &*writer;

    // Parse input JSON
    let c_str = match CStr::from_ptr(records_json).to_str() {
        Ok(s) => s,
        Err(_) => return std::ptr::null(),
    };

    #[derive(Deserialize)]
    struct Input {
        records: Vec<HashMap<String, serde_json::Value>>,
        file_counter: usize,
    }

    let input: Input = match serde_json::from_str(c_str) {
        Ok(i) => i,
        Err(e) => {
            eprintln!("Failed to parse input: {}", e);
            return std::ptr::null();
        }
    };

    // Write batch
    let metadata = match writer.write_batch(input.records, input.file_counter) {
        Ok(m) => m,
        Err(e) => {
            eprintln!("Write error: {}", e);
            return std::ptr::null();
        }
    };

    // Serialize metadata to JSON
    let json = match serde_json::to_string(&vec![metadata]) {
        Ok(j) => j,
        Err(e) => {
            eprintln!("JSON serialization error: {}", e);
            return std::ptr::null();
        }
    };

    // Convert to C string
    match CString::new(json) {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null(),
    }
}

/// Free Parquet writer
///
/// # Safety
/// writer must be a valid pointer from create_writer
#[no_mangle]
pub unsafe extern "C" fn free_writer(writer: *mut ParquetWriter) {
    if !writer.is_null() {
        drop(Box::from_raw(writer));
    }
}

/// Free string returned by write_batch
///
/// # Safety
/// s must be a valid pointer from write_batch
#[no_mangle]
pub unsafe extern "C" fn free_string(s: *const c_char) {
    if !s.is_null() {
        drop(CString::from_raw(s as *mut c_char));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_config_parsing() {
        let config_json = r#"{
            "asset_name": "test_table",
            "schema": [
                {"name": "id", "type": "integer"},
                {"name": "name", "type": "string"}
            ],
            "output_base": "/tmp/output",
            "target_type": "parquet",
            "connection": {},
            "engine": {
                "options": {
                    "compression": "snappy",
                    "row_group_size": 100000
                }
            }
        }"#;

        let config: WriterConfig = serde_json::from_str(config_json).unwrap();
        assert_eq!(config.asset_name, "test_table");
        assert_eq!(config.schema.len(), 2);
    }
}
