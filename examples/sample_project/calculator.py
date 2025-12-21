"""
Calculator module with best practices violations.
"""

# BEST PRACTICES ISSUE: Magic numbers without constants
def calculate_tax(amount):
    return amount * 0.175


# BEST PRACTICES ISSUE: Poor naming
def f(x, y):
    return x + y


class calc:  # BEST PRACTICES ISSUE: Class name not PascalCase
    def __init__(self):
        self.val = 0  # BEST PRACTICES ISSUE: Unclear variable name
    
    # BEST PRACTICES ISSUE: Method doing too many things
    def doEverything(self, a, b, c):
        result1 = a + b
        result2 = result1 * c
        result3 = result2 / 2
        result4 = result3 ** 2
        self.val = result4
        print(result4)  # BEST PRACTICES ISSUE: Side effect in calculation
        return result4
    
    # BEST PRACTICES ISSUE: Duplicate code
    def calculate_area_rectangle(self, width, height):
        if width < 0 or height < 0:
            return 0
        area = width * height
        print(f"Area: {area}")
        return area
    
    def calculate_area_triangle(self, base, height):
        if base < 0 or height < 0:
            return 0
        area = base * height / 2
        print(f"Area: {area}")
        return area


# BEST PRACTICES ISSUE: Global mutable state
global_counter = 0

def increment_counter():
    global global_counter
    global_counter += 1
    return global_counter


# BEST PRACTICES ISSUE: Function with too many parameters
def create_user(name, email, age, address, phone, city, state, zip_code, country, occupation):
    user = {
        'name': name,
        'email': email,
        'age': age,
        'address': address,
        'phone': phone,
        'city': city,
        'state': state,
        'zip': zip_code,
        'country': country,
        'occupation': occupation
    }
    return user


# BEST PRACTICES ISSUE: No error handling
def divide(a, b):
    return a / b
