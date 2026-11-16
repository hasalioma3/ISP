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
 *
 * Send-only by design: chat history sync, presence and link previews are
 * all switched off below. None of them are needed to send notifications,
 * and history sync in particular is the biggest CPU/RAM spike on a Pi.
 */
const fs = require('fs');
const path = require('path');
const express = require('express');
const QRCode = require('qrcode');
const pino = require('pino');
const {
    default: makeWASocket,
    useMultiFileAuthState,
    fetchLatestBaileysVersion,
    DisconnectReason,
    Browsers,
    makeCacheableSignalKeyStore,
} = require('@whiskeysockets/baileys');

const AUTH_DIR = process.env.WHATSAPP_AUTH_DIR || '/app/auth';
const PORT = process.env.PORT || 3000;
// Our own lifecycle logs (connect/disconnect/reconnect) stay at info --
// they're what you need when diagnosing a reconnect loop. Baileys' internal
// logger is far chattier (every frame/ack at info), so it's held at warn
// unless explicitly raised for debugging.
const logger = pino({ level: process.env.LOG_LEVEL || 'info' });
const baileysLogger = logger.child({ module: 'baileys' });
baileysLogger.level = process.env.BAILEYS_LOG_LEVEL || 'warn';

const RECONNECT_MIN_MS = 3000;
const RECONNECT_MAX_MS = 5 * 60 * 1000;

let sock = null;
let latestQrDataUri = null;
let connected = false;
let connectedNumber = null;
let reconnectTimer = null;
let reconnectDelay = RECONNECT_MIN_MS;
let qrUpdatedAt = null;
let lastError = null;

// "Waiting for this message. This may take a while." on the recipient's
// phone means they couldn't decrypt what we sent (a new device of theirs, or
// our session with them was reset) and asked us to resend it. Baileys answers
// that retry request by calling getMessage(key) -- with no store it gets
// nothing back, the retry silently fails and the placeholder stays forever.
// So remember what we sent recently. In memory only: retries come within
// seconds to minutes, and a restart losing the cache just means those few
// messages fall back to the old behaviour.
const SENT_CACHE_MAX = 1000;
const sentMessages = new Map(); // message id -> proto message content
function rememberSent(result) {
    const id = result?.key?.id;
    if (!id || !result.message) return;
    sentMessages.set(id, result.message);
    if (sentMessages.size > SENT_CACHE_MAX) sentMessages.delete(sentMessages.keys().next().value);
}

// Minimal CacheStore (get/set/del/flushAll) for Baileys' retry counters, so a
// message isn't re-sent endlessly and the counters survive socket restarts.
// Kept here rather than adding node-cache, which would mean a lockfile change.
const retryCounts = new Map();
const msgRetryCounterCache = {
    get: (k) => retryCounts.get(k),
    set: (k, v) => { retryCounts.set(k, v); if (retryCounts.size > 5000) retryCounts.delete(retryCounts.keys().next().value); return true; },
    del: (k) => retryCounts.delete(k),
    flushAll: () => retryCounts.clear(),
};

function clearAuthState() {
    // AUTH_DIR is the mounted volume itself, so empty it rather than
    // removing the directory (which would fail on a mount point).
    for (const entry of fs.readdirSync(AUTH_DIR)) {
        fs.rmSync(path.join(AUTH_DIR, entry), { recursive: true, force: true });
    }
}

function scheduleReconnect(delay = reconnectDelay) {
    // Only ever one reconnect pending, with exponential backoff -- a tight
    // fixed-interval loop on a bad session is what gets a number flagged.
    clearTimeout(reconnectTimer);
    logger.warn(`Reconnecting in ${Math.round(delay / 1000)}s...`);
    reconnectTimer = setTimeout(() => {
        startSocket().catch((err) => {
            lastError = err.message;
            logger.error({ err }, 'Reconnect failed');
            scheduleReconnect();
        });
    }, delay);
    reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS);
}

function teardownSocket() {
    if (!sock) return;
    // A closed socket's listeners would otherwise pile up across every
    // reconnect, each holding the old socket in memory.
    sock.ev.removeAllListeners('connection.update');
    sock.ev.removeAllListeners('creds.update');
    try { sock.end(undefined); } catch (_) { /* already closed */ }
    sock = null;
}

async function startSocket() {
    teardownSocket();
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    // Baileys bundles a default WhatsApp Web protocol version that drifts
    // out of date over time -- an outdated version is a common cause of a
    // connect-then-immediately-disconnect loop right after pairing. This
    // falls back to the bundled version by itself if the lookup fails.
    const { version } = await fetchLatestBaileysVersion();

    sock = makeWASocket({
        // Caching the Signal keys in memory means a burst of sends (or a
        // retry) doesn't re-read every key file from the SD card, and keeps
        // key reads and writes consistent while several sends overlap.
        auth: { creds: state.creds, keys: makeCacheableSignalKeyStore(state.keys, baileysLogger) },
        getMessage: async (key) => sentMessages.get(key.id),
        msgRetryCounterCache,
        version,
        logger: baileysLogger,
        printQRInTerminal: false,
        // Present as a standard desktop client. Without a browser identity
        // some phones refuse to link ("Couldn't link device").
        browser: Browsers.macOS('Desktop'),
        markOnlineOnConnect: false,
        syncFullHistory: false,
        shouldSyncHistoryMessage: () => false,
        generateHighQualityLinkPreview: false,
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            latestQrDataUri = await QRCode.toDataURL(qr);
            qrUpdatedAt = Date.now();
        }

        if (connection === 'open') {
            connected = true;
            latestQrDataUri = null;
            lastError = null;
            reconnectDelay = RECONNECT_MIN_MS;
            connectedNumber = sock.user?.id?.split(':')[0] || null;
            logger.info(`WhatsApp connected as ${connectedNumber}`);
        }

        if (connection === 'close') {
            connected = false;
            connectedNumber = null;
            // A QR code is only valid for ~20s and dies with this socket --
            // keeping it would leave an expired code on the settings page
            // for the whole reconnect delay, and scanning it always fails.
            latestQrDataUri = null;
            qrUpdatedAt = null;
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const reason = lastDisconnect?.error?.message || 'unknown reason';
            lastError = `${reason} (code ${statusCode})`;

            if (statusCode === DisconnectReason.loggedOut) {
                // The saved session is dead -- without clearing it, every
                // restart would fail the same way and no new QR would ever
                // appear on the settings page.
                logger.warn(`WhatsApp logged out (${reason}) -- clearing session, a fresh QR code will be shown.`);
                clearAuthState();
                reconnectDelay = RECONNECT_MIN_MS;
                scheduleReconnect(1000);
                return;
            }
            if (statusCode === DisconnectReason.forbidden) {
                logger.error(`WhatsApp refused this number (${reason}) -- it may be banned. Not reconnecting.`);
                return;
            }
            if (statusCode === DisconnectReason.connectionReplaced) {
                // Another client took over this session -- reconnecting
                // straight away just fights it, so wait the maximum.
                logger.warn(`WhatsApp session opened elsewhere (${reason}).`);
                scheduleReconnect(RECONNECT_MAX_MS);
                return;
            }
            if (statusCode === DisconnectReason.restartRequired) {
                // Expected once right after scanning: WhatsApp has saved the
                // new login and wants a fresh connection with it. Do that
                // promptly (after the creds write has had a moment).
                logger.info('Paired -- restarting the connection with the new login.');
                reconnectDelay = RECONNECT_MIN_MS;
                scheduleReconnect(1500);
                return;
            }
            const paired = Boolean(sock?.authState?.creds?.registered);
            if (!paired && statusCode === DisconnectReason.timedOut) {
                // Waiting to be scanned and the batch of QR codes ran out:
                // get a fresh one right away rather than backing off (the
                // backoff is for a paired session that keeps dropping).
                logger.info('QR code expired unscanned -- generating a new one.');
                reconnectDelay = RECONNECT_MIN_MS;
                scheduleReconnect(2000);
                return;
            }

            logger.warn(`WhatsApp connection closed (code=${statusCode}, ${reason}).`);
            scheduleReconnect();
        }
    });
}

startSocket().catch((err) => {
    lastError = err.message;
    logger.error({ err }, 'Failed to start WhatsApp socket');
    scheduleReconnect();
});

const app = express();
app.use(express.json({ limit: '64kb' }));

app.get('/status', (req, res) => {
    res.json({
        connected,
        number: connectedNumber,
        qr: connected ? null : latestQrDataUri,
        error: connected ? null : lastError,
    });
});

app.post('/send', async (req, res) => {
    const { phone, message } = req.body || {};
    if (!phone || !message) {
        return res.status(400).json({ success: false, error: 'phone and message are required' });
    }
    if (!connected || !sock) {
        return res.status(503).json({ success: false, error: 'WhatsApp is not connected -- scan the QR code first' });
    }

    try {
        const digitsOnly = String(phone).replace(/[^\d]/g, '');
        // Without this check, sending to a number that isn't on WhatsApp
        // "succeeds" and the message silently goes nowhere.
        const [lookup] = (await sock.onWhatsApp(digitsOnly)) || [];
        if (!lookup?.exists) {
            return res.status(404).json({ success: false, error: `${digitsOnly} is not on WhatsApp` });
        }
        const result = await sock.sendMessage(lookup.jid, { text: message });
        rememberSent(result);
        res.json({ success: true, messageId: result?.key?.id || null });
    } catch (err) {
        logger.error({ err }, 'WhatsApp send failed');
        res.status(500).json({ success: false, error: err.message });
    }
});

app.post('/logout', async (req, res) => {
    try {
        // Triggers a loggedOut close, which clears the session and brings
        // up a fresh QR (see connection.update above).
        if (sock) await sock.logout();
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

app.listen(PORT, () => logger.info(`whatsapp-service listening on :${PORT}`));
