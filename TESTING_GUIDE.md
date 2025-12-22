# Quick Start & Testing Guide

## ✅ Sample Data Created

Successfully created **7 billing plans**:

### PPPoE Plans
- **Bronze 5Mbps** - KES 1,500/month - Perfect for browsing
- **Silver 10Mbps** - KES 2,500/month - Great for streaming
- **Gold 20Mbps** - KES 4,000/month - Premium speed
- **Platinum 50Mbps** - KES 8,000/month - Business class

### Hotspot Plans
- **Hotspot Daily** - KES 100/day - 24-hour access
- **Hotspot Weekly** - KES 500/week - 7-day access
- **Hotspot Monthly** - KES 1,500/month - 30-day access

---

## 🚀 Quick Start

### 1. Start Backend Server
```bash
cd /Users/hassan/Desktop/ISP/backend
source venv/bin/activate
python manage.py runserver
```

### 2. Start Frontend
```bash
cd /Users/hassan/Desktop/ISP/frontend
npm run dev
```

### 3. Access the System
- **Frontend**: http://localhost:5173/
- **Django Admin**: http://localhost:8000/admin/
- **API**: http://localhost:8000/api/

---

## 🧪 Testing M-Pesa Integration

### Option 1: Using the Test Script (Recommended)

```bash
cd /Users/hassan/Desktop/ISP/backend
source venv/bin/activate
python test_mpesa.py
```

The script will:
1. ✅ Check M-Pesa configuration
2. ✅ Test OAuth token generation
3. ✅ Load sample billing plan
4. ✅ Prompt for phone number
5. ✅ Initiate STK Push
6. ✅ Show callback URL

**What you'll see:**
- Configuration details
- Access token confirmation
- STK Push prompt on your phone
- Transaction IDs for tracking

### Option 2: Using the Frontend

1. **Register a customer**: http://localhost:5173/register
   - Fill in your details
   - Use your actual phone number for M-Pesa

2. **Browse plans**: http://localhost:5173/plans
   - View all 7 billing plans
   - Click "Subscribe Now"

3. **Make payment**: http://localhost:5173/payment
   - Select a plan
   - Enter M-Pesa phone number
   - Click "Pay with M-Pesa"
   - Check your phone for STK Push
   - Enter M-Pesa PIN

4. **Watch real-time status**:
   - Frontend polls every 3 seconds
   - Shows "Waiting for Payment" spinner
   - Auto-redirects on success

---

## ⚙️ M-Pesa Configuration

### Get Daraja API Credentials

1. **Register**: https://developer.safaricom.co.ke/
2. **Create App**: Get Consumer Key & Secret
3. **Get Passkey**: From your app dashboard

### Update `.env` File

Edit `/Users/hassan/Desktop/ISP/backend/.env`:

```env
# M-Pesa Configuration (Sandbox)
MPESA_ENVIRONMENT=sandbox
MPESA_CONSUMER_KEY=your_consumer_key_here
MPESA_CONSUMER_SECRET=your_consumer_secret_here
MPESA_SHORTCODE=174379
MPESA_PASSKEY=your_passkey_here
MPESA_CALLBACK_URL=http://localhost:8000/api/payments/callback/
```

### For Production

```env
MPESA_ENVIRONMENT=production
MPESA_SHORTCODE=your_paybill_number
# Update other credentials with production values
MPESA_CALLBACK_URL=https://yourdomain.com/api/payments/callback/
```

---

## 🔧 MikroTik Router Setup

### 1. Enable API on MikroTik

```routeros
/ip service set api address=0.0.0.0/0 disabled=no
```

### 2. Create API User

```routeros
/user add name=api_user password=your_secure_password group=full
```

### 3. Update Router in Django Admin

1. Go to http://localhost:8000/admin/
2. Navigate to **Network → Routers**
3. Edit "Main Router"
4. Update:
   - IP Address: Your router IP
   - Username: `api_user`
   - Password: Your password
   - Port: `8728`

### 4. Create MikroTik Profiles

Create speed profiles matching the billing plans:

```routeros
/ppp profile
add name=bronze-5mbps rate-limit=5M/5M
add name=silver-10mbps rate-limit=10M/10M
add name=gold-20mbps rate-limit=20M/20M
add name=platinum-50mbps rate-limit=50M/50M

/ip hotspot profile
add name=hotspot-daily rate-limit=5M/5M
add name=hotspot-weekly rate-limit=10M/10M
add name=hotspot-monthly rate-limit=10M/10M
```

---

## 🧪 Complete Test Flow

### Test Payment → Network Activation

1. **Start all services**:
   ```bash
   # Terminal 1: Backend
   cd backend && source venv/bin/activate && python manage.py runserver
   
   # Terminal 2: Celery Worker
   cd backend && source venv/bin/activate && celery -A isp_billing worker -l info
   
   # Terminal 3: Frontend
   cd frontend && npm run dev
   ```

2. **Register customer** at http://localhost:5173/register

3. **Select plan** at http://localhost:5173/plans

4. **Make payment**:
   - Enter phone number
   - Confirm STK Push on phone
   - Watch real-time status

5. **Verify activation**:
   - Check Django admin for transaction
   - Check subscription created
   - Check MikroTik for PPPoE/Hotspot user
   - Try to connect to internet

### Test Expiry & Auto-Suspension

1. **Manually expire subscription**:
   ```bash
   cd backend
   source venv/bin/activate
   python manage.py shell
   ```
   
   ```python
   from apps.billing.models import Subscription
   from django.utils import timezone
   from datetime import timedelta
   
   # Get a subscription
   sub = Subscription.objects.first()
   
   # Set expiry to yesterday
   sub.expiry_date = timezone.now() - timedelta(days=1)
   sub.save()
   ```

2. **Run expiry checker**:
   ```bash
   python manage.py shell
   ```
   
   ```python
   from apps.billing.tasks import check_expired_subscriptions
   check_expired_subscriptions()
   ```

3. **Verify suspension**:
   - Check customer status changed to 'suspended'
   - Check MikroTik user disabled
   - Try to connect (should fail)

4. **Test renewal**:
   - Make another payment
   - Verify reactivation
   - Check expiry extended

---

## 📊 Django Admin Features

Access: http://localhost:8000/admin/

### Create Superuser
```bash
cd backend
source venv/bin/activate
python manage.py createsuperuser
```

### Admin Sections

1. **Customers**: View all registered users
2. **Billing Plans**: Manage packages and pricing
3. **Subscriptions**: Monitor active/expired subscriptions
4. **Transactions**: View payment history
5. **Payment Requests**: Track M-Pesa STK Push requests
6. **Routers**: Manage MikroTik devices
7. **PPPoE Secrets**: View synced PPPoE users
8. **Hotspot Users**: View synced Hotspot users

---

## 🐛 Troubleshooting

### M-Pesa Issues

**STK Push not received:**
- Check phone number format (0712345678 or 254712345678)
- Verify M-Pesa credentials in `.env`
- Check if phone is Safaricom
- Ensure sufficient balance (sandbox)

**Callback not working:**
- For local testing, use ngrok: `ngrok http 8000`
- Update `MPESA_CALLBACK_URL` with ngrok URL
- Check Django logs: `backend/logs/isp_billing.log`

### MikroTik Issues

**Cannot connect to router:**
- Verify API is enabled
- Check IP address and port
- Test credentials manually
- Ensure firewall allows API port

**User not created:**
- Check MikroTik profiles exist
- Verify router credentials in admin
- Check Django logs

### Payment Status Stuck on Pending

- Check Celery worker is running
- Verify callback URL is accessible
- Check M-Pesa callback in admin
- Look for errors in logs

---

## 📝 Next Steps

1. ✅ **Configure M-Pesa** - Add your Daraja API credentials
2. ✅ **Setup MikroTik** - Update router details and create profiles
3. ✅ **Test Payment** - Run `python test_mpesa.py`
4. ✅ **Test Frontend** - Register and make a payment
5. ✅ **Start Celery** - Enable background tasks
6. ✅ **Monitor Logs** - Check `backend/logs/isp_billing.log`

---

## 🎯 Production Deployment

When ready for production:

1. Update `.env` with production credentials
2. Change `DEBUG=False`
3. Set up PostgreSQL database
4. Configure Nginx reverse proxy
5. Set up SSL certificate
6. Run Celery as systemd service
7. Configure M-Pesa production callback URL
8. Set up monitoring and backups

See `README.md` for detailed deployment guide.
