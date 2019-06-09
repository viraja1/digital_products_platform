import os
import json
import time
import random
import sqlite3

import requests
from flask import Flask, request, render_template, redirect

app = Flask(__name__)
conn = None
BASE_URL = 'http://localhost'
PORT = 5000

OPENNODE_BASE_URL = 'https://dev-api.opennode.co/v1/'
OPENNODE_API_KEY = os.environ['OPENNODE_API_KEY']
OPENNODE_REDIRECT_BASE_URL = 'https://dev-checkout.opennode.co/'
OPENNODE_HEADERS = {
    'Authorization': OPENNODE_API_KEY,
    'content-type': 'application/json'
}

ORDER_SUCCESS_REDIRECT_URL = '{}:{}/order_success/'.format(BASE_URL, PORT)
PRODUCTS = json.loads(open("products.json", "r").read())


def get_db_connection():
    db_file = "./orders.db"
    global conn
    if conn is None:
        conn = sqlite3.connect(db_file, check_same_thread=False)
        create_table()
    return conn


def create_table():
    try:
        connection = get_db_connection()
        c = connection.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS Orders (order_id, transaction_id, amount, product_id, product_name)')
        connection.commit()
    except Exception:
        pass


def create_order_entry(order_id, transaction_id, amount, product_id, product_name):
    connection = get_db_connection()
    c = connection.cursor()
    c.execute('INSERT INTO Orders(order_id, transaction_id, amount, product_id, product_name) values(?, ?, ?, ?, ?)',
              (order_id, transaction_id, amount, product_id, product_name))
    connection.commit()


def get_order_details(order_id):
    connection = get_db_connection()
    c = connection.cursor()
    results = c.execute('Select * from Orders where order_id={}'.format(order_id)).fetchall()
    return {"transaction_id": results[0][1], "product_id": results[0][3]}


def get_product_details(product_id):
    product_details = {}
    for product in PRODUCTS:
        if int(product.get("id")) == int(product_id):
            product_details = product
    return product_details


def create_invoice(order_id, amount, description, product_id):
    data = {
        'description': description,
        'amount': amount,
        'currency': 'USD',
        'order_id': order_id,
        'success_url': '{}?order_id={}&product_id={}'.format(ORDER_SUCCESS_REDIRECT_URL, order_id, product_id)
    }
    response = requests.post(
        url="{}charges".format(OPENNODE_BASE_URL),
        headers=OPENNODE_HEADERS,
        data=json.dumps(data)
    )
    return response.json()


def get_transaction_details(transaction_id):
    response = requests.get(
        url="{}charge/{}".format(OPENNODE_BASE_URL, transaction_id),
        headers=OPENNODE_HEADERS
    )
    return response.json()


@app.route("/api/v1/create_order/", methods=['POST'])
def create_order_api():
    try:
        data = request.json
        order_id = int(time.time() * 1000000) + random.randint(1000000, 9999999)
        product_id = data["product_id"]
        amount = data["amount"]
        product_name = data["product_name"]
        invoice_details = create_invoice(order_id=order_id, amount=amount, description=product_name,
                                         product_id=product_id)
        transaction_id = invoice_details["data"]["id"]
        create_order_entry(order_id=order_id, transaction_id=transaction_id, amount=amount, product_id=product_id,
                           product_name=product_name)
        response = {
            'redirect_url': '{}{}'.format(OPENNODE_REDIRECT_BASE_URL, transaction_id)
        }
    except Exception as e:
        response = {"error": str(e)}
        return app.response_class(
            response=json.dumps(response),
            status=500,
            mimetype='application/json'
        )
    return app.response_class(
        response=json.dumps(response),
        status=200,
        mimetype='application/json'
    )


@app.route("/order_success/", methods=['GET'])
def order_success():
    try:
        order_id = request.args.get('order_id')
        product_id = request.args.get('product_id')
        order_details = get_order_details(order_id=order_id)
        if order_details.get("product_id") != product_id:
            raise ValueError("invalid product id")
        transaction_id = order_details["transaction_id"]
        transaction_details = get_transaction_details(transaction_id=transaction_id)
        if transaction_details.get("data", {}).get("status") not in ["paid", "processing"]:
            raise ValueError("invalid transaction status")
        product_details = get_product_details(product_id=product_id)
        product_details["order_id"] = order_id
    except Exception:
        return redirect("/")
    return render_template('order_success.html', product=product_details)


@app.route("/", methods=['GET'])
def home():
    return render_template('index.html', products=PRODUCTS)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
