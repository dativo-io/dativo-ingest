//! High-performance CSV reader plugin for Dativo ETL
//!
//! This Rust plugin demonstrates:
//! - Fast CSV parsing using the csv crate
//! - Zero-copy operations where possible
//! - Efficient memory management
//! - C-compatible FFI interface
//!
//! Build with: cargo build --release
//! Output: target/release/libcsv_reader_plugin.so (or .dylib/.dll)

use csv::ReaderBuilder;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::ffi::{CStr, CString};
use std::os::raw::c_char;
use std::path::PathBuf;

/// Configuration passed from Python
#[derive(Debug, Deserialize)]
struct SourceConfig {
    #[serde(rename = "type")]
    source_type: String,
    connection: HashMap<String, serde_json::Value>,
    files: Vec<FileConfig>,
    #[serde(default)]
    engine: EngineConfig,
}

#[derive(Debug, Deserialize)]
struct FileConfig {
    path: String,
    #[serde(default)]
    id: Option<String>,
}

#[derive(Debug, Deserialize, Default)]
struct EngineConfig {
    #[serde(default)]
    options: EngineOptions,
}

#[derive(Debug, Deserialize)]
struct EngineOptions {
    #[serde(default = "default_batch_size")]
    batch_size: usize,
    #[serde(default = "default_delimiter")]
    delimiter: char,
}

fn default_batch_size() -> usize {
    10000
}

fn default_delimiter() -> char {
    ','
}

impl Default for EngineOptions {
    fn default() -> Self {
        Self {
            batch_size: default_batch_size(),
            delimiter: default_delimiter(),
        }
    }
}

/// CSV Reader state
pub struct CsvReader {
    config: SourceConfig,
    current_file_idx: usize,
    current_reader: Option<csv::Reader<std::fs::File>>,
    headers: Vec<String>,
}

impl CsvReader {
    /// Create new CSV reader from configuration
    fn new(config: SourceConfig) -> Result<Self, String> {
        Ok(Self {
            config,
            current_file_idx: 0,
            current_reader: None,
            headers: Vec::new(),
        })
    }

    /// Open next file for reading
    fn open_next_file(&mut self) -> Result<bool, String> {
        if self.current_file_idx >= self.config.files.len() {
            return Ok(false);
        }

        let file_config = &self.config.files[self.current_file_idx];
        let file_path = PathBuf::from(&file_config.path);

        // Open CSV file
        // Use flexible mode to handle inconsistent field counts
        let reader = ReaderBuilder::new()
            .delimiter(self.config.engine.options.delimiter as u8)
            .flexible(true)  // Allow records with different field counts
            .from_path(&file_path)
            .map_err(|e| format!("Failed to open CSV file: {}", e))?;

        self.current_reader = Some(reader);
        self.current_file_idx += 1;

        // Read headers
        if let Some(reader) = &mut self.current_reader {
            if let Ok(headers) = reader.headers() {
                self.headers = headers.iter().map(|h| h.to_string()).collect();
            }
        }

        Ok(true)
    }

    /// Extract next batch of records
    fn extract_batch(&mut self) -> Result<Vec<HashMap<String, serde_json::Value>>, String> {
        let mut records = Vec::new();
        let batch_size = self.config.engine.options.batch_size;

        loop {
            // Ensure we have a reader
            if self.current_reader.is_none() {
                if !self.open_next_file()? {
                    // No more files
                    break;
                }
            }

            // Read records from current file
            if let Some(reader) = &mut self.current_reader {
                for result in reader.records() {
                    match result {
                        Ok(record) => {
                            let mut map = HashMap::new();
                            for (i, field) in record.iter().enumerate() {
                                if let Some(header) = self.headers.get(i) {
                                    // Try to parse as number, otherwise store as string
                                    let value = if let Ok(num) = field.parse::<i64>() {
                                        serde_json::Value::Number(num.into())
                                    } else if let Ok(num) = field.parse::<f64>() {
                                        serde_json::Number::from_f64(num)
                                            .map(serde_json::Value::Number)
                                            .unwrap_or_else(|| {
                                                serde_json::Value::String(field.to_string())
                                            })
                                    } else {
                                        serde_json::Value::String(field.to_string())
                                    };
                                    map.insert(header.clone(), value);
                                }
                            }
                            records.push(map);

                            if records.len() >= batch_size {
                                return Ok(records);
                            }
                        }
                        Err(e) => {
                            return Err(format!("CSV parsing error: {}", e));
                        }
                    }
                }

                // Finished current file
                self.current_reader = None;
            }
        }

        Ok(records)
    }
}

/// Create CSV reader from JSON config
///
/// # Safety
/// config_json must be a valid null-terminated C string
#[no_mangle]
pub unsafe extern "C" fn create_reader(config_json: *const c_char) -> *mut CsvReader {
    if config_json.is_null() {
        return std::ptr::null_mut();
    }

    // Convert C string to Rust string
    let c_str = match CStr::from_ptr(config_json).to_str() {
        Ok(s) => s,
        Err(_) => return std::ptr::null_mut(),
    };

    // Parse JSON config
    let config: SourceConfig = match serde_json::from_str(c_str) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Failed to parse config: {}", e);
            return std::ptr::null_mut();
        }
    };

    // Create reader
    match CsvReader::new(config) {
        Ok(reader) => Box::into_raw(Box::new(reader)),
        Err(e) => {
            eprintln!("Failed to create reader: {}", e);
            std::ptr::null_mut()
        }
    }
}

/// Extract next batch of records
///
/// Returns JSON string that must be freed with free_string
///
/// # Safety
/// reader must be a valid pointer from create_reader
#[no_mangle]
pub unsafe extern "C" fn extract_batch(reader: *mut CsvReader) -> *const c_char {
    if reader.is_null() {
        return std::ptr::null();
    }

    let reader = &mut *reader;

    // Extract batch
    let records = match reader.extract_batch() {
        Ok(r) => r,
        Err(e) => {
            eprintln!("Extract error: {}", e);
            return std::ptr::null();
        }
    };

    // If no records, return null to signal end
    if records.is_empty() {
        return std::ptr::null();
    }

    // Serialize to JSON
    let json = match serde_json::to_string(&records) {
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

/// Free CSV reader
///
/// # Safety
/// reader must be a valid pointer from create_reader
#[no_mangle]
pub unsafe extern "C" fn free_reader(reader: *mut CsvReader) {
    if !reader.is_null() {
        drop(Box::from_raw(reader));
    }
}

/// Free string returned by extract_batch
///
/// # Safety
/// s must be a valid pointer from extract_batch
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
            "type": "csv",
            "connection": {},
            "files": [{"path": "test.csv"}],
            "engine": {
                "options": {
                    "batch_size": 1000,
                    "delimiter": ","
                }
            }
        }"#;

        let config: SourceConfig = serde_json::from_str(config_json).unwrap();
        assert_eq!(config.source_type, "csv");
        assert_eq!(config.files.len(), 1);
        assert_eq!(config.engine.options.batch_size, 1000);
    }
}
