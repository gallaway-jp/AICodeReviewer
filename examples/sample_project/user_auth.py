"""
User authentication module with intentional security vulnerabilities.
"""
import pickle
import hashlib
import sqlite3


class UserAuth:
    def __init__(self, db_path="users.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
    
    def login(self, username, password):
        """Authenticate user - SECURITY ISSUE: SQL injection vulnerability"""
        query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
        self.cursor.execute(query)
        result = self.cursor.fetchone()
        return result is not None
    
    def hash_password(self, password):
        """Hash password - SECURITY ISSUE: Using weak MD5 hash"""
        return hashlib.md5(password.encode()).hexdigest()
    
    def load_user_data(self, data_file):
        """Load user data - SECURITY ISSUE: Unsafe pickle deserialization"""
        with open(data_file, 'rb') as f:
            user_data = pickle.load(f)
        return user_data
    
    def create_session(self, username):
        """Create session - SECURITY ISSUE: No session token randomness"""
        session_id = username + "_session"
        return session_id
    
    def check_admin(self, username):
        """Check if user is admin - SECURITY ISSUE: Hardcoded credentials"""
        admin_password = "admin123"
        if username == "admin" and self.get_password(username) == admin_password:
            return True
        return False
    
    def get_password(self, username):
        """Get password from DB"""
        query = f"SELECT password FROM users WHERE username='{username}'"
        self.cursor.execute(query)
        result = self.cursor.fetchone()
        return result[0] if result else None
