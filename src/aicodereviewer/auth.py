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

def set_profile_name(new_profile=None):
    """
    AWSプロファイル名を設定または変更します。
    """
    if new_profile is None:
        print("--- AWSプロファイル設定 ---")
        print("現在のプロファイル名を入力してください。")
        print("(例: 'default'。設定していない場合は 'aws configure sso' を先に実行してください)")
        
        new_profile = input("プロファイル名: ").strip()
        if not new_profile:
            new_profile = "default"
    
    keyring.set_password(SERVICE_NAME, "aws_profile", new_profile)
    print(f"プロファイル '{new_profile}' を保存しました。")
    return new_profile

def clear_profile():
    """
    保存されているAWSプロファイル名を削除します。
    """
    try:
        keyring.delete_password(SERVICE_NAME, "aws_profile")
        print("AWSプロファイルを削除しました。")
    except Exception as e:
        print(f"プロファイル削除エラー: {e}")
