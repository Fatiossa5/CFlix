"""Yerel veritabanında yönetici oluşturur; mevcut hesabı değiştirmez."""
import argparse
from contextlib import closing
import secrets

import server


def main():
    parser = argparse.ArgumentParser(description="CFlix yonetici hesabi olustur")
    parser.add_argument("--email", default="admin@cflix.local")
    parser.add_argument("--name", default="Admin")
    args = parser.parse_args()
    email = args.email.strip().lower()
    if not server.re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254:
        parser.error("Gecerli bir e-posta girin.")
    if not 2 <= len(args.name.strip()) <= 40:
        parser.error("Isim 2-40 karakter olmali.")
    server.init_db()
    with closing(server.connect()) as db:
        if db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            parser.exit(1, "Bu hesap zaten mevcut; sifresi ve yetkileri degistirilmedi.\n")
        password = secrets.token_urlsafe(15)
        salt = secrets.token_hex(16)
        db.execute("INSERT INTO users (id,name,email,salt,password,role) VALUES (?,?,?,?,?,?)",
                   (secrets.token_hex(12), args.name.strip(), email, salt, server.password_hash(password, salt), "admin"))
        db.commit()
    print(f"E-posta: {email}\nSifre: {password}\nRol: admin")


if __name__ == "__main__":
    main()
