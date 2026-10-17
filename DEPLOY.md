# FatihFlix: Ubuntu VPS üzerinde yayın

Bu rehber tek VPS, tek Python süreci ve Caddy içindir. Gerçek sunucu kurulumu, alan adı tahsisi veya genel HTTPS doğrulaması yapılmadı. Bilgisayarınız kapalıyken hizmetin sürmesi için uygulama sürekli açık VPS'te çalışmalıdır.

Komutlar aksi yazılmadıkça VPS'te Bash ile çalıştırılır. `read` sorularına kendi gerçek bilgilerinizi girin. Mevcut sunucuda başka hizmetler varsa port ve ağ çakışmasını önce kontrol edin.

## 1. VPS hazırlığı

Ubuntu 24.04 LTS gibi Docker'ın desteklediği bir sürüm, SSH, sudo yetkisi ve medya/yedekleri karşılayacak disk gerekir. SMTP çıkışının sağlayıcıda açık olduğunu doğrulayın. Ücretli kaynak oluşturma sizin kararınızdır; bu çalışmada oluşturulmadı.

Yerel terminalde:

```sh
read -r -p 'VPS SSH kullanıcısı ve adresi (kullanici@adres): ' VPS_SSH
ssh "$VPS_SSH"
```

VPS'te:

```sh
sudo apt update
sudo apt upgrade -y
sudo apt install -y ca-certificates curl git ufw dnsutils python3
```

## 2. Docker ve Compose kurulumu

Yeni Ubuntu sunucuda Docker'ın resmi apt deposunu kullanın. Mevcut Docker/containerd kurulumu varsa önce [resmi uyumluluk ve kurulum adımlarını](https://docs.docker.com/engine/install/ubuntu/) inceleyin; başka hizmetleri çalıştıran paketleri körlemesine kaldırmayın.

```sh
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
```

Docker komutları burada `sudo` ile kullanılır. Docker grubu sunucuda root düzeyinde yetki verebilir.

## 3. GitHub'dan kaynak alma

GitHub'a gönderme bu görevde yapılmadı. Önce bölüm 14'teki kaynak ve geçmiş denetimini kendi deponuzda tamamlayın. Yalnızca temiz kaynakları seçtiğiniz depoya gönderin.

```sh
read -r -p 'Kaynak deponuzun klon URL adresi: ' REPO_URL
git clone "$REPO_URL" fatihflix
cd fatihflix
git rev-parse HEAD
```

Özel depoda SSH anahtarı veya kimlik bilgisi yöneticisi kullanın; token'ı URL'ye yazmayın.

## 4. Alan adı, DNS ve portlar

DNS panelinde seçtiğiniz hostname için A kaydını VPS'in gerçek IPv4 adresine yönlendirin. IPv6 gerçekten çalışıyorsa AAAA ekleyin; çalışmayan AAAA sertifika ve erişim sorunlarına neden olabilir. `www` ayrı hostname'dir; kurulum tek hostname kullanır. İlk kurulumda araya CDN/proxy eklemeyin.

```sh
read -r -p 'Gerçek hostname (https:// ve yol olmadan): ' DOMAIN
dig +short A "$DOMAIN"
dig +short AAAA "$DOMAIN"
# SSH farklı porttaysa enable öncesinde o portu ayrıca açın.
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw enable
sudo ufw status
```

VPS sağlayıcısının ağ güvenlik duvarında da SSH ve 80/443 izinleri gerekir. 3000'i açmayın. Docker'ın yayınladığı portlar UFW kurallarını aşabilir; Compose yalnızca Caddy portlarını yayınlar. Gmail için dışarı TCP 587 (STARTTLS) veya 465 (TLS), ayrıca DNS ve sertifikalar için dış bağlantı gerekir.

## 5. Üretim .env dosyası

```sh
umask 077
cp -n .env.example .env
chmod 600 .env
nano .env
```

`CFLIX_DOMAIN` alanına gerçek hostname'i girin. Şema, yol, port veya birden fazla hostname yazmayın. `.env` mevcutsa üzerine yazmayın. Compose `HOST=0.0.0.0`, `PORT=3000`, `DATA_DIR=/data`, `COOKIE_SECURE=1`, `PUBLIC_ORIGIN=https://hostname` ayarlarını sabitler; yerel HTTP yapılandırması korunur. VPS dosyasını yerel `.env` yerine örnek dosyadan hazırlayın.

E-posta için `FEEDBACK_RECIPIENT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` girin. Gmail uygulama şifresi kullanın. `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_STARTTLS=1`, `SMTP_SSL=0` varsayılandır. Şifreleri komut satırına, Git'e, ekran görüntüsüne veya sohbete yazmayın. Compose'da `$` içeren sırları tek tırnakla yazın. Docker yetkisi olan kişiler container ortamını okuyabilir.

Eksik/geçersiz alıcı veya SMTP ayarında mesajlar SQLite kuyruğunda kalır. Gerçek gönderimi kendi hesabınızla ayrıca doğrulayın. Yerel Gmail kurulum aracı alıcıyı belirlemez; `.env` içinden ayrıca ayarlayın. Üretimde kurulum penceresini internete açmayın. SMTP kabulü gelen kutusuna teslim garantisi değildir.

## 6. İmaj ve kalıcı depolama hazırlığı

```sh
sudo docker compose config --quiet
sudo docker compose build --pull app
sudo docker compose run --rm --no-deps app python -c "import os; from pathlib import Path; p=Path('/data'); print('UID:',os.getuid(),'Yazilabilir:',os.access(p,os.W_OK)); assert os.access(p,os.W_OK)"
sudo docker compose run --rm --no-deps proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

`config --quiet` sırları yazdırmadan doğrular. Normal `docker compose config` sırları açığa çıkarabilir. Uygulama UID/GID 10001, salt okunur imaj ve `/data` volume'u ile çalışır. Varsayılan volume adı `fatihflix_data`; `.env` içindeki `CFLIX_DATA_VOLUME` ile değiştirilebilir. Yeni volume sahipliği imajdan gelir. Caddy sertifikaları ayrı kalıcı volume'lardadır. SQLite ve `media/` birlikte `/data` içinde tutulur.

Eski/elle taşınmış volume yazılamıyorsa uygulama durmuşken:

```sh
sudo docker compose stop app
sudo docker compose run --rm --no-deps --user 0 --cap-add CHOWN --cap-add FOWNER --cap-add DAC_OVERRIDE app python -c "import os; from pathlib import Path; p=Path('/data'); os.chown(p,10001,10001); os.chmod(p,0o700); [(os.chown(x,10001,10001),os.chmod(x,0o700 if x.is_dir() else 0o600)) for x in p.rglob('*') if not x.is_symlink()]"
```

Bind mount kullanacaksanız aynı UID/GID izinlerini host'ta hazırlayın. Compose ağı `172.30.86.0/24`, Caddy `.3`, app `.2` kullanır. Ağ çakışırsa subnet'i, iki IP'yi ve `TRUSTED_PROXY_CIDRS` değerini birlikte değiştirin. Güvenilen proxy yalnızca Caddy'dir; `X-Real-IP` bağlantıdan yeniden yazılır. Caddy önüne başka proxy eklemek ayrı bir güven incelemesi gerektirir.

## 7. Yerel verileri taşıma

Yerel sunucuyu Ctrl+C ile kapatın; Gmail yeniden deneme/kurulum araçları gibi DB'ye yazan diğer işlemleri de durdurun. Çalışan SQLite'ın tek `.db` dosyasını kopyalamayın. Kaynak veriyi silmeyin. Windows PowerShell'de proje klasöründen:

```powershell
New-Item -ItemType Directory -Force backups | Out-Null
$Archive = Join-Path $PWD ('backups/fatihflix-data-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.tar.gz')
tar -czf $Archive -C data .
Get-FileHash -Algorithm SHA256 $Archive
$VpsSsh = Read-Host 'VPS SSH kullanıcısı ve adresi'
scp $Archive "${VpsSsh}:~/"
```

Arşiv özel kullanıcı verisi/video içerir; yalnızca SSH üzerinden kendi sunucunuza taşıyın. VPS'te:

```sh
read -r -p 'Aktarılan arşivin tam yolu: ' ARCHIVE
chmod 600 "$ARCHIVE"
sha256sum "$ARCHIVE"
sudo docker compose stop app
sudo docker compose run --rm --no-deps -T app python -c "from pathlib import Path; assert not any(Path('/data').iterdir()), 'Hedef bos degil; yeni volume secin'"
sudo docker compose run --rm --no-deps -T app python -c "import sys,tarfile; tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz').extractall('/data',filter='data')" < "$ARCHIVE"
sudo docker compose run --rm --no-deps app python -c "import sqlite3; from pathlib import Path; p=Path('/data/fatihflix.db'); assert p.is_file(); db=sqlite3.connect(p); result=db.execute('PRAGMA integrity_check').fetchone()[0]; print(result); assert result=='ok'; assert Path('/data/media').is_dir()"
```

SHA256 değerlerini karşılaştırın. Hedef doluysa üzerine açmayın: `.env` içinde yeni benzersiz `CFLIX_DATA_VOLUME` seçip bu adımı yeniden uygulayın. Önceki volume korunur. Hesaplar/yönetici taşınan DB'de korunur; tekrar yönetici oluşturmanız gerekmez. Yalnızca kendi güvenilir arşivlerinizi açın. Boş hedef kontrolü başarısızsa sonraki komutu çalıştırmayın.

## 8. Başlatma ve yönetici

```sh
sudo docker compose up -d
sudo docker compose ps
# Yalnızca boş kurulumda yeni yönetici gerekiyorsa:
sudo docker compose exec app python create_admin.py --email admin@cflix.local --name Admin
```

Parolayı saklayın ve site üzerinden değiştirin. Var olan e-posta için hesap/rol/parola değişmez. Tek instance çalıştırın; `--scale app=2` kullanmayın. SQLite, oturumlar ve limitler instance'lar arasında paylaşılmaz. Restart politikası süreç çıkışında devreye girer; yalnızca `unhealthy` olmak Docker tarafından otomatik restart sağlamaz.

## 9. HTTPS ve cihaz doğrulaması

```sh
read -r -p 'Gerçek hostname: ' DOMAIN
curl -I "http://$DOMAIN/"
curl -I "https://$DOMAIN/"
curl --fail --show-error "https://$DOMAIN/api/health"
sudo docker compose exec app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:3000/api/health',timeout=3).status)"
sudo docker compose exec app python -c "import os; assert os.environ['COOKIE_SECURE']=='1'; print('Secure cookie etkin')"
sudo docker compose port app 3000
```

HTTP aynı hostname'in HTTPS adresine 3xx yönlenmeli; HTTPS geçerli sertifika ve health 200 vermeli. `curl -k` kullanmayın. Son komut app için host portu göstermemelidir. Caddy [otomatik HTTPS](https://caddyserver.com/docs/automatic-https) ile sertifikayı alır/yeniler; DNS ve 80/443 erişimi gerekir. HSTS yalnızca HTTPS proxy'de eklenir, alt alan adlarını kapsamaz. Caddy access log açılmamıştır.

Tarayıcıda gerçekten sınayın:

- Kayıt, kullanıcı/yönetici girişi, şifre değiştirme ve çıkış.
- Yönetici olmayan hesapla yüklemenin reddi; anonim video erişimine 401.
- MP4/kapak yükleme, katalog/arama, favori, geçmiş, öneri ve devam etme.
- Oynatma/sarma/kalite; geliştirici araçlarında Range için 206 ve Content-Range.
- Çerezde Secure/HttpOnly/SameSite=Strict; yanıtlarda CSP ve HSTS.
- Görüş gönderme: SMTP yoksa kuyruk; varsa gerçek teslim durumu ve gelen/spam kutusu.
- `sudo docker compose up -d --force-recreate app` sonrası yeniden giriş yaparak hesap, favori, medya ve kuyruğun korunması.
- Wi-Fi kapalı telefonun mobil internetinden aynı HTTPS adresi; tablet/bilgisayarda oynatma.

Oturumlar bellekte olduğu için yeniden başlatınca giriş tekrarlanır. Sentetik HTTP testleri codec ve fiziksel cihaz uyumunu doğrulamaz.

## 10. Yedekleme

Tutarlı DB+medya yedeği için tüm yazan işlemleri durdurun. Bakım sırasında site geçici hata verebilir. VPS'te proje klasöründen:

```sh
umask 077
mkdir -p backups
BACKUP="backups/fatihflix-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
sudo docker compose stop app
if sudo docker compose run --rm --no-deps -T app python -c "import sys,tarfile; t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz'); t.add('/data',arcname='.'); t.close()" > "$BACKUP"; then
  gzip -t "$BACKUP"
  sha256sum "$BACKUP"
else
  echo 'Yedek basarisiz; bu arsivi geri yukleme icin kullanmayin.' >&2
fi
sudo docker compose start app
```

Arşivi başka güvenli depolamaya da kopyalayın. Sunucudaki tek kopya disk kaybına karşı yedek değildir. `.env` ve sürüm kimliğini ayrı, erişimi kısıtlı yedekleyin; kaynak deposuna eklemeyin. Caddy volume'larını silmeyin. VPS'te planlı yedekleme, disk/health izleme kurun; bu çalışma zamanlayıcı kurmaz.

## 11. Geri yükleme

Mevcut volume'u değiştirmeden yeni volume'a yükleyin. Önce mevcut durumu ayrıca yedekleyin:

```sh
sudo docker compose stop app
read -r -p 'Dogrulanmis yedegin tam yolu: ' ARCHIVE
gzip -t "$ARCHIVE"
sha256sum "$ARCHIVE"
# Eski CFLIX_DATA_VOLUME degerini kaydedin, yeni benzersiz bir ad yazin.
# Bir isim uretmek icin: date -u +fatihflix_restore_%Y%m%dT%H%M%SZ
nano .env
sudo docker compose run --rm --no-deps -T app python -c "from pathlib import Path; assert not any(Path('/data').iterdir()), 'Hedef bos degil'"
sudo docker compose run --rm --no-deps -T app python -c "import sys,tarfile; tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz').extractall('/data',filter='data')" < "$ARCHIVE"
sudo docker compose run --rm --no-deps app python -c "import sqlite3; db=sqlite3.connect('file:/data/fatihflix.db?mode=ro',uri=True); result=db.execute('PRAGMA integrity_check').fetchone()[0]; print(result); assert result=='ok'"
sudo docker compose up -d --force-recreate app
```

Boş hedef veya bütünlük kontrolü başarısızsa durun. Yeniden giriş/video/favori/health kontrollerini tekrarlayın. Eski yedeğe dönüş aradaki değişiklikleri görünmez kılar; eski volume korunur. Vazgeçmek için `.env` içinde önceki volume adını seçip app'i yeniden oluşturun. `docker compose down -v`, `docker volume prune`, `docker system prune --volumes` kullanmayın.

## 12. Yeni sürüm ve geri dönüş

Önce yedek alın, mevcut sürümü kaydedin. Çalışma ağacı temiz değilse değişiklikleri kaybetmeden çözün:

```sh
git status --short
git rev-parse HEAD > backups/previous-commit.txt
git fetch origin
read -r -p 'Yayinlanacak incelenmis commit/tag: ' RELEASE
git checkout --detach "$RELEASE"
python3 -m unittest discover -s tests -v
# Node varsa:
# node --test tests/test_player.mjs tests/test_player_controls.mjs tests/test_recommendations.mjs
sudo docker compose config --quiet
sudo docker compose build --pull app
sudo docker compose up -d --no-deps --force-recreate app
sudo docker compose ps
```

Health ve gerçek kullanıcı akışlarını tekrarlayın. Test/build başarısızsa devam etmeyin. Caddy değiştiyse çalışan proxy üzerinde `sudo docker compose exec proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile`, sonra `sudo docker compose up -d --force-recreate proxy` uygulayın. Çalışan proxy varken aynı sabit IP ile ikinci proxy container'ı açmayın. Python/Caddy taban imajlarını kontrollü güncelleyin; etiketler değişebilir. Bilinen iyi imajı/yedeği saklayın.

Kod geri dönüşü:

```sh
git checkout --detach "$(cat backups/previous-commit.txt)"
sudo docker compose build app
sudo docker compose up -d --no-deps --force-recreate app
```

DB şeması geriye uyumsuz değiştiyse kod geri dönüşü yetmez: önceki sürümle eşleşen yedeği yeni volume'a yükleyin. Güncelleme sıfır kesinti değildir; oturumlar kapanır.

## 13. Loglar ve sorun giderme

```sh
sudo docker compose logs --tail=100 app proxy
sudo docker compose ps
sudo docker compose exec app python -c "import shutil; print(shutil.disk_usage('/data'))"
df -h
sudo ss -lntup
```

Loglar boyut/adet sınırıyla tutulur; paylaşmadan önce özel bilgi açısından inceleyin. HTTPS hatasında A/AAAA, 80/443, saat ve proxy loglarını; 502'de app health/volume izinlerini; girişte 403'te hostname/PUBLIC_ORIGIN eşleşmesini; 429'da 10 dakikalık limiti kontrol edin. Yüklemede 413 boyut sınırıdır; diğer hatalarda disk/bağlantı ve 120 saniyelik soket bekleme sınırına bakın. SMTP hataları yönetim panelinde güvenli kodla gösterilir; kuyruk silinmez.

## 14. GitHub öncesi gizlilik

`.gitignore` `.env*` (örnek hariç), data, DB, MP4, yedek/ZIP, log, anahtar ve özel araç klasörlerini dışlar. `.dockerignore` yalnızca uygulama kodunu ve `public/` içeriğini alır. `public/` herkese açıktır; özel dosya koymayın. Önceden izlenen dosyalar ignore ile temizlenmez.

Git kurulu kendi yerel deponuzda, çıktıları paylaşmadan:

```sh
git status --short --ignored
git ls-files .env '.env.*' data publish '*.db' '*.sqlite*' '*.mp4' '*.pem' '*.key'
git log --all --oneline -- .env data publish '*.db' '*.mp4' '*.key'
git log --all --format='%H' -- server.py
```

Önceki `server.py` sürümlerinde sabit özel e-posta adresi bulunabilir. Güvenilir yerel sır tarayıcıyla tüm geçmişi de inceleyin. Sır commit edildiyse önce iptal/yenileyin; geçmiş temizliği, uzak kopyalar ve ekip koordinasyonu ayrıca gerekir. `git rm --cached` geçmişi temizlemez. Bu çalışma klasöründe `.git` yok ve Git çalıştırılamıyor; geçmiş temiz ilan edilemez. `publish/` içindeki eski ZIP bu düzenlemelerle yenilenmez; güvenli yayın kaynağı olarak kullanmayın.

## 15. Railway ve kapasite sınırı

`railway.json` mevcut Dockerfile, health ve süreç hatası restart ayarlarını korur. Railway kurulumu yapılmadı. Alternatif platformda tek replica, kalıcı `/data`, UID 10001 izinleri, HTTPS, Secure cookie, gerçek PUBLIC_ORIGIN ve platforma uygun proxy/IP güveni ayrıca gerekir. SMTP çıkışı/depolama şartlarını platformun güncel resmi belgelerinden doğrulayın. İzin sorununu çözmek için uygulamayı sürekli root çalıştırmayın.

Standart Python HTTP işleyicisine 64 bağlantı ve 120 saniye soket bekleme sınırı eklendi; dış trafiği Caddy karşılar. Bu değişiklik üretime özel WSGI/ASGI sunucusuna geçiş veya yük testi yerine geçmez. Aktif videolar/yüklemeler de 64 sınıra dahildir; kapasite dolunca yeni bağlantı kapanabilir. SQLite tek yazıcıdır; oturumlar ve sayaçlar bellektedir. Küçük ölçekli kurulum kapasitesini gerçek cihaz/yük testleriyle belirleyin. E-posta doğrulama, şifre sıfırlama, MFA ve otomatik kodlama yoktur.
