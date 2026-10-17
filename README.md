# 🎬 CFlix

![CFlix Logo](public/assets/logo.jpg)

**CFlix**, Python ve SQLite kullanılarak geliştirilmiş, mobil uyumlu, tam kapsamlı bir film ve dizi kütüphanesi web uygulamasıdır.

Kullanıcı hesapları, kişiselleştirilmiş içerik önerileri, izleme geçmişi, video oynatıcı ve yönetici paneli gibi özellikler içerir.

Proje, backend ve frontend geliştirme, veritabanı yönetimi, kullanıcı kimlik doğrulama ve web uygulaması güvenliği üzerine geliştirilmiştir.

> **Proje durumu:** Geliştirme tamamlanmıştır. Uygulama şu anda yerel ortamda (localhost) çalışmaktadır. Herkese açık canlı bir sürümü bulunmamaktadır.

## 🛠 Kullanılan Teknolojiler

| Alan | Teknoloji |
|---|---|
| Backend | Python 3.10+ |
| Veritabanı | SQLite |
| Frontend | HTML5, CSS3, JavaScript |
| JavaScript mimarisi | ES Modules |
| API | Python HTTP Server |
| Konteyner altyapısı | Docker, Docker Compose |
| Ters proxy yapılandırması | Caddy |
| E-posta entegrasyonu | Gmail SMTP |
| Sürüm kontrolü | Git ve GitHub |

Uygulama, Python standart kütüphanesiyle geliştirilmiştir. Temel çalıştırma için ek Python veya Node.js paketlerinin kurulması gerekmez. Node.js yalnızca JavaScript testlerinde kullanılır.

## ✨ Özellikler

### Kullanıcı Yönetimi
- Kullanıcı kaydı ve güvenli oturum açma.
- Oturum kapatma ve şifre değiştirme.
- Kullanıcı ve yönetici yetkilendirmesi.
- Hesaba özel içerik ve izleme bilgileri.

### Film ve Dizi Kütüphanesi
- Film ve dizi kategorileri.
- İçerik arama ve tür filtreleme.
- Kullanıcıya özel favori listeleri.
- İzleme geçmişi ve kaldığı yerden devam etme.
- İzleme davranışı ve tür ilgisine dayalı içerik önerileri.

### Video Oynatıcı
- MP4 video oynatma desteği.
- HTTP Range üzerinden ileri ve geri sarma.
- Mobil uyumlu video oynatıcı.
- Tam ekran oynatma.
- Ayrı yüklenmiş kalite sürümleri arasında geçiş.
- Üyelik kontrollü medya erişimi.

### Yönetici Paneli
- Film ve dizi içeriği ekleme ve yönetme.
- Kapak görseli yükleme (JPG, PNG, WebP).
- MP4 video ve farklı kalite sürümlerini yükleme.
- İçerik yönetimine yönelik yetki kontrolleri.

### Görüş ve Geri Bildirim Sistemi
- SQLite üzerinde kalıcı geri bildirim kuyruğu.
- Gmail SMTP entegrasyonu.
- Başarısız gönderimlerde otomatik yeniden deneme.
- Gönderim durumunun takip edilmesi.

## 📁 Proje Yapısı

```text
CFlix/
├── public/                 # HTML, CSS, JavaScript ve oynatıcı
├── tests/                  # Python ve JavaScript testleri
├── server.py               # HTTP API ve uygulama sunucusu
├── create_admin.py         # Yönetici hesabı oluşturma
├── setup_gmail.py          # Gmail yapılandırma aracı
├── setup_gmail_window.py   # Gmail kurulum arayüzü
├── retry_feedback.py       # E-posta kuyruğunu yeniden deneme
├── baslat.bat              # Windows başlatma dosyası
├── gmail_kurulum.bat       # Windows Gmail kurulum aracı
├── Dockerfile              # Docker imajı
├── compose.yaml            # Docker Compose yapılandırması
├── Caddyfile               # HTTPS ve ters proxy yapılandırması
├── .env.example            # Örnek ortam değişkenleri
├── .gitignore              # Git dışında tutulan dosyalar
├── DEPLOY.md               # Dağıtım ve yedekleme dokümanı
├── RELEASE_REPORT.md       # Test ve sürüm değerlendirmeleri
└── README.md               # Proje dokümantasyonu
```

Uygulamanın çalışma sırasında kullandığı `data/` klasörü GitHub deposuna dahil edilmez.

Mevcut `fatihflix.db` veritabanı adı, önceki verilerle uyumluluk için korunmaktadır.

## 💻 Yerel Kurulum

### Gereksinimler

- Python 3.10 veya üzeri.
- Windows, Linux veya macOS.
- Güncel bir web tarayıcısı.

### 1. Projeyi bilgisayarınıza indirin

```bash
git clone https://github.com/Fatiossa5/CFlix.git
cd CFlix
```

### 2. Python sürümünüzü kontrol edin

```bash
python --version
```

### 3. Uygulamayı başlatın

```bash
python server.py
```

Windows kullanıcıları alternatif olarak `baslat.bat` dosyasını çalıştırabilir.

### 4. Tarayıcı üzerinden erişin

Uygulama başlatıldıktan sonra aşağıdaki adresi açın:

**http://localhost:3000**

Varsayılan sunucu dinleme adresi `0.0.0.0:3000` şeklindedir. Yalnızca kendi bilgisayarınızdan erişmek için `.env` dosyasında `HOST=127.0.0.1` kullanabilirsiniz.

### Ortam değişkenleri

Windows PowerShell üzerinde örnek yapılandırma dosyası şu komutla kopyalanabilir:

```powershell
Copy-Item .env.example .env
```

Yerel HTTP kullanımında `COOKIE_SECURE=0` ayarı kullanılır.

Gerçek `.env` dosyaları, parolalar ve kullanıcı verileri GitHub'a dahil edilmemelidir.

### Yönetici hesabı oluşturma

```bash
python create_admin.py --email admin@cflix.local --name Admin
```

Bu komut yeni bir yönetici hesabı için rastgele parola oluşturur. Parola terminalde bir kez gösterilir; güvenli şekilde saklanmalıdır.

Mevcut hesapların parolaları ve yetkileri bu komutla değiştirilmez.

## 🧪 Testler

Python testlerini çalıştırmak için:

```bash
python -m unittest discover -s tests -v
```

JavaScript oynatıcı testleri için:

```bash
node --test tests/test_player.mjs tests/test_player_controls.mjs
```

Öneri sistemi testleri için:

```bash
node --test tests/test_recommendations.mjs
```

Python testleri geçici SQLite veritabanları ve ayrı HTTP sunucuları kullanır. SMTP işlemleri testlerde taklit edilir.

Sentetik medya testleri, gerçek cihazlarda video çözme ve codec uyumluluğu testlerinin yerine geçmez.

Ayrıntılı değerlendirmeler [RELEASE_REPORT.md](RELEASE_REPORT.md) dosyasındadır.

## 🔐 Güvenlik

CFlix aşağıdaki güvenlik mekanizmalarını içerir:

- PBKDF2-SHA256 ile parola özetleme ve rastgele tuz kullanımı.
- HttpOnly ve SameSite=Strict oturum çerezleri.
- HTTPS ortamları için Secure çerez yapılandırması.
- Parametreli SQL sorguları.
- Yönetici yetki denetimleri.
- CSRF kontrolleri.
- Dosya uzantısı, imzası, boyutu ve yolu doğrulamaları.
- Content Security Policy (CSP) başlıkları.
- Erişim kontrollü video dosyaları.
- Bağlantı sayısı ve soket bekleme süresi sınırları.

Bu önlemler uygulamanın tüm tehditlere karşı güvenli olduğunu garanti etmez. Özellikle internet üzerinden kullanım öncesinde ayrıca güvenlik ve yük testleri gerekir.

## ✉️ Gmail SMTP Entegrasyonu

Geri bildirim sisteminde Gmail SMTP kullanılabilir.

Gerekli ortam değişkenleri:

```dotenv
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=
FEEDBACK_RECIPIENT=
```

Gmail bağlantısı için hesap parolası yerine Google Uygulama Şifresi kullanılmalıdır.

SMTP yapılandırması yapılmadığında veya gönderim başarısız olduğunda mesajlar SQLite kuyruğunda saklanır.

Gerekirse kuyruk aşağıdaki komutla yeniden denenebilir:

```bash
python retry_feedback.py --limit 25
```

Bu komut SMTP yapılandırılmışsa gerçek e-posta gönderimi yapabilir.

## 🐳 Docker ve Dağıtım Yapılandırması

Projede Docker Compose, kalıcı veri depolaması ve Caddy üzerinden HTTPS kullanımını destekleyen yapılandırma dosyaları bulunmaktadır.

Ancak **CFlix şu anda yalnızca yerel ortamda çalıştırılmaktadır.** Herkese açık sunucuya dağıtım yapılmamıştır.

Gelecekteki dağıtım çalışmaları için teknik bilgiler [DEPLOY.md](DEPLOY.md) dosyasında tutulmaktadır.

## ⚠️ Bilinen Sınırlar

- Uygulama tek süreç ve tek instance mimarisini destekler.
- Oturumlar ve bazı sınırlama sayaçları bellekte tutulur; yeniden başlatmada sıfırlanabilir.
- Kullanıcılar, katalog, favoriler, izleme geçmişi ve medya verileri SQLite ve yerel depolama üzerinden korunur.
- E-posta doğrulama, otomatik şifre sıfırlama ve çok faktörlü kimlik doğrulama mevcut değildir.
- Çoklu sunucu çalıştırma, CDN ve otomatik video dönüştürme desteği bulunmaz.
- Video yüklemelerinde 2 GiB, kapak görsellerinde 10 MiB sınırı vardır.
- Farklı video kalite sürümleri yönetici tarafından ayrı ayrı yüklenir.
- Yük testi tamamlanmadan yüksek trafik kapasitesi iddia edilmez.

Örnek katalogda kullanılan harici tanıtım videosu, görseller ve yazı tipleri dış kaynaklara bağlı olabilir. Yalnızca kullanım veya yayın hakkına sahip olunan medya dosyaları eklenmelidir.

## 📌 Proje Durumu

**CFlix, yerel kullanım için geliştirilmiş bir portföy projesidir.**

Kaynak kodları GitHub üzerinden incelenebilir. Gerçek kullanıcı verileri, özel yapılandırmalar ve yüklenen medya dosyaları depoda bulunmaz.

## 👨‍💻 Geliştirici

**Muhammed Fatih Atmaca**

GitHub: [@Fatiossa5](https://github.com/Fatiossa5)

---

*CFlix — Film ve dizi kütüphanesi web uygulaması.*
