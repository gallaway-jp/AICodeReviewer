# AICodeReviewer Documentation

This directory contains the complete HTML documentation for the AICodeReviewer project, generated using Python's built-in `pydoc` tool.

## 📚 Documentation Overview

The documentation includes detailed information about all modules, classes, functions, and methods in the AICodeReviewer codebase.

### Files Generated:
- `index.html` - Main documentation index with project overview and navigation
- `src.aicodereviewer.html` - Package-level documentation
- Individual module documentation files (13 total)

## 🚀 Viewing the Documentation

### Option 1: Local Server (Recommended)
```bash
cd docs
python -m http.server 8080
```
Then open http://localhost:8080 in your browser.

### Option 2: Direct File Access
Open `index.html` directly in your web browser for offline viewing.

## 📖 Documentation Contents

### Core Modules:
- **main.py** - CLI entry point and workflow orchestration
- **models.py** - Data structures for issues and reports
- **scanner.py** - File discovery and diff parsing
- **reviewer.py** - AI-powered issue detection
- **fixer.py** - Automated code fix generation
- **interactive.py** - User interaction workflow
- **reporter.py** - Report generation and formatting

### Supporting Modules:
- **bedrock.py** - AWS Bedrock AI client
- **config.py** - Configuration management
- **performance.py** - Performance monitoring
- **auth.py** - AWS authentication
- **backup.py** - Backup file management

## 🔄 Regenerating Documentation

To regenerate the documentation after code changes:

```bash
cd /path/to/AICodeReviewer

# Generate package documentation
python -m pydoc -w src.aicodereviewer

# Generate all module documentation
python -m pydoc -w \
  src.aicodereviewer.main \
  src.aicodereviewer.models \
  src.aicodereviewer.scanner \
  src.aicodereviewer.reviewer \
  src.aicodereviewer.fixer \
  src.aicodereviewer.interactive \
  src.aicodereviewer.reporter \
  src.aicodereviewer.backup \
  src.aicodereviewer.bedrock \
  src.aicodereviewer.config \
  src.aicodereviewer.performance \
  src.aicodereviewer.auth

# Move files to docs directory
mkdir -p docs
mv *.html docs/
```

## 📋 Documentation Features

- **Complete API Reference** - All public functions, classes, and methods
- **Parameter Documentation** - Detailed parameter descriptions and types
- **Return Value Information** - What each function returns
- **Usage Examples** - Code examples where applicable
- **Cross-references** - Links between related modules and functions
- **Source Code Links** - Direct links to source code locations

## 🎯 Key Features Documented

- Multi-language code analysis support
- AWS Bedrock integration with rate limiting
- Interactive review workflow
- Performance optimizations and caching
- Comprehensive error handling
- Configurable settings and thresholds
- Automated backup and cleanup
- JSON and human-readable reporting

---

**Generated:** December 21, 2025
**Version:** 1.0.0
**Test Coverage:** 100% (67 tests passing)