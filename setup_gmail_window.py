"""Gmail için standart Python ile çalışan, yalnız yerel bilgisayara açık kurulum formu."""
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import secrets
import smtplib
import sqlite3
import sys
import threading
import urllib.request
import webbrowser

import server
from setup_gmail import gmail_values, save_values, verify_login


def configure_account(email, password):
    values = gmail_values(email, password)
    verify_login(values)
    save_values(values, server.ROOT / ".env")
    os.environ.update(values)


def send_pending():
    server.init_db()
    with closing(server.connect()) as db:
        ids = [row[0] for row in db.execute("SELECT id FROM feedback_outbox WHERE status='queued' ORDER BY created_at LIMIT 5")]
    sent = sum(server.deliver_feedback(feedback_id) == "sent" for feedback_id in ids)
    return sent, len(ids)-sent


def safe_error(error):
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return "Gmail girişi kabul etmedi. Normal şifren yerine Google'dan oluşturduğun 16 karakterlik Uygulama Şifresini gir."
    if isinstance(error, ValueError):
        return "Geçerli bir e-posta adresi ve 16 harf/rakamdan oluşan Google Uygulama Şifresi gir."
    if isinstance(error, sqlite3.Error):
        return "Mesaj kayıtlarına ulaşılamadı. Kurulumu kapatıp tekrar aç."
    if isinstance(error, PermissionError):
        return "Ayar dosyasına yazılamadı. Proje klasörünün yazılabilir olduğunu kontrol et."
    return "Bağlantı tamamlanamadı. İnternet bağlantını ve Gmail SMTP erişimini kontrol edip tekrar dene."


PAGE = '''<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CFlix Gmail Kurulumu</title>
<style nonce="NONCE">*{box-sizing:border-box}body{margin:0;background:#0d1420;color:#edf1f8;font:15px Arial,sans-serif;min-height:100vh;padding:35px 16px;display:grid;place-items:center}main{width:100%;max-width:510px;background:#151f2f;border:1px solid #ffffff18;border-radius:18px;padding:32px}h1{font-size:26px;margin:0 0 15px}.tag{font-size:11px;color:#ffb771;letter-spacing:1px}p{line-height:1.7;color:#b8c2d2;font-size:13px}label{display:block;font-weight:600;margin-top:22px}input{display:block;width:100%;padding:14px;margin-top:10px;background:#0d1522;color:#fff;border:1px solid #536077;border-radius:8px;font:inherit}button{width:100%;padding:14px;border:0;border-radius:8px;margin-top:18px;background:#ffad6d;color:#151515;font:600 14px Arial;cursor:pointer}button:disabled{opacity:.5;cursor:wait}a{color:#ffc28e}#status{white-space:pre-line;overflow-wrap:anywhere;min-height:24px}#send{background:#27374e;color:#fff;border:1px solid #52617b}small{display:block;color:#9aa9bc;line-height:1.6;margin-top:12px}input:focus-visible,button:focus-visible,a:focus-visible{outline:2px solid #ffad6d;outline-offset:3px}</style></head><body><main><span class="tag">YALNIZ BU BİLGİSAYARDA · GİZLİ KURULUM</span><h1>CFlix Gmail Kurulumu</h1><p>E-posta adresini ve Google Uygulama Şifresini aşağıdaki kutulara yaz.</p><form id="form"><label for="email">Gönderici Gmail adresi</label><input id="email" name="email" type="email" autocomplete="username" placeholder="Gmail adresini buraya yaz" maxlength="254" required autofocus><label for="password">Google Uygulama Şifresi</label><input id="password" name="password" type="password" autocomplete="off" placeholder="16 karakterlik uygulama şifresi" minlength="16" maxlength="64" required><small>Normal Gmail şifreni kullanma. Google hesabında 2 Adımlı Doğrulama açık olmalı.</small><p><a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer">Google'da Uygulama Şifresi oluştur ↗</a></p><button id="save" type="submit">Bağlantıyı doğrula ve kaydet</button></form><button id="send" type="button" disabled>Bekleyen mesajları gönder</button><p id="status" role="status">İki alanı doldurduktan sonra kaydet düğmesine bas.</p><small>İşin bitince bu sekmeyi kapat; kurulumun siyah penceresinde Ctrl+C yap.</small></main>
<script nonce="NONCE">const form=document.getElementById('form'),status=document.getElementById('status'),send=document.getElementById('send');let configured=false;
function busy(value){for(const element of form.elements)element.disabled=value;send.disabled=value||!configured;}
async function request(action,data){const response=await fetch(location.pathname+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw new Error(result.error||'İşlem tamamlanamadı.');return result;}
form.addEventListener('submit',async event=>{event.preventDefault();const data=Object.fromEntries(new FormData(form));busy(true);status.textContent='Gmail bağlantısı doğrulanıyor…';try{await request('configure',data);configured=true;document.getElementById('password').value='';status.textContent='Gmail doğrulandı ve kaydedildi. Bekleyen mesajları gönderebilirsin. Sonra CFlix sunucusunu kapatıp baslat.bat ile yeniden aç.';}catch(error){status.textContent=error.message;}finally{busy(false);}});
send.addEventListener('click',async()=>{busy(true);status.textContent='Bekleyen mesajlar iletiliyor…';try{const data=await request('send',{});status.textContent='E-posta sunucusuna iletilen: '+data.sent+'. Bekleyen: '+data.pending+'. Gelen kutusunu ve spam klasörünü kontrol et.';}catch(error){status.textContent=error.message;}finally{busy(false);}});</script></body></html>'''


class SetupHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, status, data, html=False):
        payload = data.encode("utf-8") if html else json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8" if html else "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", f"default-src 'none'; style-src 'nonce-{self.server.nonce}'; script-src 'nonce-{self.server.nonce}'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def allowed_host(self):
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def do_GET(self):
        if not self.allowed_host() or self.path != self.server.setup_path:
            return self.reply(404, {"error": "Kurulum sayfası bulunamadı."})
        self.reply(200, PAGE.replace("NONCE", self.server.nonce), html=True)

    def do_POST(self):
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if not self.allowed_host() or self.headers.get("Origin") != origin:
            return self.reply(403, {"error": "Bu işlem yalnız yerel kurulum sayfasından yapılabilir."})
        if self.path not in (self.server.setup_path+"configure", self.server.setup_path+"send"):
            return self.reply(404, {"error": "İşlem bulunamadı."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096 or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError()
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError()
            if not self.server.action_lock.acquire(blocking=False):
                return self.reply(409, {"error": "Bir işlem sürüyor. Tamamlanmasını bekle."})
            try:
                if self.path.endswith("/configure"):
                    email, password = data.get("email"), data.get("password")
                    if not isinstance(email, str) or not isinstance(password, str):
                        raise ValueError()
                    configure_account(email, password)
                    self.server.configured = True
                    return self.reply(200, {"ok": True})
                if not self.server.configured:
                    return self.reply(400, {"error": "Önce Gmail bağlantısını doğrula ve kaydet."})
                sent, pending = send_pending()
                return self.reply(200, {"sent": sent, "pending": pending})
            finally:
                self.server.action_lock.release()
        except Exception as error:
            self.reply(400, {"error": safe_error(error)})


def make_server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), SetupHandler)
    httpd.setup_path = "/"+secrets.token_urlsafe(32)+"/"
    httpd.nonce = secrets.token_urlsafe(24)
    httpd.configured = False
    httpd.action_lock = threading.Lock()
    return httpd


def main():
    with make_server() as httpd:
        url = f"http://127.0.0.1:{httpd.server_port}{httpd.setup_path}"
        if "--check-ui" in sys.argv:
            worker = threading.Thread(target=httpd.serve_forever, daemon=True)
            worker.start()
            try:
                with urllib.request.urlopen(url, timeout=3) as response:
                    html = response.read().decode("utf-8")
                    assert 'id="email"' in html and 'type="password"' in html
                    assert "Gönderici Gmail adresi" in html
                print("Gmail UI OK: local browser form with email and masked password fields; no SMTP request.")
            finally:
                httpd.shutdown()
                worker.join()
            return 0
        print("CFlix Gmail kurulumu - Form tarayicida aciliyor.", flush=True)
        print("Tarayici acilmazsa bu baglantiyi bu bilgisayarda acin:", flush=True)
        print(url, flush=True)
        print("E-posta ve Uygulama Sifresini tarayicidaki kutulara yazin.", flush=True)
        print("Isiniz bitince bu pencerede Ctrl+C yapin.", flush=True)
        try:
            webbrowser.open(url)
        except webbrowser.Error:
            pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nKurulum kapatildi.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
