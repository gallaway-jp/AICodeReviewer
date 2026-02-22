# src/aicodereviewer/backends/base.py
"""
Abstract base for all AI backends.

Every backend must implement :pymethod:`get_review` and :pymethod:`get_fix`
so the rest of the application can remain backend-agnostic.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List

# ── JSON output schema (injected into system prompt) ───────────────────────

_JSON_SCHEMA_INSTRUCTION = """\

IMPORTANT — OUTPUT FORMAT:
You MUST respond with valid JSON matching this schema.  Do NOT include
markdown code fences, preamble, or any text outside the JSON object.

{
  "review_type": "<type>",
  "language": "<en|ja>",
  "files": [
    {
      "filename": "<path>",
      "findings": [
        {
          "severity": "critical|high|medium|low|info",
          "line": <int or null>,
          "category": "<review category>",
          "title": "<short title>",
          "description": "<detailed description>",
          "code_context": "<relevant code snippet>",
          "suggestion": "<how to fix>"
        }
      ]
    }
  ]
}

Rules:
- Return ONLY the JSON object.  No markdown, no fences, no extra text.
- "severity" MUST be one of: critical, high, medium, low, info.
- "line" is the 1-based line number (null if file-level).
- Include ALL findings you discover — do not merge multiple issues.
"""


# ── Central prompt registry ────────────────────────────────────────────────
REVIEW_PROMPTS = {
    "security": (
        "You are a Senior Security Auditor with deep expertise in OWASP, CWE, and CVE databases. "
        "Focus on critical vulnerabilities: injection attacks (SQL, OS command, LDAP), XSS, CSRF, "
        "authentication/authorization flaws, insecure deserialization, sensitive data exposure, "
        "insecure configurations, and cryptographic weaknesses. "
        "Provide specific remediation steps with severity levels (critical/high/medium/low)."
    ),
    "performance": (
        "You are a Performance Engineer specializing in profiling, algorithmic efficiency, "
        "and resource optimization. Identify: O(n²+) algorithms that can be improved, "
        "unnecessary memory allocations, N+1 query patterns, missing caching opportunities, "
        "blocking I/O in hot paths, and inefficient data structures. "
        "Provide actionable optimizations with estimated impact."
    ),
    "best_practices": (
        "You are a Lead Developer and Clean Code advocate. Review for SOLID principles, "
        "DRY violations, proper encapsulation, appropriate design patterns, consistent "
        "naming conventions, idiomatic language usage, and code organization. "
        "Reference specific principles or patterns when identifying issues."
    ),
    "maintainability": (
        "You are a Code Maintenance Expert. Analyze readability, cognitive complexity, "
        "coupling and cohesion, dead code, duplicated logic, overly long functions, "
        "and technical debt. Suggest refactoring opportunities that improve long-term "
        "maintenance without changing behavior."
    ),
    "documentation": (
        "You are a Technical Writer and Documentation Specialist. Review inline comments, "
        "docstrings/JSDoc/Javadoc, README accuracy, API documentation completeness, "
        "misleading or outdated comments, and missing documentation for public interfaces. "
        "Rate documentation coverage and suggest improvements."
    ),
    "testing": (
        "You are a QA Engineer and Test Architect. Analyze testability, missing test "
        "coverage, inadequate assertions, brittle tests, missing edge cases, untested "
        "error paths, and suggest testing strategies (unit, integration, property-based). "
        "Identify code that is hard to test and suggest refactoring for testability."
    ),
    "accessibility": (
        "You are an Accessibility Specialist certified in WCAG 2.1 AA. Review for "
        "missing ARIA labels, insufficient color contrast, keyboard navigation issues, "
        "screen reader compatibility, focus management, and semantic HTML usage. "
        "Reference specific WCAG success criteria."
    ),
    "scalability": (
        "You are a System Architect specializing in distributed systems. Analyze "
        "scalability bottlenecks, stateful components that hinder horizontal scaling, "
        "missing connection pooling, unbounded queues, lack of circuit breakers, "
        "and missing rate limiting. Suggest architectural improvements."
    ),
    "compatibility": (
        "You are a Platform Engineer. Review cross-platform compatibility, deprecated "
        "API usage, browser compatibility issues, Python 2/3 or Node version concerns, "
        "OS-specific code paths, and dependency version conflicts. "
        "Flag potential breakage across environments."
    ),
    "error_handling": (
        "You are a Reliability Engineer. Analyze error handling completeness, bare "
        "except clauses, swallowed exceptions, missing finally blocks, insufficient "
        "error context, missing input validation at boundaries, and missing retry "
        "logic for transient failures. Suggest resilience improvements."
    ),
    "complexity": (
        "You are a Code Analyst specializing in complexity metrics. Evaluate cyclomatic "
        "complexity, cognitive complexity, nesting depth, method/class size, parameter "
        "counts, and coupling metrics. Suggest concrete simplifications and decompositions."
    ),
    "architecture": (
        "You are a Software Architect. Review code structure, layer separation, "
        "dependency direction, module boundaries, interface design, and adherence to "
        "architectural patterns (MVC, hexagonal, event-driven, etc.). "
        "Identify architectural smells and propose improvements."
    ),
    "license": (
        "You are a License Compliance Specialist. Review third-party library usage, "
        "license compatibility (GPL, MIT, Apache, etc.), attribution requirements, "
        "copyleft obligations, and potential compliance risks. "
        "Flag any license conflicts or missing notices."
    ),
    "localization": (
        "You are an Internationalization Specialist. Review for hardcoded strings, "
        "missing translation keys, date/time/number/currency formatting issues, "
        "RTL layout support, locale-sensitive comparisons, and cultural compliance. "
        "Identify i18n anti-patterns and suggest proper externalization."
    ),
    "specification": (
        "You are a Requirements Analyst. Compare the code against the provided "
        "specification document. Identify deviations, missing implementations, "
        "incorrect interpretations, unhandled edge cases from the spec, and any "
        "functionality that exceeds or contradicts the requirements."
    ),
    # ── New review types ──────────────────────────────────────────────────
    "dependency": (
        "You are a Dependency Management Expert. Analyze imported libraries and "
        "packages for: known vulnerabilities, outdated versions, unnecessary "
        "dependencies, license risks, heavy transitive dependency trees, and "
        "missing lockfile discipline. Recommend safer or lighter alternatives."
    ),
    "concurrency": (
        "You are a Concurrency and Parallelism Expert. Analyze thread safety, "
        "race conditions, deadlock potential, improper synchronization, shared "
        "mutable state, missing locks, async/await anti-patterns, and resource "
        "contention. Suggest correct synchronization strategies."
    ),
    "api_design": (
        "You are an API Design Specialist. Review REST/GraphQL endpoint design, "
        "resource naming, HTTP method usage, status code correctness, pagination, "
        "versioning strategy, request/response schema design, and backward "
        "compatibility. Reference relevant API design guidelines."
    ),
    "data_validation": (
        "You are a Data Validation Expert. Analyze input validation completeness, "
        "missing sanitization, type coercion risks, boundary checks, SQL/NoSQL "
        "injection vectors through unvalidated input, and schema validation gaps. "
        "Suggest validation strategies and libraries."
    ),
    # ── Fix prompt (internal) ─────────────────────────────────────────────
    "fix": (
        "You are an expert code fixer. Fix the code issues identified. "
        "Return ONLY the complete corrected code, no explanations or markdown."
    ),
}

# Human-readable metadata for each review type (used by CLI help and GUI)
REVIEW_TYPE_META = {
    "security":        {"label": "Security Audit",         "group": "Quality"},
    "performance":     {"label": "Performance",            "group": "Quality"},
    "best_practices":  {"label": "Best Practices",         "group": "Quality"},
    "maintainability": {"label": "Maintainability",        "group": "Quality"},
    "documentation":   {"label": "Documentation",          "group": "Quality"},
    "testing":         {"label": "Testing",                "group": "Quality"},
    "error_handling":  {"label": "Error Handling",         "group": "Quality"},
    "complexity":      {"label": "Complexity Analysis",    "group": "Quality"},
    "accessibility":   {"label": "Accessibility",          "group": "Compliance"},
    "scalability":     {"label": "Scalability",            "group": "Architecture"},
    "compatibility":   {"label": "Compatibility",          "group": "Architecture"},
    "architecture":    {"label": "Architecture",           "group": "Architecture"},
    "license":         {"label": "License Compliance",     "group": "Compliance"},
    "localization":    {"label": "Localization / i18n",    "group": "Compliance"},
    "specification":   {"label": "Specification Match",    "group": "Compliance"},
    "dependency":      {"label": "Dependency Analysis",    "group": "Architecture"},
    "concurrency":     {"label": "Concurrency Safety",     "group": "Quality"},
    "api_design":      {"label": "API Design",             "group": "Architecture"},
    "data_validation": {"label": "Data Validation",        "group": "Quality"},
}

# Public list of selectable review type keys (excludes "fix")
REVIEW_TYPE_KEYS: List[str] = sorted(
    k for k in REVIEW_PROMPTS if k != "fix"
)


class AIBackend(ABC):
    """
    Abstract base class for AI code-review backends.

    Subclasses must implement :meth:`get_review` and :meth:`get_fix`.
    """

    # Project-level context string (set once per review session by the
    # orchestrator).  Backends read this when building the system prompt.
    _project_context: Optional[str] = None

    def set_project_context(self, context: Optional[str]) -> None:
        """Store project context for injection into system prompts."""
        self._project_context = context

    # ── public API ─────────────────────────────────────────────────────────

    @abstractmethod
    def get_review(
        self,
        code_content: str,
        review_type: str = "best_practices",
        lang: str = "en",
        spec_content: Optional[str] = None,
    ) -> str:
        """
        Run an AI code review and return the feedback as plain text.

        Args:
            code_content: Source code to review.
            review_type: One of :data:`REVIEW_TYPE_KEYS`.
            lang: ``'en'`` or ``'ja'``.
            spec_content: Specification document (required when
                          *review_type* is ``'specification'``).

        Returns:
            AI feedback text, or a string starting with ``"Error:"`` on failure.
        """
        ...

    @abstractmethod
    def get_fix(
        self,
        code_content: str,
        issue_feedback: str,
        review_type: str = "best_practices",
        lang: str = "en",
    ) -> Optional[str]:
        """
        Generate an AI-powered code fix.

        Args:
            code_content: Original source code.
            issue_feedback: AI feedback describing the issue.
            review_type: The review type that found the issue.
            lang: Response language.

        Returns:
            Fixed code as a string, or *None* on failure.
        """
        ...

    @abstractmethod
    def validate_connection(self) -> bool:
        """
        Test whether the backend is reachable and authenticated.

        Returns:
            True if a trivial request succeeds.
        """
        ...

    # ── helpers available to all subclasses ─────────────────────────────────

    @staticmethod
    def _build_system_prompt(
        review_type: str,
        lang: str,
        project_context: Optional[str] = None,
    ) -> str:
        """Combine the review persona prompt with a language instruction.

        When *review_type* contains ``'+'`` (e.g. ``'security+performance'``),
        the personas for all included types are merged into a single prompt.

        The prompt now also includes a JSON output schema so models return
        structured findings that can be reliably parsed.

        Args:
            review_type:     Review type key(s), ``'+'``-delimited for multi.
            lang:            ``'en'`` or ``'ja'``.
            project_context: Optional compact project summary string
                             produced by :mod:`context_collector`.
        """
        if "+" in review_type:
            parts = review_type.split("+")
            combined_parts: List[str] = []
            for rt in parts:
                prompt = REVIEW_PROMPTS.get(rt)
                if prompt:
                    combined_parts.append(prompt)
            if not combined_parts:
                combined_parts.append(REVIEW_PROMPTS["best_practices"])
            base = (
                "You are a multi-disciplinary code review expert. "
                "Perform a combined review covering ALL of the following areas. "
                "Tag each finding with its category.\n\n"
                + "\n\n".join(
                    f"[{rt.upper()}]: {REVIEW_PROMPTS.get(rt, '')}"
                    for rt in parts if REVIEW_PROMPTS.get(rt)
                )
            )
        else:
            base = REVIEW_PROMPTS.get(review_type, REVIEW_PROMPTS["best_practices"])

        # Prepend project context if available
        if project_context:
            base = f"{project_context}\n\n{base}"

        if lang == "ja":
            lang_inst = "IMPORTANT: Provide your entire response in Japanese (日本語で回答してください)."
        else:
            lang_inst = "IMPORTANT: Provide your entire response in English."
        return f"{base} {lang_inst}{_JSON_SCHEMA_INSTRUCTION}"

    @staticmethod
    def _build_user_message(
        code_content: str,
        review_type: str,
        spec_content: Optional[str] = None,
    ) -> str:
        """Build the user-role message for the AI.

        The message now reminds the model to respond with JSON.
        """
        has_spec = ("specification" in review_type) and spec_content
        if has_spec:
            return (
                f"SPECIFICATION DOCUMENT:\n{spec_content}\n\n---\n\n"
                f"CODE TO REVIEW:\n{code_content}\n\n---\n\n"
                "Compare the code against the specification and identify "
                "deviations, missing implementations, or areas that don't "
                "meet the requirements.\n\n"
                "Respond with the JSON format described in your instructions."
            )
        return (
            f"Review this code:\n\n{code_content}\n\n"
            "Respond with the JSON format described in your instructions."
        )

    @staticmethod
    def _build_multi_file_user_message(
        files: List[Dict[str, Any]],
        review_type: str,
        spec_content: Optional[str] = None,
    ) -> str:
        """Build a user-role message that combines multiple files.

        Each entry in *files* is ``{"name": "...", "content": "..."}``.
        The model is instructed to respond with JSON (schema is in the
        system prompt).  Legacy ``=== FILE:`` delimiters are kept as
        a hint so the fallback parser still works if the model ignores
        the JSON instruction.
        """
        parts: List[str] = []
        if review_type == "specification" and spec_content:
            parts.append(f"SPECIFICATION DOCUMENT:\n{spec_content}\n\n---\n")

        parts.append(
            "Review each of the following files. "
            "Respond with JSON following the schema in your instructions. "
            "Include a separate entry in the \"files\" array for each file, "
            "and a separate object in \"findings\" for each distinct issue.\n"
        )
        for f in files:
            parts.append(f"=== FILE: {f['name']} ===")
            parts.append(f"{f['content']}\n")

        return "\n".join(parts)

    @staticmethod
    def _build_fix_message(code_content: str, issue_feedback: str, review_type: str) -> str:
        """Build the user-role message for a fix request."""
        return (
            f"You are an expert code fixer. Fix this specific issue in the code:\n\n"
            f"ISSUE TYPE: {review_type}\n"
            f"FEEDBACK: {issue_feedback}\n\n"
            f"CODE TO FIX:\n{code_content}\n\n"
            "Return ONLY the complete corrected code, no explanations or markdown."
        )
