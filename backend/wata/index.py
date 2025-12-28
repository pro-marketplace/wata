"""
WATA Payment Extension - Create Payment Link
"""
import json
import os
import httpx
import psycopg2
import random
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional


@dataclass
class WATAPaymentParams:
    """Parameters for WATA payment."""
    amount: float
    currency: str = "RUB"
    order_id: Optional[str] = None
    description: Optional[str] = None
    success_redirect_url: Optional[str] = None
    fail_redirect_url: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    expires_in_hours: int = 24


def get_db_connection():
    """Get database connection."""
    dsn = os.environ.get('DATABASE_URL')
    if not dsn:
        raise ValueError('DATABASE_URL not configured')
    return psycopg2.connect(dsn)


HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-User-Id, X-Session-Id, X-Auth-Token',
    'Access-Control-Max-Age': '86400',
    'Content-Type': 'application/json'
}

WATA_API_URL = 'https://api.wata.pro/api/h2h'


def handler(event: dict, context) -> dict:
    """
    Create order and generate WATA payment link.
    POST body: amount, user_name, user_email, user_phone, user_address, cart_items
    Returns: payment_url, order_id, order_number
    """
    method = event.get('httpMethod', 'GET').upper()

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': HEADERS, 'body': '', 'isBase64Encoded': False}

    if method != 'POST':
        return {'statusCode': 405, 'headers': HEADERS, 'body': json.dumps({'error': 'Method not allowed'}), 'isBase64Encoded': False}

    wata_token = os.environ.get('WATA_API_TOKEN')
    if not wata_token:
        return {'statusCode': 500, 'headers': HEADERS, 'body': json.dumps({'error': 'WATA credentials not configured'}), 'isBase64Encoded': False}

    body_str = event.get('body', '{}')
    payload = json.loads(body_str)

    amount = float(payload.get('amount', 0))
    user_name = str(payload.get('user_name', ''))
    user_email = str(payload.get('user_email', ''))
    user_phone = str(payload.get('user_phone', ''))
    user_address = str(payload.get('user_address', ''))
    order_comment = str(payload.get('order_comment', ''))
    cart_items = payload.get('cart_items', [])
    success_url = str(payload.get('success_url', ''))
    fail_url = str(payload.get('fail_url', ''))

    if amount <= 0:
        return {'statusCode': 400, 'headers': HEADERS, 'body': json.dumps({'error': 'Amount must be greater than 0'}), 'isBase64Encoded': False}
    if not user_name or not user_email:
        return {'statusCode': 400, 'headers': HEADERS, 'body': json.dumps({'error': 'user_name and user_email required'}), 'isBase64Encoded': False}

    conn = get_db_connection()
    cur = conn.cursor()

    # Generate unique order ID
    for _ in range(10):
        wata_order_id = random.randint(100000, 2147483647)
        cur.execute("SELECT COUNT(*) FROM orders WHERE wata_order_id = %s", (wata_order_id,))
        if cur.fetchone()[0] == 0:
            break

    order_number = f"ORD-{datetime.now().strftime('%Y%m%d')}-{wata_order_id}"

    cur.execute("""
        INSERT INTO orders (order_number, user_name, user_email, user_phone, amount, wata_order_id, status, delivery_address, order_comment)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (order_number, user_name, user_email, user_phone, round(amount, 2), wata_order_id, 'pending', user_address, order_comment))

    order_id = cur.fetchone()[0]

    for item in cart_items:
        cur.execute("""
            INSERT INTO order_items (order_id, product_id, product_name, product_price, quantity)
            VALUES (%s, %s, %s, %s, %s)
        """, (order_id, item.get('id'), item.get('name'), item.get('price'), item.get('quantity')))

    # Create WATA payment link
    expiration_time = datetime.utcnow() + timedelta(hours=24)

    request_data = {
        "amount": amount,
        "currency": "RUB",
        "orderId": str(wata_order_id),
        "description": f"Order {order_number}",
        "expirationDateTime": expiration_time.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
    }

    if success_url:
        request_data["successRedirectUrl"] = success_url
    if fail_url:
        request_data["failRedirectUrl"] = fail_url
    if user_email:
        request_data["customerEmail"] = user_email
    if user_phone:
        request_data["customerPhone"] = user_phone

    # Make request to WATA API
    with httpx.Client() as client:
        response = client.post(
            f"{WATA_API_URL}/links",
            json=request_data,
            headers={
                "Authorization": f"Bearer {wata_token}",
                "Content-Type": "application/json",
            },
            timeout=60,
        )

        if response.status_code != 200:
            cur.close()
            conn.close()
            return {
                'statusCode': 500,
                'headers': HEADERS,
                'body': json.dumps({'error': f'WATA API error: {response.text}'}),
                'isBase64Encoded': False
            }

        data = response.json()
        payment_url = data.get("paymentUrl") or data.get("url")
        wata_transaction_id = data.get("id")

        if not payment_url:
            cur.close()
            conn.close()
            return {
                'statusCode': 500,
                'headers': HEADERS,
                'body': json.dumps({'error': 'Invalid response from WATA API'}),
                'isBase64Encoded': False
            }

    cur.execute("UPDATE orders SET payment_url = %s, wata_transaction_id = %s WHERE id = %s",
                (payment_url, wata_transaction_id, order_id))
    conn.commit()
    cur.close()
    conn.close()

    return {
        'statusCode': 200,
        'headers': HEADERS,
        'body': json.dumps({
            'payment_url': payment_url,
            'order_id': order_id,
            'order_number': order_number,
            'wata_transaction_id': wata_transaction_id
        }),
        'isBase64Encoded': False
    }
