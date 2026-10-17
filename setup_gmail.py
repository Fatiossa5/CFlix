"""Gmail SMTP'yi bu bilgisayarda kurar; gizli bilgileri ekrana yazmaz."""
from contextlib import closing
import getpass
import os
from pathlib import Path
import re
import smtplib
import ssl

import server


def gmail_values(username, password):
    username = username.strip()
    password = re.sub(r"\s+", "", password)
    if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", username):
        raise ValueError("Gecerli bir Google hesap e-postasi girin.")
    if not re.fullmatch(r"[A-Za-z0-9]{16}", password):
        raise ValueError("Google'dan alinan 16 karakterlik Uygulama Sifresini girin. Normal hesap sifrenizi kullanmayin.")
    return {"SMTP_PROVIDER": "gmail", "SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587",
            "SMTP_USERNAME": username, "SMTP_PASSWORD": password, "SMTP_FROM": username,
            "SMTP_STARTTLS": "1", "SMTP_SSL": "0"}


def save_values(values, path):
    """İlgisiz ayarları koruyarak .env dosyasını atomik günceller."""
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    kept = [line for line in text.splitlines() if line.strip().removeprefix("export ").partition("=")[0].strip() not in values]
    temp = path.with_name(path.name + ".tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as output:
            output.write("\n".join(kept + [f"{key}={value}" for key, value in values.items()]) + "\n")
        os.chmod(temp, 0o600)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def verify_login(values):
    with smtplib.SMTP(values["SMTP_HOST"], int(values["SMTP_PORT"]), timeout=15) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(values["SMTP_USERNAME"], values["SMTP_PASSWORD"])


def main():
    print("CFlix - Gmail kurulumu")
    print("Google hesabinizda 2 Adimli Dogrulama acik olmali.")
    print("Uygulama Sifresi olusturun: https://myaccount.google.com/apppasswords")
    print("Sifreyi sohbete yazmayin; bu ekrandaki giris gizlidir.")
    try:
        values = gmail_values(input("Gonderici Google hesap e-postasi: "), getpass.getpass("16 karakterlik Uygulama Sifresi: "))
        verify_login(values)
        save_values(values, server.ROOT / ".env")
        os.environ.update(values)
        print("Gmail baglantisi dogrulandi. Ayarlar yerel .env dosyasina kaydedildi.")
        print("Alici adresi sitede gosterilmeyecek.")
        server.init_db()
        with closing(server.connect()) as db:
            pending = [row[0] for row in db.execute("SELECT id FROM feedback_outbox WHERE status='queued' ORDER BY created_at LIMIT 5")]
        if pending:
            answer = input(f"Bekleyen {len(pending)} mesaji simdi e-postayla gonderelim mi? [e/H]: ").strip().lower()
            if answer == "e":
                sent = sum(server.deliver_feedback(fid) == "sent" for fid in pending)
                print(f"E-posta sunucusuna iletilen: {sent}; bekleyen: {len(pending)-sent}.")
        print("Acik CFlix sunucusunu Ctrl+C ile kapatip baslat.bat ile yeniden acin.")
    except smtplib.SMTPAuthenticationError:
        print("Gmail girisi kabul edilmedi. Normal sifre yerine gecerli Uygulama Sifresi kullanin. Ayarlar degistirilmedi.")
        return 1
    except (smtplib.SMTPException, OSError):
        print("Gmail baglantisi veya kayit tamamlanamadi. Internet/SMTP erisimi ve dosya izinlerini kontrol edin.")
        return 1
    except (ValueError, EOFError) as error:
        print(str(error) if isinstance(error, ValueError) else "Giris tamamlanmadi.")
        return 1
    except KeyboardInterrupt:
        print("\nKurulum iptal edildi.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
