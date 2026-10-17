# FatihFlix yayın hazırlığı raporu

Tarih: 17 Ekim 2026. Kaynak kodu düzenlendi; gerçek sunucuya yayın yapılmadı. Ücretli kaynak oluşturulmadı, GitHub'a gönderim veya gerçek e-posta gönderimi yapılmadı. Mevcut kullanıcı veritabanı ve medya silinmedi; testler geçici verilerle çalıştı.

## 1. İncelenen dosyalar

- `server.py`, `create_admin.py`, `retry_feedback.py`, `setup_gmail.py`, `setup_gmail_window.py`.
- `Dockerfile`, `compose.yaml`, `Caddyfile`, `railway.json`.
- `README.md`, `DEPLOY.md`, `.env.example`, `.gitignore`, `.dockerignore`.
- `public/` yapısı; `index.html`, CSS dış kaynakları, `app.js`, `player.js`, `player-core.js`, `recommendations.js` ve varlıklar.
- `tests/` Python HTTP/medya/yönetici/SMTP testleri ve JavaScript test dosyaları.
- Proje kökü ve eski `publish/CFlix-yayin.zip` dosyasının giriş adları; özel dosya içerikleri rapora alınmadı.

`railway.json` mevcut Dockerfile/health/restart ayarlarıyla bırakıldı. `create_admin.py` hesapları ezmeme davranışını koruyor. `.dockerignore` zaten bir izin listesi kullanıyordu; ek özel dosya desenleriyle güçlendirildi.

## 2. Yapılan değişiklikler

- `server.py`: sınırlı eşzamanlı bağlantı, soket bekleme sınırı, güvenli proxy IP işleme, ek CSRF/JSON ve istek uzunluğu denetimi, ortak güvenlik başlıkları, medya yolu kontrolü, sağlık kontrolünde DB sorgusu, güvenli logout çerezi.
- `Dockerfile`: UID/GID 10001 korunarak `/data` izinleri 0700 yapıldı; uygulama kodunun gereksiz sahiplik değişikliği kaldırıldı.
- `compose.yaml`: sabit proje adı, yalnızca proxy'ye açık host portları, kalıcı adlandırılmış veri volume'u, salt okunur uygulama imajı, yetki kısıtları, kaynak/PID sınırları, init, log rotasyonu ve açık proxy güven ağı.
- `Caddyfile`: gerçek alan adı ortam değişkeni korunarak HSTS, header timeout, header/gövde boyut sınırı ve yeniden yazılan X-Real-IP eklendi. HTTP→HTTPS ve sertifika yönetimi Caddy'nin gerçek DNS gerektiren otomatik HTTPS mekanizmasına bırakıldı.
- `.env.example`: yerel HTTP/üretim ayrımı, alıcı, güvenilen proxy, bağlantı sayısı, gerçek domain ve isteğe bağlı veri volume'u açıklandı.
- `.gitignore`, `.dockerignore`: özel ortam, DB, video, anahtar, log ve arşiv dosyaları için koruma genişletildi.
- `public/app.js`: CSP ile uyum için inline görsel hata işleyicisi normal olay dinleyicisine taşındı. Tasarım, oynatıcı ve öneri algoritması yeniden yazılmadı.
- `README.md` ve `DEPLOY.md` gerçek kod davranışına göre yenilendi. Ubuntu kurulumu, veri taşıma, yeni volume'a geri yükleme ve sürüm geri dönüş komutları eklendi.
- `tests/test_security.py`, `tests/test_lifecycle.py` eklendi; ilgili medya, SMTP ve sağlık testleri güncellendi.

## 3. Düzeltilen hatalar

- Reverse proxy arkasında bütün ziyaretçilerin aynı IP limitine girmesi: yalnızca açıkça güvenilen Caddy IP'sinden gelen, Caddy'nin yeniden yazdığı X-Real-IP kullanılıyor. İstemcinin keyfi X-Forwarded-For başlığına güvenilmiyor.
- Sınırsız thread oluşturma: çalışan sunucuda varsayılan 64 bağlantı sınırı ve 120 saniye soket bekleme sınırı var.
- Health'in DB bozulduğunda/ulaşılamadığında koşulsuz sağlıklı dönmesi: DB sorgusu hatasında 503.
- Güvenli giriş çerezi kullanılırken çıkış çerezinde Secure eksikliği giderildi.
- Kaynak koddaki kişisel alıcı adresi ortam değişkenine taşındı. Mevcut yerel alıcı `.env` içinde korundu; alıcı boş/geçersizse mesajlar kuyrukta kalıyor.
- Eski sürüm numarasını sabit bekleyen sağlık testi sürüm biçimini doğrulayacak şekilde düzeltildi.
- Yeni süreç testi sırasında Windows'ta açık kalan test DB bağlantısı kapatıldı; son test turunda hata kalmadı.

## 4. Güvenlik sonuçları

| Konu | İnceleme ve sonuç |
| --- | --- |
| SQL injection | Mevcut sorgular parametreli. SQL benzeri kullanıcı girdisinin sorgu olarak çalışmadığı test edildi; açık bulunduğu iddia edilmiyor. |
| XSS | Kullanıcı adı textContent, başlık/açıklama escape ile işleniyor; katalog türleri sunucuda sınırlı. Script için yalnızca aynı kaynak izinli CSP eklendi; inline event kaldırıldı. Gerçek tarayıcı saldırı testi yapılmadı. |
| CSRF | SameSite=Strict ve Origin denetimine JSON zorunluluğu, Sec-Fetch-Site kontrolü ve üretimde sabit PUBLIC_ORIGIN eklendi. |
| Yönetici/API | Mevcut rol ve sahiplik kontrolleri korundu; normal/anonim kullanıcının yükleme ve kalite değişikliği yapamadığı test edildi. |
| Parola | Mevcut 600.000 turlu PBKDF2-SHA256, tuz ve karşılaştırma korundu; şifre değişiminde diğer oturumların kapanması test ediliyor. |
| Oturum | HttpOnly/SameSite=Strict korunuyor, Compose Secure=1 zorunlu. Giriş ve çıkış çerezi test edildi. Bellekteki oturumlar restart'ta kapanır. |
| Yükleme | Mevcut imza/boyut/rastgele ad kontrolleri korundu. 2 GiB MP4 ve 10 MiB JPG/PNG/WebP; SVG yüklemesi kabul edilmiyor. Tam codec analizi/antivirüs yok. |
| Yol geçişi | Statik dosya kök kontrolü korundu. Medya DB kaydı bile kök dışı dosyaya yönelse erişimi reddeden kontrol ve test eklendi. |
| Deneme sınırı | Mevcut IP/hesap bazlı limitler korundu; proxy IP davranışı düzeltildi. Sayaçlar bellekte, dağıtık saldırı/DDoS koruması değil. |
| Gizli bilgiler | SMTP hataları güvenli kodlarla döner; HTTP hatalarında ham istek/çerez/sır yazılmaz. Sınırlı kaynak örüntü taramasında bilinen token/özel anahtar/sabit SMTP parola eşleşmesi yok. Bu tam bir sır tarama sertifikası değildir. |
| Video üyeliği | Orijinal ve alternatif yüklenen MP4'lerde giriş kontrolü mevcut; anonim 401 ve giriş sonrası Range 206 test edildi. Kapak/katalog herkese açıktır. |
| HTTPS | Caddy yapılandırması ve güvenli çerez ayarı hazır; gerçek sertifika/DNS/HTTPS testi yapılmadı. |

CSP mevcut inline stillere izin verir; inline script ve eval açılmadı. Google Fonts, Unsplash ve örnek Google video kaynağı için gerekli izinler korundu.

## 5. Çalıştırılan testler

Çalıştırılabilir Python: kurulu Python 3.14.8; `python` PATH kaydı Windows uygulama takma adına gittiği için gerçek executable kullanıldı:

```powershell
& 'C:/Users/mfati/AppData/Local/Python/pythoncore-3.14-64/python.exe' -m unittest discover -s tests -v
```

Son tam tur: **63 test, 25.419 saniye, OK**.

Kapsam: hesap/şifre/yönetici, favori/geçmiş/öneri, geçici DB migration, dosya yükleme, kalite, HTTP Range/HEAD, üyelik, kuyruk, sahte SMTP başarılı/hatalı teslimat, CSRF, proxy IP güveni, istek framing, bağlantı sınırı ve health hata davranışı.

Gerçek ayrı Python sürecinin durdurulup yeniden başlatıldığı testte yönetici hesabı, favori, izleme konumu, yüklenen video ve bekleyen e-posta korundu. Eski session 401 verdi; tekrar giriş ve video Range 206 çalıştı. Bu bir Docker container yeniden oluşturma testi değildir.

Ek doğrulamalar:

- Compose dosyası yerel PyYAML ile parse edildi; uygulamada host portu olmaması, Secure cookie, tmpfs, volume ve sabit IP tutarlılığı kontrol edildi. Bu `docker compose config` doğrulaması değildir.
- Geçici DB+medya arşivlendi, stdin üzerinden `tarfile` data filtresiyle yeni dizine geri yüklendi; dosya eşitliği/SHA256 ve SQLite integrity_check geçti. Gerçek Docker volume'u kullanılmadı.
- Kaynakta sınırlı sır desenleri ve public içinde özel dosya uzantıları tarandı; eşleşme bulunmadı. `.env` içeriği/logları dışarı aktarılmadı.
- Eski ZIP'te 23 giriş içinde `.env`, DB, MP4 veya anahtar yolu bulunmadı; eski server.py içerdiğinden güncel yayın paketi olarak kullanılmamalı.

## 6. Test edilemeyen alanlar

- Node.js çalıştırıcısı bulunamadı: `node --test tests/test_player*.mjs` ve öneri JavaScript testleri çalıştırılamadı.
- Docker CLI/daemon bulunamadı: build, Compose doğrulama, container health/recreate/volume izinleri ve Caddy validate çalıştırılamadı.
- Gerçek Caddy reverse proxy, DNS, sertifika alımı/yenileme, HTTP→HTTPS ve HSTS tarayıcı davranışı.
- Telefon/tablet/farklı ağ, gerçek codec ve görsel oynatıcı davranışı; CSP'nin tüm tarayıcılarda uçtan uca doğrulanması.
- Gerçek Gmail SMTP bağlantısı/teslimatı; testlerde SMTP taklit edildi.
- Yük/uzun süreli video performansı, kapasite ve disk dolumu senaryoları.
- Python 3.10/3.13 üzerinde ayrı test matrisi; bu ortamda yalnızca 3.14.8 çalıştırıldı.
- Git yürütülebilir dosyası ve `.git` bulunmadığından geçmiş/uzak depo sır denetimi yapılamadı.

## 7. Yayına çıkmadan eksikler

Gerçek VPS ve SSH erişimi, gerçek hostname/domain, A/AAAA DNS yönlendirmesi, açık gerekli portlar, yeterli kalıcı disk ve sunucuda Docker gerekiyor. Sonrasında DEPLOY.md'deki container/HTTPS/cihaz doğrulaması yapılmalı. SMTP istenirse Gmail uygulama şifresi yalnızca kendi sunucunuzun özel `.env` dosyasına girilmeli.

Python işleyicisi standart kütüphanede kaldı; sınırlamalar azaltıldı ancak yüksek trafik için üretime özel bir sunucuya geçilmiş gibi gösterilmiyor. Tek instance ve bellek oturumu sınırları devam ediyor. Güncel Python [HTTP sunucusu belgesi](https://docs.python.org/3/library/http.server.html) bu sunucunun üretim sınırlamasını belirtir.

## 8. Sizin yapacağınız işlemler

1. VPS sağlayıcısını ve kullanacağınız gerçek hostname'i seçin; ödeme/satın alma bu görevde yapılmadı.
2. Kaynakları paylaşmadan önce Git geçmişini ve eski paketleri yerelde denetleyin; bu klasörün dışındaki uzak geçmişin temiz olduğu varsayılmamalı.
3. DEPLOY.md üzerinden VPS/Docker/DNS kurulumunu uygulayın.
4. Mevcut yerel sunucuyu ve DB'ye yazan araçları kapatıp DB+medyayı birlikte yedekleyin, SSH üzerinden aktarın.
5. Sunucuda gizli ayarları kendiniz girin; parola, token veya Gmail şifresini sohbete göndermeyin.
6. Gerçek HTTPS, container kalıcılığı ve mobil cihaz kontrol listesini tamamlayın; düzenli dış yedek/health/disk izlemesi kurun.

Kuruluma devam etmek için paylaşılabilecek bilgiler: seçilen gerçek hostname, VPS işletim sistemi/sürümü, sunucu adresi ve kaynak deposu URL'si. SSH parolası/özel anahtar, Gmail uygulama şifresi ve kullanıcı DB'si bu sohbette istenmiyor.

## 9. Sunucuda başlangıç komutları

Tam Docker kurulumu, kaynak alma ve veri aktarımı [DEPLOY.md](DEPLOY.md) içindedir. Bunlar tamamlandıktan sonra proje klasöründe:

```sh
umask 077
cp -n .env.example .env
chmod 600 .env
nano .env
# Gerçek CFLIX_DOMAIN ve isteniyorsa SMTP/alıcı ayarlarını girin.
sudo docker compose config --quiet
sudo docker compose build --pull app
sudo docker compose run --rm --no-deps proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
# Mevcut verileri taşıyacaksanız başlatmadan önce DEPLOY.md bölüm 7'yi uygulayın.
sudo docker compose up -d
sudo docker compose ps
# Yalnızca yeni boş kurulumda:
sudo docker compose exec app python create_admin.py --email admin@cflix.local --name Admin
read -r -p 'Gerçek hostname: ' DOMAIN
curl --fail --show-error "https://$DOMAIN/api/health"
```

Mevcut veri için yeni yönetici komutuna gerek yoktur. Başarısız kontrolden sonra devam etmeyin. Güncelleme/geri yüklemede mevcut volume'u silmeyin. Caddy'nin [otomatik HTTPS koşulları](https://caddyserver.com/docs/automatic-https) ve Docker'ın [Ubuntu kurulum belgesi](https://docs.docker.com/engine/install/ubuntu/) rehber hazırlanırken kontrol edildi.
