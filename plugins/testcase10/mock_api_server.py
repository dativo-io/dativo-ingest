from flask import Flask, jsonify
app = Flask(__name__)

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/data')
def data():
    return jsonify([
        {"id": 1, "name": "Product A", "price": 29.99},
        {"id": 2, "name": "Product B", "price": 49.99},
        {"id": 3, "name": "Product C", "price": 19.99}
    ])

if __name__ == '__main__':
    app.run(port=8080)
