//! High-performance CSV writer plugin for Dativo ETL
//!
//! This Rust plugin demonstrates:
//! - Fast CSV writing using the csv crate
//! - Efficient memory management
//! - Configurable formatting options
//! - Size-based file splitting for optimal file sizes
//! - C-compatible FFI interface
//!
//! Build with: cargo build --release
//! Output: target/release/libcsv_writer_plugin.so (or .dylib/.dll)

use csv::WriterBuilder;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::ffi::{CStr, CString};
use std::fs::File;
use std::os::raw::c_char;
use std::path::PathBuf;

/// Configuration passed from Python
#[derive(Debug, Deserialize)]
struct WriterConfig {
    #[allow(dead_code)]
    asset_name: String,
    schema: Vec<SchemaField>,
    output_base: String,
    #[allow(dead_code)]
    target_type: String,
    #[allow(dead_code)]
    connection: HashMap<String, serde_json::Value>,
    #[serde(default)]
    engine: EngineConfig,
}

#[derive(Debug, Deserialize)]
struct SchemaField {
    name: String,
    #[serde(rename = "type")]
    #[allow(dead_code)]
    field_type: String,
}

#[derive(Debug, Deserialize, Default)]
struct EngineConfig {
    #[serde(default)]
    options: EngineOptions,
}

#[derive(Debug, Deserialize, Default)]
struct EngineOptions {
    #[serde(default = "default_delimiter")]
    delimiter: String,
    #[serde(default = "default_include_header")]
    include_header: bool,
    #[serde(default = "default_target_size_mb")]
    target_size_mb: u64,
}

fn default_delimiter() -> String {
    ",".to_string()
}

fn default_include_header() -> bool {
    true
}

fn default_target_size_mb() -> u64 {
    // Default to 50 MB for CSV files (smaller than Parquet since CSV is uncompressed)
    50
}

#[derive(Debug, Serialize)]
struct FileMetadata {
    path: String,
    size_bytes: u64,
    record_count: usize,
    format: String,
}

/// CSV Writer state
pub struct CsvWriter {
    config: WriterConfig,
    file_counter: usize,
    header_written: bool,
}

impl CsvWriter {
    /// Create new CSV writer from configuration
    fn new(config: WriterConfig) -> Result<Self, String> {
        Ok(Self {
            config,
            file_counter: 0,
            header_written: false,
        })
    }

    /// Efficiently convert serde_json::Value to String
    /// Optimized to avoid unnecessary allocations for common types
    #[inline]
    fn value_to_string(value: &serde_json::Value) -> String {
        match value {
            // For strings, we still need to clone, but this is explicit
            serde_json::Value::String(s) => s.clone(),
            // For numbers, use to_string which is already optimized in serde_json
            serde_json::Value::Number(n) => n.to_string(),
            // For bools, directly create String from static str (slightly more efficient)
            serde_json::Value::Bool(b) => {
                if *b {
                    String::from("true")
                } else {
                    String::from("false")
                }
            }
            // Null is empty string
            serde_json::Value::Null => String::new(),
            // For arrays/objects, fall back to to_string
            _ => value.to_string(),
        }
    }

    /// Estimate CSV size for a sample of records
    fn estimate_csv_size(
        &self,
        records: &[HashMap<String, serde_json::Value>],
        fieldnames: &[String],
        delimiter_byte: u8,
        include_header: bool,
    ) -> u64 {
        if records.is_empty() {
            return 0;
        }

        // Sample up to 1000 records to estimate size
        let sample_size = records.len().min(1000);
        let sample = &records[0..sample_size];

        // Create a temporary buffer to estimate size
        let mut buffer = Vec::new();
        let mut writer = WriterBuilder::new()
            .delimiter(delimiter_byte)
            .has_headers(false)
            .from_writer(&mut buffer);

        // Write header if needed
        if include_header {
            let _ = writer.write_record(fieldnames);
        }

        // Write sample records
        let fieldname_refs: Vec<&str> = fieldnames.iter().map(|s| s.as_str()).collect();
        let mut row = Vec::with_capacity(fieldnames.len());
        for record in sample {
            row.clear();
            for fieldname in &fieldname_refs {
                let value = record
                    .get(*fieldname)
                    .map(|v| Self::value_to_string(v))
                    .unwrap_or_default();
                row.push(value);
            }
            let _ = writer.write_record(&row);
        }

        let _ = writer.flush();
        // Drop writer to release borrow on buffer
        drop(writer);
        let sample_size_bytes = buffer.len() as u64;

        // Estimate total size based on sample
        if sample_size > 0 {
            (sample_size_bytes * records.len() as u64) / sample_size as u64
        } else {
            0
        }
    }

    /// Write a chunk of records to a single CSV file
    fn write_chunk(
        &mut self,
        records: &[HashMap<String, serde_json::Value>],
        file_counter: usize,
        fieldnames: &[String],
        fieldname_refs: &[&str],
        delimiter_byte: u8,
    ) -> Result<FileMetadata, String> {
        if records.is_empty() {
            return Err("No records to write".to_string());
        }

        // Build output path
        let output_dir = PathBuf::from(&self.config.output_base);
        std::fs::create_dir_all(&output_dir)
            .map_err(|e| format!("Failed to create output directory: {}", e))?;

        let output_file = output_dir.join(format!("part-{:05}.csv", file_counter));

        let file = File::create(&output_file)
            .map_err(|e| format!("Failed to create output file: {}", e))?;

        let mut writer = WriterBuilder::new()
            .delimiter(delimiter_byte)
            .has_headers(false) // We'll write headers manually if needed
            .from_writer(file);

        // Write header if needed (only for first file)
        if self.config.engine.options.include_header && !self.header_written {
            writer
                .write_record(fieldnames)
                .map_err(|e| format!("Failed to write header: {}", e))?;
            self.header_written = true;
        }

        // Write records with optimized conversion
        let mut row = Vec::with_capacity(fieldnames.len());
        
        for record in records {
            row.clear();
            
            for fieldname in fieldname_refs {
                let value = record
                    .get(*fieldname)
                    .map(|v| Self::value_to_string(v))
                    .unwrap_or_default();
                row.push(value);
            }
            
            writer
                .write_record(&row)
                .map_err(|e| format!("Failed to write record: {}", e))?;
        }

        writer
            .flush()
            .map_err(|e| format!("Failed to flush writer: {}", e))?;

        // Get file size
        let file_size = std::fs::metadata(&output_file)
            .map(|m| m.len())
            .unwrap_or(0);

        Ok(FileMetadata {
            path: output_file.to_string_lossy().to_string(),
            size_bytes: file_size,
            record_count: records.len(),
            format: "csv".to_string(),
        })
    }

    /// Write batch of records to CSV file(s) with size-based splitting
    fn write_batch_with_counter(
        &mut self,
        records: Vec<HashMap<String, serde_json::Value>>,
        file_counter: usize,
    ) -> Result<Vec<FileMetadata>, String> {
        if records.is_empty() {
            return Err("No records to write".to_string());
        }

        // Get field names from schema or first record
        let fieldnames: Vec<String> = if !self.config.schema.is_empty() {
            self.config.schema.iter().map(|f| f.name.clone()).collect()
        } else {
            records[0].keys().map(|k| k.clone()).collect()
        };
        
        // Create string slice references for efficient HashMap lookups
        let fieldname_refs: Vec<&str> = fieldnames.iter().map(|s| s.as_str()).collect();

        // Get delimiter
        let delimiter_byte = if self.config.engine.options.delimiter.len() == 1 {
            self.config.engine.options.delimiter.as_bytes()[0]
        } else {
            b','
        };

        // Calculate target size in bytes
        let target_size_bytes = self.config.engine.options.target_size_mb * 1024 * 1024;

        // Estimate total size
        let estimated_total_size = self.estimate_csv_size(
            &records,
            &fieldnames,
            delimiter_byte,
            self.config.engine.options.include_header && !self.header_written,
        );

        let mut all_metadata = Vec::new();
        let mut current_counter = file_counter;

        // If estimated size is less than target, write everything in one file
        if estimated_total_size <= target_size_bytes || target_size_bytes == 0 {
            let metadata = self.write_chunk(
                &records,
                current_counter,
                &fieldnames,
                &fieldname_refs,
                delimiter_byte,
            )?;
            all_metadata.push(metadata);
        } else {
            // Split into multiple files based on estimated size
            let estimated_records_per_file = if estimated_total_size > 0 {
                (records.len() as u64 * target_size_bytes) / estimated_total_size
            } else {
                records.len() as u64
            };

            let mut chunk_start = 0;
            while chunk_start < records.len() {
                // Calculate chunk end based on estimated size
                let chunk_end = if estimated_records_per_file > 0 {
                    (chunk_start + estimated_records_per_file as usize).min(records.len())
                } else {
                    records.len()
                };

                // Write chunk
                let chunk = &records[chunk_start..chunk_end];
                let metadata = self.write_chunk(
                    chunk,
                    current_counter,
                    &fieldnames,
                    &fieldname_refs,
                    delimiter_byte,
                )?;

                // If file is still too large, we'll split more aggressively next time
                // For now, just move to next file
                all_metadata.push(metadata);
                current_counter += 1;
                chunk_start = chunk_end;
            }
        }

        Ok(all_metadata)
    }
}

/// Create CSV writer from JSON config
///
/// # Safety
/// config_json must be a valid null-terminated C string
#[no_mangle]
pub unsafe extern "C" fn create_writer(config_json: *const c_char) -> *mut CsvWriter {
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
    match CsvWriter::new(config) {
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
    writer: *mut CsvWriter,
    records_json: *const c_char,
) -> *const c_char {
    if writer.is_null() || records_json.is_null() {
        return std::ptr::null();
    }

    let writer = &mut *writer;

    // Parse input JSON - use bytes directly for better performance
    let c_str = match CStr::from_ptr(records_json).to_str() {
        Ok(s) => s,
        Err(_) => return std::ptr::null(),
    };

    #[derive(Deserialize)]
    struct Input {
        records: Vec<HashMap<String, serde_json::Value>>,
        #[serde(default)]
        file_counter: Option<usize>,
    }

    // Use from_str which is already optimized in serde_json
    // For very large inputs, consider using a streaming parser in the future
    let input: Input = match serde_json::from_str(c_str) {
        Ok(i) => i,
        Err(e) => {
            eprintln!("Failed to parse input: {}", e);
            return std::ptr::null();
        }
    };

    // Use provided file_counter if available, otherwise use internal counter
    let current_counter = input.file_counter.unwrap_or(writer.file_counter);

    // Write batch (may return multiple files if split)
    let metadata_vec = match writer.write_batch_with_counter(input.records, current_counter) {
        Ok(m) => m,
        Err(e) => {
            eprintln!("Write error: {}", e);
            return std::ptr::null();
        }
    };

    // Update internal counter based on number of files written
    writer.file_counter = current_counter + metadata_vec.len();

    // Serialize metadata to JSON
    let json = match serde_json::to_string(&metadata_vec) {
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

/// Free CSV writer
///
/// # Safety
/// writer must be a valid pointer from create_writer
#[no_mangle]
pub unsafe extern "C" fn free_writer(writer: *mut CsvWriter) {
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
            "target_type": "csv",
            "connection": {},
            "engine": {
                "options": {
                    "delimiter": ",",
                    "include_header": true
                }
            }
        }"#;

        let config: WriterConfig = serde_json::from_str(config_json).unwrap();
        assert_eq!(config.asset_name, "test_table");
        assert_eq!(config.schema.len(), 2);
        assert_eq!(config.engine.options.delimiter, ",");
        assert_eq!(config.engine.options.include_header, true);
    }
}
