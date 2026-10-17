"""Kayıtlı bildirimlerin bekleyen e-posta teslimatını yeniden dene."""
import argparse
from contextlib import closing
import time

import server


def main():
    parser = argparse.ArgumentParser(description="CFlix bekleyen bildirimleri yeniden ilet")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("Limit 1–100 arasında olmalı.")
    server.init_db()
    if server.smtp_config() is None:
        parser.exit(1, "SMTP ayarları eksik veya geçersiz; bildirimler kayıtlı olarak bekliyor.\n")
    with closing(server.connect()) as db:
        ids = [row[0] for row in db.execute("SELECT id FROM feedback_outbox WHERE status='queued' OR (status='sending' AND last_attempt<?) ORDER BY created_at LIMIT ?", (time.time()-300, args.limit))]
    sent = sum(server.deliver_feedback(feedback_id) == "sent" for feedback_id in ids)
    print(f"İletilen: {sent}; bekleyen: {len(ids)-sent}")


if __name__ == "__main__":
    main()
