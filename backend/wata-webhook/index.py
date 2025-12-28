"""
WATA Payment Extension - Webhook Handler
"""
import json
import os
import base64
import httpx
import psycopg2
from typing import Optional
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature


# Cache for public key
_public_key_cache: Optional[str] = None


def get_db_connection():
    """Get database connection."""
    dsn = os.environ.get('DATABASE_URL')
    if not dsn:
        raise ValueError('DATABASE_URL not configured')
    return psycopg2.connect(dsn)


def get_wata_public_key() -> Optional[str]:
    """Get WATA public key for webhook signature verification."""
    global _public_key_cache

    if _public_key_cache:
        return _public_key_cache

    base_url = os.environ.get("WATA_API_URL", "https://api.wata.pro/api/h2h")

    with httpx.Client() as client:
        response = client.get(
            f"{base_url}/public-key",
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        if response.status_code != 200:
            return None

        data = response.json()
        public_key = data.get("value")

        if public_key:
            _public_key_cache = public_key
            return public_key

    return None


def verify_webhook_signature(payload: str, signature: str) -> bool:
    """
    Verify WATA webhook signature using RSA.

    Args:
        payload: Webhook payload as string
        signature: Signature from webhook headers

    Returns:
        True if signature is valid
    """
    public_key_pem = get_wata_public_key()
    if not public_key_pem:
        print("Could not get WATA webhook public key")
        return False

    # Load public key
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode())
    except Exception as e:
        print(f"Failed to load public key: {e}")
        return False

    # Decode signature from base64
    try:
        signature_bytes = base64.b64decode(signature)
    except Exception as e:
        print(f"Failed to decode signature from base64: {e}")
        return False

    # Verify signature - WATA uses SHA512
    try:
        key.verify(
            signature_bytes,
            payload.encode(),
            padding.PKCS1v15(),
            hashes.SHA512(),
        )
        return True
    except InvalidSignature:
        print("Invalid WATA webhook signature")
        return False
    except Exception as e:
        print(f"Error verifying WATA webhook signature: {e}")
        return False


def parse_webhook_data(data: dict) -> dict:
    """Parse WATA webhook data."""
    return {
        "transaction_id": data.get("transactionId"),
        "order_id": data.get("orderId"),
        "status": data.get("transactionStatus"),
        "amount": data.get("amount"),
        "currency": data.get("currency"),
        "error_code": data.get("errorCode"),
        "error_message": data.get("errorDescription"),
        "payment_method": data.get("transactionType"),
        "payment_time": data.get("paymentTime"),
        "terminal_name": data.get("terminalName"),
        "terminal_public_id": data.get("terminalPublicId"),
        "commission": data.get("commission"),
        "email": data.get("email"),
    }


HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Signature, X-Wata-Signature',
    'Content-Type': 'application/json'
}


def handler(event: dict, context) -> dict:
    """
    WATA webhook handler for payment confirmation.
    Verifies signature and updates order status.
    """
    method = event.get('httpMethod', 'GET').upper()

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': HEADERS, 'body': '', 'isBase64Encoded': False}

    # Get request body
    body = event.get('body', '')
    if event.get('isBase64Encoded', False):
        body = base64.b64decode(body).decode('utf-8')

    # Get signature from headers
    headers = event.get('headers', {})
    signature = (
        headers.get('X-Signature') or
        headers.get('x-signature') or
        headers.get('X-Wata-Signature') or
        headers.get('x-wata-signature') or
        ''
    )

    # Verify signature
    if not verify_webhook_signature(body, signature):
        return {
            'statusCode': 401,
            'headers': HEADERS,
            'body': json.dumps({'error': 'Invalid signature'}),
            'isBase64Encoded': False
        }

    # Parse webhook data
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {
            'statusCode': 400,
            'headers': HEADERS,
            'body': json.dumps({'error': 'Invalid JSON'}),
            'isBase64Encoded': False
        }

    webhook_data = parse_webhook_data(data)

    # Get order_id from webhook
    order_id_str = webhook_data.get("order_id")
    if not order_id_str:
        return {
            'statusCode': 400,
            'headers': HEADERS,
            'body': json.dumps({'error': 'Missing order_id'}),
            'isBase64Encoded': False
        }

    # Find order in database
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT id, status FROM orders WHERE wata_order_id = %s",
        (int(order_id_str),)
    )
    result = cur.fetchone()

    if not result:
        cur.close()
        conn.close()
        return {
            'statusCode': 404,
            'headers': HEADERS,
            'body': json.dumps({'error': 'Order not found'}),
            'isBase64Encoded': False
        }

    db_order_id, current_status = result

    # Process based on status
    status = (webhook_data.get("status") or "").lower()

    if status in ["success", "completed", "paid"]:
        # Payment successful
        if current_status != 'paid':
            cur.execute("""
                UPDATE orders
                SET status = 'paid', paid_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (db_order_id,))
            conn.commit()
            print(f"WATA payment confirmed for order: {order_id_str}")

    elif status in ["failed", "error", "rejected"]:
        # Payment failed
        cur.execute("""
            UPDATE orders
            SET status = 'failed', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (db_order_id,))
        conn.commit()
        print(f"WATA payment failed for order: {order_id_str}")

    cur.close()
    conn.close()

    return {
        'statusCode': 200,
        'headers': HEADERS,
        'body': json.dumps({'status': 'ok'}),
        'isBase64Encoded': False
    }
