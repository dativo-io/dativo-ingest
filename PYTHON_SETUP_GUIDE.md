# Python Setup Guide

Dativo-ingest requires **Python 3.10 or higher**. This guide helps you get the right Python version installed.

---

## Quick Version Check

```bash
python3 --version
```

**Expected:** `Python 3.10.0` or higher  
**Problem:** If you see `Python 3.9.x` or below, follow the upgrade instructions below

---

## Why Python 3.10+?

Dativo-ingest uses features introduced in Python 3.10:
- Structural pattern matching
- Union type syntax improvements
- Better type hints
- Performance improvements

**Error you'll see with Python 3.9:**
```
ERROR: Package 'dativo-ingest' requires a different Python: 3.9.x not in '>=3.10'
```

---

## Upgrade Instructions

Choose the method that matches your system:

### Option 1: Conda (Recommended - Works on all platforms)

**Advantages:**
- ✅ Easy to manage multiple Python versions
- ✅ Isolated from system Python
- ✅ Works on macOS, Linux, Windows

**Steps:**

```bash
# 1. Create new environment with Python 3.10
conda create -n dativo python=3.10 -y

# 2. Activate the environment
conda activate dativo

# 3. Verify version
python --version  # Should show 3.10.x or higher

# 4. Navigate to dativo-ingest directory
cd /path/to/dativo-ingest

# 5. Install dativo-ingest
pip install -e .

# 6. Verify installation
dativo --help
```

**To use this environment in the future:**
```bash
conda activate dativo
```

**To deactivate:**
```bash
conda deactivate
```

---

### Option 2: Homebrew (macOS)

**Steps:**

```bash
# 1. Install Python 3.10
brew install python@3.10

# 2. Verify installation
python3.10 --version

# 3. Navigate to dativo-ingest directory
cd /path/to/dativo-ingest

# 4. Create virtual environment
python3.10 -m venv venv

# 5. Activate virtual environment
source venv/bin/activate

# 6. Verify Python version in venv
python --version  # Should show 3.10.x

# 7. Install dativo-ingest
pip install -e .

# 8. Verify installation
dativo --help
```

**To use this environment in the future:**
```bash
cd /path/to/dativo-ingest
source venv/bin/activate
```

**To deactivate:**
```bash
deactivate
```

---

### Option 3: pyenv (Version Manager)

**Advantages:**
- ✅ Manages multiple Python versions
- ✅ Project-specific Python versions
- ✅ Works on macOS and Linux

**Installation:**

```bash
# macOS
brew install pyenv

# Linux
curl https://pyenv.run | bash
```

**Setup:**

```bash
# 1. Install Python 3.10
pyenv install 3.10.13

# 2. List available versions (optional)
pyenv versions

# 3. Navigate to dativo-ingest directory
cd /path/to/dativo-ingest

# 4. Set local Python version
pyenv local 3.10.13

# 5. Verify version
python --version  # Should show 3.10.13

# 6. Create virtual environment
python -m venv venv

# 7. Activate virtual environment
source venv/bin/activate

# 8. Install dativo-ingest
pip install -e .

# 9. Verify installation
dativo --help
```

---

### Option 4: apt (Ubuntu/Debian)

```bash
# 1. Add deadsnakes PPA
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update

# 2. Install Python 3.10
sudo apt install python3.10 python3.10-venv python3.10-dev

# 3. Verify installation
python3.10 --version

# 4. Navigate to dativo-ingest directory
cd /path/to/dativo-ingest

# 5. Create virtual environment
python3.10 -m venv venv

# 6. Activate virtual environment
source venv/bin/activate

# 7. Upgrade pip
pip install --upgrade pip

# 8. Install dativo-ingest
pip install -e .

# 9. Verify installation
dativo --help
```

---

### Option 5: Windows

**Using Python.org Installer:**

1. Download Python 3.10+ from https://www.python.org/downloads/windows/
2. Run installer, check "Add Python to PATH"
3. Open Command Prompt or PowerShell:

```powershell
# Verify installation
python --version

# Navigate to dativo-ingest directory
cd C:\path\to\dativo-ingest

# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\activate

# Install dativo-ingest
pip install -e .

# Verify installation
dativo --help
```

---

## Verification Steps

After installation, verify everything works:

```bash
# 1. Check Python version
python --version  # Should be 3.10+

# 2. Check dativo is installed
dativo --help

# 3. Check pip packages
pip list | grep dativo

# 4. Run preflight check
./scripts/preflight-check.sh
```

**Expected preflight check output:**
```
1. Python Environment
  ✓ python3 is installed
     Version: 3.10.x (OK)
  ✓ pip3 is installed
  ✓ dativo-ingest package installed
  ✓ dativo CLI available
```

---

## Troubleshooting

### Issue: "pip install -e ." fails with permission error

**Solution:** Use virtual environment (don't install globally)
```bash
python3.10 -m venv venv
source venv/bin/activate
pip install -e .
```

### Issue: Multiple Python versions conflict

**Solution:** Use virtual environments or conda to isolate
```bash
# Create clean environment
conda create -n dativo python=3.10 -y
conda activate dativo
pip install -e .
```

### Issue: "python3.10: command not found"

**Solution:** Install Python 3.10 first
```bash
# macOS
brew install python@3.10

# Ubuntu/Debian
sudo apt install python3.10

# Or use conda
conda install python=3.10
```

### Issue: "dativo: command not found" after installation

**Solutions:**

1. Ensure virtual environment is activated:
   ```bash
   source venv/bin/activate  # or conda activate dativo
   ```

2. Reinstall in editable mode:
   ```bash
   pip install -e .
   ```

3. Use full path:
   ```bash
   python -m dativo_ingest.cli --help
   ```

---

## Environment Management Best Practices

### Keep Environments Isolated

**❌ Don't:**
- Install globally with `sudo pip install`
- Mix multiple projects in one environment

**✅ Do:**
- Use virtual environments or conda
- One environment per project
- Document which environment to use

### Recommended Project Structure

```
dativo-ingest/
├── venv/               # Virtual environment (gitignored)
├── .python-version     # For pyenv users
├── environment.yml     # For conda users
└── ...
```

### Activating Environment Each Session

Add to your shell profile (`~/.bashrc`, `~/.zshrc`):

```bash
# For conda users
alias dativo='conda activate dativo'

# For venv users
alias dativo='cd /path/to/dativo-ingest && source venv/bin/activate'
```

---

## Summary

| Method | Best For | Command |
|--------|----------|---------|
| **Conda** | All platforms, beginners | `conda create -n dativo python=3.10` |
| **Homebrew** | macOS users | `brew install python@3.10` |
| **pyenv** | Multiple Python versions | `pyenv install 3.10.13` |
| **apt** | Ubuntu/Debian | `sudo apt install python3.10` |
| **Python.org** | Windows | Download and run installer |

**Recommended:** Use Conda for easiest management across all platforms.

---

## Next Steps

Once Python 3.10+ is installed:

1. ✅ **Verify environment:** `./scripts/preflight-check.sh`
2. ✅ **Start services:** `docker-compose -f docker-compose.dev.yml up -d`
3. ✅ **Run tests:** Follow [TESTING_PLAYBOOK.md](TESTING_PLAYBOOK.md)

---

## Related Documentation

- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [README.md](README.md) - Platform overview
- [TESTING_GUIDE_INDEX.md](TESTING_GUIDE_INDEX.md) - Complete testing guide

---

**Need help?** Run `./scripts/preflight-check.sh` for detailed environment diagnostics.
