# AICodeReviewer

An AI-powered code review tool that analyzes your codebase for security, performance, and best practices issues. Supports 12+ programming languages including Python, JavaScript, TypeScript, Java, C/C++, C#, Go, Ruby, PHP, Rust, Swift, Kotlin, and Objective-C. Includes framework support for React (.jsx, .tsx), Laravel (.blade.php), Vue, Svelte, and Astro, plus web technologies like HTML, CSS, Sass, Less, JSON, XML, and YAML.

## Installation

1. Clone or download this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Running with Python Interpreter

You can run the program directly using Python:

```bash
# From the project root (after installing with pip install -e .)
python -m aicodereviewer /path/to/your/project

# Or directly
python src/aicodereviewer/main.py /path/to/your/project
```

### Running the Windows Executable

After building with `build_exe.bat`, you can run the standalone executable:

```bash
dist\AICodeReviewer.exe /path/to/your/project
```

### Command Line Options

- `path`: Path to the project folder to review (required for project scope, optional for diff scope to provide additional context)
- `--scope`: Review scope - `project` (default, entire project) or `diff` (changes only)
- `--diff-file FILE`: Path to diff file (TortoiseSVN/TortoiseGit format) when using diff scope
- `--commits RANGE`: Commit range for diff generation (e.g., `HEAD~1..HEAD`) when using diff scope
- `--type`: Review type (default: best_practices)
  - `security`: Comprehensive security analysis covering OWASP Top 10 vulnerabilities and additional security risks including injection attacks, authentication issues, XSS, CSRF, insecure configurations, and secure coding practices with severity levels
  - `performance`: Optimize efficiency and resources
  - `best_practices`: Review for clean code and SOLID principles
  - `maintainability`: Analyze code for readability and long-term sustainability
  - `documentation`: Review documentation, comments, and docstrings
  - `testing`: Analyze testability and suggest testing improvements
  - `accessibility`: Review for accessibility compliance
  - `scalability`: Analyze for scalability and resource management
  - `compatibility`: Review cross-platform and version compatibility
  - `error_handling`: Analyze error handling and fault tolerance
  - `complexity`: Evaluate code complexity and suggest simplifications
  - `architecture`: Review code structure and design patterns
  - `license`: Review third-party library usage and license compliance
- `--lang`: Output language - `en` (English), `ja` (Japanese), or `default` (auto-detect system language)
- `--set-profile PROFILE`: Set or change the AWS profile name
- `--clear-profile`: Remove the stored AWS profile from keyring
- `--output FILE`: Output file path for the review report (JSON format, default: auto-generated timestamped file)

## Interactive Review Workflow

AICodeReviewer now features an interactive review process that requires you to actively confirm each AI-identified issue before generating a final report. For each issue found, you have four options:

1. **RESOLVED** - Mark the issue as resolved (program will verify the fix)
2. **IGNORE** - Ignore the issue (requires providing a reason)
3. **AI FIX** - Let AI automatically fix the code issue (shows before/after diff for review before applying)
4. **VIEW CODE** - Display the full file content for context

The program will not generate a final report until all issues have been addressed through one of these actions. This ensures thorough review and prevents overlooking important issues.

### Report Generation

After completing the interactive review, AICodeReviewer generates two output files:

- **JSON Report** (`review_report_YYYYMMDD_HHMMSS.json`): Complete structured data including all issues, resolutions, and metadata
- **Summary Report** (`review_report_YYYYMMDD_HHMMSS_summary.txt`): Human-readable summary with issue counts and details

You can specify a custom output filename using the `--output` option.

Examples:
```bash
# Review entire project for security issues
python -m aicodereviewer . --type security --lang ja

# Review performance aspects of a specific project
python -m aicodereviewer /path/to/project --type performance

# Review only changes from a diff file (with project context)
python -m aicodereviewer . --scope diff --diff-file changes.patch --type best_practices

# Review only changes from a diff file (without project context)
python -m aicodereviewer --scope diff --diff-file changes.patch --type best_practices

# Review changes between two commits
python -m aicodereviewer . --scope diff --commits HEAD~1..HEAD --type maintainability

# Review recent changes in a pull request style
python -m aicodereviewer . --scope diff --commits main..feature-branch --type testing

# Generate a custom-named report
python -m aicodereviewer . --type best_practices --output my_review_report.json
```

## Building Windows Executable

To create a standalone Windows executable with custom icon:

1. Run the build script:
   ```bash
   build_exe.bat
   ```

2. The build script will:
   - Generate the application icon from `tools/convert_icon.py`
   - Bundle all dependencies into a single executable
   - Create `AICodeReviewer.exe` in the `dist` folder

### Icon Generation

The application icon is converted from the SVG design to ICO format:

```bash
# Convert SVG to ICO
python tools/convert_icon.py
```

This creates `build/icon.ico` with multiple resolutions for optimal display across different Windows contexts. The script tries multiple conversion methods (cairosvg, ImageMagick, Inkscape) and falls back to a programmatic placeholder if needed.

## Performance Optimizations

AICodeReviewer includes several performance optimizations to handle large codebases efficiently:

### Resource Management
- **File Size Limits**: Automatically skips files larger than 10MB to prevent memory issues
- **Content Length Limits**: Restricts API requests to 100KB to stay within model limits
- **File Caching**: Caches up to 100 recently read files to avoid redundant I/O operations
- **Memory Monitoring**: Tracks memory usage during operations (optional)

### API Efficiency
- **Rate Limiting**: Maintains 6-second intervals between API calls (10 requests/minute max)
- **Connection Pooling**: Reuses AWS connections with automatic retry logic
- **Request Batching**: Optimized prompt sizes to maximize API efficiency
- **Error Handling**: Graceful handling of API timeouts and throttling

### Processing Optimizations
- **Efficient File Scanning**: Uses `os.walk()` with filtered directory pruning
- **Optimized Diff Parsing**: Streamlined parsing logic for large diff files
- **Parallel Processing Ready**: Architecture supports future parallel file processing

### Configuration

Performance settings can be customized in `config.ini`:

```ini
[performance]
max_file_size_mb = 10          # Maximum file size to process
max_fix_file_size_mb = 5       # Maximum file size for AI fixes
file_cache_size = 100          # Number of files to cache in memory
min_request_interval_seconds = 6.0  # API rate limiting
max_requests_per_minute = 10   # API request limit per minute
max_content_length = 100000    # Maximum content length for API
max_fix_content_length = 50000 # Maximum content for fix operations

[logging]
enable_performance_logging = true  # Enable performance monitoring
```

### Performance Tips

1. **Large Codebases**: Use `--scope diff` to review only changed files instead of entire projects
2. **File Types**: The scanner automatically excludes common build/dependency directories
3. **Memory Usage**: Monitor memory usage with `enable_performance_logging = true`
4. **API Limits**: The tool automatically handles AWS Bedrock rate limits and retries

## Development

### Running Tests

The project includes a comprehensive test suite for the diff functionality:

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_diff_functionality.py
```

### Profile Management

You can manage your AWS profile settings using these commands:

```bash
# Set or change your AWS profile
python -m aicodereviewer --set-profile myprofile

# Remove stored profile (will prompt for new one on next run)
python -m aicodereviewer --clear-profile
```