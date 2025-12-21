# AICodeReviewer Documentation

This directory contains the complete HTML documentation for the AICodeReviewer project, generated using Python's built-in `pydoc` tool.

## 📚 Documentation Overview

The documentation includes detailed information about all modules, classes, functions, and methods in the AICodeReviewer codebase.

### Files Generated:
- `index.html` - Main documentation index with project overview and navigation
- `src.aicodereviewer.html` - Package-level documentation
- Individual module documentation files (15 total)

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
- **bedrock.py** - AWS Bedrock AI client with rate limiting and timeout configuration
- **config.py** - Configuration management with batch and parallel processing settings
- **performance.py** - Performance monitoring and metrics tracking
- **auth.py** - AWS authentication and language detection
- **backup.py** - Backup file management and cleanup
- **orchestration.py** - Workflow orchestration with dependency injection
- **interfaces.py** - Protocol definitions for client abstraction

## 🔄 Regenerating Documentation

To regenerate the documentation after code changes:

```bash
cd /path/to/AICodeReviewer

# Generate package documentation
python -m pydoc -w src.aicodereviewer

# Generate all module documentation (15 modules total)
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
  src.aicodereviewer.auth \
  src.aicodereviewer.orchestration \
  src.aicodereviewer.interfaces

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

- Multi-language code analysis support (12+ languages)
- AWS Bedrock integration with configurable timeout settings
- Rate limiting and intelligent throttling with per-minute tracking
- Parallel file scanning for large codebases (ThreadPoolExecutor)
- Batch processing of files for efficient review workflow
- Interactive review workflow with multi-step issue resolution
- Performance optimizations including file caching and size limits
- Comprehensive error handling and retry logic
- Configurable settings for processing, logging, and API limits
- Automated backup and cleanup with timestamped archives
- JSON and human-readable reporting with summary statistics
- License compliance automation and third-party library auditing

---

**Generated:** December 21, 2025
**Version:** 1.0.0
**Test Coverage:** 93 passing tests with 100% core feature coverage