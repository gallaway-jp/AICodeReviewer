# src/aicodereviewer/bedrock.py
import boto3
import time
from botocore.exceptions import ClientError, ProfileNotFound, TokenRetrievalError

class BedrockClient:
    def __init__(self, profile_name, region="us-east-1"):
        try:
            # プロファイル名を使用してセッションを作成
            self.session = boto3.Session(profile_name=profile_name, region_name=region)
            self.client = self.session.client("bedrock-runtime")
            self.model_id = "anthropic.claude-3-5-sonnet-20240620-v1:0"
            # Rate limiting: max 10 requests per minute
            self.last_request_time = 0
            self.min_request_interval = 6  # seconds
        except ProfileNotFound:
            raise Exception(f"AWSプロファイル '{profile_name}' が見つかりません。")

    def get_review(self, code_content, review_type="security", lang="en"):
        """
        Runs a review with a specific persona and language instruction.
        """
        # Rate limiting
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last_request
            time.sleep(sleep_time)
        
        try:
            # セッションが有効か確認するために呼び出し
            response = self.client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": "Hello"}]}], # 接続確認用
                inferenceConfig={"maxTokens": 1}
            )
        except (TokenRetrievalError, ClientError):
            raise Exception("AWSログインの期限が切れています。'aws sso login --profile <プロファイル名>' を実行してください。")

        prompts = {
            "security": "You are a Senior Security Auditor and Penetration Tester. Conduct a comprehensive security analysis focusing on:\n\nCRITICAL VULNERABILITIES:\n- Injection attacks (SQL, NoSQL, Command, LDAP, XPath)\n- Broken Authentication & Session Management\n- Cross-Site Scripting (XSS) vulnerabilities\n- Insecure Direct Object References\n- Security Misconfigurations\n- Sensitive Data Exposure\n- Missing Function Level Access Control\n- Cross-Site Request Forgery (CSRF)\n- Known Vulnerable Components\n- Unvalidated Redirects & Forwards\n\nCODE SECURITY PATTERNS:\n- Input validation and sanitization\n- Authentication and authorization mechanisms\n- Session management security\n- Error handling that doesn't leak sensitive information\n- Secure password storage (proper hashing)\n- HTTPS/TLS usage and certificate validation\n- Secure random number generation\n- File upload security\n- API security (rate limiting, authentication)\n\nLANGUAGE-SPECIFIC CONCERNS:\n- Buffer overflows and memory safety (C/C++/Rust)\n- Type safety and injection prevention\n- Framework-specific vulnerabilities\n- Third-party library security\n\nProvide specific recommendations with severity levels (Critical/High/Medium/Low) and actionable fixes.",
            "performance": "You are a Performance Engineer. Optimize efficiency and resources.",
            "best_practices": "You are a Lead Developer. Review for clean code and SOLID principles.",
            "maintainability": "You are a Code Maintenance Expert. Analyze code for readability, maintainability, and long-term sustainability.",
            "documentation": "You are a Technical Writer. Review code documentation, comments, and docstrings for clarity and completeness.",
            "testing": "You are a QA Engineer. Analyze code for testability, identify missing test cases, and suggest testing improvements.",
            "accessibility": "You are an Accessibility Specialist. Review code for accessibility compliance and inclusive design principles.",
            "scalability": "You are a System Architect. Analyze code for scalability, concurrency, and resource management.",
            "compatibility": "You are a Platform Engineer. Review code for cross-platform compatibility, version compatibility, and portability.",
            "error_handling": "You are a Reliability Engineer. Analyze error handling, exception management, and fault tolerance.",
            "complexity": "You are a Code Analyst. Evaluate code complexity, cyclomatic complexity, and suggest simplifications.",
            "architecture": "You are a Software Architect. Review code structure, design patterns, and architectural decisions.",
            "license": "You are a License Compliance Specialist. Review third-party library usage, check for appropriate licenses, ensure license compatibility, and verify proper attribution.",
            "fix": "You are an expert code fixer. Fix the code issues identified in the feedback. Return only the corrected code without explanations."
        }

        base_prompt = prompts.get(review_type, prompts["best_practices"])
        
        # Add language instruction
        if lang == "ja":
            lang_instruction = "IMPORTANT: Provide your entire response in Japanese (日本語で回答してください)."
        else:
            lang_instruction = "IMPORTANT: Provide your entire response in English."

        system_msg = f"{base_prompt} {lang_instruction}"
        
        messages = [{
            "role": "user",
            "content": [{"text": f"Review this code:\n\n{code_content}"}]
        }]

        try:
            response = self.client.converse(
                modelId=self.model_id,
                messages=messages,
                system=[{"text": system_msg}],
                inferenceConfig={"maxTokens": 2000, "temperature": 0.1}
            )
            self.last_request_time = time.time()  # Update timestamp after successful request
            return response["output"]["message"]["content"][0]["text"]
        except Exception as e:
            return f"Error: {str(e)}"
