# Contributing to Dativo ETL

Thank you for your interest in contributing to Dativo ETL!

## Development Setup

### 1. Clone Repository

```bash
git clone https://github.com/YOUR_ORG/dativo-etl.git
cd dativo-etl
```

### 2. Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-mock pytest-cov

# Set Python path
export PYTHONPATH="$PWD/src:$PYTHONPATH"
```

### 3. Set Up Rust (Optional)

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# Build Rust plugins
cd examples/plugins/rust
make build-release
```

## Running Tests

### Before Submitting PR

Always run the full test suite:

```bash
# Run all tests
./tests/run_all_plugin_tests.sh
```

### Specific Test Suites

```bash
# Python unit tests
pytest tests/test_plugins.py -v

# Integration tests
./tests/test_plugin_integration.sh

# Rust plugin tests
cd examples/plugins/rust && ./test_rust_plugins.sh
```

## Making Changes

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

### 2. Make Your Changes

- Follow existing code style
- Add tests for new functionality
- Update documentation

### 3. Run Tests

```bash
# Run tests that cover your changes
pytest tests/test_*.py -v

# Run full suite
./tests/run_all_plugin_tests.sh
```

### 4. Commit Changes

```bash
git add .
git commit -m "feat: add new feature"
# or
git commit -m "fix: resolve bug in plugin loader"
```

**Commit message format:**
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Test additions/changes
- `refactor:` Code refactoring
- `perf:` Performance improvements

### 5. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub.

## Contributing Guidelines

### Code Style

- Follow PEP 8 for Python code
- Use type hints where appropriate
- Add docstrings to functions and classes
- Keep functions focused and small

### Testing Requirements

**All PRs must include tests:**

1. **Unit Tests** - For new functionality
   - Add to `tests/test_plugins.py` or create new test file
   - Test happy paths and edge cases
   - Mock external dependencies

2. **Integration Tests** - For plugin changes
   - Add to `tests/test_plugin_integration.sh`
   - Test with real file I/O
   - Verify error handling

3. **Rust Tests** - For Rust plugins
   - Add Rust unit tests in `src/lib.rs`
   - Update `test_rust_plugins.sh` if needed

### Documentation

Update documentation for:
- New features → `docs/CUSTOM_PLUGINS.md`
- API changes → docstrings
- Configuration → `docs/CONFIG_REFERENCE.md`
- Examples → `examples/` directory

### Plugin Contributions

#### Python Plugins

```python
# examples/plugins/your_plugin.py
from dativo_ingest.plugins import BaseReader

class YourReader(BaseReader):
    """Your plugin description."""
    
    def extract(self, state_manager=None):
        """Extract data from your source."""
        # Implementation
        yield batch_of_records
```

**Requirements:**
- Inherit from `BaseReader` or `BaseWriter`
- Add docstrings
- Include usage example
- Add tests
- Update `examples/plugins/README.md`

#### Rust Plugins

```rust
// examples/plugins/rust/your_plugin/src/lib.rs
#[no_mangle]
pub unsafe extern "C" fn create_reader(config_json: *const c_char) -> *mut Reader {
    // Implementation
}
```

**Requirements:**
- Follow FFI conventions
- Export required functions
- Add Rust unit tests
- Update build system
- Update `examples/plugins/rust/README.md`

## Pull Request Process

### 1. PR Description

Include:
- **What**: What does this PR do?
- **Why**: Why is this change needed?
- **How**: How does it work?
- **Testing**: What tests were added?

### 2. Checklist

Before submitting, ensure:

- [ ] Tests added and passing
- [ ] Documentation updated
- [ ] Code follows style guidelines
- [ ] Commit messages are clear
- [ ] No merge conflicts
- [ ] CI checks passing

### 3. Review Process

1. **Automated Checks** - CI must pass
2. **Code Review** - At least one approval needed
3. **Testing** - Reviewers may test locally
4. **Merge** - Squash and merge to main

### 4. After Merge

- Delete your branch
- Monitor CI on main branch
- Address any issues promptly

## CI/CD Pipeline

### GitHub Actions

All PRs run:
1. Linting checks
2. Core unit tests (Python 3.10, 3.11)
3. Plugin unit tests
4. Plugin integration tests
5. Rust plugin builds (Ubuntu, macOS)
6. Master test suite

**See:** `.github/workflows/` for details

### Required Checks

For merge approval:
- ✅ Core Tests (Python 3.10)
- ✅ Plugin Tests
- ✅ Rust Plugin Build

## Getting Help

### Resources

- **Documentation**: `docs/CUSTOM_PLUGINS.md`
- **Testing Guide**: `tests/PLUGIN_TESTING.md`
- **Examples**: `examples/plugins/`

### Questions?

- Check existing issues
- Review documentation
- Ask in discussions

### Reporting Bugs

**Use GitHub Issues** with:
- Clear title
- Steps to reproduce
- Expected vs actual behavior
- Environment details
- Error messages/logs

**Example:**
```
Title: Plugin loader fails with Rust .dylib files on macOS

Description:
When trying to load a Rust plugin with .dylib extension on macOS,
the plugin loader throws a ValueError.

Steps to reproduce:
1. Build Rust plugin on macOS
2. Configure job with custom_reader pointing to .dylib
3. Run job

Expected: Plugin loads successfully
Actual: ValueError: Plugin module not found

Environment:
- OS: macOS 13.2
- Python: 3.10.9
- Rust: 1.70.0
```

## Development Tips

### Fast Testing

```bash
# Test only what you changed
pytest tests/test_plugins.py::TestPluginLoader::test_your_new_test -v

# Run with debug output
pytest tests/test_plugins.py -v -s

# Skip slow tests
pytest tests/test_plugins.py -m "not slow"
```

### Debugging

```python
# Add breakpoints
import pdb; pdb.set_trace()

# Verbose logging
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Plugin Development

```bash
# Quick test cycle for Python plugins
export PYTHONPATH="$PWD/src:$PYTHONPATH"
python examples/plugins/your_plugin.py

# Quick test cycle for Rust plugins
cd examples/plugins/rust/your_plugin
cargo test
cargo build --release
```

## Code of Conduct

### Our Standards

- Be respectful and inclusive
- Accept constructive criticism
- Focus on what's best for the project
- Show empathy towards others

### Unacceptable Behavior

- Harassment or discrimination
- Trolling or insulting comments
- Publishing others' private information
- Other unprofessional conduct

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.

## Recognition

Contributors will be:
- Listed in `CONTRIBUTORS.md`
- Credited in release notes
- Acknowledged in documentation

Thank you for contributing to Dativo ETL! 🎉
