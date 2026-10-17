"""CFlix — Python 3.10+, yalnızca standart kütüphane."""
import hashlib
import hmac
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import smtplib
import socket
import sqlite3
import ssl
import threading
import time
from contextlib import closing
from datetime import datetime, timezone
from email.message import EmailMessage
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent


def load_local_env(path=None):
    """Load local configuration without printing values or overriding the process environment."""
    try:
        lines = (Path(path) if path is not None else ROOT / ".env").read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if separator and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ.setdefault(key, value)


load_local_env()
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
APP_VERSION = "2026.10.17.1"
FEATURES = ["password", "feedback", "gmail-smtp", "qualities", "media-range", "lan"]
# Kept only on the server; never included in responses or diagnostic messages.
FEEDBACK_RECIPIENT = os.environ.get("FEEDBACK_RECIPIENT", "").strip()
SESSIONS = {}
ATTEMPTS = {}
LOCK = threading.Lock()
VIDEO = "https://storage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
ROWS = [
    ("aurora", "Aurora", "Bilim Kurgu", "Film", 2025, 8.7, "Bilinmeyen bir gezegenden gelen sinyal, insanlığın kaderini değiştirecek bir yolculuğun ilk adımıdır.", "photo-1446776811953-b23d57bd21aa", 148),
    ("sessiz-orman", "Sessiz Orman", "Gerilim", "Film", 2025, 8.2, "Kaybolan bir iz, unutulmuş bir hikâye. Ormanın sessizliğinde hiçbir şey göründüğü gibi değildir.", "photo-1448375240586-882707db888b", 112),
    ("son-durak", "Son Durak", "Dram", "Dizi", 2026, 8.8, "Aynı trenin yolcuları, farklı hayatlar. Küçük bir karşılaşma her şeyi değiştirebilir.", "photo-1474487548417-781cb71495f3", 45),
    ("mavi-gezegen", "Mavi Gezegen", "Belgesel", "Dizi", 2025, 9.1, "Okyanusların derinliklerinden en uzak kıyılara, hayatın olağanüstü yolculuğu.", "photo-1518837695005-2083093ee35b", 52),
    ("gece-vardiyasi", "Gece Vardiyası", "Aksiyon", "Film", 2026, 8.0, "Şehir uyurken başlayan bir takip. Şafak sökmeden verilmesi gereken tek bir karar.", "photo-1519608487953-e999c86e7455", 126),
    ("kiyi", "Kıyı", "Dram", "Film", 2024, 8.5, "Doğduğu kasabaya dönen Deniz, geçmişiyle ve yarım kalan bir aşkla yüzleşir.", "photo-1476514525535-07fb3b4ae5f1", 105),
    ("yildiz-tozu", "Yıldız Tozu", "Bilim Kurgu", "Dizi", 2025, 8.6, "Uzayın en uzak köşesinde bir mürettebat, evine dönmenin yeni bir yolunu arıyor.", "photo-1462331940025-496dfbfc7564", 48),
    ("rota", "Rota: Bilinmeyen", "Macera", "Dizi", 2026, 8.4, "Haritaların bittiği yerde macera başlar. İki dost ve dünyanın ötesine uzanan bir yolculuk.", "photo-1464822759023-fed622ff2c3b", 42),
    ("bir-yaz", "Bir Yaz Daha", "Romantik", "Film", 2025, 7.9, "Bir yaz akşamı, eski bir şarkı ve yeniden karşılaşan iki yabancı.", "photo-1470252649378-9c29740c9fa8", 98),
    ("zirve", "Zirve", "Belgesel", "Film", 2026, 8.9, "Sınırlarını aşan insanların dünyanın çatısına uzanan yolculuklarından ilham alan bir hikâye.", "photo-1454496522488-7a8e488e8606", 89),
    ("golge", "Gölge", "Gerilim", "Dizi", 2025, 8.3, "Kendi izini süren bir dedektif, geçmişindeki karanlık düğümü çözmek zorunda.", "photo-1514565131-fce0801e5785", 50),
    ("yaban", "Yaban", "Macera", "Film", 2024, 8.1, "Her şeyden uzaklaşmak isteyen bir gezgin, doğada kendine giden yolu bulur.", "photo-1472396961693-142e6e269027", 116),
]
CATALOG = [dict(zip(("id", "title", "genre", "type", "year", "rating", "description", "photo", "duration"), row), video=VIDEO) for row in ROWS]
IDS = {m["id"] for m in CATALOG}
QUALITY_LABELS = ("360p", "480p", "720p", "1080p", "1440p", "2160p")


def connect():
    db = sqlite3.connect(DATA_DIR / "fatihflix.db", timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with closing(connect()) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, name TEXT NOT NULL,
          email TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS favorites (user_id TEXT REFERENCES users(id),
          movie_id TEXT, PRIMARY KEY(user_id,movie_id));
        CREATE TABLE IF NOT EXISTS history (user_id TEXT REFERENCES users(id), movie_id TEXT,
          position REAL, duration REAL, updated_at TEXT, completed INTEGER,
          PRIMARY KEY(user_id,movie_id));
        CREATE TABLE IF NOT EXISTS content (id TEXT PRIMARY KEY, payload TEXT NOT NULL,
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, filename TEXT NOT NULL,
          kind TEXT NOT NULL, mime TEXT NOT NULL, owner_id TEXT NOT NULL REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS feedback_outbox (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
          kind TEXT NOT NULL, subject TEXT NOT NULL, message TEXT NOT NULL,
          sender_name TEXT NOT NULL, sender_email TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued', created_at TEXT NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0, last_attempt REAL,
          sent_at TEXT, error_code TEXT);
        """)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
        if "role" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user', 'admin'))")
        for movie in CATALOG:
            db.execute("INSERT OR IGNORE INTO content VALUES (?,?,?)", (movie["id"], json.dumps(dict(movie, demo=True, cover=None), ensure_ascii=False), "2026-01-01"))
        db.commit()
    (DATA_DIR / "media").mkdir(exist_ok=True)


def get_catalog(db):
    movies = [json.loads(row[0]) for row in db.execute("SELECT payload FROM content ORDER BY created_at DESC, rowid DESC")]
    for movie in movies:
        movie.setdefault("qualities", [])
    return movies


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()


def smtp_config():
    if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", FEEDBACK_RECIPIENT):
        return None
    provider = os.environ.get("SMTP_PROVIDER", "").strip().lower()
    host = os.environ.get("SMTP_HOST", "").strip().lower() or ("smtp.gmail.com" if provider == "gmail" else "")
    username, password = os.environ.get("SMTP_USERNAME", ""), os.environ.get("SMTP_PASSWORD", "")
    if host == "smtp.gmail.com":
        username = username.strip()
        password = re.sub(r"\s+", "", password)
        if not username or not password:
            return None
    sender = os.environ.get("SMTP_FROM", "").strip() or (username if host == "smtp.gmail.com" else "")
    use_ssl = os.environ.get("SMTP_SSL", "0").lower() in ("1", "true", "yes")
    try:
        port = int(os.environ.get("SMTP_PORT", "") or ("465" if use_ssl else "587"))
    except ValueError:
        return None
    if not host or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", sender) or not 0 < port < 65536 or bool(username) != bool(password):
        return None
    starttls = os.environ.get("SMTP_STARTTLS", "1").lower() in ("1", "true", "yes")
    # Credentials must never be sent through an unencrypted connection.
    if username and not (use_ssl or starttls):
        return None
    return dict(host=host, port=port, sender=sender, username=username, password=password,
        use_ssl=use_ssl, starttls=starttls and not use_ssl, provider="gmail" if host == "smtp.gmail.com" else "smtp")


SMTP_SAFE_MESSAGES = {
    "smtp_not_configured": "E-posta bağlantısı henüz yapılandırılmadı; mesajlar güvenle kaydediliyor.",
    "smtp_auth_failed": "E-posta hesabı doğrulanamadı. Gmail için yerel kurulumdaki uygulama şifresini kontrol edin.",
    "smtp_unreachable": "E-posta sunucusuna ulaşılamadı. Ağ bağlantısını ve sunucu ayarlarını kontrol edin.",
    "smtp_delivery_failed": "E-posta teslimatı tamamlanamadı; bekleyen mesajlar yeniden denenecek.",
}


def mail_status(db):
    config = smtp_config()
    totals = dict(db.execute("SELECT status,COUNT(*) FROM feedback_outbox GROUP BY status").fetchall())
    row = db.execute("SELECT error_code FROM feedback_outbox WHERE status!='sent' AND error_code IS NOT NULL ORDER BY COALESCE(last_attempt,0) DESC,created_at DESC LIMIT 1").fetchone()
    code = "smtp_not_configured" if config is None else (row[0] if row else None)
    if code is not None and code not in SMTP_SAFE_MESSAGES:
        code = "smtp_delivery_failed"
    provider = config["provider"] if config else ("gmail" if os.environ.get("SMTP_PROVIDER", "").lower() == "gmail" or os.environ.get("SMTP_HOST", "").strip().lower() == "smtp.gmail.com" else "smtp")
    return {"configured": config is not None, "provider": provider,
        "queued": totals.get("queued", 0) + totals.get("sending", 0), "sent": totals.get("sent", 0),
        "lastErrorCode": code, "safeMessage": SMTP_SAFE_MESSAGES.get(code, "E-posta bağlantısı yapılandırıldı; teslimat sonucu gönderim sırasında doğrulanır.")}


def feedback_retry_delay(attempts):
    return min(3600, 60 * 2 ** min(max(attempts - 1, 0), 6))


def deliver_feedback(feedback_id, respect_backoff=False):
    """Try one durable queued message. Errors remain queued and reveal no SMTP details."""
    config = smtp_config()
    if config is None:
        with closing(connect()) as db:
            db.execute("UPDATE feedback_outbox SET error_code='smtp_not_configured' WHERE id=? AND status='queued'", (feedback_id,))
            db.commit()
        return "queued"
    with closing(connect()) as db:
        now = time.time()
        # A short lease prevents simultaneous HTTP/CLI retries from sending twice.
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM feedback_outbox WHERE id=?", (feedback_id,)).fetchone()
        if not row:
            return "missing"
        if row["status"] == "sent":
            return "sent"
        if row["status"] == "sending" and row["last_attempt"] and row["last_attempt"] > now - 300:
            return "queued"
        if respect_backoff and row["last_attempt"] is not None and now - row["last_attempt"] < feedback_retry_delay(row["attempts"]):
            return "queued"
        db.execute("UPDATE feedback_outbox SET status='sending',attempts=attempts+1,last_attempt=?,error_code=NULL WHERE id=?", (now, feedback_id))
        db.commit()
    message = EmailMessage()
    message["From"] = config["sender"]
    message["To"] = FEEDBACK_RECIPIENT
    message["Reply-To"] = row["sender_email"]
    category = "Öneri" if row["kind"] == "suggestion" else "Şikayet"
    message["Subject"] = f"CFlix {category}: {row['subject'] or feedback_id}"
    message["Message-ID"] = f"<cflix-feedback-{feedback_id}@{config['sender'].split('@')[-1]}>"
    message.set_content(f"Tür: {category}\nÜye: {row['sender_name']}\nE-posta: {row['sender_email']}\nKayıt: {feedback_id}\n\n{row['message']}")
    sent = False
    error_code = "smtp_delivery_failed"
    try:
        connection = smtplib.SMTP_SSL(config["host"], config["port"], timeout=10, context=ssl.create_default_context()) if config["use_ssl"] else smtplib.SMTP(config["host"], config["port"], timeout=10)
        with connection as smtp:
            smtp.ehlo()
            if config["starttls"]:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if config["username"]:
                smtp.login(config["username"], config["password"])
            # send_message returns refused recipients; an empty dictionary means accepted.
            sent = not smtp.send_message(message, from_addr=config["sender"], to_addrs=[FEEDBACK_RECIPIENT])
    except smtplib.SMTPAuthenticationError:
        error_code = "smtp_auth_failed"
    except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected):
        error_code = "smtp_unreachable"
    except smtplib.SMTPException:
        error_code = "smtp_delivery_failed"
    except OSError:
        error_code = "smtp_unreachable"
    except ValueError:
        error_code = "smtp_delivery_failed"
    with closing(connect()) as db:
        db.execute("UPDATE feedback_outbox SET status=?,sent_at=?,error_code=? WHERE id=?",
            ("sent" if sent else "queued", datetime.now(timezone.utc).isoformat() if sent else None,
             None if sent else error_code, feedback_id))
        db.commit()
    return "sent" if sent else "queued"


def retry_feedback_batch(stop_event, limit=5):
    """Retry at most five due messages; preserve active leases and failure backoff."""
    if stop_event.is_set() or smtp_config() is None:
        return 0
    now = time.time()
    with closing(connect()) as db:
        rows = db.execute("SELECT id,status,attempts,last_attempt FROM feedback_outbox WHERE status IN ('queued','sending') ORDER BY COALESCE(last_attempt,0),created_at").fetchall()
    attempted = 0
    for row in rows:
        if stop_event.is_set() or attempted >= min(limit, 5):
            break
        last = row["last_attempt"]
        if last is not None and (now-last < feedback_retry_delay(row["attempts"]) or (row["status"] == "sending" and now-last < 300)):
            continue
        deliver_feedback(row["id"], respect_backoff=True)
        attempted += 1
    return attempted


def feedback_worker(stop_event):
    while not stop_event.is_set():
        try:
            retry_feedback_batch(stop_event)
        except (sqlite3.Error, OSError):
            pass  # Retry next minute without logging message content or SMTP details.
        if stop_event.wait(60):
            return


def start_feedback_worker(stop_event):
    if smtp_config() is None:
        return None
    worker = threading.Thread(target=feedback_worker, args=(stop_event,), name="cflix-feedback", daemon=True)
    worker.start()
    return worker


def local_urls(host, port):
    if host not in ("0.0.0.0", "::"):
        return [f"http://{host}:{port}"]
    addresses = set()
    try:
        addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return [f"http://localhost:{port}"] + [f"http://{address}:{port}" for address in sorted(addresses) if not address.startswith("127.") and address != "0.0.0.0"]


def public_user(db, user):
    result = {key: user[key] for key in ("id", "name", "email", "role")}
    result["favorites"] = [r[0] for r in db.execute("SELECT movie_id FROM favorites WHERE user_id=?", (user["id"],))]
    result["history"] = {r["movie_id"]: {"position": r["position"], "duration": r["duration"], "updatedAt": r["updated_at"], "completed": bool(r["completed"])} for r in db.execute("SELECT * FROM history WHERE user_id=?", (user["id"],))}
    return result


def recommend(user, catalog=None):
    """Favori türüne +3, 10 sn üzeri izlenen türe +2; eşitlikte katalog puanı."""
    if catalog is None:
        with closing(connect()) as db:
            catalog = get_catalog(db)
    weights = {}
    for movie in catalog:
        score = (3 if movie["id"] in user["favorites"] else 0) + (2 if user["history"].get(movie["id"], {}).get("position", 0) > 10 else 0)
        weights[movie["genre"]] = weights.get(movie["genre"], 0) + score
    return [m["id"] for m in sorted(catalog, key=lambda m: (weights.get(m["genre"], 0), m["rating"]), reverse=True)]


class LimitedHTTPServer(ThreadingHTTPServer):
    """Bound worker creation; Caddy remains the public HTTP/TLS server."""
    request_queue_size = 64

    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(int(os.environ.get("MAX_CONNECTIONS", "64")))
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        # Never log raw requests, cookies, SMTP settings or exception payloads.
        print("HTTP isteği tamamlanamadı.", flush=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "CFlix"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(120)  # Idle socket bound, including upload reads.

    def client_ip(self):
        peer = ipaddress.ip_address(self.client_address[0])
        trusted = [ipaddress.ip_network(value.strip()) for value in
                   os.environ.get("TRUSTED_PROXY_CIDRS", "").split(",") if value.strip()]
        if any(peer in network for network in trusted):
            # Caddy overwrites X-Real-IP; never trust arbitrary X-Forwarded-For.
            try:
                return str(ipaddress.ip_address(self.headers.get("X-Real-IP", "")))
            except ValueError:
                pass
        return str(peer)

    def end_headers(self):
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; "
                         "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                         "font-src 'self' https://fonts.gstatic.com; "
                         "img-src 'self' https://images.unsplash.com; "
                         "media-src 'self' https://storage.googleapis.com; "
                         "connect-src 'self'; object-src 'none'; base-uri 'none'; "
                         "frame-ancestors 'none'; form-action 'self'")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # Kullanıcı girdilerini ve oturum bilgilerini günlüğe yazma.

    def send_json(self, status, payload, cookie=None):
        data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(data)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def read_json(self):
        if self.headers.get_content_type() != "application/json":
            raise ValueError("JSON gerekli")
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 16384:
            raise ValueError("Geçersiz istek boyutu")
        value = json.loads(self.rfile.read(length), parse_constant=lambda _: None)
        if not isinstance(value, dict):
            raise ValueError("Geçersiz istek")
        return value

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith("/media/"):
            return self.serve_media(path)
        if path.startswith("/api/"):
            return self.api(path)
        public = (ROOT / "public").resolve()
        file = (public / unquote(path).lstrip("/")).resolve() if path != "/" else public / "index.html"
        if not file.is_relative_to(public):
            return self.send_json(403, {"error": "Erişim engellendi."})
        if not file.is_file():
            return self.send_json(404, {"error": "Sayfa bulunamadı."})
        data = file.read_bytes()
        self.send_response(200)
        content_type = {".js": "text/javascript", ".css": "text/css", ".html": "text/html"}.get(file.suffix, mimetypes.guess_type(file.name)[0] or "application/octet-stream")
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") else ""))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_POST(self):
        if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
            return self.send_json(400, {"error": "Geçersiz istek uzunluğu."})
        if urlsplit(self.path).path != "/api/admin/uploads" and self.headers.get_content_type() != "application/json":
            return self.send_json(415, {"error": "JSON içerik türü gerekli."})
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        expected = os.environ.get("PUBLIC_ORIGIN", "").rstrip("/")
        allowed = (expected,) if expected else (f"http://{host}", f"https://{host}")
        if self.headers.get("Sec-Fetch-Site") == "cross-site" or (origin and origin not in allowed):
            # Windows may reset the connection before delivering the response if
            # a small POST body remains unread. Never drain arbitrary uploads.
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if 0 < length <= 16384 and not self.headers.get("Transfer-Encoding"):
                    previous_timeout = self.connection.gettimeout()
                    try:
                        self.connection.settimeout(1)
                        self.rfile.read(length)
                    finally:
                        self.connection.settimeout(previous_timeout)
            except (ValueError, OSError):
                pass
            return self.send_json(403, {"error": "Geçersiz kaynak."})
        self.api(urlsplit(self.path).path)

    def api(self, path):
        try:
            if path == "/api/health" and self.command in ("GET", "HEAD"):
                with closing(connect()) as health_db:
                    health_db.execute("SELECT 1 FROM users LIMIT 1").fetchone()
                return self.send_json(200, {"app": "CFlix", "version": APP_VERSION, "features": FEATURES})
            with closing(connect()) as db:
                if path == "/api/catalog" and self.command == "GET":
                    return self.send_json(200, {"movies": get_catalog(db)})
                token, user = self.session_user(db)
                if path in ("/api/login", "/api/register") and self.command == "POST":
                    return self.authenticate(db, path, token)
                if user is None:
                    return self.send_json(401, {"error": "Devam etmek için giriş yapın. Oturumunuz sona ermiş olabilir.", "code": "auth_required"})
                if path.startswith("/api/admin/"):
                    if user["role"] != "admin":
                        return self.send_json(403, {"error": "Bu işlem yalnızca yöneticiler içindir."})
                    if path == "/api/admin/uploads" and self.command == "POST":
                        return self.upload(db, user)
                    if path == "/api/admin/content" and self.command == "POST":
                        return self.create_content(db, user)
                    if path == "/api/admin/qualities" and self.command == "POST":
                        return self.add_quality(db, user)
                    if path == "/api/admin/mail-status" and self.command == "GET":
                        return self.send_json(200, mail_status(db))
                    return self.send_json(404, {"error": "İşlem bulunamadı."})
                if path == "/api/logout" and self.command == "POST":
                    with LOCK:
                        SESSIONS.pop(token, None)
                    secure = "; Secure" if os.environ.get("COOKIE_SECURE") == "1" else ""
                    return self.send_json(200, {"ok": True}, "ff_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0" + secure)
                if path == "/api/password" and self.command == "POST":
                    return self.change_password(db, user, token)
                if path == "/api/feedback" and self.command == "POST":
                    return self.create_feedback(db, user)
                if path == "/api/me" and self.command == "GET":
                    result = public_user(db, user)
                    return self.send_json(200, {"user": result, "recommendations": recommend(result)})
                if path == "/api/favorites" and self.command == "POST":
                    movie_id = self.read_json().get("id")
                    if not isinstance(movie_id, str) or not db.execute("SELECT 1 FROM content WHERE id=?", (movie_id,)).fetchone():
                        return self.send_json(404, {"error": "İçerik bulunamadı."})
                    exists = db.execute("SELECT 1 FROM favorites WHERE user_id=? AND movie_id=?", (user["id"], movie_id)).fetchone()
                    db.execute("DELETE FROM favorites WHERE user_id=? AND movie_id=?" if exists else "INSERT INTO favorites VALUES (?,?)", (user["id"], movie_id))
                    db.commit()
                    result = public_user(db, user)
                    return self.send_json(200, {"user": result, "recommendations": recommend(result)})
                if path == "/api/progress" and self.command == "POST":
                    data = self.read_json()
                    movie_id, position, duration = data.get("id"), data.get("position"), data.get("duration")
                    import math
                    if not isinstance(movie_id, str) or not db.execute("SELECT 1 FROM content WHERE id=?", (movie_id,)).fetchone() or type(position) not in (int, float) or type(duration) not in (int, float) or not math.isfinite(position) or not math.isfinite(duration) or not 0 <= position <= duration or duration <= 0:
                        return self.send_json(400, {"error": "Geçersiz izleme bilgisi."})
                    db.execute("INSERT OR REPLACE INTO history VALUES (?,?,?,?,?,?)", (user["id"], movie_id, position, duration, datetime.now(timezone.utc).isoformat(), int(position/duration >= .95)))
                    db.commit()
                    return self.send_json(200, {"ok": True})
                self.send_json(404, {"error": "İşlem bulunamadı."})
        except (ValueError, TypeError, OverflowError):
            self.send_json(400, {"error": "Geçersiz istek."})
        except sqlite3.Error:
            self.send_json(503, {"error": "Kayıt işlemi tamamlanamadı. Lütfen tekrar deneyin."})
        except OSError:
            self.send_json(503, {"error": "Dosya kaydedilemedi. Disk alanını ve bağlantınızı kontrol edin."})

    def session_user(self, db):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        token = cookie["ff_session"].value if "ff_session" in cookie else ""
        with LOCK:
            now = time.time()
            for expired in [k for k, value in SESSIONS.items() if value[1] < now]:
                SESSIONS.pop(expired, None)
            session = SESSIONS.get(token)
        user = db.execute("SELECT * FROM users WHERE id=?", (session[0],)).fetchone() if session else None
        return token, user

    def change_password(self, db, user, token):
        with LOCK:
            now = time.time()
            for expired in [key for key, value in ATTEMPTS.items() if value[1] < now]:
                ATTEMPTS.pop(expired, None)
            key = ("password", user["id"], self.client_ip())
            count, until = ATTEMPTS.get(key, (0, now + 600))
            ATTEMPTS[key] = (count + 1, until)
        if count >= 10:
            return self.send_json(429, {"error": "Çok fazla şifre değiştirme denemesi. 10 dakika sonra tekrar deneyin.", "code": "password_rate_limited"})
        data = self.read_json()
        current, new = data.get("currentPassword"), data.get("newPassword")
        if not isinstance(current, str) or not 8 <= len(current) <= 128:
            return self.send_json(400, {"error": "Mevcut şifreni eksiksiz gir; 8–128 karakter olmalı.", "code": "invalid_current_password"})
        if not isinstance(new, str) or not 8 <= len(new) <= 128:
            return self.send_json(400, {"error": "Yeni şifre 8–128 karakter olmalı.", "code": "invalid_new_password"})
        if not hmac.compare_digest(password_hash(current, user["salt"]), user["password"]):
            return self.send_json(401, {"error": "Mevcut şifre hatalı. Giriş yaparken kullandığın şifreyi gir.", "code": "current_password_incorrect"})
        if current == new:
            return self.send_json(400, {"error": "Yeni şifre mevcut şifreden farklı olmalı.", "code": "password_unchanged"})
        salt = secrets.token_hex(16)
        hashed = password_hash(new, salt)
        # Compare-and-swap prevents overlapping requests from replacing a newer password.
        # Session creation uses the same lock to exclude a login verified against the old hash.
        with LOCK:
            updated = db.execute("UPDATE users SET salt=?,password=? WHERE id=? AND password=?",
                (salt, hashed, user["id"], user["password"])).rowcount
            db.commit()
            if updated:
                for other in [key for key, value in SESSIONS.items() if value[0] == user["id"] and key != token]:
                    SESSIONS.pop(other, None)
        if not updated:
            return self.send_json(401, {"error": "Şifren değişti. Mevcut şifrenle tekrar dene.", "code": "password_changed"})
        self.send_json(200, {"ok": True})

    def create_feedback(self, db, user):
        data = self.read_json()
        kind, message, subject = data.get("kind"), data.get("message"), data.get("subject", "")
        if kind not in ("suggestion", "complaint") or not isinstance(message, str) or not 10 <= len(message.strip()) <= 4000 or not isinstance(subject, str) or len(subject.strip()) > 120 or "\r" in subject or "\n" in subject:
            return self.send_json(400, {"error": "Öneri veya şikayet seç; mesaj 10–4000, konu en fazla 120 karakter olmalı.", "code": "invalid_feedback"})
        now = time.time()
        with LOCK:
            for expired in [key for key, value in ATTEMPTS.items() if value[1] < now]:
                ATTEMPTS.pop(expired, None)
            key = ("feedback", user["id"])
            count, until = ATTEMPTS.get(key, (0, now + 600))
            ATTEMPTS[key] = (count + 1, until)
        if count >= 5:
            return self.send_json(429, {"error": "10 dakikada en fazla 5 bildirim gönderebilirsin. Daha sonra tekrar dene.", "code": "feedback_rate_limited"})
        feedback_id = secrets.token_hex(16)
        db.execute("INSERT INTO feedback_outbox (id,user_id,kind,subject,message,sender_name,sender_email,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (feedback_id, user["id"], kind, subject.strip(), message.strip(), user["name"], user["email"], datetime.now(timezone.utc).isoformat()))
        db.commit()
        status = deliver_feedback(feedback_id)
        row = db.execute("SELECT error_code FROM feedback_outbox WHERE id=?", (feedback_id,)).fetchone()
        code = row["error_code"] if row and row["error_code"] in SMTP_SAFE_MESSAGES else None
        message = "Bildirimin e-posta sunucusuna iletildi." if status == "sent" else "Bildirimin kaydedildi; e-posta teslimatı için sırada bekliyor."
        if status != "sent" and code == "smtp_not_configured":
            message = "E-posta bağlantısı henüz yapılandırılmadı; mesajın kaydedildi ve bağlantı kurulduğunda yeniden denenecek."
        self.send_json(201 if status == "sent" else 202, {"id": feedback_id, "status": status,
            "code": code, "message": message})

    def upload(self, db, user):
        from urllib.parse import parse_qs
        kind = parse_qs(urlsplit(self.path).query).get("kind", [""])[0]
        if kind not in ("video", "cover"):
            return self.send_json(400, {"error": "Dosya türü video veya cover olmalı."})
        size = int(self.headers.get("Content-Length", "0"))
        limit = 2*1024**3 if kind == "video" else 10*1024**2
        if not 0 < size <= limit:
            return self.send_json(413, {"error": "Video en fazla 2 GB, kapak en fazla 10 MB olabilir; dosya boş olamaz."})
        if self.headers.get("Transfer-Encoding"):
            return self.send_json(400, {"error": "Dosya uzunluğu belirtilmeli."})
        prefix = self.rfile.read(min(32, size))
        mime, extension = "", ""
        if kind == "video" and len(prefix) >= 12 and prefix[4:8] == b"ftyp":
            mime, extension = "video/mp4", ".mp4"
        elif kind == "cover":
            if prefix.startswith(b"\xff\xd8\xff"):
                mime, extension = "image/jpeg", ".jpg"
            elif prefix.startswith(b"\x89PNG\r\n\x1a\n"):
                mime, extension = "image/png", ".png"
            elif prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP":
                mime, extension = "image/webp", ".webp"
        if not mime:
            return self.send_json(400, {"error": "Geçersiz dosya. Video MP4; kapak JPG, PNG veya WebP olmalı."})
        aid = secrets.token_hex(16)
        target = DATA_DIR / "media" / (aid + extension)
        try:
            with target.open("xb") as output:
                output.write(prefix)
                remaining = size-len(prefix)
                while remaining:
                    chunk = self.rfile.read(min(1024*1024, remaining))
                    if not chunk:
                        raise ValueError("Yükleme yarım kaldı")
                    output.write(chunk)
                    remaining -= len(chunk)
            db.execute("INSERT INTO assets VALUES (?,?,?,?,?)", (aid, target.name, kind, mime, user["id"]))
            db.commit()
        except Exception:
            target.unlink(missing_ok=True)
            raise
        self.send_json(201, {"asset": {"id": aid, "kind": kind, "url": f"/media/{aid}"}})

    def create_content(self, db, user):
        data = self.read_json()
        if any(not isinstance(data.get(key), str) for key in ("title", "description", "genre")):
            return self.send_json(400, {"error": "Başlık, açıklama ve tür metin olmalı."})
        title, description, genre = (data[key].strip() for key in ("title", "description", "genre"))
        year, kind = data.get("year"), data.get("type")
        if not 1 <= len(title) <= 100 or not 1 <= len(description) <= 2000 or genre not in {m["genre"] for m in CATALOG} or kind not in ("Film", "Dizi") or type(year) is not int or not 1888 <= year <= 2100:
            return self.send_json(400, {"error": "Başlık, açıklama, tür, film/dizi seçimi ve 1888–2100 arasında yıl girin."})
        video_id, cover_id = data.get("videoId"), data.get("coverId")
        if not isinstance(video_id, str) or (cover_id is not None and not isinstance(cover_id, str)):
            return self.send_json(400, {"error": "Video veya kapak bilgisi geçersiz."})
        asset = db.execute("SELECT * FROM assets WHERE id=? AND kind='video' AND owner_id=?", (video_id, user["id"])).fetchone()
        cover = db.execute("SELECT * FROM assets WHERE id=? AND kind='cover' AND owner_id=?", (cover_id, user["id"])).fetchone() if cover_id else None
        if not asset or (cover_id and not cover):
            return self.send_json(400, {"error": "Önce video ve seçtiğiniz kapağı yükleyin."})
        movie_id = secrets.token_hex(12)
        movie = dict(id=movie_id, title=title, description=description, genre=genre, type=kind, year=year, rating=0, duration=0, photo=None, cover=f"/media/{cover_id}" if cover else None, video=f"/media/{video_id}", demo=False, qualities=[])
        db.execute("INSERT INTO content VALUES (?,?,?)", (movie_id, json.dumps(movie, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
        db.commit()
        self.send_json(201, {"movie": movie})

    def add_quality(self, db, user):
        data = self.read_json()
        movie_id, asset_id, quality = data.get("id"), data.get("assetId"), data.get("quality")
        if not isinstance(movie_id, str) or not isinstance(asset_id, str) or quality not in QUALITY_LABELS:
            return self.send_json(400, {"error": "İçerik, video dosyası ve geçerli görüntü kalitesi seçin."})
        # Acquire the SQLite write lock before reading to preserve concurrent label updates.
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT payload FROM content WHERE id=?", (movie_id,)).fetchone()
        if not row:
            return self.send_json(404, {"error": "İçerik bulunamadı."})
        movie = json.loads(row["payload"])
        if movie.get("demo", True):
            return self.send_json(400, {"error": "Kalite seçenekleri yalnızca yüklenen içeriklere eklenebilir."})
        asset = db.execute("SELECT id FROM assets WHERE id=? AND kind='video' AND owner_id=?", (asset_id, user["id"])).fetchone()
        if not asset:
            return self.send_json(400, {"error": "Önce bu yönetici hesabıyla alternatif MP4 dosyasını yükleyin."})
        qualities = [entry for entry in movie.get("qualities", []) if entry["label"] != quality]
        qualities.append({"label": quality, "src": f"/media/{asset_id}"})
        movie["qualities"] = sorted(qualities, key=lambda entry: QUALITY_LABELS.index(entry["label"]))
        db.execute("UPDATE content SET payload=? WHERE id=?", (json.dumps(movie, ensure_ascii=False), movie_id))
        db.commit()
        self.send_json(200, {"movie": movie})

    def serve_media(self, path):
        asset_id = path.removeprefix("/media/")
        if not re.fullmatch(r"[a-f0-9]{32}", asset_id):
            return self.send_json(404, {"error": "Dosya bulunamadı."})
        with closing(connect()) as db:
            asset = db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
            if not asset:
                return self.send_json(404, {"error": "Dosya bulunamadı."})
            if asset["kind"] == "video" and self.session_user(db)[1] is None:
                return self.send_json(401, {"error": "Videoyu izlemek için giriş yapın."})
        media_root = (DATA_DIR / "media").resolve()
        file = (media_root / asset["filename"]).resolve()
        if not file.is_relative_to(media_root):
            return self.send_json(403, {"error": "Erişim engellendi."})
        try:
            source = file.open("rb")
        except FileNotFoundError:
            return self.send_json(404, {"error": "Dosya bulunamadı."})
        with source:
            size = os.fstat(source.fileno()).st_size
            start, end, status = 0, size-1, 200
            # RFC Range, HEAD isteğinde uygulanmaz.
            range_header = self.headers.get("Range") if self.command != "HEAD" else None
            if range_header:
                match = re.fullmatch(r"bytes=([0-9]{0,20})-([0-9]{0,20})", range_header)
                valid = match and any(match.groups())
                if valid:
                    first, last = match.groups()
                    if first:
                        start = int(first)
                        end = min(int(last), size-1) if last else size-1
                    else:
                        suffix = int(last)
                        valid = suffix > 0
                        start = max(0, size-suffix)
                    valid = valid and 0 <= start <= end < size
                if not valid:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206
            self.send_response(status)
            self.send_header("Content-Type", asset["mime"])
            self.send_header("Content-Length", str(end-start+1))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "private, no-store" if asset["kind"] == "video" else "public, max-age=86400")
            self.send_header("X-Content-Type-Options", "nosniff")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if self.command == "HEAD":
                return
            source.seek(start)
            remaining = end-start+1
            try:
                while remaining:
                    chunk = source.read(min(1024*1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # Kullanıcı videoda başka konuma geçti veya oynatıcıyı kapattı.

    def authenticate(self, db, path, old_token):
        with LOCK:
            now = time.time()
            for key in [k for k,v in ATTEMPTS.items() if v[1] < now]:
                ATTEMPTS.pop(key, None)
            key = self.client_ip()
            count, until = ATTEMPTS.get(key, (0, now + 600))
            ATTEMPTS[key] = (count + 1, until)
        if count >= 30:
            return self.send_json(429, {"error": "Çok fazla deneme. 10 dakika sonra tekrar deneyin."})
        data = self.read_json()
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or not 8 <= len(password) <= 128:
            return self.send_json(400, {"error": "Geçerli bir e-posta ve 8–128 karakterlik şifre girin."})
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if path == "/api/register":
            name = str(data.get("name", "")).strip()
            if not 2 <= len(name) <= 40:
                return self.send_json(400, {"error": "İsminiz 2–40 karakter olmalı."})
            if user:
                return self.send_json(409, {"error": "Bu e-posta zaten kayıtlı. Giriş yapabilirsiniz."})
            salt, uid = secrets.token_hex(16), secrets.token_hex(12)
            try:
                db.execute("INSERT INTO users (id,name,email,salt,password) VALUES (?,?,?,?,?)", (uid, name, email, salt, password_hash(password, salt)))
                db.commit()
            except sqlite3.IntegrityError:
                return self.send_json(409, {"error": "Bu e-posta zaten kayıtlı."})
            user = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        else:
            candidate = password_hash(password, user["salt"] if user else "0"*32)
            if not user or not hmac.compare_digest(candidate, user["password"]):
                return self.send_json(401, {"error": "E-posta veya şifre hatalı."})
        token = secrets.token_urlsafe(32)
        with LOCK:
            latest = db.execute("SELECT password FROM users WHERE id=?", (user["id"],)).fetchone()
            unchanged = latest and hmac.compare_digest(latest["password"], user["password"])
            if unchanged:
                SESSIONS.pop(old_token, None)
                SESSIONS[token] = (user["id"], time.time() + 7*86400)
        if not unchanged:
            return self.send_json(401, {"error": "Şifren değişti. Yeni şifrenle tekrar giriş yap."})
        secure = "; Secure" if os.environ.get("COOKIE_SECURE") == "1" else ""
        self.send_json(200, {"user": public_user(db, user)}, f"ff_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800{secure}")


if __name__ == "__main__":
    os.umask(0o077)
    init_db()
    port = int(os.environ.get("PORT", "3000"))
    host = os.environ.get("HOST", "0.0.0.0")
    feedback_stop = threading.Event()
    delivery_worker = None
    try:
        with LimitedHTTPServer((host, port), Handler) as httpd:
            print(f"CFlix {APP_VERSION} hazır:", flush=True)
            for address in local_urls(host, port):
                print(f"  {address}", flush=True)
            delivery_worker = start_feedback_worker(feedback_stop)
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nCFlix kapatıldı.")
    except OSError as error:
        if getattr(error, "winerror", None) == 10048 or error.errno in (48, 98, 10048):
            print(f"Port {port} kullanımda; eski CFlix sunucusunu Ctrl+C ile kapatın ve tekrar başlatın.", flush=True)
        else:
            print("Sunucu başlatılamadı. HOST/PORT ayarlarını ve ağ erişim izinlerini kontrol edin.", flush=True)
        raise SystemExit(1)
    finally:
        feedback_stop.set()
        if delivery_worker is not None:
            delivery_worker.join(timeout=1)
