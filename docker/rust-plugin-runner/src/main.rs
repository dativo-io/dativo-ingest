// Rust plugin runner that loads and executes plugins in a container
// Communicates via JSON over stdin/stdout

use libloading::{Library, Symbol};
use serde_json::{json, Value};
use std::io::{self, BufRead, Write};
use std::os::raw::c_char;

type CreateReaderFn = unsafe extern "C" fn(*const u8, usize) -> *mut u8;
type CreateWriterFn = unsafe extern "C" fn(*const u8, usize) -> *mut u8;
type ExtractBatchFn = unsafe extern "C" fn(*mut u8) -> *const u8;
type WriteBatchFn = unsafe extern "C" fn(*mut u8, *const u8, usize) -> *const u8;
type DiscoverFn = unsafe extern "C" fn(*const u8, usize) -> *const u8;
type CommitFilesFn = unsafe extern "C" fn(*mut u8, *const u8, usize) -> *const u8;
type FreeReaderFn = unsafe extern "C" fn(*mut u8);
type FreeWriterFn = unsafe extern "C" fn(*mut u8);
type FreeStringFn = unsafe extern "C" fn(*const u8);

struct PluginRunner {
    lib: Library,
    reader_ptr: Option<*mut u8>,
    writer_ptr: Option<*mut u8>,
}

impl PluginRunner {
    fn new(lib_path: &str) -> Result<Self, String> {
        let lib = unsafe { Library::new(lib_path) }
            .map_err(|e| format!("Failed to load library: {}", e))?;

        Ok(PluginRunner {
            lib,
            reader_ptr: None,
            writer_ptr: None,
        })
    }

    fn handle_request(&mut self, request: Value) -> Value {
        let method = match request
            .get("method")
            .and_then(|m| m.as_str())
        {
            Some(m) => m,
            None => return json!({"error": "Missing method"}),
        };

        match method {
            "create_reader" => self.create_reader(&request),
            "create_writer" => self.create_writer(&request),
            "extract_batch" => self.extract_batch(),
            "write_batch" => self.write_batch(&request),
            "check_connection" => self.check_connection(&request),
            "discover" => self.discover(&request),
            "extract" => self.extract(&request),
            "commit_files" => self.commit_files(&request),
            _ => json!({"error": format!("Unknown method: {}", method)}),
        }
    }

    fn create_reader(&mut self, request: &Value) -> Value {
        let config_json = match request
            .get("config")
            .and_then(|c| c.as_str())
        {
            Some(c) => c,
            None => return json!({"error": "Missing config"}),
        };

        unsafe {
            let create_reader: Symbol<CreateReaderFn> = match self
                .lib
                .get(b"create_reader")
            {
                Ok(f) => f,
                Err(e) => return json!({"error": format!("Failed to get create_reader: {}", e)}),
            };

            let config_bytes = config_json.as_bytes();
            let reader_ptr = create_reader(config_bytes.as_ptr(), config_bytes.len());
            self.reader_ptr = Some(reader_ptr);

            json!({"status": "success", "reader_ptr": reader_ptr as u64})
        }
    }

    fn create_writer(&mut self, request: &Value) -> Value {
        let config_json = match request
            .get("config")
            .and_then(|c| c.as_str())
        {
            Some(c) => c,
            None => return json!({"error": "Missing config"}),
        };

        unsafe {
            let create_writer: Symbol<CreateWriterFn> = match self
                .lib
                .get(b"create_writer")
            {
                Ok(f) => f,
                Err(e) => return json!({"error": format!("Failed to get create_writer: {}", e)}),
            };

            let config_bytes = config_json.as_bytes();
            let writer_ptr = create_writer(config_bytes.as_ptr(), config_bytes.len());
            self.writer_ptr = Some(writer_ptr);

            json!({"status": "success", "writer_ptr": writer_ptr as u64})
        }
    }

    fn extract_batch(&self) -> Value {
        if let Some(reader_ptr) = self.reader_ptr {
            unsafe {
                let extract_batch: Symbol<ExtractBatchFn> = match self
                    .lib
                    .get(b"extract_batch")
                {
                    Ok(f) => f,
                    Err(e) => return json!({"error": format!("Failed to get extract_batch: {}", e)}),
                };

                let result_ptr = extract_batch(reader_ptr);
                if result_ptr.is_null() {
                    return json!({"status": "done"});
                }

                // Convert C string to Rust string
                let result_str = std::ffi::CStr::from_ptr(result_ptr as *const c_char)
                    .to_str()
                    .unwrap()
                    .to_string();

                // Free the string
                let free_string: Symbol<FreeStringFn> = self
                    .lib
                    .get(b"free_string")
                    .unwrap();
                free_string(result_ptr);

                json!({"status": "success", "data": serde_json::from_str::<Value>(&result_str).unwrap()})
            }
        } else {
            json!({"error": "Reader not initialized"})
        }
    }

    fn write_batch(&mut self, request: &Value) -> Value {
        // If writer is not initialized, try to create it from config
        if self.writer_ptr.is_none() {
            if let Some(config_json) = request.get("config").and_then(|c| c.as_str()) {
                let create_request = json!({"method": "create_writer", "config": config_json});
                let create_result = self.create_writer(&create_request);
                if create_result.get("error").is_some() {
                    return create_result;
                }
            } else {
                return json!({"error": "Writer not initialized and no config provided"});
            }
        }

        if let Some(writer_ptr) = self.writer_ptr {
            let records_json = match request.get("records") {
                Some(r) => r,
                None => return json!({"error": "Missing records"}),
            };

            unsafe {
                let write_batch: Symbol<WriteBatchFn> = match self
                    .lib
                    .get(b"write_batch")
                {
                    Ok(f) => f,
                    Err(e) => return json!({"error": format!("Failed to get write_batch: {}", e)}),
                };

                let records_str = serde_json::to_string(records_json).unwrap();
                let records_bytes = records_str.as_bytes();
                let result_ptr = write_batch(writer_ptr, records_bytes.as_ptr(), records_bytes.len());

                if result_ptr.is_null() {
                    return json!({"error": "Write failed"});
                }

                // Convert C string to Rust string
                let result_str = std::ffi::CStr::from_ptr(result_ptr as *const c_char)
                    .to_str()
                    .unwrap()
                    .to_string();

                // Free the string
                let free_string: Symbol<FreeStringFn> = self
                    .lib
                    .get(b"free_string")
                    .unwrap();
                free_string(result_ptr);

                json!({"status": "success", "data": serde_json::from_str::<Value>(&result_str).unwrap()})
            }
        } else {
            json!({"error": "Writer not initialized"})
        }
    }

    fn check_connection(&self, _request: &Value) -> Value {
        // For now, return success
        // This would need to call a check_connection function from the plugin
        json!({"status": "success", "success": true, "message": "Connection OK"})
    }

    fn discover(&self, request: &Value) -> Value {
        let config_json = match request
            .get("config")
            .and_then(|c| c.as_str())
        {
            Some(c) => c,
            None => return json!({"error": "Missing config"}),
        };

        unsafe {
            // Try to get discover function from plugin
            let discover: Symbol<DiscoverFn> = match self.lib.get(b"discover") {
                Ok(f) => f,
                Err(_) => {
                    // If discover function doesn't exist, return empty result
                    return json!({"status": "success", "data": {"objects": [], "metadata": {}}});
                }
            };

            let config_bytes = config_json.as_bytes();
            let result_ptr = discover(config_bytes.as_ptr(), config_bytes.len());

            if result_ptr.is_null() {
                return json!({"status": "success", "data": {"objects": [], "metadata": {}}});
            }

            // Convert C string to Rust string
            let result_str = std::ffi::CStr::from_ptr(result_ptr as *const c_char)
                .to_str()
                .unwrap()
                .to_string();

            // Free the string
            let free_string: Symbol<FreeStringFn> = self
                .lib
                .get(b"free_string")
                .unwrap();
            free_string(result_ptr);

            json!({"status": "success", "data": serde_json::from_str::<Value>(&result_str).unwrap()})
        }
    }

    fn extract(&mut self, request: &Value) -> Value {
        // Extract uses the stateful API: create_reader, then extract_batch in a loop
        let config_json = match request
            .get("config")
            .and_then(|c| c.as_str())
        {
            Some(c) => c,
            None => return json!({"error": "Missing config"}),
        };

        // First, create reader if not already created
        if self.reader_ptr.is_none() {
            let create_request = json!({"method": "create_reader", "config": config_json});
            let create_result = self.create_reader(&create_request);
            if create_result.get("error").is_some() {
                return create_result;
            }
        }

        // Now extract all batches
        let mut batches = Vec::new();
        loop {
            let batch_result = self.extract_batch();
            
            // Check for errors first
            if let Some(error) = batch_result.get("error") {
                return json!({"error": error, "batches_extracted": batches.len()});
            }

            // Check if we're done
            if let Some(status) = batch_result.get("status").and_then(|s| s.as_str()) {
                if status == "done" {
                    break;
                }
            }

            // Extract data from batch result
            if let Some(data) = batch_result.get("data") {
                batches.push(data.clone());
            } else if let Some(status) = batch_result.get("status").and_then(|s| s.as_str()) {
                // If status is "success" but no data, skip this batch
                if status != "success" {
                    // Unexpected status, break to avoid infinite loop
                    break;
                }
            } else {
                // If no data field and no status, use the whole result
                batches.push(batch_result.clone());
            }
        }

        json!({"status": "success", "data": batches})
    }

    fn commit_files(&self, request: &Value) -> Value {
        if let Some(writer_ptr) = self.writer_ptr {
            let file_metadata_json = match request.get("file_metadata") {
                Some(fm) => fm,
                None => return json!({"error": "Missing file_metadata"}),
            };

            unsafe {
                // Try to get commit_files function from plugin
                let commit_files: Symbol<CommitFilesFn> = match self.lib.get(b"commit_files") {
                    Ok(f) => f,
                    Err(_) => {
                        // If commit_files function doesn't exist, return success
                        return json!({"status": "success", "data": {"status": "success", "files_committed": 0}});
                    }
                };

                let file_metadata_str = serde_json::to_string(file_metadata_json).unwrap();
                let file_metadata_bytes = file_metadata_str.as_bytes();
                let result_ptr = commit_files(writer_ptr, file_metadata_bytes.as_ptr(), file_metadata_bytes.len());

                if result_ptr.is_null() {
                    return json!({"status": "success", "data": {"status": "success", "files_committed": 0}});
                }

                // Convert C string to Rust string
                let result_str = std::ffi::CStr::from_ptr(result_ptr as *const c_char)
                    .to_str()
                    .unwrap()
                    .to_string();

                // Free the string
                let free_string: Symbol<FreeStringFn> = self
                    .lib
                    .get(b"free_string")
                    .unwrap();
                free_string(result_ptr);

                json!({"status": "success", "data": serde_json::from_str::<Value>(&result_str).unwrap()})
            }
        } else {
            json!({"error": "Writer not initialized"})
        }
    }
}

impl Drop for PluginRunner {
    fn drop(&mut self) {
        unsafe {
            if let Some(reader_ptr) = self.reader_ptr {
                if let Ok(free_reader) = self.lib.get::<FreeReaderFn>(b"free_reader") {
                    free_reader(reader_ptr);
                }
            }
            if let Some(writer_ptr) = self.writer_ptr {
                if let Ok(free_writer) = self.lib.get::<FreeWriterFn>(b"free_writer") {
                    free_writer(writer_ptr);
                }
            }
        }
    }
}

fn main() {
    let stdin = io::stdin();
    let mut stdout = io::stdout();
    let mut runner: Option<PluginRunner> = None;

    for line in stdin.lock().lines() {
        let line = line.unwrap();
        if line.is_empty() {
            continue;
        }

        let request: Value = match serde_json::from_str(&line) {
            Ok(r) => r,
            Err(e) => {
                let error_response = json!({
                    "status": "error",
                    "error": format!("Failed to parse request: {}", e)
                });
                writeln!(stdout, "{}", serde_json::to_string(&error_response).unwrap()).unwrap();
                stdout.flush().unwrap();
                continue;
            }
        };

        // Handle initialization request
        if let Some(lib_path) = request.get("init").and_then(|i| i.as_str()) {
            match PluginRunner::new(lib_path) {
                Ok(r) => {
                    runner = Some(r);
                    let response = json!({"status": "success", "message": "Initialized"});
                    writeln!(stdout, "{}", serde_json::to_string(&response).unwrap()).unwrap();
                }
                Err(e) => {
                    let response = json!({"status": "error", "error": e});
                    writeln!(stdout, "{}", serde_json::to_string(&response).unwrap()).unwrap();
                }
            }
            stdout.flush().unwrap();
            continue;
        }

        // Handle method calls
        if let Some(ref mut r) = runner {
            let response = r.handle_request(request);
            writeln!(stdout, "{}", serde_json::to_string(&response).unwrap()).unwrap();
        } else {
            let response = json!({"status": "error", "error": "Not initialized"});
            writeln!(stdout, "{}", serde_json::to_string(&response).unwrap()).unwrap();
        }
        stdout.flush().unwrap();
    }
}

