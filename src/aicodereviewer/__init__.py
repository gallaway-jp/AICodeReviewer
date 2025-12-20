# src/aicodereviewer/__init__.py
"""
AICodeReviewer - AI-powered code review tool.

This package provides comprehensive code analysis capabilities for multiple programming
languages, focusing on security, performance, maintainability, and best practices.
Supports interactive review workflows and automated AI-powered fixes.

Main Components:
- scanner: File discovery and diff parsing
- reviewer: Issue collection and verification
- fixer: AI-powered code fix generation
- interactive: User interaction workflow
- reporter: Report generation and formatting
- models: Data structures for issues and reports
- bedrock: AWS Bedrock API client with rate limiting
- config: Configuration management
- performance: Performance monitoring utilities
"""

__version__ = "1.0.0"
__author__ = "AICodeReviewer Team"
__description__ = "AI-powered code review tool for multiple programming languages"