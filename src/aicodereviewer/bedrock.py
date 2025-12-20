# src/aicodereviewer/bedrock.py
import boto3
from botocore.exceptions import ClientError, ProfileNotFound, TokenRetrievalError

class BedrockClient:
    def __init__(self, profile_name, region="us-east-1"):
        try:
            # プロファイル名を使用してセッションを作成
            self.session = boto3.Session(profile_name=profile_name, region_name=region)
            self.client = self.session.client("bedrock-runtime")
            self.model_id = "anthropic.claude-3-5-sonnet-20240620-v1:0"
        except ProfileNotFound:
            raise Exception(f"AWSプロファイル '{profile_name}' が見つかりません。")

    def get_review(self, code_content, review_type="security", lang="en"):
        """
        Runs a review with a specific persona and language instruction.
        """
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
            "security": "You are a Security Auditor. Analyze code for vulnerabilities.",
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
            "architecture": "You are a Software Architect. Review code structure, design patterns, and architectural decisions."
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
            return response["output"]["message"]["content"][0]["text"]
        except Exception as e:
            return f"Error: {str(e)}"
