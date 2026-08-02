import base64
from datetime import datetime
import requests
from requests.auth import HTTPBasicAuth

# 1. API Configuration (Production Credentials)
CONSUMER_KEY = "4Ooa7bFOgP6cthbD2udKBTKiaZZ23OwPe82BZAE0dojPa1u5"
CONSUMER_SECRET = "byP0GwSP0Wq7GAvGxaAQ4xcObVCBveddkwhjAjnOXggtov7CipuTp6LMuRplaLZh"
BUSINESS_SHORT_CODE = "5473834"  # Head office/API shortcode -- BusinessShortCode + password
TILL_NUMBER = "4992946"  # Actual till customers pay to -- PartyB
PASSKEY = "f17a593eb5dcff1fafa438d88cd2ff10332549dd2f2cea6b0df8b20bb7dae34d"  # Production Passkey

# API Endpoints -- note the "api." subdomain, and both are v1 (Safaricom
# has never published a v2 for either oauth/generate or stkpush).
AUTH_URL = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
STK_PUSH_URL = "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"


def generate_access_token():
    """Fetches the OAuth2 access token from Safaricom."""
    try:
        response = requests.get(
            AUTH_URL, auth=HTTPBasicAuth(CONSUMER_KEY, CONSUMER_SECRET)
        )
        response.raise_for_status()
        return response.json().get("access_token")
    except requests.exceptions.RequestException as e:
        print(f"Error generating token: {e}")
        return None


def initiate_stk_push(phone_number, amount, callback_url, account_ref="Ref001"):
    """Generates the necessary credentials and triggers the M-Pesa STK Push."""
    # Generate Access Token
    access_token = generate_access_token()
    if not access_token:
        return

    # Generate Timestamp (Format: YYYYMMDDHHMMSS)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    # Generate Password: Base64(ShortCode + PassKey + Timestamp)
    password_string = f"{BUSINESS_SHORT_CODE}{PASSKEY}{timestamp}"
    password_bytes = password_string.encode("utf-8")
    password = base64.b64encode(password_bytes).decode("utf-8")

    # Request Headers
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Request Payload
    payload = {
        "BusinessShortCode": BUSINESS_SHORT_CODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerBuyGoodsOnline",  # CustomerBuyGoodsOnline for Till Numbers
        "Amount": int(amount),
        "PartyA": phone_number,  # The phone sending money
        "PartyB": TILL_NUMBER,  # The till actually receiving the money
        "PhoneNumber": phone_number,
        "CallBackURL": callback_url,  # Public live endpoint to receive Daraja results
        "AccountReference": account_ref,
        "TransactionDesc": "Payment Description",
    }

    # Send Request
    try:
        response = requests.post(STK_PUSH_URL, json=payload, headers=headers)
        print("Response Code:", response.status_code)
        print("Response Body:", response.json())
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"STK Push Request Failed: {e}")
        return None


# --- Execution Example ---
if __name__ == "__main__":
    # Formats allowed: 2547XXXXXXXX or 2541XXXXXXXX
    TARGET_PHONE = "254726686337"
    PAY_AMOUNT = 1
    # Must be a publicly accessible secure URL (e.g., via ngrok during development)
    CALLBACK = "https://portal.hasanet.net/api/payments/callback/"

    initiate_stk_push(
        phone_number=TARGET_PHONE, amount=PAY_AMOUNT, callback_url=CALLBACK
    )
