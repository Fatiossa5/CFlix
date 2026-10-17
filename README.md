# FatihFlix

Python ve SQLite ile geliştirilen, mobil uyumlu film ve dizi kütüphanesi. Arayüzde ve bazı dosyalarda CFlix adı kullanılır. Mevcut `fatihflix.db` adı veri uyumluluğu için korunur.

## Özellikler

- Kullanıcı kaydı, giriş/çıkış, şifre değiştirme ve yönetici rolleri.
- Hesaba özel favoriler, izleme geçmişi, kaldığı yerden devam ve tür ilgisine dayalı öneriler.
- Film/dizi ayrımı, arama ve tür filtreleri.
- Yönetici panelinden MP4, JPG/PNG/WebP kapak ve ayrı kalite sürümleri yükleme.
- Üyelik kontrollü video erişimi, HTTP Range ile ileri/geri sarma, mobil oynatıcı ve tam ekran.
- SQLite üzerinde kalıcı görüş/öneri kuyruğu; Gmail SMTP, yeniden deneme ve güvenli teslimat durumu.
- Docker Compose ile tek uygulama örneği, kalıcı veri ve Caddy üzerinden HTTPS yayını.

## Teknolojiler ve yapı

Python 3.10+ standart kütüphanesi, SQLite, HTML/CSS ve ES modülleri kullanılır. Uygulama için pip veya Node.js bağımlılığı gerekmez. Docker imajı Python 3.13 kullanır.

```text
server.py                 HTTP API, kimlik doğrulama, SQLite ve medya
public/                   Arayüz ve oynatıcı
create_admin.py           Yönetici oluşturma
setup_gmail*.py            Yerel Gmail kurulum araçları
retry_feedback.py         Kuyruğu elle yeniden deneme
tests/                   Python HTTP ve JavaScript testleri
data/fatihflix.db        Özel kullanıcı/katalog verisi (Git dışında)
data/media/              Video ve kapaklar (Git dışında)
compose.yaml, Caddyfile    VPS üzerinde HTTPS ve kalıcı depolama
DEPLOY.md                 Kurulum, veri taşıma, yedek ve geri dönüş
```

## Yerel kurulum

```sh
python --version
python server.py
```

Windows'ta `baslat.bat` da kullanılabilir. Tarayıcıda `http://localhost:3000` açılır. Varsayılan dinleme adresi `0.0.0.0:3000` olduğundan aynı ağdaki cihazlar bilgisayarın ağ IP adresini kullanabilir; yalnızca yerel erişim için `HOST=127.0.0.1` ayarlayın. Telefonun `localhost` adresi telefonu gösterir.

İsteğe bağlı `.env.example` dosyasını `.env` adıyla kopyalayın. Yerel HTTP için `COOKIE_SECURE=0`; Compose üretimde bunu `1` yapar. `.env` ve `data/` özel kalmalıdır. İlk kayıtta otomatik yönetici atanmaz:

```sh
python create_admin.py --email admin@cflix.local --name Admin
```

Bu komut yeni hesap ve rastgele parola oluşturur. Parola terminalde bir kez gösterilir; güvenle saklayıp hesap ayarlarından değiştirin. Aynı e-posta varsa hesap, parola ve rol değiştirilmez. Mevcut yönetici taşınan veritabanında korunur.

## İnternet üzerinden yayın

Hedef: `İnternet → Caddy HTTPS → Python → /data (SQLite + medya)`.

Gerçek alan adı ve sürekli açık VPS gerekir. Kurulum komutları ve doğrulama listesi [DEPLOY.md](DEPLOY.md) içindedir. Üretim başlangıcı:

```sh
cp .env.example .env
chmod 600 .env
# .env içinde gerçek CFLIX_DOMAIN ve isteğe bağlı SMTP ayarlarını düzenleyin.
docker compose config --quiet
docker compose up -d --build
docker compose exec app python create_admin.py --email admin@cflix.local
```

Uygulamanın 3000 portu host'a açılmaz. Caddy 80/443 sunar; HTTP yönlendirmesi ve sertifika yönetimi gerçek DNS yönlendirmesiyle çalışır. Bu depoda çalışan genel URL veya satın alınmış kaynak bulunmaz. Yerel veriler boş sunucuya kendiliğinden taşınmaz.

## SMTP ve görüşler

`.env` içinde `FEEDBACK_RECIPIENT`, `SMTP_USERNAME`, `SMTP_PASSWORD` ve `SMTP_FROM` ayarlayın. Gmail için hesap parolası yerine Google Uygulama Şifresi kullanın. Yerel `gmail_kurulum.bat` bağlantı doğrulamayı kolaylaştırır; alıcı `.env` üzerinden ayrıca belirlenir. Kimlik bilgilerini Git'e veya sohbetlere eklemeyin.

Eksik ayar veya SMTP hatasında mesaj SQLite kuyruğunda kalır. Yapılandırılmış bağlantıda açılışta ve yaklaşık 60 saniyede bir en fazla 5 mesaj denenir; hatalarda bekleme artar. `python retry_feedback.py --limit 25` gerçek e-posta gönderebilir. SMTP kabulü gelen kutusuna teslim garantisi değildir; bağlantı burada gerçek Gmail hesabıyla doğrulanmamıştır.

## Testler

```sh
python -m unittest discover -s tests -v
node --test tests/test_player*.mjs
node --test tests/test_recommendations.mjs
```

Node.js yalnızca JavaScript testleri için gerekir. PowerShell joker karakteri genişletmezse `node --test tests/test_player.mjs tests/test_player_controls.mjs` kullanın. Python testleri geçici SQLite ve ayrı HTTP sunucuları kullanır; SMTP taklit edilir. Medya testlerindeki sentetik dosyalar gerçek video çözme ve fiziksel cihaz testi yerine geçmez. Son doğrulama ve eksikler [RELEASE_REPORT.md](RELEASE_REPORT.md) içindedir.

## Güvenlik ve sınırlar

Parolalar 600.000 turlu PBKDF2-SHA256 ve rastgele tuzla saklanır. Oturum çerezleri HttpOnly/SameSite=Strict; üretimde Secure'dür. Parametreli SQL, yönetici yetki denetimi, kaynak/JSON CSRF kontrolü, dosya imzası/boyutu/yolu kontrolü ve CSP başlıkları uygulanır. Yüklenen videolar giriş gerektirir; kapaklar ve katalog herkese açıktır. Üyelik ücretli abonelik anlamına gelmez.

Tek süreç/tek instance desteklenir. Oturumlar ve deneme sayaçları bellektedir; yeniden başlatmada oturumlar biter ve sayaçlar sıfırlanır. Kullanıcılar, favoriler, geçmiş, katalog, medya ve e-posta kuyruğu kalıcıdır. Compose volume'larını silmeyin (`down -v` kullanmayın). Yedeklerde veritabanı ve medya birlikte tutulur.

HTTP işleyicisi mevcut API'leri korumak için standart kütüphanede kalır; 64 eşzamanlı bağlantı ve 120 saniye soket bekleme sınırı eklenmiştir. Caddy zorunlu dış katmandır. Python [http.server belgesi](https://docs.python.org/3/library/http.server.html) üretim kısıtlarını açıklar; yüksek trafik veya DDoS dayanıklılığı garantisi yoktur. Yük testi yapılmadan kapasite iddiasında bulunulmaz. E-posta doğrulama, şifre sıfırlama, MFA, CDN, çoklu instance ve otomatik video dönüştürme yoktur.

MP4 en fazla 2 GiB, kapak en fazla 10 MiB olabilir. Kalite sürümlerini yönetici ayrı yükler; otomatik kodlama yapılmaz. Dizilerde her bölüm ayrı içerik olarak eklenebilir. Yayınlanmayan yüklemeler için otomatik temizlik yoktur.

Örnek katalog kurgusaldır ve Big Buck Bunny tanıtım videosunu kullanır. Örnek video Google depolamasından, görseller Unsplash'ten, yazı tipleri Google Fonts'tan gelir. Yüklenen içerikler kendi dosyalarını oynatır. Dış kaynak erişimi ve gerçek cihazda codec uyumu ayrıca sınanmalıdır. Yalnızca yayın hakkınız olan içerikleri yükleyin.
