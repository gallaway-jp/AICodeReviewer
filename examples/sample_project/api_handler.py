"""
API handler with error handling issues.
"""
import requests
import json


class APIHandler:
    def __init__(self, base_url):
        self.base_url = base_url
    
    def fetch_data(self, endpoint):
        """ERROR HANDLING ISSUE: No exception handling"""
        response = requests.get(f"{self.base_url}/{endpoint}")
        return response.json()
    
    def process_response(self, data):
        """ERROR HANDLING ISSUE: Assuming data structure without validation"""
        user_id = data['user']['id']
        user_name = data['user']['profile']['name']
        return f"User {user_id}: {user_name}"
    
    def save_to_file(self, data, filename):
        """ERROR HANDLING ISSUE: File operations without try-catch"""
        with open(filename, 'w') as f:
            json.dump(data, f)
    
    def parse_config(self, config_str):
        """ERROR HANDLING ISSUE: No validation of input"""
        config = json.loads(config_str)
        return config['database']['connection_string']
    
    def connect_to_service(self, retries=3):
        """ERROR HANDLING ISSUE: Bare except clause"""
        for i in range(retries):
            try:
                result = self.fetch_data("status")
                return result
            except:  # ISSUE: Catching all exceptions
                pass
        return None
    
    def calculate_total(self, items):
        """ERROR HANDLING ISSUE: No validation of list items"""
        total = 0
        for item in items:
            total += item['price'] * item['quantity']
        return total
