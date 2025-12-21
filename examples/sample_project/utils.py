"""
Utility functions with maintainability issues.
"""


# MAINTAINABILITY ISSUE: Complex nested conditions
def check_eligibility(age, income, credit_score, employment_status, has_collateral):
    if age >= 18:
        if income > 30000:
            if credit_score > 600:
                if employment_status == "employed":
                    if has_collateral:
                        return "approved"
                    else:
                        if credit_score > 700:
                            return "approved"
                        else:
                            return "rejected"
                else:
                    return "rejected"
            else:
                return "rejected"
        else:
            return "rejected"
    else:
        return "rejected"


# MAINTAINABILITY ISSUE: Very long function
def process_order(order_id, customer_id, items, shipping_address, billing_address, payment_method, discount_code, gift_wrap, priority_shipping):
    # Validate order
    if not order_id:
        return {"error": "Invalid order ID"}
    if not customer_id:
        return {"error": "Invalid customer ID"}
    if not items or len(items) == 0:
        return {"error": "No items in order"}
    
    # Calculate totals
    subtotal = 0
    for item in items:
        subtotal += item['price'] * item['quantity']
    
    # Apply discount
    discount = 0
    if discount_code == "SAVE10":
        discount = subtotal * 0.1
    elif discount_code == "SAVE20":
        discount = subtotal * 0.2
    elif discount_code == "SAVE30":
        discount = subtotal * 0.3
    
    # Calculate shipping
    shipping_cost = 0
    if priority_shipping:
        shipping_cost = 25.00
    else:
        shipping_cost = 10.00
    
    # Add gift wrap
    if gift_wrap:
        shipping_cost += 5.00
    
    # Calculate tax
    tax = (subtotal - discount) * 0.08
    
    # Calculate total
    total = subtotal - discount + shipping_cost + tax
    
    # Process payment
    payment_result = process_payment(payment_method, total)
    
    # Update inventory
    for item in items:
        update_inventory(item['id'], item['quantity'])
    
    # Send confirmation email
    send_email(customer_id, order_id, total)
    
    # Generate invoice
    invoice = generate_invoice(order_id, items, total)
    
    # Return result
    return {
        "order_id": order_id,
        "total": total,
        "invoice": invoice,
        "payment": payment_result
    }


def process_payment(method, amount):
    return {"status": "success"}


def update_inventory(item_id, quantity):
    pass


def send_email(customer, order, total):
    pass


def generate_invoice(order, items, total):
    return f"Invoice for {order}"


# MAINTAINABILITY ISSUE: Single letter variable names
def p(a, b, c):
    x = a + b
    y = x * c
    z = y / 2
    return z
