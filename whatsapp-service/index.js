/**
 * Internal-only sidecar wrapping Baileys (unofficial WhatsApp Web
 * protocol, QR-paired) -- never expose this service's port publicly.
 * Django's whatsapp_service.py is the only intended caller, reaching it
 * by Docker service name on the internal network.
 *
 * Deliberate trade-off (accepted): this is against WhatsApp's ToS and the
 * paired number can be banned, especially for bulk/promo sends -- use a
 * dedicated number, not a personal one, and keep the broadcast throttle in
 * apps/notifications/tasks.py::send_promo_broadcast in place.
 */
const express = require('express');
const QRCode = require('qrcode');
const pino = require('pino');
const {
    default: makeWASocket,
    useMultiFileAuthState,
    fetchLatestBaileysVersion,
    DisconnectReason,
} = require('@whiskeysockets/baileys');

const AUTH_DIR = process.env.WHATSAPP_AUTH_DIR || '/app/auth';
const PORT = process.env.PORT || 3000;
// 'warn' by default would hide the connect/disconnect lifecycle logs below
// that are exactly what you need when diagnosing a reconnect loop.
const logger = pino({ level: process.env.LOG_LEVEL || 'info' });

let sock = null;
let latestQrDataUri = null;
let connected = false;
let connectedNumber = null;
let reconnectTimer = null;

async function startSocket() {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    // Baileys bundles a default WhatsApp Web protocol version that drifts
    // out of date over time -- an outdated version is a common cause of a
    // connect-then-immediately-disconnect loop right after pairing.
    // Fetching the actual current version avoids that.
    const { version } = await fetchLatestBaileysVersion();

    sock = makeWASocket({
        auth: state,
        version,
        logger,
        printQRInTerminal: false,
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            latestQrDataUri = await QRCode.toDataURL(qr);
        }

        if (connection === 'open') {
            connected = true;
            latestQrDataUri = null;
            connectedNumber = sock.user?.id?.split(':')[0] || null;
            logger.info(`WhatsApp connected as ${connectedNumber}`);
        }

        if (connection === 'close') {
            connected = false;
            connectedNumber = null;
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const reason = lastDisconnect?.error?.message || 'unknown reason';

            if (statusCode === DisconnectReason.loggedOut) {
                logger.warn(`WhatsApp logged out (${reason}) -- scan a fresh QR code to reconnect.`);
                return;
            }

            // Baileys forces one reconnect right after the very first
            // successful pairing (a "restart required" close, expected) --
            // and transient network drops are routine too. Reconnecting
            // immediately in a loop (e.g. if the session itself is bad)
            // risks WhatsApp rate-limiting/flagging the connection, so this
            // waits briefly and only ever has one reconnect scheduled at a time.
            logger.warn(`WhatsApp connection closed (code=${statusCode}, ${reason}), reconnecting in 3s...`);
            clearTimeout(reconnectTimer);
            reconnectTimer = setTimeout(() => {
                startSocket().catch((err) => logger.error({ err }, 'Reconnect failed'));
            }, 3000);
        }
    });
}

startSocket().catch((err) => logger.error({ err }, 'Failed to start WhatsApp socket'));

const app = express();
app.use(express.json());

app.get('/status', (req, res) => {
    res.json({ connected, number: connectedNumber, qr: connected ? null : latestQrDataUri });
});

app.post('/send', async (req, res) => {
    const { phone, message } = req.body || {};
    if (!phone || !message) {
        return res.status(400).json({ success: false, error: 'phone and message are required' });
    }
    if (!connected) {
        return res.status(503).json({ success: false, error: 'WhatsApp is not connected -- scan the QR code first' });
    }

    try {
        const digitsOnly = String(phone).replace(/[^\d]/g, '');
        const jid = `${digitsOnly}@s.whatsapp.net`;
        const result = await sock.sendMessage(jid, { text: message });
        res.json({ success: true, messageId: result?.key?.id || null });
    } catch (err) {
        logger.error({ err }, 'WhatsApp send failed');
        res.status(500).json({ success: false, error: err.message });
    }
});

app.post('/logout', async (req, res) => {
    try {
        if (sock) await sock.logout();
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

app.listen(PORT, () => logger.info(`whatsapp-service listening on :${PORT}`));
