# src/aicodereviewer/auth.py
import keyring

SERVICE_NAME = "AICodeReviewer"

def get_profile_name():
    """
    保存されているAWSプロファイル名を取得します。
    なければユーザーに入力を促します。
    """
    profile = keyring.get_password(SERVICE_NAME, "aws_profile")

    if not profile:
        print("--- AICodeReviewer 初期設定 ---")
        print("AWS IAM Identity Centerのプロファイル名を入力してください。")
        print("(例: 'default'。設定していない場合は 'aws configure sso' を先に実行してください)")
        
        profile = input("プロファイル名: ").strip()
        if not profile:
            profile = "default"
            
        keyring.set_password(SERVICE_NAME, "aws_profile", profile)
        print(f"プロファイル '{profile}' を保存しました。\n")

    return profile

def clear_settings():
    try:
        keyring.delete_password(SERVICE_NAME, "aws_profile")
        print("設定をクリアしました。")
    except:
        pass
