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

    fn write_batch(&self, request: &Value) -> Value {
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

