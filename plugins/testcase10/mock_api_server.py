from flask import Flask, jsonify
app = Flask(__name__)

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/data')
def data():
    return jsonify([
        {"product_id": 1, "product_name": "Product A", "price": 29.99, "category": "Electronics", "in_stock": True},
        {"product_id": 2, "product_name": "Product B", "price": 49.99, "category": "Electronics", "in_stock": True},
        {"product_id": 3, "product_name": "Product C", "price": 19.99, "category": "Home", "in_stock": False}
    ])

if __name__ == '__main__':
    app.run(port=8080)
