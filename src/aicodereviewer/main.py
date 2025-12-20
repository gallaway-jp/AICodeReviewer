# src/aicodereviewer/main.py
import os
import argparse
import locale
from pathlib import Path
from aicodereviewer.auth import get_profile_name, set_profile_name, clear_profile
from aicodereviewer.bedrock import BedrockClient

def get_system_language():
    """Detects if the system language is Japanese, defaults to English."""
    try:
        lang, _ = locale.getdefaultlocale()
        if lang and lang.startswith('ja'):
            return 'ja'
    except:
        pass
    return 'en'

def scan_project(directory):
    """Finds source files for most common programming languages."""
    # Add or remove extensions based on your needs
    # Supports: Python, JavaScript/TypeScript, Java, C/C++, C#, Go, Ruby, PHP, Rust, Swift, Kotlin, Objective-C
    # Frameworks: React (.jsx, .tsx), Laravel (.blade.php)
    # Web: HTML, CSS, Sass, Less, Vue, Svelte, Astro, JSON, XML, YAML
    valid_extensions = {
        '.py', '.js', '.ts', '.java', '.cpp', '.c', '.cs', 
        '.go', '.rb', '.php', '.rs', '.swift', '.kt', '.m', '.h', '.mm',
        '.blade.php', '.jsx', '.tsx', '.html', '.css', '.scss', '.sass', 
        '.less', '.vue', '.svelte', '.astro', '.json', '.xml', '.yaml', '.yml'
    }
    files = []
    ignore_dirs = {'.git', '.venv', '__pycache__', 'node_modules', 'bin', 'obj', 'dist'}
    
    for root, dirs, filenames in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for f in filenames:
            ext = Path(f).suffix.lower()
            if ext in valid_extensions:
                files.append(Path(root) / f)
    return files

def main():
    parser = argparse.ArgumentParser(description="AICodeReviewer - Multi-language AI Review")
    
    # Profile management options
    parser.add_argument("--set-profile", metavar="PROFILE", 
                        help="Set or change AWS profile name")
    parser.add_argument("--clear-profile", action="store_true",
                        help="Remove stored AWS profile from keyring")
    
    # Code review options
    parser.add_argument("path", nargs="?", help="Path to the project folder")
    parser.add_argument("--type", choices=['security', 'performance', 'best_practices', 'maintainability', 'documentation', 'testing', 'accessibility', 'scalability', 'compatibility', 'error_handling', 'complexity', 'architecture', 'license'], 
                        default='best_practices')
    # Manual language override
    parser.add_argument("--lang", choices=['en', 'ja', 'default'], default='default',
                        help="Review language (en: English, ja: Japanese)")
    
    args = parser.parse_args()
    
    # Handle profile management commands
    if args.set_profile:
        set_profile_name(args.set_profile)
        return
    elif args.clear_profile:
        clear_profile()
        return
    
    # Require path for code review
    if not args.path:
        parser.error("path is required for code review (or use --set-profile or --clear-profile)")
    
    # Continue with normal code review...

    # Determine final language
    target_lang = args.lang
    if target_lang == 'default':
        target_lang = get_system_language()

    profile = get_profile_name()
    client = BedrockClient(profile)

    print(f"Scanning {args.path} (Output Language: {target_lang})...")
    target_files = scan_project(args.path)
    
    for file_path in target_files:
        print(f"\n[Reviewing] {file_path}")
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()
            # Pass the target language to the Bedrock client
            feedback = client.get_review(code, review_type=args.type, lang=target_lang)
            print(feedback)

if __name__ == "__main__":
    main()
