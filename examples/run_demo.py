"""
Demo script to run AICodeReviewer with different review types.
Demonstrates the tool's capabilities on intentionally flawed code.

This script runs reviews in a controlled manner and shows the results.
"""
import subprocess
import json
from pathlib import Path


SAMPLE_PROJECT = Path(__file__).parent / "sample_project"
OUTPUT_DIR = Path(__file__).parent / "demo_outputs"


def run_review(review_type, output_suffix=""):
    """Run a code review and capture the output."""
    output_file = OUTPUT_DIR / f"review_{review_type}{output_suffix}.json"
    
    cmd = [
        "python", "-m", "aicodereviewer",
        str(SAMPLE_PROJECT),
        "--type", review_type,
        "--programmers", "Demo User",
        "--reviewers", "AI Reviewer",
        "--output", str(output_file),
        "--lang", "en"
    ]
    
    print(f"\n{'='*80}")
    print(f"Running {review_type.upper()} Review")
    print(f"{'='*80}\n")
    print(f"Command: {' '.join(cmd)}\n")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        print(f"\nReview completed. Results saved to: {output_file}")
        return output_file
    except subprocess.TimeoutExpired:
        print(f"Review timed out after 5 minutes")
        return None
    except Exception as e:
        print(f"Error running review: {e}")
        return None


def main():
    """Run multiple review types on the sample project."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    print("="*80)
    print("AICodeReviewer Demo - Multiple Review Types")
    print("="*80)
    print(f"\nSample Project: {SAMPLE_PROJECT}")
    print(f"Output Directory: {OUTPUT_DIR}\n")
    
    # Note: In a real demo, you would run these sequentially.
    # For this example, we'll show what the command structure looks like.
    
    review_types = [
        "security",
        "performance", 
        "best_practices",
        "error_handling",
        "maintainability"
    ]
    
    print("This demo would run the following reviews:")
    print("-" * 80)
    for review_type in review_types:
        print(f"  • {review_type.replace('_', ' ').title()} Review")
    
    print("\n" + "="*80)
    print("DEMO MODE - Not running actual reviews")
    print("="*80)
    print("\nTo run reviews manually, use:")
    print("\nExample commands:")
    for review_type in review_types:
        output_file = OUTPUT_DIR / f"review_{review_type}.json"
        print(f"\n# {review_type.replace('_', ' ').title()} Review")
        print(f"python -m aicodereviewer {SAMPLE_PROJECT} \\")
        print(f"  --type {review_type} \\")
        print(f"  --programmers \"Demo User\" \\")
        print(f"  --reviewers \"AI Reviewer\" \\")
        print(f"  --output {output_file}")
    
    print("\n" + "="*80)
    print("Note: Each review will require interactive confirmation.")
    print("The tool will present issues and ask you to resolve/ignore/fix each one.")
    print("="*80)


if __name__ == "__main__":
    main()
