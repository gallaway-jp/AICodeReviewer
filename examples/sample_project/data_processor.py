"""
Data processing module with intentional performance issues.
"""
import time


class DataProcessor:
    def __init__(self):
        self.data = []
    
    def process_large_dataset(self, items):
        """PERFORMANCE ISSUE: Multiple string concatenations in loop"""
        result = ""
        for item in items:
            result = result + str(item) + ","
        return result
    
    def find_duplicates(self, numbers):
        """PERFORMANCE ISSUE: Nested loops with O(n²) complexity"""
        duplicates = []
        for i in range(len(numbers)):
            for j in range(len(numbers)):
                if i != j and numbers[i] == numbers[j]:
                    if numbers[i] not in duplicates:
                        duplicates.append(numbers[i])
        return duplicates
    
    def load_config(self):
        """PERFORMANCE ISSUE: File I/O in loop"""
        configs = []
        for i in range(100):
            with open('config.txt', 'r') as f:
                config = f.read()
                configs.append(config)
        return configs
    
    def calculate_stats(self, data_list):
        """PERFORMANCE ISSUE: Inefficient list operations"""
        # Create new list in every iteration
        result = []
        for item in data_list:
            temp_list = []
            for i in range(1000):
                temp_list.append(i)
            result.append(sum(temp_list) + item)
        return result
    
    def filter_data(self, data):
        """PERFORMANCE ISSUE: Multiple passes over data"""
        # First pass
        filtered = []
        for item in data:
            if item > 0:
                filtered.append(item)
        
        # Second pass
        doubled = []
        for item in filtered:
            doubled.append(item * 2)
        
        # Third pass
        result = []
        for item in doubled:
            if item < 1000:
                result.append(item)
        
        return result
    
    def wait_for_data(self):
        """PERFORMANCE ISSUE: Blocking sleep instead of async"""
        time.sleep(5)
        return "Data ready"
