# ISP Billing & Network Management System

A comprehensive ISP automation system with real-time M-Pesa payments, automated network access control via MikroTik RouterOS, and billing management for PPPoE and Hotspot services.

## 🚀 Features

### Backend (Django REST Framework)
- **Customer Management**: Registration, authentication, profile management
- **Billing System**: Prepaid/postpaid plans, subscriptions, expiry tracking
- **M-Pesa Integration**: STK Push payments, callback handling, automatic activation
- **MikroTik Automation**: PPPoE/Hotspot user management, session control
- **Network Access Control**: Automatic activation/suspension based on payment status
- **Background Tasks**: Celery tasks for expiry checking and payment cleanup
- **RADIUS Support**: Optional RADIUS integration for authentication
- **Notifications**: SMS (Africa's Talking/Twilio), WhatsApp (Meta Cloud API/Twilio) and Telegram alerts for customers and admins

### Frontend (React + Vite)
- **Customer Portal**: Dashboard, subscription status, payment interface
- **M-Pesa STK Push**: Real-time payment processing with status polling
- **Usage Statistics**: Data consumption and session history
- **Responsive Design**: Mobile-friendly Tailwind CSS interface

## 📋 Prerequisites

- Python 3.9+
- Node.js 18+
- PostgreSQL (or SQLite for development)
- Redis (for Celery)
- MikroTik Router with API enabled
- M-Pesa Daraja API credentials (sandbox or production)

## 🛠️ Installation

### Backend Setup

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your credentials

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

### Celery Setup

```bash
cd backend
source venv/bin/activate

# Start Celery worker
celery -A isp_billing worker -l info

# Start Celery beat (in another terminal)
celery -A isp_billing beat -l info
```

## ⚙️ Configuration

### M-Pesa Configuration

1. Register for M-Pesa Daraja API at https://developer.safaricom.co.ke/
2. Create an app and get your credentials
3. Update `.env`:

```env
MPESA_ENVIRONMENT=sandbox  # or production
MPESA_CONSUMER_KEY=your_consumer_key
MPESA_CONSUMER_SECRET=your_consumer_secret
MPESA_SHORTCODE=174379  # Your paybill/till number
MPESA_PASSKEY=your_passkey
MPESA_CALLBACK_URL=https://yourdomain.com/api/payments/callback/
```

### MikroTik Configuration

1. Enable API on your MikroTik router:
   ```
   /ip service set api address=0.0.0.0/0 disabled=no
   ```

2. Create API user:
   ```
   /user add name=api_user password=your_password group=full
   ```

3. Update `.env`:

```env
MIKROTIK_HOST=192.168.88.1
MIKROTIK_USERNAME=admin
MIKROTIK_PASSWORD=jazino
MIKROTIK_PORT=8728
```


### Notifications Configuration (SMS / WhatsApp / Telegram)

Customers are notified on: welcome/registration, payment received, payment
failed, subscription expiring soon (default 24h before, hourly Celery Beat
check), and subscription expired/suspended. Admins (staff users with role
`admin`, plus any extra recipients configured in `.env`) are notified on:
new registration, payment received, and a summary when subscriptions expire.
Every send is recorded in **Django admin → Notification Logs** with status
and provider error, and failed sends can be re-queued from there. An admin
test endpoint is available: `POST /api/notifications/test/` with
`{"channel": "sms|whatsapp|telegram", "recipient": "...", "message": "..."}`.

Each channel is off until you enable it in `.env`:

```env
# Master switches
NOTIFY_SMS_ENABLED=True
NOTIFY_WHATSAPP_ENABLED=True
NOTIFY_TELEGRAM_ENABLED=True

# SMS via Africa's Talking (or SMS_PROVIDER=twilio)
SMS_PROVIDER=africastalking
AFRICASTALKING_USERNAME=your_username     # 'sandbox' for testing
AFRICASTALKING_API_KEY=your_api_key
AFRICASTALKING_SENDER_ID=YOURBRAND        # optional

# WhatsApp via Meta WhatsApp Cloud API (or WHATSAPP_PROVIDER=twilio)
WHATSAPP_PROVIDER=meta
WHATSAPP_ACCESS_TOKEN=your_meta_access_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id

# Telegram bot (create one with @BotFather)
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_WEBHOOK_SECRET=any-random-string

# Extra admin recipients beyond staff admins' phone numbers
ADMIN_NOTIFY_PHONES=+2547XXXXXXXX
ADMIN_TELEGRAM_CHAT_IDS=123456789
```

**Telegram linking**: register the webhook once —
`https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<your-domain>/api/notifications/telegram/webhook/&secret_token=<TELEGRAM_WEBHOOK_SECRET>`
— then customers link their account by messaging the bot
`/start <username or phone>`. Admins can get their own chat ID the same way
(it is logged) or via @userinfobot.

**WhatsApp caveat**: with the Meta Cloud API, free-form text messages are
only delivered within 24 hours of the customer last messaging your WhatsApp
number. For alerts outside that window Meta requires pre-approved template
messages — either have customers send one opt-in message to your number, or
use `WHATSAPP_PROVIDER=twilio` and configure Twilio content templates.

## 📊 System Flow

### Payment → Network Activation Flow

```
1. Customer selects plan and enters M-Pesa number
2. Backend initiates STK Push via Daraja API
3. Customer confirms payment on phone
4. M-Pesa sends callback to backend
5. Backend validates payment and creates transaction
6. Backend updates subscription (create/extend)
7. Backend activates network access:
   - Enable PPPoE secret / Hotspot user
   - Assign active speed profile
   - Disconnect old session (force reconnect)
8. Customer gets instant internet access
```

### Expiry & Auto-Suspension Flow

```
1. Celery Beat runs expiry checker every hour
2. Find expired subscriptions
3. For each expired subscription:
   - Update subscription status to 'expired'
   - Disable PPPoE/Hotspot user on MikroTik
   - Disconnect active session
   - Update customer status to 'suspended'
```

## 🔒 Security

- JWT authentication for API endpoints
- M-Pesa callback validation
- IP whitelisting for M-Pesa callbacks (recommended)
- HTTPS required for production
- Environment-based configuration
- Password hashing for customer accounts

## 📱 API Endpoints

### Authentication
- `POST /api/customers/register/` - Register new customer
- `POST /api/customers/login/` - Login
- `GET /api/customers/profile/` - Get profile

### Billing
- `GET /api/billing/plans/` - List billing plans
- `GET /api/billing/subscriptions/current/` - Current subscription
- `GET /api/billing/transactions/` - Payment history

### Payments
- `POST /api/payments/initiate/` - Initiate STK Push
- `POST /api/payments/callback/` - M-Pesa callback (webhook)
- `GET /api/payments/status/<id>/` - Check payment status

## 🧪 Testing

### Backend Tests
```bash
cd backend
python manage.py test
```

### M-Pesa Sandbox Testing
Use Safaricom's test credentials:
- Shortcode: 174379
- Passkey: (provided by Safaricom)
- Test phone: Use any Safaricom number

## 🚀 Deployment

### Backend Deployment

1. Set up PostgreSQL database
2. Configure production environment variables
3. Collect static files: `python manage.py collectstatic`
4. Use Gunicorn: `gunicorn isp_billing.wsgi:application`
5. Set up Nginx as reverse proxy
6. Configure SSL certificate
7. Run Celery worker and beat as systemd services

### Frontend Deployment

```bash
npm run build
# Deploy dist/ folder to your web server
```

## 📖 Admin Panel

Access Django admin at `http://localhost:8000/django-admin/` (or `https://<your-domain>/django-admin/` through the nginx proxy)

Features:
- Customer management
- Billing plan configuration
- Transaction monitoring
- Payment request tracking
- Network device management

## 🤝 Support

For issues or questions:
- Check the implementation plan in `/brain/implementation_plan.md`
- Review the walkthrough in `/brain/walkthrough.md`
- Check logs in `backend/logs/isp_billing.log`

## 📄 License

This project is proprietary software for ISP network management.

## 🎯 Key Features Summary

✅ **No Revenue Leakage**: Payment confirmed before network access  
✅ **Instant Activation**: Automatic network enable after payment  
✅ **Auto-Suspension**: Expired users automatically disabled  
✅ **Real-time Payments**: M-Pesa STK Push integration  
✅ **Network Automation**: MikroTik API integration  
✅ **Scalable**: Handles high-volume payment processing  
✅ **Secure**: JWT auth, payment validation, audit logging

## 🔧 Troubleshooting

### Hotspot Redirect Not Working
If users are not redirected to the external portal (e.g. running on your laptop `192.168.88.13`), you must whitelist your laptop in the MikroTik Walled Garden so unauthenticated users can reach it.

1. Run the helper script:
```bash
./backend/venv/bin/python add_walled_garden.py
```
2. Verify in MikroTik WinBox: IP -> Hotspot -> Walled Garden -> IP List.
