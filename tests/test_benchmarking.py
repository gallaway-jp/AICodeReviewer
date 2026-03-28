"""Tests for holistic benchmark fixture discovery and evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from aicodereviewer import benchmarking


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "benchmarks" / "holistic_review" / "fixtures"


def test_discover_fixtures_returns_expected_catalog():
    fixtures = benchmarking.discover_fixtures(FIXTURES_ROOT)

    ids = {fixture.id for fixture in fixtures}

    assert len(fixtures) == 78
    assert ids == {
        "accessibility-dialog-semantic-gap",
        "accessibility-fieldset-without-legend",
        "accessibility-icon-button-label-gap",
        "api-design-create-missing-201-contract",
        "api-design-get-create-endpoint",
        "api-design-patch-without-change-contract",
        "architectural-layer-leak",
        "architectural-service-web-context-leak",
        "auth-guard-regression",
        "cache-invalidation-gap",
        "compatibility-macos-open-command",
        "compatibility-python311-tomllib-runtime-gap",
        "compatibility-windows-path-separator-assumption",
        "concurrency-async-slot-double-booking",
        "concurrency-map-mutation-during-iteration",
        "concurrency-shared-sequence-race",
        "complexity-notification-rule-ladder",
        "complexity-nested-sync-decision-tree",
        "complexity-state-machine-branch-explosion",
        "data-validation-enum-field-not-constrained",
        "data-validation-inverted-time-window",
        "data-validation-rollout-percent-range",
        "dead-code-obsolete-compat-shim",
        "dead-code-stale-feature-flag",
        "dead-code-unreachable-fallback",
        "dependency-missing-pyyaml-declaration",
        "dependency-transitive-api-removal-runtime-gap",
        "dependency-runtime-imports-dev-only-pytest",
        "error-handling-context-manager-exception-not-cleaned",
        "license-apache-notice-omission",
        "license-agpl-notice-conflict",
        "license-embedded-mit-code-without-attribution",
        "desktop-cross-tab-preference-gap",
        "desktop-confirmation-gap",
        "desktop-busy-feedback-gap",
        "desktop-settings-discoverability-gap",
        "desktop-wizard-orientation-gap",
        "diff-signature-break",
        "documentation-deployment-topology-docs-incomplete",
        "documentation-stale-dry-run-flag",
        "documentation-stale-sync-token-doc",
        "error-handling-retryless-sync-timeout",
        "error-handling-swallowed-import-failure",
        "field-rename-contract",
        "localization-hardcoded-settings-labels",
        "localization-concatenated-translation-grammar-break",
        "localization-us-only-receipt-format",
        "maintainability-duplicated-sync-window-rules",
        "maintainability-overloaded-settings-controller",
        "maintainability-parallel-parser-variants-drift",
        "performance-n-plus-one-order-queries",
        "partial-refactor-callers",
        "regression-default-sync-disabled",
        "regression-inverted-sync-start-guard",
        "regression-stale-caller-utility-signature-change",
        "scalability-instance-local-rate-limit-state",
        "scalability-connection-pool-exhaustion-under-burst",
        "scalability-unbounded-pending-events-buffer",
        "security-idor-invoice-download",
        "security-jwt-signature-bypass",
        "security-open-redirect-login",
        "security-path-traversal-download",
        "security-predictable-reset-token",
        "security-shell-command-injection",
        "security-ssrf-avatar-fetch",
        "security-sql-query-interpolation",
        "security-unsafe-yaml-load",
        "security-zip-slip-theme-import",
        "specification-batch-atomicity-contract",
        "specification-profile-display-name-contract",
        "specification-type-mismatch-vs-spec-enum",
        "testing-rollout-percent-range-untested",
        "testing-order-rollback-untested",
        "testing-timeout-retry-untested",
        "transaction-split",
        "ui-form-recovery-gap",
        "ui-loading-feedback-gap",
        "validation-drift",
    }


def test_evaluate_security_fixture_matches_shell_command_injection(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "security-shell-command-injection" / "fixture.json"
    )
    report_path = tmp_path / "security-shell-command-injection.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-sec-0001",
                            "file_path": "src/api.py",
                            "issue_type": "injection_risk",
                            "severity": "high",
                            "description": "User-controlled export arguments are interpolated into a shell command, which creates a command injection risk.",
                            "ai_feedback": "api.py forwards request fields into report_export.py, where subprocess.run executes one formatted command string with shell=True.",
                            "context_scope": "cross_file",
                            "related_files": ["src/report_export.py"],
                            "systemic_impact": "An attacker can inject shell metacharacters and execute arbitrary commands on the host through the export flow.",
                            "evidence_basis": "report_export.py builds one command string from username, output_format, and output_path before calling subprocess.run(..., shell=True).",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_security_fixture_matches_path_traversal_download(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "security-path-traversal-download" / "fixture.json"
    )
    report_path = tmp_path / "security-path-traversal-download.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-sec-0004",
                            "file_path": "src/attachment_store.py",
                            "issue_type": "path_traversal",
                            "severity": "high",
                            "description": "Request-controlled filename values can trigger path traversal because the download helper joins them directly onto the attachment root before opening the file.",
                            "ai_feedback": "api.py forwards filename into attachment_store.py, which opens ATTACHMENTS_ROOT / account_id / filename without constraining traversal segments.",
                            "context_scope": "cross_file",
                            "related_files": ["src/api.py"],
                            "systemic_impact": "An attacker can escape the account attachment directory and read arbitrary files that the process can access.",
                            "evidence_basis": "attachment_store.py opens ATTACHMENTS_ROOT / account_id / filename directly, so traversal sequences in filename can reach unexpected files.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_security_fixture_matches_jwt_signature_bypass(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "security-jwt-signature-bypass" / "fixture.json"
    )
    report_path = tmp_path / "security-jwt-signature-bypass.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-sec-0007",
                            "file_path": "src/token_service.py",
                            "issue_type": "cryptographic-weakness",
                            "severity": "high",
                            "description": "JWT decoding disables signature verification, which lets attackers forge tokens and bypass authentication.",
                            "ai_feedback": "api.py forwards the bearer token into token_service.py, which calls jwt.decode with verify_signature disabled.",
                            "context_scope": "cross_file",
                            "related_files": ["src/api.py"],
                            "systemic_impact": "An attacker can forge session tokens and bypass authentication because the server accepts unsigned or tampered claims.",
                            "evidence_basis": "token_service.py disables signature verification in jwt.decode before api.py trusts the resulting role claim.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_security_fixture_matches_predictable_reset_token(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "security-predictable-reset-token" / "fixture.json"
    )
    report_path = tmp_path / "security-predictable-reset-token.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-sec-0009",
                            "file_path": "src/password_reset.py",
                            "issue_type": "cryptographic-weakness",
                            "severity": "high",
                            "description": "Password reset tokens are deterministic because they are derived directly from the email address, which lets attackers forge valid reset links for known users.",
                            "ai_feedback": "api.py forwards email into password_reset.py, which computes the reset token with hashlib.sha256(email.encode(...)).hexdigest() instead of using an unpredictable secret token.",
                            "context_scope": "cross_file",
                            "related_files": ["src/api.py"],
                            "systemic_impact": "Anyone who can guess or know a victim email address can generate a valid reset link and take over that account.",
                            "evidence_basis": "password_reset.py builds a deterministic token directly from the email address and api.py returns that token in the reset link.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_security_fixture_matches_open_redirect_login(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "security-open-redirect-login" / "fixture.json"
    )
    report_path = tmp_path / "security-open-redirect-login.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-sec-0010",
                            "file_path": "src/api.py",
                            "issue_type": "open_redirect",
                            "severity": "medium",
                            "description": "The login flow has an open redirect because it sends users to an attacker-controlled return_to URL after authentication.",
                            "ai_feedback": "api.py forwards request['return_to'] into redirects.py, which returns that destination unchanged instead of restricting redirects to trusted internal paths.",
                            "context_scope": "cross_file",
                            "related_files": ["src/redirects.py"],
                            "systemic_impact": "Attackers can use trusted login links to bounce users to phishing pages or malicious domains immediately after sign-in.",
                            "evidence_basis": "login() passes the untrusted return_to parameter into build_post_login_redirect(), which returns the external destination without validation.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_documentation_fixture_matches_deployment_topology_gap(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "documentation-deployment-topology-docs-incomplete" / "fixture.json"
    )
    report_path = tmp_path / "documentation-deployment-topology-docs-incomplete.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-doc-0003",
                            "file_path": "docs/deployment.md",
                            "issue_type": "documentation",
                            "severity": "medium",
                            "description": "The deployment guide incorrectly describes the worker as stateless and safe to scale across replicas even though job leases live in process-local memory.",
                            "ai_feedback": "docs/deployment.md tells operators to run multiple worker replicas without shared coordination, but worker.py relies on lease_store.py where lease state is held in a local LEASES dictionary.",
                            "context_scope": "cross_file",
                            "related_files": ["src/lease_store.py", "src/worker.py"],
                            "systemic_impact": "Operators following the deployment guide can roll out multiple workers that each maintain independent lease state, causing duplicate job processing in production.",
                            "evidence_basis": "deployment.md says the worker is stateless and that lease state is not stored locally, while lease_store.py keeps claims in the process-local LEASES dictionary used by worker.py.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_testing_fixture_matches_timeout_retry_gap(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "testing-timeout-retry-untested" / "fixture.json"
    )
    report_path = tmp_path / "testing-timeout-retry-untested.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-test-0003",
                            "file_path": "tests/test_sync.py",
                            "issue_type": "testing",
                            "severity": "medium",
                            "description": "The tests never exercise the TimeoutError retry path even though sync.py already retries the first timeout before surfacing a failure.",
                            "ai_feedback": "test_sync.py only verifies the immediate success case, but fetch_profile_with_retry in sync.py catches TimeoutError and retries once, leaving that regression-prone branch unpinned.",
                            "context_scope": "cross_file",
                            "related_files": ["src/sync.py"],
                            "systemic_impact": "A future refactor can break the timeout retry path without a failing test, letting transient upstream outages regress unnoticed.",
                            "evidence_basis": "test_fetch_profile_returns_profile_on_first_attempt covers only the happy path while fetch_profile_with_retry has a TimeoutError retry branch that no test exercises.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_data_validation_fixture_matches_enum_constraint_gap(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "data-validation-enum-field-not-constrained" / "fixture.json"
    )
    report_path = tmp_path / "data-validation-enum-field-not-constrained.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-val-0003",
                            "file_path": "src/validation.py",
                            "issue_type": "data_validation",
                            "severity": "medium",
                            "description": "The validator accepts any delivery_mode string because it never constrains the field to the supported enum values before api.py persists it.",
                            "ai_feedback": "api.py trusts validate_workflow, but validation.py only coerces delivery_mode to str and never checks that it matches an allowed mode such as email or webhook.",
                            "context_scope": "cross_file",
                            "related_files": ["src/api.py"],
                            "systemic_impact": "Invalid delivery_mode values can reach runtime scheduling logic, leaving impossible workflow states accepted as valid input.",
                            "evidence_basis": "validate_workflow only checks presence and str(payload['delivery_mode']) without any enum membership check before api.py returns that delivery_mode.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_security_fixture_matches_idor_invoice_download(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "security-idor-invoice-download" / "fixture.json"
    )
    report_path = tmp_path / "security-idor-invoice-download.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-sec-0008",
                            "file_path": "src/invoice_service.py",
                            "issue_type": "authorization",
                            "severity": "high",
                            "description": "Invoice download authorizes by identifier alone, which creates an insecure direct object reference because any caller who knows another invoice_id can fetch that invoice.",
                            "ai_feedback": "api.py forwards request invoice_id into invoice_service.py, which loads the invoice record and returns pdf_bytes without checking ownership against current_account.",
                            "context_scope": "cross_file",
                            "related_files": ["src/api.py"],
                            "systemic_impact": "Attackers can enumerate invoice identifiers and download other customers' billing documents.",
                            "evidence_basis": "api.py forwards invoice_id into download_invoice_pdf, and invoice_service.py calls load_invoice_record(invoice_id) without comparing the result account_id to the current account.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_security_fixture_matches_ssrf_avatar_fetch(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "security-ssrf-avatar-fetch" / "fixture.json"
    )
    report_path = tmp_path / "security-ssrf-avatar-fetch.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-sec-0005",
                            "file_path": "src/avatar_fetcher.py",
                            "issue_type": "Server-Side Request Forgery (SSRF)",
                            "severity": "high",
                            "description": "Request-controlled avatar_url is fetched server-side, which creates an SSRF risk because the server will request arbitrary URLs on behalf of the caller.",
                            "ai_feedback": "api.py forwards avatar_url into avatar_fetcher.py, which calls requests.get on that URL without constraining internal destinations.",
                            "context_scope": "cross_file",
                            "related_files": ["src/api.py"],
                            "systemic_impact": "An attacker can use the server to reach internal services or cloud metadata endpoints that should not be exposed externally.",
                            "evidence_basis": "avatar_fetcher.py calls requests.get(avatar_url, timeout=5) on a request-controlled URL.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_security_fixture_matches_zip_slip_theme_import(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "security-zip-slip-theme-import" / "fixture.json"
    )
    report_path = tmp_path / "security-zip-slip-theme-import.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-sec-0006",
                            "file_path": "src/theme_importer.py",
                            "issue_type": "Path traversal (Zip Slip)",
                            "severity": "high",
                            "description": "The theme importer extracts an untrusted archive with extractall, which creates a zip-slip path traversal risk because archive entries can escape the destination directory.",
                            "ai_feedback": "api.py forwards archive_path into theme_importer.py, which calls zipfile.ZipFile(...).extractall(destination) without validating member paths.",
                            "context_scope": "cross_file",
                            "related_files": ["src/api.py"],
                            "systemic_impact": "A malicious theme archive can overwrite arbitrary files writable by the process outside the intended theme directory.",
                            "evidence_basis": "theme_importer.py opens the request-controlled archive path and calls archive.extractall(destination) with no member path validation.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_security_fixture_matches_sql_query_interpolation(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "security-sql-query-interpolation" / "fixture.json"
    )
    report_path = tmp_path / "security-sql-query-interpolation.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-sec-0002",
                            "file_path": "src/api.py",
                            "issue_type": "injection_risk",
                            "severity": "high",
                            "description": "Request-controlled status flows into a raw SQL query, which creates a SQL injection risk.",
                            "ai_feedback": "api.py forwards status into user_repository.py, where an f-string builds the SELECT query directly.",
                            "context_scope": "cross_file",
                            "related_files": ["src/user_repository.py"],
                            "systemic_impact": "An attacker can alter the database query and read or manipulate records beyond the intended filter.",
                            "evidence_basis": "user_repository.py interpolates status into SELECT ... WHERE status = '{status}' before db.execute(query).",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_security_fixture_matches_unsafe_yaml_load(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "security-unsafe-yaml-load" / "fixture.json"
    )
    report_path = tmp_path / "security-unsafe-yaml-load.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-sec-0003",
                            "file_path": "src/api.py",
                            "issue_type": "insecure-deserialization",
                            "severity": "high",
                            "description": "Request-controlled YAML is deserialized through yaml.load, which is an unsafe load path.",
                            "ai_feedback": "api.py forwards config into settings_loader.py, where yaml.load parses the payload with yaml.Loader instead of a safe loader.",
                            "context_scope": "cross_file",
                            "related_files": ["src/settings_loader.py"],
                            "systemic_impact": "Unsafe deserialization can trigger arbitrary object construction or code execution when untrusted YAML reaches the loader.",
                            "evidence_basis": "settings_loader.py calls yaml.load(raw_config, Loader=yaml.Loader).",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_complexity_fixture_matches_nested_sync_decision_tree(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "complexity-nested-sync-decision-tree" / "fixture.json"
    )
    report_path = tmp_path / "complexity-nested-sync-decision-tree.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-cx-0001",
                            "file_path": "src/sync_strategy.py",
                            "issue_type": "complexity",
                            "severity": "medium",
                            "description": "The sync strategy helper is overly complex because the nested decision tree mixes account state, retry mode, network conditions, and feature flags in one function.",
                            "ai_feedback": "choose_sync_strategy contains deeply nested conditionals that combine multiple policy dimensions, which makes the flow difficult to reason about or refactor safely.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "This level of nesting increases maintenance risk because small rule changes can break adjacent branches that are hard to see during review.",
                            "evidence_basis": "sync_strategy.py implements a nested chain of if/else branches inside choose_sync_strategy instead of isolating the decision rules.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_complexity_fixture_matches_notification_rule_ladder(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "complexity-notification-rule-ladder" / "fixture.json"
    )
    report_path = tmp_path / "complexity-notification-rule-ladder.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-cx-0003",
                            "file_path": "src/notification_policy.py",
                            "issue_type": "complexity",
                            "severity": "medium",
                            "description": "The notification planner has too many branches because one function mixes event type, quiet hours, compliance mode, and account-tier rules in a long conditional ladder.",
                            "ai_feedback": "plan_notification_delivery combines several policy dimensions in one long branch-heavy function, which makes the delivery rules difficult to reason about or change safely.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "This concentrated decision logic is brittle during changes because policy updates can break neighboring branches.",
                            "evidence_basis": "plan_notification_delivery contains a long branch ladder across several policy dimensions including event kind, quiet hours, compliance mode, and account tier.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_complexity_fixture_matches_state_machine_branch_explosion(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "complexity-state-machine-branch-explosion" / "fixture.json"
    )
    report_path = tmp_path / "complexity-state-machine-branch-explosion.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-cx-0005",
                            "file_path": "src/workflow_state_machine.py",
                            "issue_type": "complexity",
                            "severity": "medium",
                            "description": "The workflow state handler is overly complex because one function packs too many state and event branches into the same transition path.",
                            "ai_feedback": "advance_workflow_state mixes draft, queued, running, paused, and failed state transitions with retry and feature-flag rules, which makes the state machine difficult to reason about or modify safely.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "This branch-heavy state machine is brittle to change because edits to one transition can easily break adjacent state paths without obvious coverage.",
                            "evidence_basis": "workflow_state_machine.py implements advance_workflow_state as one large state-branch structure with nested event, retry_mode, and feature-flag checks instead of isolating transition rules.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_scalability_fixture_matches_instance_local_rate_limit_state(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "scalability-instance-local-rate-limit-state" / "fixture.json"
    )
    report_path = tmp_path / "scalability-instance-local-rate-limit-state.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-scale-0001",
                            "file_path": "src/app.py",
                            "issue_type": "scalability",
                            "severity": "high",
                            "description": "The rate limiter keeps request counts in per-process memory, so the limit stops being consistent once the service scales out to multiple workers.",
                            "ai_feedback": "RATE_LIMIT_STATE lives inside each worker process, but gunicorn.conf.py starts four workers, so requests can bypass the intended quota by landing on different processes.",
                            "context_scope": "cross_file",
                            "related_files": ["gunicorn.conf.py"],
                            "systemic_impact": "Horizontal scaling weakens the quota because each worker tracks its own rate-limit window instead of sharing state.",
                            "evidence_basis": "app.py stores counters in RATE_LIMIT_STATE while gunicorn.conf.py configures workers = 4.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_scalability_alias_for_instance_local_rate_limit_state(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "scalability-instance-local-rate-limit-state" / "fixture.json"
    )
    report_path = tmp_path / "scalability-instance-local-rate-limit-state-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-scale-0002",
                            "file_path": "src/app.py",
                            "issue_type": "stateful-component",
                            "severity": "medium",
                            "description": "Per-process rate limiting breaks once the service runs behind multiple workers.",
                            "ai_feedback": "RATE_LIMIT_STATE stays local to each process, so scaling out weakens the intended quota.",
                            "context_scope": "cross_file",
                            "related_files": ["gunicorn.conf.py"],
                            "systemic_impact": "Distributed workers no longer share one global rate-limit view.",
                            "evidence_basis": "RATE_LIMIT_STATE in app.py is combined with workers = 4 in gunicorn.conf.py.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_infers_cross_file_scalability_links_from_related_issues(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "scalability-instance-local-rate-limit-state" / "fixture.json"
    )
    report_path = tmp_path / "scalability-instance-local-rate-limit-state-related-issues.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-scale-0003",
                            "file_path": "src/app.py",
                            "issue_type": "scalability",
                            "severity": "high",
                            "description": "Process-local rate limiting breaks once requests can land on different workers.",
                            "ai_feedback": "RATE_LIMIT_STATE stays in each process, so global quotas drift once the deployment fans out.",
                            "context_scope": "local",
                            "related_files": [],
                            "related_issues": [1],
                            "systemic_impact": "Horizontal scaling weakens one global quota because each worker tracks its own state.",
                            "evidence_basis": "app.py stores counters in RATE_LIMIT_STATE without shared coordination.",
                        },
                        {
                            "issue_id": "issue-scale-0004",
                            "file_path": "gunicorn.conf.py",
                            "issue_type": "scalability",
                            "severity": "medium",
                            "description": "The deployment starts four workers.",
                            "context_scope": "local",
                            "related_files": [],
                            "related_issues": [0],
                            "systemic_impact": "More workers increase the chance that process-local state diverges.",
                            "evidence_basis": "gunicorn.conf.py sets workers = 4.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_scalability_fixture_matches_unbounded_pending_events_buffer(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "scalability-unbounded-pending-events-buffer" / "fixture.json"
    )
    report_path = tmp_path / "scalability-unbounded-pending-events-buffer.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-scale-0005",
                            "file_path": "src/event_buffer.py",
                            "issue_type": "scalability",
                            "severity": "high",
                            "description": "The event buffer grows without any capacity limit or backpressure when the downstream sender falls behind.",
                            "ai_feedback": "pending_events stores every incoming event in memory and queue_event keeps appending to it, so a slow sink turns higher traffic into an unbounded backlog.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Memory usage rises with traffic because the process has no bounded queue or backpressure when send_batch stalls.",
                            "evidence_basis": "event_buffer.py appends every payload into pending_events and only drains up to 100 entries per flush.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_scalability_fixture_matches_connection_pool_exhaustion_under_burst(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "scalability-connection-pool-exhaustion-under-burst" / "fixture.json"
    )
    report_path = tmp_path / "scalability-connection-pool-exhaustion-under-burst.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-scale-0006",
                            "file_path": "src/api.py",
                            "issue_type": "scalability",
                            "severity": "high",
                            "description": "Burst export processing can exhaust the shared connection pool because the executor fans out 64 workers while each job holds one of only 8 database connections across a slow remote fetch.",
                            "ai_feedback": "EXPORT_EXECUTOR submits up to 64 concurrent jobs, but db_pool.py exposes only 8 connections and borrow_connection blocks indefinitely. Because process_export_job acquires a connection before fetch_remote_snapshot, burst traffic can starve the pool and stall throughput.",
                            "context_scope": "cross_file",
                            "related_files": ["src/db_pool.py"],
                            "systemic_impact": "Throughput can collapse under burst load because workers pile up waiting for connections while the limited pool is held across slow remote work.",
                            "evidence_basis": "api.py configures ThreadPoolExecutor(max_workers=64) and acquires a connection before fetch_remote_snapshot(...), while db_pool.py limits the pool with DB_POOL_SIZE = 8 and BoundedSemaphore(DB_POOL_SIZE).",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_specification_fixture_matches_batch_atomicity_contract(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "specification-batch-atomicity-contract" / "fixture.json"
    )
    report_path = tmp_path / "specification-batch-atomicity-contract.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-spec-0001",
                            "file_path": "src/service.py",
                            "issue_type": "specification",
                            "severity": "high",
                            "description": "The batch handler violates the atomic contract because it persists valid orders and still reports partial success when one item fails.",
                            "ai_feedback": "The requirements say submit_batch must be atomic and must not allow partial success, but service.py returns partial_success after already persisting accepted orders.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Callers receive behavior that diverges from the documented contract, which makes integrations rely on semantics the specification explicitly forbids.",
                            "evidence_basis": "submit_batch returns status='partial_success' after persist_order has already written accepted orders from the same batch.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_specification_issue_type_aliases(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "specification-batch-atomicity-contract" / "fixture.json"
    )
    report_path = tmp_path / "specification-batch-atomicity-contract-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-spec-0002",
                            "file_path": "src/service.py",
                            "issue_type": "atomicity_violation",
                            "severity": "critical",
                            "description": "The batch handler is not atomic because it returns partial success after persisting accepted orders.",
                            "ai_feedback": "The requirements say the batch must be atomic, but service.py still returns partial_success after persisting accepted orders.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Callers observe behavior the specification forbids.",
                            "evidence_basis": "submit_batch returns status='partial_success' after persist_order has already written accepted orders.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_specification_fixture_matches_profile_display_name_contract(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "specification-profile-display-name-contract" / "fixture.json"
    )
    report_path = tmp_path / "specification-profile-display-name-contract.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-spec-0003",
                            "file_path": "src/profile_api.py",
                            "issue_type": "specification",
                            "severity": "high",
                            "description": "The profile response violates the spec because it returns name instead of display_name and omits the required email_verified field.",
                            "ai_feedback": "The requirements document says build_profile_response must return display_name and email_verified, but profile_api.py returns only user_id and name.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Clients receive a response shape that diverges from the documented contract, so integrations can break when they expect display_name and email_verified.",
                            "evidence_basis": "build_profile_response returns name instead of display_name and never includes email_verified in the response object.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_specification_fixture_matches_type_mismatch_vs_spec_enum(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "specification-type-mismatch-vs-spec-enum" / "fixture.json"
    )
    report_path = tmp_path / "specification-type-mismatch-vs-spec-enum.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-spec-0004",
                            "file_path": "src/sync_api.py",
                            "issue_type": "specification",
                            "severity": "high",
                            "description": "The response contract violates the spec because sync_mode is returned as a boolean instead of the required string enum values manual, scheduled, or disabled.",
                            "ai_feedback": "The specification says build_sync_job_response must return sync_mode as a string enum, but sync_api.py serializes sync_mode with bool(job.schedule_enabled).",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Clients can break when they branch on the documented sync_mode enum values but receive booleans instead of the specified contract.",
                            "evidence_basis": "build_sync_job_response returns sync_mode as bool(job.schedule_enabled) even though the specification requires sync_mode to be one of manual, scheduled, or disabled.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_specification_alias_for_type_mismatch_vs_spec_enum(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "specification-type-mismatch-vs-spec-enum" / "fixture.json"
    )
    report_path = tmp_path / "specification-type-mismatch-vs-spec-enum-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-spec-0005",
                            "file_path": "src/sync_api.py",
                            "issue_type": "spec_mismatch_return_value",
                            "severity": "medium",
                            "description": "The function returns the wrong response type for sync_mode because callers get a boolean where the spec documents a string enum.",
                            "ai_feedback": "The implementation should map schedule state to one of the documented sync_mode strings instead of returning a bool.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Integrations relying on the documented sync_mode values can mis-handle the response because the return type does not match the specification.",
                            "evidence_basis": "sync_api.py returns sync_mode with bool(job.schedule_enabled) instead of one of the enum values listed in the specification.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_complexity_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "complexity-nested-sync-decision-tree" / "fixture.json"
    )
    report_path = tmp_path / "complexity-nested-sync-decision-tree-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-cx-0002",
                            "file_path": "src/sync_strategy.py",
                            "issue_type": "cyclomatic_complexity",
                            "severity": "medium",
                            "description": "The nested decision tree makes choose_sync_strategy overly complex and difficult to reason about.",
                            "ai_feedback": "choose_sync_strategy has deeply nested conditionals across multiple policy dimensions.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "This concentration of branching raises maintenance risk because changes can break neighboring branches.",
                            "evidence_basis": "choose_sync_strategy contains nested if/else branches across account state, retry mode, network conditions, and feature flags.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_complexity_alias_for_notification_rule_ladder(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "complexity-notification-rule-ladder" / "fixture.json"
    )
    report_path = tmp_path / "complexity-notification-rule-ladder-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-cx-0004",
                            "file_path": "src/notification_policy.py",
                            "issue_type": "cognitive_complexity",
                            "severity": "medium",
                            "description": "plan_notification_delivery is a branch-heavy rule ladder that is difficult to follow.",
                            "ai_feedback": "The function packs too many policy rules into one place.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Policy edits are easy to break because the rule branches are concentrated in one function.",
                            "evidence_basis": "plan_notification_delivery contains several conditional branches across policy dimensions such as quiet hours, compliance mode, event kind, and account tier.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_maintainability_fixture_matches_duplicated_sync_window_rules(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "maintainability-duplicated-sync-window-rules" / "fixture.json"
    )
    report_path = tmp_path / "maintainability-duplicated-sync-window-rules.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-main-0001",
                            "file_path": "src/cli_sync_settings.py",
                            "issue_type": "maintainability",
                            "severity": "medium",
                            "description": "The sync window normalization logic is duplicated between the CLI and GUI settings modules, which increases maintenance cost.",
                            "ai_feedback": "normalize_sync_window appears in both settings entry points with nearly identical behavior, so future policy updates can drift if one copy changes without the other.",
                            "context_scope": "cross_file",
                            "related_files": ["src/gui_sync_settings.py"],
                            "systemic_impact": "Policy changes can drift across the two settings flows because the same normalization rules have to be updated in multiple places.",
                            "evidence_basis": "cli_sync_settings.py and gui_sync_settings.py both define normalize_sync_window with the same hour and timezone normalization rules.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_maintainability_alias_for_duplicated_sync_window_rules(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "maintainability-duplicated-sync-window-rules" / "fixture.json"
    )
    report_path = tmp_path / "maintainability-duplicated-sync-window-rules-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-main-0002",
                            "file_path": "src/cli_sync_settings.py",
                            "issue_type": "code_reuse",
                            "severity": "medium",
                            "description": "normalize_sync_window is duplicated across the CLI and GUI settings modules, which creates duplicated maintenance work.",
                            "ai_feedback": "The duplicated normalization logic means future fixes can drift across entry points.",
                            "context_scope": "cross_file",
                            "related_files": ["src/gui_sync_settings.py"],
                            "systemic_impact": "Future updates can drift because the same sync-window rules must stay synchronized across both entry points.",
                            "evidence_basis": "normalize_sync_window is implemented in both cli_sync_settings.py and gui_sync_settings.py.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_maintainability_fixture_matches_overloaded_settings_controller(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "maintainability-overloaded-settings-controller" / "fixture.json"
    )
    report_path = tmp_path / "maintainability-overloaded-settings-controller.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-main-0003",
                            "file_path": "src/settings_controller.py",
                            "issue_type": "maintainability",
                            "severity": "medium",
                            "description": "SettingsController carries too many responsibilities because it loads configuration, validates form input, writes settings, coordinates sync side effects, and formats UI output in one class.",
                            "ai_feedback": "This controller has low cohesion and will be difficult to change safely because unrelated settings, audit, sync, and presentation concerns are coupled together.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Future refactors are risky because changes to one settings concern can affect persistence, sync orchestration, audit logging, and display formatting in the same class.",
                            "evidence_basis": "SettingsController.load_settings, save_settings, export_debug_snapshot, and build_summary mix configuration, validation, persistence, sync orchestration, telemetry, and UI summary formatting.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_maintainability_alias_for_overloaded_settings_controller(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "maintainability-overloaded-settings-controller" / "fixture.json"
    )
    report_path = tmp_path / "maintainability-overloaded-settings-controller-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-main-0004",
                            "file_path": "src/settings_controller.py",
                            "issue_type": "god_class",
                            "severity": "medium",
                            "description": "SettingsController behaves like a god class because it owns configuration loading, validation, persistence, sync orchestration, and UI summary generation.",
                            "ai_feedback": "The mixed responsibilities make the class hard to understand and refactor.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Changes to one responsibility can destabilize unrelated settings behavior because multiple concerns are coupled in the same class.",
                            "evidence_basis": "SettingsController includes load_settings, save_settings, export_debug_snapshot, and build_summary for separate concerns.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_maintainability_fixture_matches_parallel_parser_variants_drift(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "maintainability-parallel-parser-variants-drift" / "fixture.json"
    )
    report_path = tmp_path / "maintainability-parallel-parser-variants-drift.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-main-0005",
                            "file_path": "src/cli_selector_parser.py",
                            "issue_type": "maintainability",
                            "severity": "medium",
                            "description": "parse_sync_selector is implemented in parallel parser modules that have already diverged, which leaves manual and scheduled sync entry points with different selector rules to maintain.",
                            "ai_feedback": "The manual and scheduled sync flows each maintain their own parse_sync_selector logic, but only the CLI variant supports the wildcard selector, the tag alias, lowercasing values, and broader truthy handling. Future selector fixes now have to be applied in both places.",
                            "context_scope": "cross_file",
                            "related_files": ["src/job_selector_parser.py"],
                            "systemic_impact": "Selector behavior can keep drifting between entry points because maintenance work has to be duplicated across the two parser variants.",
                            "evidence_basis": "cli_selector_parser.py and job_selector_parser.py both define parse_sync_selector, but the CLI version treats * as all-projects, accepts tag as an alias for label, lowercases values, and accepts 1 or yes for all=true while the job parser does not.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_maintainability_alias_for_parallel_parser_variants_drift(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "maintainability-parallel-parser-variants-drift" / "fixture.json"
    )
    report_path = tmp_path / "maintainability-parallel-parser-variants-drift-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-main-0006",
                            "file_path": "src/cli_selector_parser.py",
                            "issue_type": "duplicate_logic",
                            "severity": "medium",
                            "description": "The selector parser logic is duplicated across manual and scheduled sync modules and the copies have drifted into different behavior.",
                            "ai_feedback": "Both modules define parse_sync_selector, but one copy now supports wildcard and alias handling that the other copy lacks.",
                            "context_scope": "cross_file",
                            "related_files": ["src/job_selector_parser.py"],
                            "systemic_impact": "Parser changes can drift across entry points because the same selector rules have to be maintained in multiple copies.",
                            "evidence_basis": "parse_sync_selector exists in both cli_selector_parser.py and job_selector_parser.py with different wildcard, alias, and normalization rules.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_concurrency_fixture_matches_shared_sequence_race(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "concurrency-shared-sequence-race" / "fixture.json"
    )
    report_path = tmp_path / "concurrency-shared-sequence-race.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-con-0001",
                            "file_path": "src/dispatch.py",
                            "issue_type": "concurrency",
                            "severity": "high",
                            "description": "The dispatcher mutates shared state from multiple threads without synchronization, so sequence assignment and per-recipient queues can race.",
                            "ai_feedback": "NotificationDispatcher starts one thread per job, but _queue_delivery reads and writes shared state without a lock, which makes duplicate sequence values and lost updates possible.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Concurrent sends can produce duplicate sequence numbers or overwrite queue state under load.",
                            "evidence_basis": "_queue_delivery reads self.next_sequence, sleeps, and writes the incremented value back without a lock while also appending to shared recipient queues.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_concurrency_alias_for_shared_sequence_race(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "concurrency-shared-sequence-race" / "fixture.json"
    )
    report_path = tmp_path / "concurrency-shared-sequence-race-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-con-0002",
                            "file_path": "src/dispatch.py",
                            "issue_type": "race_condition",
                            "severity": "medium",
                            "description": "The worker threads race on shared mutable state in NotificationDispatcher.",
                            "ai_feedback": "Sequence generation is not thread-safe because multiple workers can observe the same counter before it is incremented.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Concurrent delivery batches can assign duplicate sequence values.",
                            "evidence_basis": "self.next_sequence is read and written in _queue_delivery without any lock or synchronization primitive.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_concurrency_fixture_matches_async_slot_double_booking(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "concurrency-async-slot-double-booking" / "fixture.json"
    )
    report_path = tmp_path / "concurrency-async-slot-double-booking.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-con-0003",
                            "file_path": "src/reservations.py",
                            "issue_type": "concurrency",
                            "severity": "high",
                            "description": "The async reservation flow has a check-then-await race on shared slot capacity, so overlapping requests can reserve the same slot twice.",
                            "ai_feedback": "reserve_slot reads shared availability, awaits policy loading, and then writes the decremented count back, which makes double booking possible when two coroutines overlap.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Concurrent reservation requests can oversubscribe the same slot and leave the allocator in an inconsistent state.",
                            "evidence_basis": "reserve_slot reads self.available_slots before await _load_policy and then writes the decremented value back after the await without any synchronization.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_concurrency_alias_for_async_slot_double_booking(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "concurrency-async-slot-double-booking" / "fixture.json"
    )
    report_path = tmp_path / "concurrency-async-slot-double-booking-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-con-0004",
                            "file_path": "src/reservations.py",
                            "issue_type": "race_condition",
                            "severity": "medium",
                            "description": "reserve_slot can double-book a slot when coroutines overlap around the await.",
                            "ai_feedback": "This is an async race on shared capacity rather than a purely local logic bug.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "The same capacity can be promised to multiple users under load.",
                            "evidence_basis": "available_slots is checked before awaiting _load_policy and updated afterward, so two coroutines can observe the same remaining count.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_concurrency_fixture_matches_map_muation_during_iteration(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "concurrency-map-mutation-during-iteration" / "fixture.json"
    )
    report_path = tmp_path / "concurrency-map-mutation-during-iteration.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-con-0005",
                            "file_path": "src/subscription_index.py",
                            "issue_type": "concurrency",
                            "severity": "high",
                            "description": "The subscription index iterates a shared topic dictionary while worker threads mutate that same map, so snapshots can race with topic additions and removals.",
                            "ai_feedback": "refresh_and_snapshot launches worker threads and immediately iterates listeners_by_topic in _snapshot_topics without synchronization, which makes dictionary-size changes during iteration possible.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Concurrent refreshes can fail during iteration or return inconsistent topic snapshots under load.",
                            "evidence_basis": "_apply_event uses setdefault on listeners_by_topic while _snapshot_topics iterates self.listeners_by_topic.items() without a lock.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_concurrency_alias_for_map_mutation_during_iteration(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "concurrency-map-mutation-during-iteration" / "fixture.json"
    )
    report_path = tmp_path / "concurrency-map-mutation-during-iteration-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-con-0006",
                            "file_path": "src/subscription_index.py",
                            "issue_type": "race_condition",
                            "severity": "medium",
                            "description": "The subscription snapshot can race with concurrent topic-map mutations.",
                            "ai_feedback": "The code iterates shared listeners_by_topic while other threads mutate it.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Concurrent snapshots can observe inconsistent topic state or crash during iteration.",
                            "evidence_basis": "listeners_by_topic is iterated in _snapshot_topics while _apply_event uses setdefault and mutates the same dictionary from worker threads.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_api_design_fixture_matches_get_create_endpoint(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "api-design-get-create-endpoint" / "fixture.json"
    )
    report_path = tmp_path / "api-design-get-create-endpoint.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-api-0001",
                            "file_path": "src/api.py",
                            "issue_type": "api_design",
                            "severity": "high",
                            "description": "The API uses GET for a resource-creation endpoint, which violates HTTP semantics and makes clients or intermediaries treat a mutating call like a safe read.",
                            "ai_feedback": "create_invitation is registered with @app.get even though it appends a new invitation, so the endpoint should be POST instead of GET.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Caches, retries, and client assumptions can trigger duplicate invitation creation or unsafe side effects.",
                            "evidence_basis": "api.py declares @app.get('/api/invitations/create') for create_invitation and appends to INVITATIONS inside that handler.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_api_design_alias_for_get_create_endpoint(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "api-design-get-create-endpoint" / "fixture.json"
    )
    report_path = tmp_path / "api-design-get-create-endpoint-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-api-0002",
                            "file_path": "src/api.py",
                            "issue_type": "rest_api",
                            "severity": "medium",
                            "description": "This endpoint design misuses GET for a state-changing create operation.",
                            "ai_feedback": "A safe, cacheable GET route should not create invitations.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Clients may repeat or prefetch the request and create duplicate server-side state.",
                            "evidence_basis": "The create_invitation handler is wired to a GET route and mutates the invitations list.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_api_design_fixture_matches_create_missing_201_contract(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "api-design-create-missing-201-contract" / "fixture.json"
    )
    report_path = tmp_path / "api-design-create-missing-201-contract.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-api-0003",
                            "file_path": "src/api.py",
                            "issue_type": "api_design",
                            "severity": "medium",
                            "description": "The create endpoint uses POST but still returns the default 200 response and a raw dict instead of an explicit creation contract, which weakens client expectations for resource creation semantics.",
                            "ai_feedback": "create_invitation is a creation route, so it should communicate 201 Created semantics and a clearer response contract rather than defaulting to a plain 200 response.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Generated clients and API consumers can miss that this route creates a new resource because the response contract looks like a generic read handler.",
                            "evidence_basis": "api.py registers create_invitation with @app.post('/api/invitations') but does not set status_code=201 or an explicit response model on the creation route.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_api_design_alias_for_create_missing_201_contract(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "api-design-create-missing-201-contract" / "fixture.json"
    )
    report_path = tmp_path / "api-design-create-missing-201-contract-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-api-0004",
                            "file_path": "src/api.py",
                            "issue_type": "response modeling",
                            "severity": "medium",
                            "description": "The creation endpoint has weak create-response semantics because it returns a plain 200 contract without an explicit created response shape.",
                            "ai_feedback": "This should behave like a resource creation endpoint rather than a generic POST that returns an untyped dict.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "API consumers can generate weaker client assumptions around creation responses and resource discovery.",
                            "evidence_basis": "The POST route lacks explicit 201 or response-model metadata and returns a raw dict from create_invitation.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_api_design_fixture_matches_patch_without_change_contract(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "api-design-patch-without-change-contract" / "fixture.json"
    )
    report_path = tmp_path / "api-design-patch-without-change-contract.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-api-0005",
                            "file_path": "src/api.py",
                            "issue_type": "api_design",
                            "severity": "medium",
                            "description": "The PATCH settings route advertises partial-update semantics but replaces the entire stored object with the sparse request payload, so omitted fields are silently cleared.",
                            "ai_feedback": "Clients generally expect PATCH to preserve unspecified fields, but patch_user_settings writes payload.model_dump() directly into USER_SETTINGS and turns missing values into nulls instead of merging changes.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "API consumers can lose existing settings when they send a partial PATCH request because omitted properties are overwritten rather than preserved.",
                            "evidence_basis": "api.py registers patch_user_settings with @app.patch('/api/users/{user_id}/settings') but replaces USER_SETTINGS[user_id] with payload.model_dump() instead of merging only changed fields.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_api_design_alias_for_patch_without_change_contract(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "api-design-patch-without-change-contract" / "fixture.json"
    )
    report_path = tmp_path / "api-design-patch-without-change-contract-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-api-0006",
                            "file_path": "src/api.py",
                            "issue_type": "request_contract",
                            "severity": "medium",
                            "description": "This PATCH endpoint has a weak partial-update contract because omitted fields are not preserved and the handler behaves like full replacement.",
                            "ai_feedback": "The route should define merge semantics or use PUT if the payload replaces the full resource.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Clients can unintentionally erase existing settings when they send only the fields they mean to change.",
                            "evidence_basis": "The @app.patch handler stores payload.model_dump() directly instead of merging changed attributes into the existing settings document.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_compatibility_fixture_matches_macos_open_command(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "compatibility-macos-open-command" / "fixture.json"
    )
    report_path = tmp_path / "compatibility-macos-open-command.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-comp-0001",
                            "file_path": "src/report_viewer.py",
                            "issue_type": "compatibility",
                            "severity": "high",
                            "description": "The report opener hardcodes the macOS `open` command, so the feature will break on Windows and Linux.",
                            "ai_feedback": "open_exported_report shells out to `open` without any platform check or alternative launcher, which makes the implementation macOS-specific.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Users on non-macOS environments will be unable to open exported reports through the desktop flow.",
                            "evidence_basis": "report_viewer.py calls subprocess.run(['open', report_path]) directly and does not branch on the operating system.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_compatibility_alias_for_macos_open_command(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "compatibility-macos-open-command" / "fixture.json"
    )
    report_path = tmp_path / "compatibility-macos-open-command-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-comp-0002",
                            "file_path": "src/report_viewer.py",
                            "issue_type": "cross_platform",
                            "severity": "medium",
                            "description": "This helper is not cross-platform because it assumes the macOS shell command for opening files.",
                            "ai_feedback": "The implementation needs platform-specific handling instead of always using `open`.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Desktop users on unsupported operating systems will hit a broken report-opening action.",
                            "evidence_basis": "The function invokes the `open` executable directly rather than using an OS-aware launcher.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_compatibility_fixture_matches_python311_tomllib_runtime_gap(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "compatibility-python311-tomllib-runtime-gap" / "fixture.json"
    )
    report_path = tmp_path / "compatibility-python311-tomllib-runtime-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-comp-0003",
                            "file_path": "src/config_loader.py",
                            "issue_type": "compatibility",
                            "severity": "high",
                            "description": "The loader imports tomllib directly even though the project still claims Python 3.9 support, so supported runtimes before 3.11 will fail to import this module.",
                            "ai_feedback": "tomllib is only available in Python 3.11+, but pyproject.toml still declares >=3.9, so the implementation breaks the advertised runtime contract.",
                            "context_scope": "cross_file",
                            "related_files": ["pyproject.toml"],
                            "systemic_impact": "Users on supported Python 3.9 or 3.10 environments will hit import-time failures before configuration loading can start.",
                            "evidence_basis": "config_loader.py imports tomllib directly while pyproject.toml still sets requires-python = '>=3.9'.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_compatibility_alias_for_python311_tomllib_runtime_gap(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "compatibility-python311-tomllib-runtime-gap" / "fixture.json"
    )
    report_path = tmp_path / "compatibility-python311-tomllib-runtime-gap-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-comp-0004",
                            "file_path": "src/config_loader.py",
                            "issue_type": "runtime_compatibility",
                            "severity": "medium",
                            "description": "This module assumes a Python 3.11 stdlib feature even though the package metadata still advertises older runtimes.",
                            "ai_feedback": "The code and declared runtime support are out of sync.",
                            "context_scope": "cross_file",
                            "related_files": ["pyproject.toml"],
                            "systemic_impact": "Supported environments below Python 3.11 will fail before the application can parse configuration.",
                            "evidence_basis": "tomllib is imported directly while the project metadata still allows Python 3.9 and 3.10.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_compatibility_fixture_matches_windows_path_separator_assumption(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "compatibility-windows-path-separator-assumption" / "fixture.json"
    )
    report_path = tmp_path / "compatibility-windows-path-separator-assumption.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-comp-0005",
                            "file_path": "src/export_history.py",
                            "issue_type": "compatibility",
                            "severity": "high",
                            "description": "The export parser assumes forward-slash path separators, so native Windows paths will be parsed incorrectly or crash when this helper indexes the expected segments.",
                            "ai_feedback": "describe_export splits the incoming path with '/' and then indexes fixed positions, which only works when paths already use POSIX separators instead of Windows backslashes.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Windows users can hit broken export history labels or runtime index errors when the desktop flow passes native paths into this helper.",
                            "evidence_basis": "export_history.py calls export_path.split('/') and then reads path_parts[-3], which assumes slash-delimited paths rather than OS-aware path handling.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_compatibility_alias_for_windows_path_separator_assumption(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "compatibility-windows-path-separator-assumption" / "fixture.json"
    )
    report_path = tmp_path / "compatibility-windows-path-separator-assumption-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-comp-0006",
                            "file_path": "src/export_history.py",
                            "issue_type": "cross_platform",
                            "severity": "medium",
                            "description": "This helper is not cross-platform because it parses file paths as if every environment used forward slashes.",
                            "ai_feedback": "The implementation should use pathlib or os.path semantics instead of manual slash splitting.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Desktop exports can break on Windows when native backslash-separated paths reach the history formatter.",
                            "evidence_basis": "The function invokes split('/') on the input path and indexes the resulting segments directly.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_dependency_fixture_matches_missing_pyyaml_declaration(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "dependency-missing-pyyaml-declaration" / "fixture.json"
    )
    report_path = tmp_path / "dependency-missing-pyyaml-declaration.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-dep-0001",
                            "file_path": "src/config_writer.py",
                            "issue_type": "dependency",
                            "severity": "high",
                            "description": "config_writer imports yaml and uses yaml.safe_dump, but the project metadata never declares PyYAML as an install dependency.",
                            "ai_feedback": "Installing this package from pyproject.toml will not pull in PyYAML, so environments without a manually preinstalled yaml package can fail at runtime.",
                            "context_scope": "cross_file",
                            "related_files": ["pyproject.toml"],
                            "systemic_impact": "Fresh installs can hit ModuleNotFoundError when config writing runs because the required third-party package is missing from the dependency contract.",
                            "evidence_basis": "config_writer.py imports yaml, but pyproject.toml only declares requests and never lists PyYAML.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_dependency_alias_for_missing_pyyaml_declaration(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "dependency-missing-pyyaml-declaration" / "fixture.json"
    )
    report_path = tmp_path / "dependency-missing-pyyaml-declaration-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-dep-0002",
                            "file_path": "src/config_writer.py",
                            "issue_type": "missing_dependency",
                            "severity": "medium",
                            "description": "The code depends on yaml but the package declaration does not include the dependency needed to provide it.",
                            "ai_feedback": "The runtime dependency contract is incomplete.",
                            "context_scope": "cross_file",
                            "related_files": ["pyproject.toml"],
                            "systemic_impact": "New environments can fail when the feature first imports yaml.",
                            "evidence_basis": "yaml is imported in config_writer.py, but PyYAML is not declared in the project dependencies.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_dependency_fixture_matches_runtime_imports_dev_only_pytest(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "dependency-runtime-imports-dev-only-pytest" / "fixture.json"
    )
    report_path = tmp_path / "dependency-runtime-imports-dev-only-pytest.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-dep-0003",
                            "file_path": "src/metrics.py",
                            "issue_type": "dependency",
                            "severity": "high",
                            "description": "The runtime metrics helper imports pytest.approx even though pytest is only declared in the dev extra, so production installs can fail when this path is loaded.",
                            "ai_feedback": "Application code should not depend on a test-only package for runtime behavior because non-dev installs usually omit pytest.",
                            "context_scope": "cross_file",
                            "related_files": ["pyproject.toml"],
                            "systemic_impact": "Deployments that install only runtime dependencies can hit ModuleNotFoundError before the approximation helper runs.",
                            "evidence_basis": "metrics.py imports pytest, but pyproject.toml only declares pytest in the dev optional-dependencies group.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_dependency_alias_for_runtime_imports_dev_only_pytest(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "dependency-runtime-imports-dev-only-pytest" / "fixture.json"
    )
    report_path = tmp_path / "dependency-runtime-imports-dev-only-pytest-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-dep-0004",
                            "file_path": "src/metrics.py",
                            "issue_type": "dependency_management",
                            "severity": "medium",
                            "description": "Runtime code depends on pytest even though the package is only present in the development dependency group.",
                            "ai_feedback": "The dependency is scoped incorrectly for runtime use.",
                            "context_scope": "cross_file",
                            "related_files": ["pyproject.toml"],
                            "systemic_impact": "Non-dev installations can fail when the module imports pytest.",
                            "evidence_basis": "pytest is imported by metrics.py, but the manifest only lists pytest under dev optional dependencies.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_dependency_fixture_matches_transitive_api_removal_runtime_gap(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "dependency-transitive-api-removal-runtime-gap" / "fixture.json"
    )
    report_path = tmp_path / "dependency-transitive-api-removal-runtime-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-dep-0005",
                            "file_path": "src/aws_client.py",
                            "issue_type": "dependency",
                            "severity": "high",
                            "description": "The runtime helper imports botocore.vendored.requests even though the declared botocore version no longer exposes that vendored API, so supported installs can fail at import time.",
                            "ai_feedback": "aws_client.py depends on a vendored requests shim inside botocore, but pyproject.toml pins modern botocore versions where that compatibility path is no longer part of the supported runtime surface.",
                            "context_scope": "cross_file",
                            "related_files": ["pyproject.toml"],
                            "systemic_impact": "Fresh installs or upgrades to the declared botocore version can fail before the client runs because the vendored import path is no longer available.",
                            "evidence_basis": "aws_client.py imports botocore.vendored.requests, but pyproject.toml declares botocore==1.34.34 where the vendored requests API is not part of the supported dependency contract.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_dependency_alias_for_transitive_api_removal_runtime_gap(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "dependency-transitive-api-removal-runtime-gap" / "fixture.json"
    )
    report_path = tmp_path / "dependency-transitive-api-removal-runtime-gap-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-dep-0006",
                            "file_path": "src/aws_client.py",
                            "issue_type": "dependency_management",
                            "severity": "medium",
                            "description": "The code depends on a vendored botocore requests API that is no longer available in the declared runtime dependency version.",
                            "ai_feedback": "This is a dependency contract gap caused by relying on a removed vendored API surface instead of a supported direct dependency.",
                            "context_scope": "cross_file",
                            "related_files": ["pyproject.toml"],
                            "systemic_impact": "Supported runtime environments can fail to import the client module after installs that use the declared botocore version.",
                            "evidence_basis": "botocore.vendored.requests is imported by aws_client.py, but the manifest only declares a modern botocore version where that vendored API is gone.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_license_fixture_matches_agpl_notice_conflict(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "license-agpl-notice-conflict" / "fixture.json"
    )
    report_path = tmp_path / "license-agpl-notice-conflict.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-lic-0001",
                            "file_path": "licenses_check.csv",
                            "issue_type": "license",
                            "severity": "high",
                            "description": "The project ships under MIT but the dependency inventory marks networksync as AGPL-3.0-only while THIRD_PARTY_NOTICES.md still claims all dependencies are permissive and MIT-compatible.",
                            "ai_feedback": "This creates a license compliance problem because the distribution metadata and notices say the dependency set is MIT-compatible even though licenses_check.csv records an AGPL-3.0-only runtime dependency.",
                            "context_scope": "cross_file",
                            "related_files": ["LICENSE", "THIRD_PARTY_NOTICES.md", "pyproject.toml"],
                            "systemic_impact": "Distributing the application with this dependency set can create a real licensing conflict and misleading third-party notice package.",
                            "evidence_basis": "licenses_check.csv records networksync as AGPL-3.0-only while LICENSE is MIT and THIRD_PARTY_NOTICES.md says dependencies are permissive and compatible with MIT.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_license_alias_for_agpl_notice_conflict(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "license-agpl-notice-conflict" / "fixture.json"
    )
    report_path = tmp_path / "license-agpl-notice-conflict-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-lic-0002",
                            "file_path": "pyproject.toml",
                            "issue_type": "license compliance",
                            "severity": "medium",
                            "description": "The runtime dependency set introduces an AGPL-3.0-only package even though the project metadata and notices present the distribution as MIT-compatible.",
                            "ai_feedback": "The dependency manifest and notice files disagree about the project's license obligations.",
                            "context_scope": "cross_file",
                            "related_files": ["licenses_check.csv", "THIRD_PARTY_NOTICES.md", "LICENSE"],
                            "systemic_impact": "Releases can ship with incompatible or incomplete licensing disclosures.",
                            "evidence_basis": "pyproject.toml declares networksync, and licenses_check.csv classifies it as AGPL-3.0-only.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_license_fixture_matches_apache_notice_omission(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "license-apache-notice-omission" / "fixture.json"
    )
    report_path = tmp_path / "license-apache-notice-omission.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-lic-0003",
                            "file_path": "THIRD_PARTY_NOTICES.md",
                            "issue_type": "license",
                            "severity": "medium",
                            "description": "The notice file says the Apache-2.0 telemetry-sdk dependency does not require shipping its upstream NOTICE text, even though the package is distributed in the binary and the project is relying on a third-party notice file for compliance.",
                            "ai_feedback": "This creates a license compliance gap because the project documents telemetry-sdk as Apache-2.0 but explicitly says its NOTICE does not need to be shipped with binaries.",
                            "context_scope": "cross_file",
                            "related_files": ["licenses_check.csv", "pyproject.toml"],
                            "systemic_impact": "Binary releases can omit required third-party attribution materials and ship incomplete licensing notices.",
                            "evidence_basis": "THIRD_PARTY_NOTICES.md says telemetry-sdk ships with an upstream NOTICE file but that binaries will not include it, while licenses_check.csv records telemetry-sdk as Apache-2.0.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_license_alias_for_apache_notice_omission(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "license-apache-notice-omission" / "fixture.json"
    )
    report_path = tmp_path / "license-apache-notice-omission-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-lic-0004",
                            "file_path": "licenses_check.csv",
                            "issue_type": "notice requirements",
                            "severity": "medium",
                            "description": "The packaged Apache-2.0 dependency has an upstream NOTICE file, but the project's third-party notice doc says the binary build omits that attribution material.",
                            "ai_feedback": "The project is documenting away a NOTICE retention obligation for a distributed Apache dependency.",
                            "context_scope": "cross_file",
                            "related_files": ["THIRD_PARTY_NOTICES.md", "pyproject.toml"],
                            "systemic_impact": "Distributed binaries can ship with incomplete attribution and licensing materials.",
                            "evidence_basis": "licenses_check.csv lists telemetry-sdk as Apache-2.0 and THIRD_PARTY_NOTICES.md says the upstream NOTICE file will not be included in binaries.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_license_fixture_matches_embedded_mit_code_without_attribution(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "license-embedded-mit-code-without-attribution" / "fixture.json"
    )
    report_path = tmp_path / "license-embedded-mit-code-without-attribution.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-lic-0005",
                            "file_path": "src/vendor/markdown_table.py",
                            "issue_type": "license",
                            "severity": "medium",
                            "description": "The project vendors code copied from the MIT-licensed tinytable package, but the distributed source tree does not preserve tinytable's copyright and permission notice anywhere in the shipped notices or file header.",
                            "ai_feedback": "MIT allows bundling this helper, but the copied code still needs the original copyright and permission notice. THIRD_PARTY_NOTICES.md currently says no third-party source is bundled even though markdown_table.py says it was copied from tinytable.",
                            "context_scope": "cross_file",
                            "related_files": ["THIRD_PARTY_NOTICES.md", "LICENSE", "src/report_builder.py"],
                            "systemic_impact": "Shipped source bundles can omit required third-party attribution and distribute copied MIT code under incomplete notice terms.",
                            "evidence_basis": "src/vendor/markdown_table.py says it was copied from tinytable 1.4.0 (MIT), but THIRD_PARTY_NOTICES.md says the distribution does not bundle third-party source files and no preserved tinytable copyright or permission notice is shipped.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_license_alias_for_embedded_mit_code_without_attribution(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "license-embedded-mit-code-without-attribution" / "fixture.json"
    )
    report_path = tmp_path / "license-embedded-mit-code-without-attribution-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-lic-0006",
                            "file_path": "THIRD_PARTY_NOTICES.md",
                            "issue_type": "license attribution",
                            "severity": "medium",
                            "description": "Bundled tinytable code is missing the MIT notice and attribution that should travel with the copied source.",
                            "ai_feedback": "The shipped notice package says no third-party source is bundled, but markdown_table.py is explicitly copied from tinytable under MIT.",
                            "context_scope": "cross_file",
                            "related_files": ["src/vendor/markdown_table.py", "src/report_builder.py"],
                            "systemic_impact": "Released artifacts can ship copied third-party source with incomplete attribution materials.",
                            "evidence_basis": "THIRD_PARTY_NOTICES.md denies bundling third-party source, while src/vendor/markdown_table.py says the helper was copied from tinytable 1.4.0 (MIT).",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_localization_fixture_matches_hardcoded_settings_labels(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "localization-hardcoded-settings-labels" / "fixture.json"
    )
    report_path = tmp_path / "localization-hardcoded-settings-labels.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-loc-0001",
                            "file_path": "src/settings_panel.py",
                            "issue_type": "localization",
                            "severity": "medium",
                            "description": "The settings panel still hardcodes visible strings like 'Sync now' and 'Delete cache' even though the rest of the screen uses the translation helper.",
                            "ai_feedback": "These user-facing labels bypass i18n extraction, so the panel will remain partially untranslated in non-English locales.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Users in other locales will see mixed-language controls and status text on the same screen.",
                            "evidence_basis": "settings_panel.py calls t('settings.title') and t('settings.description') but hardcodes 'Sync now', 'Delete cache', and 'Last synced successfully'.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_localization_alias_for_hardcoded_settings_labels(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "localization-hardcoded-settings-labels" / "fixture.json"
    )
    report_path = tmp_path / "localization-hardcoded-settings-labels-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-loc-0002",
                            "file_path": "src/settings_panel.py",
                            "issue_type": "i18n",
                            "severity": "medium",
                            "description": "Several visible labels are hardcoded instead of being externalized through translation keys.",
                            "ai_feedback": "The screen is not fully translation-ready.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Localized builds will still show English-only controls.",
                            "evidence_basis": "The file mixes calls to t(...) with hardcoded user-facing strings.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_localization_fixture_matches_us_only_receipt_format(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "localization-us-only-receipt-format" / "fixture.json"
    )
    report_path = tmp_path / "localization-us-only-receipt-format.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-loc-0003",
                            "file_path": "src/receipt_formatter.py",
                            "issue_type": "localization",
                            "severity": "medium",
                            "description": "The receipt formatter hardcodes US-only date and currency presentation instead of using locale-aware formatting.",
                            "ai_feedback": "strftime('%m/%d/%Y') and a '$' prefix will produce the wrong format for many locales.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "International users can see misleading or unfamiliar receipts because dates and amounts are rendered in a US-centric format.",
                            "evidence_basis": "receipt_formatter.py uses strftime('%m/%d/%Y') and formats totals as f'${total_amount:.2f}'.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_localization_alias_for_us_only_receipt_format(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "localization-us-only-receipt-format" / "fixture.json"
    )
    report_path = tmp_path / "localization-us-only-receipt-format-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-loc-0004",
                            "file_path": "src/receipt_formatter.py",
                            "issue_type": "internationalization",
                            "severity": "medium",
                            "description": "Date and currency rendering is locale-specific rather than locale-aware.",
                            "ai_feedback": "The output is not internationalization-ready.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Users outside the US can get incorrectly formatted receipts.",
                            "evidence_basis": "The code uses %m/%d/%Y and a hardcoded dollar-prefixed amount format.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_localization_fixture_matches_concatenated_translation_grammar_break(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "localization-concatenated-translation-grammar-break" / "fixture.json"
    )
    report_path = tmp_path / "localization-concatenated-translation-grammar-break.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-loc-0005",
                            "file_path": "src/renewal_banner.py",
                            "issue_type": "localization",
                            "severity": "medium",
                            "description": "The renewal banner assembles a sentence from multiple translated fragments around dynamic values, so other locales cannot reorder the customer name and renewal date naturally.",
                            "ai_feedback": "Using separate keys for the prefix, middle, and suffix forces one English sentence structure instead of giving translators one full template with placeholders.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Localized builds can produce awkward or incorrect grammar because translators cannot control the full sentence structure around the inserted values.",
                            "evidence_basis": "renewal_banner.py concatenates t('billing.renewal_prefix'), customer_name, t('billing.renewal_middle'), renewal_date_label, and t('billing.renewal_suffix') into one message.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_localization_alias_for_concatenated_translation_grammar_break(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "localization-concatenated-translation-grammar-break" / "fixture.json"
    )
    report_path = tmp_path / "localization-concatenated-translation-grammar-break-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-loc-0006",
                            "file_path": "src/renewal_banner.py",
                            "issue_type": "i18n",
                            "severity": "medium",
                            "description": "This message is not translation-safe because it concatenates translated fragments instead of using one template with placeholders.",
                            "ai_feedback": "Translators need one full sentence key so they can reorder variables for other languages.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Users in other locales can see unnatural grammar when the banner mixes dynamic values with fixed fragment order.",
                            "evidence_basis": "The banner joins renewal_prefix, renewal_middle, and renewal_suffix keys around the inserted customer name and date label.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_accessibility_fixture_matches_icon_button_label_gap(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "accessibility-icon-button-label-gap" / "fixture.json"
    )
    report_path = tmp_path / "accessibility-icon-button-label-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-a11y-0001",
                            "file_path": "src/SearchToolbar.tsx",
                            "issue_type": "accessibility",
                            "severity": "medium",
                            "description": "The icon-only search button and adjacent input do not expose an accessible label, so screen reader users cannot identify the search controls.",
                            "ai_feedback": "The input relies on placeholder text and the button only contains an SVG icon, so neither control has a stable accessible name for assistive technology.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Screen reader users can struggle to understand or operate the search toolbar because the primary controls are announced without a clear label.",
                            "evidence_basis": "SearchToolbar.tsx renders an input and icon-only button without a label, aria-label, or other accessible name.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_accessibility_fixture_matches_dialog_semantic_gap(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "accessibility-dialog-semantic-gap" / "fixture.json"
    )
    report_path = tmp_path / "accessibility-dialog-semantic-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-a11y-dialog-0001",
                            "file_path": "src/SettingsModal.tsx",
                            "issue_type": "accessibility",
                            "severity": "medium",
                            "description": "The modal is rendered with plain div elements and no dialog semantics, so screen reader users are not told they entered a modal context.",
                            "ai_feedback": "SettingsModal returns backdrop and panel divs, but the panel lacks role=dialog, aria-modal, and an accessible relationship to the heading.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Screen reader users may not understand that the settings panel is a modal dialog or that the rest of the page is temporarily inactive.",
                            "evidence_basis": "SettingsModal.tsx renders the modal with div elements and no role=dialog or aria-modal attribute on the panel.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_accessibility_fixture_matches_fieldset_without_legend(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "accessibility-fieldset-without-legend" / "fixture.json"
    )
    report_path = tmp_path / "accessibility-fieldset-without-legend.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-a11y-fieldset-0001",
                            "file_path": "src/NotificationPreferences.tsx",
                            "issue_type": "accessibility",
                            "severity": "medium",
                            "description": "The related notification options are wrapped in fieldset elements without legends, so screen reader users do not hear an accessible group label for the controls.",
                            "ai_feedback": "The component uses fieldset for the delivery channel and digest groups, but each group is headed by a paragraph instead of a legend, so assistive technology does not announce the purpose of the grouped controls.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Screen reader users may hear the individual checkboxes and radio buttons without the shared group context that explains what set of options they belong to.",
                            "evidence_basis": "NotificationPreferences.tsx renders two fieldset elements with paragraph headings and no legend element to label the grouped controls.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_matches_tool_mode_envelope(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "field-rename-contract" / "fixture.json"
    )
    report_path = tmp_path / "field-rename-contract.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-0001",
                            "file_path": "src/handlers.py",
                            "issue_type": "best_practices",
                            "severity": "high",
                            "description": "Handler still reads display_name after serializer renamed the field to full_name.",
                            "ai_feedback": "This is a cross-file contract mismatch between serializers.py and handlers.py.",
                            "context_scope": "cross_file",
                            "related_files": ["src/serializers.py"],
                            "systemic_impact": "Breaks callers expecting display_name in downstream payloads.",
                            "evidence_basis": "Serializer now emits full_name while handler still accesses display_name.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_dead_code_fixture_matches_unreachable_fallback(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "dead-code-unreachable-fallback" / "fixture.json"
    )
    report_path = tmp_path / "dead-code-unreachable-fallback.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-dead-0001",
                            "file_path": "src/formatter.py",
                            "issue_type": "unreachable_code",
                            "severity": "medium",
                            "description": "The legacy fallback branch is unreachable because USE_LEGACY_RENDERER is permanently false, so the old renderer is dead code.",
                            "ai_feedback": "render_invoice always returns the modern path because USE_LEGACY_RENDERER is false at module scope, leaving _render_legacy_invoice as a legacy fallback that no live flow can execute.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Keeping the obsolete fallback path around makes future maintenance harder because engineers may assume the legacy renderer still matters.",
                            "evidence_basis": "formatter.py defines USE_LEGACY_RENDERER = False and only calls _render_legacy_invoice inside that guarded branch.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_dead_code_fixture_matches_obsolete_compat_shim(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "dead-code-obsolete-compat-shim" / "fixture.json"
    )
    report_path = tmp_path / "dead-code-obsolete-compat-shim.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-dead-0002",
                            "file_path": "src/legacy_export.py",
                            "issue_type": "dead_code",
                            "severity": "medium",
                            "description": "The legacy CSV exporter is unused now that the live report flow only calls the modern exporter, so this compatibility shim looks obsolete.",
                            "ai_feedback": "api.py routes through report_service.generate_report, which only imports render_modern_csv from modern_export.py and never references render_legacy_csv from legacy_export.py.",
                            "context_scope": "cross_file",
                            "related_files": ["src/report_service.py", "src/api.py"],
                            "systemic_impact": "Leaving the obsolete shim in place increases cleanup risk because future changes may update dead code that is no longer part of the shipped path.",
                            "evidence_basis": "report_service.py imports render_modern_csv and generate_report returns that path directly, while render_legacy_csv in legacy_export.py has no remaining caller.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_dead_code_fixture_matches_stale_feature_flag(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "dead-code-stale-feature-flag" / "fixture.json"
    )
    report_path = tmp_path / "dead-code-stale-feature-flag.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-dead-0003",
                            "file_path": "src/toolbar.py",
                            "issue_type": "obsolete_code",
                            "severity": "medium",
                            "description": "The bulk archive UI path is dead code because the feature flag is permanently disabled, so the dormant handler is never reachable.",
                            "ai_feedback": "MessageToolbar only appends the Bulk archive action when ENABLE_BULK_ARCHIVE is true, but feature_flags.py hard-codes that flag to False, leaving _handle_bulk_archive and its dialog path dormant.",
                            "context_scope": "cross_file",
                            "related_files": ["src/feature_flags.py"],
                            "systemic_impact": "Keeping the obsolete feature-flag path around adds cleanup risk because future UI changes may update handlers that are no longer exposed to users.",
                            "evidence_basis": "toolbar.py guards the Bulk archive action on ENABLE_BULK_ARCHIVE, and feature_flags.py sets ENABLE_BULK_ARCHIVE = False.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_error_handling_fixture_matches_swallowed_import_failure(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "error-handling-swallowed-import-failure" / "fixture.json"
    )
    report_path = tmp_path / "error-handling-swallowed-import-failure.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-err-0001",
                            "file_path": "src/import_job.py",
                            "issue_type": "error_handling",
                            "severity": "high",
                            "description": "The import job catches a broad exception and still returns a completed status, so the controller can report success after a failed import.",
                            "ai_feedback": "import_job.py swallows the failure in except Exception and returns {'status': 'completed'}, while import_controller.py treats that completed status as a successful import.",
                            "context_scope": "cross_file",
                            "related_files": ["src/import_controller.py"],
                            "systemic_impact": "Operators can see a false success message even when the import failed, which hides the error and delays recovery.",
                            "evidence_basis": "import_job.py uses except Exception and returns status='completed'; import_controller.py shows 'Import finished' whenever status is completed.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_error_handling_fixture_matches_retryless_sync_timeout(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "error-handling-retryless-sync-timeout" / "fixture.json"
    )
    report_path = tmp_path / "error-handling-retryless-sync-timeout.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-err-0002",
                            "file_path": "src/sync_worker.py",
                            "issue_type": "error_handling",
                            "severity": "high",
                            "description": "The sync worker treats TimeoutError as a terminal failure path even though the result is explicitly retryable, so the controller disables background sync instead of retrying or preserving a recovery path.",
                            "ai_feedback": "sync_worker.py catches TimeoutError and returns retryable=True, but sync_controller.py disables background sync immediately whenever status == 'failed' instead of retrying the transient timeout.",
                            "context_scope": "cross_file",
                            "related_files": ["src/sync_controller.py"],
                            "systemic_impact": "A transient outage can disable sync entirely and delay recovery because operators lose the automatic retry path after a single timeout.",
                            "evidence_basis": "sync_worker.py catches TimeoutError and returns retryable=True, while sync_controller.py disables background sync as soon as status is failed.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_error_handling_fixture_matches_context_manager_exception_not_cleaned(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "error-handling-context-manager-exception-not-cleaned" / "fixture.json"
    )
    report_path = tmp_path / "error-handling-context-manager-exception-not-cleaned.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-err-0003",
                            "file_path": "src/job_runner.py",
                            "issue_type": "error_handling",
                            "severity": "high",
                            "description": "The export lease is not cleaned up when the with-block raises, so failed exports remain marked as running and later retries are blocked.",
                            "ai_feedback": "lease_store.py only discards ACTIVE_EXPORTS inside ExportLease.__exit__ when exc_type is None. If send_archive(...) raises inside job_runner.py, the leaked active marker causes future run_export calls to return already-running instead of retrying cleanly.",
                            "context_scope": "cross_file",
                            "related_files": ["src/lease_store.py"],
                            "systemic_impact": "A transient export failure can leave work permanently stuck because the leaked running marker blocks every later retry for the same export.",
                            "evidence_basis": "ExportLease.__exit__ only calls ACTIVE_EXPORTS.discard(...) when exc_type is None, while job_runner.py performs send_archive(...) inside the with ExportLease(export_id) block.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_data_validation_fixture_matches_inverted_time_window(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "data-validation-inverted-time-window" / "fixture.json"
    )
    report_path = tmp_path / "data-validation-inverted-time-window.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-dv-0001",
                            "file_path": "src/api.py",
                            "issue_type": "data_validation",
                            "severity": "high",
                            "description": "The maintenance window validator never checks that end_hour is after start_hour, so the API can schedule an inverted time window with a negative duration.",
                            "ai_feedback": "api.py trusts validate_window from validation.py even though the validator only checks presence and integer coercion for start_hour and end_hour.",
                            "context_scope": "cross_file",
                            "related_files": ["src/validation.py"],
                            "systemic_impact": "Invalid maintenance windows can be accepted and scheduled, which allows impossible durations to propagate into downstream planning logic.",
                            "evidence_basis": "validation.py coerces start_hour and end_hour to int but never checks that end_hour is greater than start_hour before api.py computes duration_hours.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_data_validation_fixture_matches_rollout_percent_range(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "data-validation-rollout-percent-range" / "fixture.json"
    )
    report_path = tmp_path / "data-validation-rollout-percent-range.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-dv-0003",
                            "file_path": "src/api.py",
                            "issue_type": "data_validation",
                            "severity": "high",
                            "description": "The rollout validator never constrains rollout_percent to the valid 0..100 range, so the API can schedule impossible batch sizes.",
                            "ai_feedback": "api.py trusts validate_rollout from validation.py even though the validator only checks presence and integer coercion for rollout_percent.",
                            "context_scope": "cross_file",
                            "related_files": ["src/validation.py"],
                            "systemic_impact": "Invalid rollout percentages can reach runtime use and produce impossible deployment batch sizes or over-allocation decisions.",
                            "evidence_basis": "validation.py coerces rollout_percent to int but never checks that rollout_percent stays between 0 and 100 before api.py computes batch_size.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_testing_fixture_matches_rollout_percent_range_gap(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "testing-rollout-percent-range-untested" / "fixture.json"
    )
    report_path = tmp_path / "testing-rollout-percent-range-untested.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-test-0001",
                            "file_path": "tests/test_api.py",
                            "issue_type": "testing",
                            "severity": "medium",
                            "description": "The test suite never exercises the rollout_percent range guard, so out-of-range rollout inputs can regress without a failing test.",
                            "ai_feedback": "validation.py rejects rollout_percent values outside 0..100, but test_api.py only checks the success case and a missing-field error instead of the range boundary behavior.",
                            "context_scope": "cross_file",
                            "related_files": ["src/validation.py"],
                            "systemic_impact": "A regression in the rollout_percent range check could ship unnoticed because the suite does not pin the existing boundary contract.",
                            "evidence_basis": "validation.py raises for rollout_percent outside 0..100, but tests/test_api.py never asserts that create_rollout rejects rollout_percent values such as -1 or 101.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_testing_fixture_matches_order_rollback_gap(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "testing-order-rollback-untested" / "fixture.json"
    )
    report_path = tmp_path / "testing-order-rollback-untested.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-test-rollback-0001",
                            "file_path": "tests/test_orders.py",
                            "issue_type": "testing",
                            "severity": "medium",
                            "description": "The tests cover the successful checkout path but never assert that submit_order rolls back the repository when payment capture raises.",
                            "ai_feedback": "orders.py already calls repository.rollback() in the exception path, but tests/test_orders.py only pins the accepted path and does not exercise a failing charge.",
                            "context_scope": "cross_file",
                            "related_files": ["src/orders.py"],
                            "systemic_impact": "The rollback behavior is unpinned, so a regression in the failure path could ship unnoticed without a failing test.",
                            "evidence_basis": "tests/test_orders.py asserts begin/save/commit for the happy path, but never verifies that orders.py executes repository.rollback() when payment_gateway.charge raises.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_regression_fixture_matches_default_sync_disabled(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "regression-default-sync-disabled" / "fixture.json"
    )
    report_path = tmp_path / "regression-default-sync-disabled.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-reg-0001",
                            "file_path": "src/settings_defaults.py",
                            "issue_type": "regression",
                            "severity": "medium",
                            "description": "The diff changes the default sync_enabled preference to false, which disables background sync for users who rely on the existing defaults.",
                            "ai_feedback": "app_startup.py only starts the scheduler when load_default_preferences returns sync_enabled=True, so changing the default to False silently turns off the current startup behavior.",
                            "context_scope": "cross_file",
                            "related_files": ["src/app_startup.py"],
                            "systemic_impact": "Background sync becomes disabled by default, so an existing feature silently stops starting for default-configured users.",
                            "evidence_basis": "settings_defaults.py changes sync_enabled from True to False, and app_startup.py gates scheduler startup directly on preferences['sync_enabled'].",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_regression_fixture_matches_inverted_sync_start_guard(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "regression-inverted-sync-start-guard" / "fixture.json"
    )
    report_path = tmp_path / "regression-inverted-sync-start-guard.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-reg-guard-0001",
                            "file_path": "src/app_startup.py",
                            "issue_type": "regression",
                            "severity": "medium",
                            "description": "The diff inverts the sync_enabled startup guard, so background sync no longer starts for users whose defaults still enable sync.",
                            "ai_feedback": "settings_defaults.py still returns sync_enabled=True, but app_startup.py now starts the scheduler only when sync_enabled is false.",
                            "context_scope": "cross_file",
                            "related_files": ["src/settings_defaults.py"],
                            "systemic_impact": "Background sync is effectively disabled for the default-enabled path, so an existing startup workflow silently stops running.",
                            "evidence_basis": "settings_defaults.py returns sync_enabled=True, but app_startup.py changed the startup guard to if not preferences['sync_enabled'] before calling sync_scheduler.start().",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_regression_fixture_matches_stale_caller_utility_signature_change(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "regression-stale-caller-utility-signature-change" / "fixture.json"
    )
    report_path = tmp_path / "regression-stale-caller-utility-signature-change.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-reg-utility-0001",
                            "file_path": "src/retry_policy.py",
                            "issue_type": "regression",
                            "severity": "medium",
                            "description": "The retry-delay helper signature now expects network_profile before retry_count, but sync_worker.py still calls it with the old argument order, which changes the existing retry delay behavior.",
                            "ai_feedback": "build_retry_delay now treats the first positional argument as network_profile, yet schedule_retry still passes retry_count first, so metered and cellular jobs fall through to the default delay logic.",
                            "context_scope": "cross_file",
                            "related_files": ["src/sync_worker.py"],
                            "systemic_impact": "Existing retry scheduling behavior changes because jobs no longer receive the intended metered or cellular delay values after the helper signature change.",
                            "evidence_basis": "retry_policy.py changed build_retry_delay to build_retry_delay(network_profile, retry_count), but sync_worker.py still calls build_retry_delay(job['retry_count'], job['network_profile']).",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_documentation_fixture_matches_stale_dry_run_flag(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "documentation-stale-dry-run-flag" / "fixture.json"
    )
    report_path = tmp_path / "documentation-stale-dry-run-flag.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-doc-0001",
                            "file_path": "README.md",
                            "issue_type": "documentation",
                            "severity": "medium",
                            "description": "The README still documents a --dry-run option, but cli.py no longer defines that flag for syncctl run.",
                            "ai_feedback": "Operators following README.md will try syncctl run --workspace acme --dry-run, but build_parser in cli.py only accepts --workspace and --apply.",
                            "context_scope": "cross_file",
                            "related_files": ["src/cli.py"],
                            "systemic_impact": "Operators can rely on a documented preview mode that does not exist, which makes the sync instructions misleading during live operations.",
                            "evidence_basis": "README.md tells users to run syncctl with --dry-run, but cli.py never registers a --dry-run argument for the run command.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_documentation_fixture_matches_stale_sync_token_doc(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "documentation-stale-sync-token-doc" / "fixture.json"
    )
    report_path = tmp_path / "documentation-stale-sync-token-doc.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-doc-token-0001",
                            "file_path": "docs/operations.md",
                            "issue_type": "documentation",
                            "severity": "medium",
                            "description": "The operations guide still tells operators to export SYNC_API_TOKEN, but config.py only reads SYNC_TOKEN.",
                            "ai_feedback": "Users following docs/operations.md will configure the wrong environment variable because load_sync_token in config.py now requires SYNC_TOKEN instead.",
                            "context_scope": "cross_file",
                            "related_files": ["src/config.py"],
                            "systemic_impact": "Operators following the published setup steps can start the worker with a broken authentication configuration.",
                            "evidence_basis": "docs/operations.md documents SYNC_API_TOKEN, but config.py only reads os.getenv('SYNC_TOKEN') and raises when SYNC_TOKEN is missing.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_data_validation_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "data-validation-inverted-time-window" / "fixture.json"
    )
    report_path = tmp_path / "data-validation-inverted-time-window-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-dv-0002",
                            "file_path": "src/validation.py",
                            "issue_type": "validation/contract",
                            "severity": "high",
                            "description": "The validator contract allows an end before start to reach runtime use.",
                            "ai_feedback": "validation.py only coerces start_hour and end_hour before api.py computes duration.",
                            "context_scope": "cross_file",
                            "related_files": ["src/api.py", "src/validation.py"],
                            "systemic_impact": "Unvalidated input can propagate into incorrect scheduling behavior.",
                            "evidence_basis": "validation.py never checks that end_hour is greater than start_hour before api.py subtracts the fields.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_testing_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "testing-rollout-percent-range-untested" / "fixture.json"
    )
    report_path = tmp_path / "testing-rollout-percent-range-untested-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-test-0002",
                            "file_path": "tests/test_api.py",
                            "issue_type": "insufficient test coverage",
                            "severity": "medium",
                            "description": "The test suite misses the rollout_percent range guard.",
                            "ai_feedback": "validation.py rejects rollout_percent outside 0..100 but tests do not cover that branch.",
                            "context_scope": "cross_file",
                            "related_files": ["src/validation.py"],
                            "systemic_impact": "The rollout_percent boundary could regress without a failing test.",
                            "evidence_basis": "tests/test_api.py never asserts that create_rollout rejects rollout_percent values such as -1 or 101.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_documentation_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "documentation-stale-dry-run-flag" / "fixture.json"
    )
    report_path = tmp_path / "documentation-stale-dry-run-flag-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-doc-0002",
                            "file_path": "src/cli.py",
                            "issue_type": "documentation mismatch / cli contract",
                            "severity": "high",
                            "description": "README still documents --dry-run even though the CLI no longer supports it.",
                            "ai_feedback": "README and cli.py disagree about the dry-run flag.",
                            "context_scope": "cross_file",
                            "related_files": ["README.md"],
                            "systemic_impact": "Users and automation following the documented workflow can hit a broken command.",
                            "evidence_basis": "README.md documents --dry-run, but cli.py never registers that flag.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_regression_systemic_impact_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "testing-rollout-percent-range-untested" / "fixture.json"
    )
    report_path = tmp_path / "testing-rollout-percent-range-untested-regression.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-test-0003",
                            "file_path": "tests/test_api.py",
                            "issue_type": "testing",
                            "severity": "medium",
                            "description": "The rollout_percent boundary is never tested.",
                            "ai_feedback": "validation.py already has the guard but the suite does not pin it.",
                            "context_scope": "cross_file",
                            "related_files": ["src/validation.py"],
                            "systemic_impact": "The boundary can regress silently and ship unnoticed during refactors.",
                            "evidence_basis": "tests/test_api.py never covers rollout_percent values outside 0..100.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_regression_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "regression-default-sync-disabled" / "fixture.json"
    )
    report_path = tmp_path / "regression-default-sync-disabled-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-reg-0002",
                            "file_path": "src/settings_defaults.py",
                            "issue_type": "behavioral change",
                            "severity": "medium",
                            "description": "Changing sync_enabled alters default startup behavior.",
                            "ai_feedback": "The default behavior changes for existing users.",
                            "context_scope": "cross_file",
                            "related_files": ["src/app_startup.py"],
                            "systemic_impact": "Background sync is disabled by default for users who rely on defaults.",
                            "evidence_basis": "settings_defaults.py changes sync_enabled from True to False and app_startup.py gates startup on sync_enabled.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_disabled_systemic_impact_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "regression-default-sync-disabled" / "fixture.json"
    )
    report_path = tmp_path / "regression-default-sync-disabled-impact.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-reg-0003",
                            "file_path": "src/settings_defaults.py",
                            "issue_type": "regression",
                            "severity": "medium",
                            "description": "Changing sync_enabled disables the startup path.",
                            "ai_feedback": "The startup behavior no longer runs.",
                            "context_scope": "cross_file",
                            "related_files": ["src/app_startup.py"],
                            "systemic_impact": "The existing startup flow no longer runs for default-configured users.",
                            "evidence_basis": "settings_defaults.py changes sync_enabled from True to False and app_startup.py gates startup on sync_enabled.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_accepts_recovery_systemic_impact_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "error-handling-retryless-sync-timeout" / "fixture.json"
    )
    report_path = tmp_path / "error-handling-retryless-sync-timeout-recovery.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-err-0003",
                            "file_path": "src/sync_controller.py",
                            "issue_type": "error_handling",
                            "severity": "high",
                            "description": "The controller converts a retryable timeout into terminal disablement.",
                            "ai_feedback": "sync_worker.py catches TimeoutError and returns retryable=True while sync_controller.py disables the feature immediately.",
                            "context_scope": "cross_file",
                            "related_files": ["src/sync_worker.py"],
                            "systemic_impact": "A transient timeout can cause prolonged outage because automatic retries never get a chance to recover.",
                            "evidence_basis": "sync_worker.py catches TimeoutError and returns retryable=True, while sync_controller.py disables background sync immediately.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_ui_ux_fixture_matches_missing_feedback_states(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "ui-loading-feedback-gap" / "fixture.json"
    )
    report_path = tmp_path / "ui-loading-feedback-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-ui-0001",
                            "file_path": "src/AccountPanel.tsx",
                            "issue_type": "ui_ux",
                            "severity": "medium",
                            "description": "The panel has no loading, error, or empty state, so users see a blank area instead of feedback while data is unavailable.",
                            "ai_feedback": "AccountPanel reads isLoading and error from useAccount but returns null whenever data is missing, which hides progress and recovery guidance.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "Users can feel confused when the panel stays empty without any visible loading feedback.",
                            "evidence_basis": "The component returns null when data is absent, so the loading state gives no user-visible feedback.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_ui_ux_fixture_matches_form_recovery_gap(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "ui-form-recovery-gap" / "fixture.json"
    )
    report_path = tmp_path / "ui-form-recovery-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-ui-0002",
                            "file_path": "src/ProfileForm.tsx",
                            "issue_type": "ui_ux",
                            "severity": "medium",
                            "description": "The form waits until submit to validate, clears invalid values, and gives no inline recovery guidance, forcing users to re-enter data after a failed save.",
                            "ai_feedback": "ProfileForm relies on validateProfile from validators.ts but only reports a generic failure message after submit instead of attaching field-level feedback near the inputs.",
                            "context_scope": "cross_file",
                            "related_files": ["src/validators.ts"],
                            "systemic_impact": "Users must re-enter their values and guess what to fix, which adds friction and makes the failure feel punitive.",
                            "evidence_basis": "handleSubmit calls validateProfile, then clears name and email and only sets a generic status message when validation fails.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_ui_ux_fixture_matches_desktop_busy_feedback_gap(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "desktop-busy-feedback-gap" / "fixture.json"
    )
    report_path = tmp_path / "desktop-busy-feedback-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-ui-0003",
                            "file_path": "src/export_dialog.py",
                            "issue_type": "ui_ux",
                            "severity": "medium",
                            "description": "The desktop export dialog shows almost no busy-state feedback, leaves controls active, and gives users no progress indication during the blocking export.",
                            "ai_feedback": "start_export calls export_report synchronously while the Export and Close buttons remain active, so users can click repeatedly without understanding whether the export is still running.",
                            "context_scope": "local",
                            "related_files": [],
                            "systemic_impact": "The weak busy feedback invites repeated clicks and makes the dialog feel frozen during a long export.",
                            "evidence_basis": "export_dialog.py calls export_report directly and only swaps the label text before setting it to Done.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_ui_ux_fixture_matches_desktop_confirmation_gap(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "desktop-confirmation-gap" / "fixture.json"
    )
    report_path = tmp_path / "desktop-confirmation-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-ui-0004",
                            "file_path": "src/settings_dialog.py",
                            "issue_type": "ui_ux",
                            "severity": "medium",
                            "description": "The desktop settings dialog performs a destructive reset immediately, with no confirmation, no cancel context, and no undo path if the click was accidental.",
                            "ai_feedback": "reset_everything calls reset_all_settings from settings_store.py straight away, then closes the dialog, so users lose context and cannot review the impact before the reset is committed.",
                            "context_scope": "cross_file",
                            "related_files": ["src/settings_store.py"],
                            "systemic_impact": "An accidental click can wipe user preferences without a recovery path, which makes the confirmation flow feel unsafe.",
                            "evidence_basis": "settings_dialog.py calls reset_all_settings directly and destroys the window immediately afterward.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_ui_ux_fixture_matches_desktop_settings_discoverability_gap(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "desktop-settings-discoverability-gap" / "fixture.json"
    )
    report_path = tmp_path / "desktop-settings-discoverability-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-ui-0005",
                            "file_path": "src/settings_window.py",
                            "issue_type": "ui_ux",
                            "severity": "medium",
                            "description": "The desktop settings flow hides important options and save behavior behind unclear navigation, making core configuration paths hard to discover.",
                            "ai_feedback": "SettingsWindow labels the dialog as Preferences, hides advanced options in a separate Advanced window, and closes on OK without telling users that it also commits changes, so the information architecture makes key settings hard to find.",
                            "context_scope": "cross_file",
                            "related_files": ["src/advanced_panel.py"],
                            "systemic_impact": "Users may fail to find the setting they need or understand where changes are applied, which makes configuration feel inconsistent and hard to navigate.",
                            "evidence_basis": "The only route to the extra settings is a vague Advanced button, while advanced_panel.py contains additional configuration groups and the main window uses OK instead of an explicit Save action.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_ui_ux_fixture_matches_desktop_wizard_orientation_gap(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "desktop-wizard-orientation-gap" / "fixture.json"
    )
    report_path = tmp_path / "desktop-wizard-orientation-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-ui-0006",
                            "file_path": "src/setup_wizard.py",
                            "issue_type": "ui_ux",
                            "severity": "medium",
                            "description": "The desktop wizard gives weak step orientation and hides dependency context, so later options appear disabled without telling users which earlier choice unlocked them.",
                            "ai_feedback": "SetupWizard sends users to a separate Advanced step with no progress indicator or explanation, while AdvancedStep disables sync options unless Enable cloud sync was chosen earlier, which makes the step flow confusing.",
                            "context_scope": "cross_file",
                            "related_files": ["src/advanced_step.py"],
                            "systemic_impact": "Users can lose their place in the wizard and misread disabled controls as broken instead of understanding the prerequisite step.",
                            "evidence_basis": "The only clue is the earlier Enable cloud sync checkbox, and advanced_step.py disables its sync settings when that choice was not enabled.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_ui_ux_fixture_matches_desktop_cross_tab_preference_gap(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "desktop-cross-tab-preference-gap" / "fixture.json"
    )
    report_path = tmp_path / "desktop-cross-tab-preference-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-ui-0007",
                            "file_path": "src/settings_window.py",
                            "issue_type": "ui_ux",
                            "severity": "medium",
                            "description": "The desktop settings flow silently overrides a sync preference from another tab, so users can configure one option and lose it at save time without understanding why.",
                            "ai_feedback": "SettingsWindow saves values gathered from SyncTab, but when Lite mode is selected it overrides sync_enabled to False without warning in the UI, which creates a hidden cross-tab dependency between General and Sync.",
                            "context_scope": "cross_file",
                            "related_files": ["src/sync_tab.py"],
                            "systemic_impact": "Users can think sync is enabled when the save flow silently changes that preference, which makes the settings model feel inconsistent and hard to trust.",
                            "evidence_basis": "save_settings writes payload values from sync_tab.py and then forces sync_enabled to False when performance_mode is lite.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_directory_marks_missing_reports(tmp_path):
    fixtures = benchmarking.discover_fixtures(FIXTURES_ROOT)

    results = benchmarking.evaluate_fixture_directory(fixtures[:2], tmp_path)

    assert len(results) == 2
    assert all(result.passed is False for result in results)
    assert all(result.missing_report is True for result in results)


def test_evaluate_fixture_reports_failed_checks_for_best_candidate(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "auth-guard-regression" / "fixture.json"
    )
    report_path = tmp_path / "auth-guard-regression.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0007",
                        "file_path": "src/admin.py",
                        "issue_type": "dependency",
                        "severity": "high",
                        "description": "The admin endpoint bypasses the admin guard by skipping require_admin and accepts any authenticated user.",
                        "context_scope": "cross_file",
                        "related_files": ["src/auth.py"],
                        "systemic_impact": "Privilege checks are inconsistent across admin routes.",
                        "evidence_basis": "admin.py stopped calling require_admin before returning sensitive data.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is False
    expectation = result.expectation_results[0]
    assert expectation.best_candidate_issue_id == "issue-0007"
    assert expectation.best_candidate_file_path == "src/admin.py"
    assert expectation.failed_checks == ["issue_type"]


def test_evaluate_fixture_accepts_semantic_issue_type_aliases(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "field-rename-contract" / "fixture.json"
    )
    report_path = tmp_path / "field-rename-contract.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0010",
                        "file_path": "src/handlers.py",
                        "issue_type": "contract_mismatch",
                        "severity": "high",
                        "description": "Handler still reads display_name after serializer renamed the field to full_name.",
                        "context_scope": "cross_file",
                        "related_files": ["src/serializers.py"],
                        "systemic_impact": "Breaks callers expecting display_name in downstream payloads.",
                        "evidence_basis": "Serializer now emits full_name while handler still accesses display_name.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0010"


def test_evaluate_fixture_accepts_caching_issue_type_alias_for_performance(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "cache-invalidation-gap" / "fixture.json"
    )
    report_path = tmp_path / "cache-invalidation-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0011",
                        "file_path": "src/profile_service.py",
                        "issue_type": "caching",
                        "severity": "medium",
                        "description": "Profile updates do not invalidate the reader cache.",
                        "context_scope": "cross_file",
                        "related_files": ["src/cache.py"],
                        "systemic_impact": "Stale user profile reads may continue after updates.",
                        "evidence_basis": "update_user_profile changes persisted state while get_user_profile reads user_profile data from PROFILE_CACHE.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0011"


def test_evaluate_performance_fixture_matches_n_plus_one_query_loop(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "performance-n-plus-one-order-queries" / "fixture.json"
    )
    report_path = tmp_path / "performance-n-plus-one-order-queries.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-perf-0001",
                        "file_path": "src/order_service.py",
                        "issue_type": "performance",
                        "severity": "high",
                        "description": "The dashboard service issues one repository-backed query per order id instead of loading the rows in a batch.",
                        "context_scope": "cross_file",
                        "related_files": ["src/order_repository.py"],
                        "systemic_impact": "Request latency grows with the number of orders because each item adds another round trip.",
                        "evidence_basis": "build_dashboard_order_summaries calls fetch_order inside the for order_id loop, and fetch_order runs a query for each item.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-perf-0001"


def test_evaluate_performance_fixture_accepts_algorithmic_efficiency_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "performance-n-plus-one-order-queries" / "fixture.json"
    )
    report_path = tmp_path / "performance-n-plus-one-order-queries-alias.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-perf-0002",
                        "file_path": "src/order_service.py",
                        "issue_type": "algorithmic efficiency",
                        "severity": "high",
                        "description": "The helper adds one query per order instead of batching the load.",
                        "context_scope": "cross_file",
                        "related_files": ["src/order_repository.py"],
                        "systemic_impact": "Performance degradation grows with input size because every order adds another round trip.",
                        "evidence_basis": "fetch_order is called inside the for order_id loop and fetch_order executes the query.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-perf-0002"


def test_evaluate_fixture_accepts_exception_handling_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "error-handling-swallowed-import-failure" / "fixture.json"
    )
    report_path = tmp_path / "error-handling-swallowed-import-failure.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-err-0010",
                        "file_path": "src/import_job.py",
                        "issue_type": "exception-handling",
                        "severity": "high",
                        "description": "The import job swallows exceptions and still reports success to callers.",
                        "context_scope": "cross_file",
                        "related_files": ["src/import_controller.py"],
                        "systemic_impact": "Callers can surface a false success state after a failed import.",
                        "evidence_basis": "run_import uses except Exception and still returns status='completed'.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-err-0010"


def test_evaluate_fixture_accepts_except_exception_evidence_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "error-handling-swallowed-import-failure" / "fixture.json"
    )
    report_path = tmp_path / "error-handling-swallowed-import-failure-evidence.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-err-0011",
                        "file_path": "src/import_job.py",
                        "issue_type": "error_handling",
                        "severity": "high",
                        "description": "The import job catches a broad exception and still reports completion, so callers can treat a failed import as success.",
                        "context_scope": "cross_file",
                        "related_files": ["src/import_controller.py"],
                        "systemic_impact": "Operators can see a false success message even after the import failed.",
                        "evidence_basis": "run_import's except returns status 'completed' with count 0 while import_controller treats completed as success.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-err-0011"


def test_evaluate_fixture_accepts_user_profile_evidence_aliases(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "cache-invalidation-gap" / "fixture.json"
    )
    report_path = tmp_path / "cache-invalidation-gap-evidence.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012",
                        "file_path": "src/cache.py",
                        "issue_type": "cache_invalidation",
                        "severity": "medium",
                        "description": "Profile updates do not invalidate the cache.",
                        "context_scope": "cross_file",
                        "related_files": ["src/profile_service.py"],
                        "systemic_impact": "Stale profile reads may continue after updates.",
                        "evidence_basis": "profile_service.py updates profiles while get_user_profile and set_user_profile continue serving cached profile data.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012"


def test_evaluate_fixture_accepts_invalidation_description_keyword_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "cache-invalidation-gap" / "fixture.json"
    )
    report_path = tmp_path / "cache-invalidation-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012ca",
                        "file_path": "src/profile_service.py",
                        "issue_type": "caching",
                        "severity": "high",
                        "description": "Missing cache invalidation mechanism between the writer and cached reader.",
                        "context_scope": "cross_file",
                        "related_files": ["src/cache.py"],
                        "systemic_impact": "Stale user_profile data can reach callers.",
                        "evidence_basis": "update_user_profile writes state but cache.py keeps serving user_profile entries.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012ca"


def test_evaluate_fixture_accepts_issue_type_spacing_variants(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "diff-signature-break" / "fixture.json"
    )
    report_path = tmp_path / "diff-signature-break.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0010b",
                        "file_path": "src/user_service.py",
                        "issue_type": "API Contract",
                        "severity": "high",
                        "description": "tenant_id was added but callers were not updated.",
                        "context_scope": "cross_file",
                        "related_files": ["src/controller.py"],
                        "systemic_impact": "Existing callers will fail at runtime.",
                        "evidence_basis": "fetch_user now requires tenant_id but controller.py still uses the old call shape.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0010b"


def test_evaluate_fixture_accepts_issue_type_slash_variants(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "partial-refactor-callers" / "fixture.json"
    )
    report_path = tmp_path / "partial-refactor-callers.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0010c",
                        "file_path": "src/service.py",
                        "issue_type": "interface/contract violation",
                        "severity": "high",
                        "description": "The caller still expects result while the service now returns value.",
                        "context_scope": "cross_file",
                        "related_files": ["src/client.py"],
                        "systemic_impact": "Callers will break at runtime.",
                        "evidence_basis": "service.py returns value while client.py still reads result.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0010c"


def test_evaluate_fixture_accepts_caller_callee_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "field-rename-contract" / "fixture.json"
    )
    report_path = tmp_path / "field-rename-contract.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0010d",
                        "file_path": "src/handlers.py",
                        "issue_type": "caller/callee mismatch",
                        "severity": "high",
                        "description": "The handler still expects display_name while the serializer returns full_name.",
                        "context_scope": "cross_file",
                        "related_files": ["src/serializers.py"],
                        "systemic_impact": "Callers will fail at runtime.",
                        "evidence_basis": "handlers.py reads display_name while serializers.py returns full_name.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0010d"


def test_evaluate_fixture_accepts_integration_consistency_for_cache_performance(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "cache-invalidation-gap" / "fixture.json"
    )
    report_path = tmp_path / "cache-invalidation-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0010e",
                        "file_path": "src/cache.py",
                        "issue_type": "integration-consistency",
                        "severity": "high",
                        "description": "The cache layer is not invalidated when profile updates occur.",
                        "context_scope": "cross_file",
                        "related_files": ["src/profile_service.py", "src/cache.py"],
                        "systemic_impact": "Stale reads persist after profile updates.",
                        "evidence_basis": "update_user_profile never coordinates with set_user_profile for the same user_profile data.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0010e"


def test_evaluate_fixture_accepts_api_signature_break_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "diff-signature-break" / "fixture.json"
    )
    report_path = tmp_path / "diff-signature-break.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0010f",
                        "file_path": "src/user_service.py",
                        "issue_type": "API/Signature Break",
                        "severity": "high",
                        "description": "tenant_id was added and existing callers still use the old signature.",
                        "context_scope": "cross_file",
                        "related_files": ["src/controller.py"],
                        "systemic_impact": "Call flows will fail at runtime.",
                        "evidence_basis": "controller.py still omits tenant_id when calling fetch_user.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0010f"


def test_evaluate_fixture_accepts_semantic_systemic_impact_aliases(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "field-rename-contract" / "fixture.json"
    )
    report_path = tmp_path / "field-rename-contract.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0011",
                        "file_path": "src/handlers.py",
                        "issue_type": "contract_mismatch",
                        "severity": "high",
                        "description": "Handler still reads display_name after serializer renamed the field to full_name.",
                        "context_scope": "cross_file",
                        "related_files": ["src/serializers.py"],
                        "systemic_impact": "Downstream payload consumers continue reading the old field name.",
                        "evidence_basis": "Serializer now emits full_name while handler still accesses display_name.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0011"


def test_evaluate_fixture_accepts_semantic_evidence_basis_aliases(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "architectural-layer-leak" / "fixture.json"
    )
    report_path = tmp_path / "architectural-layer-leak.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012",
                        "file_path": "src/controller.py",
                        "issue_type": "layer-leakage",
                        "severity": "medium",
                        "description": "Architecture violation in request flow.",
                        "context_scope": "project",
                        "related_files": ["src/service.py", "src/database.py"],
                        "systemic_impact": "Dependency direction between layers becomes inconsistent.",
                        "evidence_basis": "controller.py imports the database helper directly even though service.py already owns that access pattern.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012"


def test_evaluate_fixture_accepts_layering_violation_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "architectural-layer-leak" / "fixture.json"
    )
    report_path = tmp_path / "architectural-layer-leak.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012a",
                        "file_path": "src/controller.py",
                        "issue_type": "layering_violation",
                        "severity": "high",
                        "description": "Controller reaches into the database layer directly.",
                        "context_scope": "project",
                        "related_files": ["src/service.py", "src/db.py"],
                        "systemic_impact": "Layer boundaries are bypassed.",
                        "evidence_basis": "controller.py imports execute_query even though service.py owns that access.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012a"


def test_evaluate_fixture_accepts_layer_separation_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "architectural-layer-leak" / "fixture.json"
    )
    report_path = tmp_path / "architectural-layer-leak.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012aa",
                        "file_path": "src/controller.py",
                        "issue_type": "layer-separation",
                        "severity": "high",
                        "description": "The controller bypasses the service layer and reaches the database directly.",
                        "context_scope": "project",
                        "related_files": ["src/service.py", "src/db.py"],
                        "systemic_impact": "Layer boundaries are broken.",
                        "evidence_basis": "controller.py imports db.py directly instead of delegating through service.py.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012aa"


def test_evaluate_fixture_accepts_execute_query_as_db_evidence_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "architectural-layer-leak" / "fixture.json"
    )
    report_path = tmp_path / "architectural-layer-leak.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012b",
                        "file_path": "src/controller.py",
                        "issue_type": "architecture",
                        "severity": "high",
                        "description": "Controller bypasses the service layer and talks to the database directly.",
                        "context_scope": "project",
                        "related_files": ["src/service.py"],
                        "systemic_impact": "Layering boundaries are broken.",
                        "evidence_basis": "orders_page calls execute_query directly even though service.list_orders exists.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012b"


def test_evaluate_architecture_fixture_matches_controller_repository_bypass(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "architectural-service-web-context-leak" / "fixture.json"
    )
    report_path = tmp_path / "architectural-service-web-context-leak.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012c",
                        "file_path": "src/web/orders_controller.py",
                        "issue_type": "architecture",
                        "severity": "high",
                        "description": "The controller bypasses the service layer and reaches order_repository.py directly instead of delegating through order_service.py.",
                        "context_scope": "project",
                        "related_files": ["src/services/order_service.py", "src/repositories/order_repository.py"],
                        "systemic_impact": "Layer boundaries become inconsistent because controllers now couple directly to persistence-facing modules instead of the service boundary.",
                        "evidence_basis": "orders_controller.py imports order_repository.py directly even though order_service.py owns the orders workflow.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012c"


def test_evaluate_fixture_accepts_transactional_safety_pipe_delimited_issue_type(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "transaction-split" / "fixture.json"
    )
    report_path = tmp_path / "transaction-split.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012e",
                        "file_path": "src/service.py",
                        "issue_type": "encapsulation|transactional-safety",
                        "severity": "high",
                        "description": "The transaction wrapper is bypassed and partial writes are possible.",
                        "context_scope": "cross_file",
                        "related_files": ["src/repository.py"],
                        "systemic_impact": "Partial writes can escape the repository transaction boundary.",
                        "evidence_basis": "place_order bypasses save_order, which owns the begin/commit sequence.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012e"


def test_evaluate_fixture_accepts_transaction_boundary_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "transaction-split" / "fixture.json"
    )
    report_path = tmp_path / "transaction-split.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012ea",
                        "file_path": "src/service.py",
                        "issue_type": "transaction_boundary",
                        "severity": "high",
                        "description": "The service bypasses the transaction wrapper and partial writes are possible.",
                        "context_scope": "cross_file",
                        "related_files": ["src/repository.py"],
                        "systemic_impact": "Partial writes can escape the repository transaction boundary.",
                        "evidence_basis": "place_order bypasses save_order and the begin/commit sequence.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012ea"


def test_evaluate_fixture_accepts_api_mismatch_issue_type_variants(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "partial-refactor-callers" / "fixture.json"
    )
    report_path = tmp_path / "partial-refactor-callers.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012f",
                        "file_path": "src/client.py",
                        "issue_type": "API mismatch / runtime error",
                        "severity": "high",
                        "description": "The client still expects result while the service returns value.",
                        "context_scope": "cross_file",
                        "related_files": ["src/service.py"],
                        "systemic_impact": "Any downstream code expecting the old response key will fail.",
                        "evidence_basis": "service.py returns value while client.py still reads result.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012f"


def test_evaluate_fixture_accepts_downstream_code_as_callers_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "field-rename-contract" / "fixture.json"
    )
    report_path = tmp_path / "field-rename-contract.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012g",
                        "file_path": "src/handlers.py",
                        "issue_type": "caller/callee mismatch",
                        "severity": "high",
                        "description": "The serializer and handler now disagree on the exported field name.",
                        "context_scope": "cross_file",
                        "related_files": ["src/serializers.py"],
                        "systemic_impact": "Any downstream code expecting display_name will fail at runtime.",
                        "evidence_basis": "serialize_user returns full_name while the handler still reads display_name.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012g"


def test_evaluate_fixture_accepts_tool_mode_envelope_with_top_level_issues(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "diff-signature-break" / "fixture.json"
    )
    report_path = tmp_path / "diff-signature-break.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "no_issues",
                "report": None,
                "issues": [],
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is False
    assert result.missing_report is False
    assert result.expectation_results[0].reason == "No issue matched the expected holistic finding"


def test_evaluate_fixture_accepts_multilingual_semantic_matches(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "architectural-layer-leak" / "fixture.json"
    )
    report_path = tmp_path / "architectural-layer-leak.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0013",
                        "file_path": "src/controller.py",
                        "issue_type": "layer-leak",
                        "severity": "high",
                        "description": "コントローラーがデータベース関数を直接呼び出している。",
                        "context_scope": "project",
                        "related_files": ["src/service.py"],
                        "systemic_impact": "レイヤー間の依存関係ルールが破られます。",
                        "evidence_basis": "controller.py が db.py を直接インポートしており、service.py を経由していません。",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0013"


def test_evaluate_fixture_accepts_expected_related_file_in_primary_file_path(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "cache-invalidation-gap" / "fixture.json"
    )
    report_path = tmp_path / "cache-invalidation-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0014",
                        "file_path": "src/cache.py",
                        "issue_type": "cache_invalidation",
                        "severity": "high",
                        "description": "Cache entries are never invalidated after profile updates.",
                        "context_scope": "cross_file",
                        "related_files": ["src/profile_service.py"],
                        "systemic_impact": "Stale cache entries can be served after writes.",
                        "evidence_basis": "profile_service.update_user_profile changes stored data while cache.py only provides set/get helpers for user_profile.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0014"


def test_evaluate_fixture_accepts_unvalidated_semantic_aliases(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "validation-drift" / "fixture.json"
    )
    report_path = tmp_path / "validation-drift.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0015",
                        "file_path": "src/validation.py",
                        "issue_type": "input validation",
                        "severity": "high",
                        "description": "Validation no longer enforces email even though the API depends on it.",
                        "context_scope": "cross_file",
                        "related_files": ["src/api.py"],
                        "systemic_impact": "Malformed input can proceed into request handling and trigger runtime failures.",
                        "evidence_basis": "api.py reads payload['email'] while validation.py only validates username and password.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0015"


def test_evaluate_fixture_accepts_validation_runtime_error_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "validation-drift" / "fixture.json"
    )
    report_path = tmp_path / "validation-drift-2.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0016",
                        "file_path": "src/api.py",
                        "issue_type": "input validation / runtime error",
                        "severity": "high",
                        "description": "create_account depends on email that validation no longer enforces in validate_signup.",
                        "context_scope": "cross_file",
                        "related_files": ["src/validation.py"],
                        "systemic_impact": "Runtime crashes occur when requests proceed without email.",
                        "evidence_basis": "api.py indexes payload['email'] while validation.py does not require email.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0016"


def test_evaluate_fixture_accepts_validation_issue_type_alias_for_security(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "validation-drift" / "fixture.json"
    )
    report_path = tmp_path / "validation-drift-3.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0017",
                        "file_path": "src/api.py",
                        "issue_type": "validation",
                        "severity": "high",
                        "description": "create_account consumes email even though validate_signup does not enforce it.",
                        "context_scope": "cross_file",
                        "related_files": ["src/validation.py"],
                        "systemic_impact": "Unvalidated input can proceed without email and trigger runtime failures.",
                        "evidence_basis": "api.py reads payload['email'] while validation.py does not validate it.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0017"


def test_cli_single_fixture_returns_success_for_matching_report(tmp_path, capsys):
    report_path = tmp_path / "single.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "file_path": "src/admin.py",
                        "issue_type": "security",
                        "severity": "high",
                        "description": "The admin endpoint bypasses the admin guard by skipping require_admin and accepts any authenticated user.",
                        "context_scope": "cross_file",
                        "related_files": ["src/auth.py"],
                        "systemic_impact": "Privilege checks are inconsistent across admin routes.",
                        "evidence_basis": "admin.py stopped calling require_admin before returning sensitive data.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = benchmarking.main(
        [
            "--fixtures-root",
            str(FIXTURES_ROOT),
            "--fixture",
            "auth-guard-regression",
            "--report-file",
            str(report_path),
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["fixtures_passed"] == 1
    assert payload["results"][0]["fixture_id"] == "auth-guard-regression"