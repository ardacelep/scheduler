"""Yardım — uygulama içi Türkçe kullanım kılavuzu.

Hedef kitle teknik değildir: buradaki metinler dosya yolu, terim ve
kısaltma kullanmadan "önce şunu yap, sonra şunu yap" diliyle yazılır.
Kılavuzun dışarıda da kalması gereken kısımları (kurulum, SmartScreen,
kapatma) zip içindeki OKU-BENI.txt ile aynı bilgiyi verir.
"""
from __future__ import annotations

import sys
import threading
import time

import streamlit as st

from rotasyon import __version__


def _link(url_path: str, label: str, icon: str) -> None:
    pages = st.session_state.get("_pages", {})
    if url_path in pages:
        st.page_link(pages[url_path], label=label, icon=icon)


def render(store) -> None:
    st.header("❓ Yardım")
    st.caption(
        f"Staj Rotasyonu sürüm {__version__} — tüm veriler bu bilgisayarda "
        "kalır, internete hiçbir bilgi gönderilmez."
    )

    tab_start, tab_screens, tab_faq, tab_trouble = st.tabs(
        ["🚀 Nasıl başlarım?", "🗺️ Ekranlar", "❔ Sık sorulanlar", "🔧 Sorun giderme"]
    )
    with tab_start:
        _getting_started()
    with tab_screens:
        _screens()
    with tab_faq:
        _faq()
    with tab_trouble:
        _troubleshooting()


# ---------------------------------------------------------------- başlangıç
def _getting_started() -> None:
    st.subheader("Sezon başında sırasıyla ne yapılır?")
    st.markdown(
        """
**1. Sezonu açın.**
Sol taraftaki **📅 Sezon** bölümünden **➕ Yeni sezon oluştur**'a basın,
adını yazın (örneğin `2026-2027`). "Birimler nereden gelsin?" sorusunda
**hazır birim kataloğu** seçili kalsın — hastanenin birimleri kontenjan,
cinsiyet kısıtı ve yoğunluk bilgisiyle hazır gelir. Katalog, elle
hazırladığınız rotasyon dosyalarındaki kontenjanlardan türetilmiştir; grup
büyüklüğüne göre değişen birimlerde **üst sınır** yazılıdır, gerekirse
Kapasite Planı'ndan düşürebilirsiniz.

**2. Öğrenci listesini yükleyin.**
**📊 Excel** ekranından okuldan gelen öğrenci listesini
(Excel ya da e-okul PDF'i) seçin. Uygulama dosya türünü kendi anlar;
öğrencileri, sınıfları ve bölümleri okur, isimlerden cinsiyeti tahmin eder.
Size **hangi sınıfın hangi gruba** gideceğini sorar.

**3. Eksikleri tamamlayın.**
**📋 Veri Yönetimi** → *Öğrenciler*: cinsiyeti tahmin edilemeyen öğrenci
varsa tabloda elle seçin. *Birimler*: kontenjanı, cinsiyet kısıtı veya
kapalı olan birimleri düzenleyin.

**4. Rotasyonu oluşturun.**
**📅 Yıllık Tablo** ekranında **sıradaki boş ayı otomatik doldur**'a basın.
Sonuç önce **taslak**tır; beğenmezseniz *farklı çözüm* isteyebilir, tek tek
hücreleri elle değiştirebilirsiniz. **Kaydet**'e basmadan hiçbir şey
kalıcı olmaz.

**5. Kontrol edip dışa aktarın.**
Kaydettikten sonra uygulama tüm kuralları denetler. **📊 Excel İçe/Dışa
Aktarım** ekranından yıllık renkli tabloyu Excel olarak indirip
yazdırabilirsiniz.
        """
    )
    st.info(
        "💡 **Hiçbir işlem geri alınamaz değildir.** Her kayıtta önceki hâlin "
        "yedeği otomatik alınır, silinen sezonlar çöp klasörüne taşınır. "
        "Yine de ayda bir kendi yedeğinizi almanız önerilir → "
        "Veri Yönetimi ▸ 💾 Yedekleme."
    )
    c1, c2 = st.columns(2)
    with c1:
        _link("excel", "Öğrenci listesi yükle", "📥")
    with c2:
        _link("yillik-tablo", "Yıllık Tablo'ya git", "📅")


# ---------------------------------------------------------------- ekranlar
_SCREENS = [
    (
        "🏠 Ana Sayfa",
        "Sezonun özeti: kaç öğrenci, kaç birim, hangi aylar tamamlandı. "
        "Eksik bilgi varsa buradan uyarılırsınız.",
    ),
    (
        "🧭 Kurulum Sihirbazı",
        "Yeni sezonu kurarken nerede kaldığınızı gösterir: beş adım, her "
        "birinin durumu verinizden okunur ve ilgili ekrana bağlantı verir.",
    ),
    (
        "📅 Yıllık Tablo",
        "En çok kullanacağınız ekran. Sezonun tamamı tek tabloda: satırlar "
        "öğrenci, sütunlar aylar. Ay üretmek, hücre düzeltmek ve tüm sezonu "
        "görmek burada yapılır. Altındaki **Toplu oluşturma** kalan bütün "
        "ayları tek seferde üretir.",
    ),
    (
        "🛡️ Kural Kontrolü",
        "Sezonunuzun iki yandan sağlık kontrolü: **kayıtlı atamalar** "
        "kurallara uyuyor mu ve **kalan sezon** tamamlanabilir mi. İkisinin "
        "özeti en üstte birlikte durur.",
    ),
    (
        "📋 Veri Yönetimi",
        "Öğrenciler, birimler, sınıflar, özel kurallar ve yedekleme. "
        "Sezon içinde bir şey değiştiğinde (öğrenci ayrıldı, birim kapandı) "
        "buraya gelirsiniz.",
    ),
    (
        "🕘 Öğrenci Geçmişi",
        "Tek bir öğrencinin sezon boyunca hangi aylarda nerede olduğunu "
        "gösterir.",
    ),
    (
        "📊 Excel İçe/Dışa Aktarım",
        "Dışarıdan liste almak ve hazır rotasyonu Excel olarak vermek için.",
    ),
    (
        "🎯 Gereksinimler (Sezon Kurulumu)",
        "Bu sezonun zorunluluklarını gelen öğrencilere göre belirlersiniz. "
        "Her satır tek bir cümledir: kime — hangi birimlerden — kaç kez. "
        "Örn. 'D sınıfı — DOĞUM SALONU, 2.KAT DOĞUM birimlerinden en az 1'. "
        "Branş seçmenize gerek yok, birimleri doğrudan adıyla seçersiniz. "
        "Varsayılan katalogdan sezon açtıysanız rotasyon belgelerinizdeki "
        "kurallar **hazır gelir**; her satırı ✏️ ile düzenleyebilir, "
        "pasifleştirebilir ya da silebilirsiniz.",
    ),
    (
        "📦 Kapasite Planı (Sezon Kurulumu)",
        "Hangi birime kaç kişi gideceğini ve nasıl doldurulacağını "
        "belirlersiniz: her birimin tek bir politikası vardır (Tam dolmalı / "
        "Mümkünse dolsun / Havuz / Yedek / Serbest). Ekran toplamı canlı "
        "hesaplar: tam dolanlar kaç kişi çekiyor, geriye kaç öğrenci kalıyor, "
        "kalanlar havuz birimi başına kaça düşüyor.",
    ),
]


def _screens() -> None:
    st.subheader("Hangi ekran ne işe yarar?")
    for title, text in _SCREENS:
        st.markdown(f"**{title}** — {text}")
    st.divider()
    st.markdown(
        "**Sol taraftaki kenar çubuğu** her ekranda görünür: üstte sayfa "
        "listesi, altta sezon seçimi ve *geçmişe dönük uyarıları göster* "
        "ayarı bulunur."
    )


# ---------------------------------------------------------------- SSS
_FAQ = [
    (
        "Rotasyon oluşturdum, kural ihlali uyarısı çıktı. Ne yapmalıyım?",
        "Uyarılar iki türlüdür. **⚠️ Uyarı** bilgilendirmedir, kayıt yapmanızı "
        "engellemez. **❌ Hata** kural ihlalidir; ilgili hücreyi Yıllık "
        "Tablo'da değiştirip yeniden kaydedebilir ya da yine de kaydetmeyi "
        "onaylayabilirsiniz. Uygulama hiçbir zaman sizin haberiniz olmadan "
        "kural çiğnemez.",
    ),
    (
        "Sezon ortasında bir öğrenci okuldan ayrıldı.",
        "Veri Yönetimi ▸ Öğrenciler tablosunda o öğrencinin **Aktif** "
        "kutusunun işaretini kaldırın. Geçmiş ayları olduğu gibi kalır, "
        "bundan sonraki aylara atanmaz. **Silmeyin** — silmek geçmişi bozar.",
    ),
    (
        "Sezon ortasında yeni öğrenci geldi.",
        "Veri Yönetimi ▸ Öğrenciler ▸ *Yeni öğrenci ekle*. Yalnız bundan "
        "sonraki aylara atanır; geçmiş aylar değişmez.",
    ),
    (
        "Bir birim kapandı veya kontenjanı değişti.",
        "Veri Yönetimi ▸ Birimler'den kontenjanı değiştirin veya **Aktif** "
        "işaretini kaldırın. Bu değişiklik **bundan sonra üretilecek** aylar "
        "için geçerlidir; daha önce kaydedilmiş aylar kendiliğinden "
        "değişmez.",
    ),
    (
        "“Geçmişe dönük uyarı” ne demek?",
        "Kontenjan düşürmek gibi sonradan yapılan bir değişiklik, siz "
        "dokunmadığınız eski ayları da kurala aykırı gösterebilir. Bunlar "
        "yeni kaydı engellemez. Kalabalık gelirse sol alttaki *Geçmişe dönük "
        "uyarıları göster* kutusunu kapatabilirsiniz.",
    ),
    (
        "İleride çıkacak sorunlardan önceden haberim olur mu?",
        "Evet, uygulama bunu sürekli hesaplar. Bazı sorunlar sonradan fark "
        "edilirse telafisi olmaz (öğrencinin palyatif görmediği HAZİRAN'da "
        "anlaşılırsa yapılacak bir şey yoktur), o yüzden **kalan sezon** ayrıca "
        "denetlenir:\n\n"
        "- **Ana Sayfa**'da risk varsa kırmızı/sarı bir özet çıkar.\n"
        "- **Yıllık Tablo** üstünde *🔎 Sezon ön-denetimi* paneli bulunur.\n"
        "- **Kural Kontrolü**'nde *🔮 Kalan sezon* bölümünde tam liste "
        "vardır.\n\n"
        "Denetlenenler: kontenjan yetiyor mu, her öğrenci zorunlu branşlarını "
        "(cerrahi, dahili, yoğun bakım, palyatif; ebelikte doğum salonu) "
        "görebilecek mi, gidebileceği birim tükeniyor mu ve eklediğiniz özel "
        "kurallar ileride çakışacak mı.",
    ),
    (
        "“Derin risk analizi” nedir, ne zaman kullanmalıyım?",
        "Kural Kontrolü'ndeki *🔮 Kalan sezon* bölümünün bu düğmesi, kalan ayları "
        "**gerçekten çözmeyi dener** ve “bu sezon tamamlanabilir mi?” "
        "sorusuna kesin cevap verir. Normal denetim hesapla bulunabilecek "
        "tıkanmaları gösterir; bu ise kuralların birlikte tıkanıp "
        "tıkanmadığını da yakalar. **Hiçbir şeyi kaydetmez** — sadece dener. "
        "Önemli bir değişiklik yaptıktan sonra (kontenjan düşürme, birim "
        "kapatma, yeni kural) çalıştırmak iyi bir alışkanlıktır.\n\n"
        "Zor bir grupta *“🐢 daha uzun deniyor”* yazarsa endişelenmeyin: "
        "uygulama süreyi kendiliğinden büyütüp yeniden deniyor, takılmadı.",
    ),
    (
        "“Bu grup bilgisayarın rahat çözebileceğinden daha zor” diyor, ne yapmalıyım?",
        "Bu, **çözümü olmadığı anlamına gelmez** — kuralların çok sıkı olduğu "
        "anlamına gelir. Uygulama süreyi zaten kendiliğinden büyütüp denedi, "
        "yani bir ayarı değiştirmenize gerek yok. Sırayla şunları deneyin:\n\n"
        "1. **📦 Kapasite Planı**'nda kontenjanlara bir-iki kişilik pay "
        "bırakın. *“Toplam kontenjan öğrenci sayısına tam eşit”* uyarısı "
        "varsa neredeyse kesin sebep odur: pay yoksa her birim her ay dolmak "
        "zorunda kalır.\n"
        "2. **🎯 Gereksinimler**'de bir zorunluluğu **tercih**'e çevirin; "
        "tercih karşılanamazsa sezon yine üretilir, yalnız uyarı çıkar.\n"
        "3. **📅 Yıllık Tablo**'dan ayları tek tek üretin — tek ay çözmek "
        "bütün sezonu birlikte çözmekten çok daha kolaydır.\n\n"
        "İsterseniz Ayarlar'dan **🐢 Sabırlı** kademesini seçip daha uzun "
        "bekletebilirsiniz, ama genelde yukarıdaki üç adım daha etkilidir.",
    ),
    (
        "Bir grubun hangi birimlere kaç kişi verildiğini nasıl görürüm/ayarlarım?",
        "📦 **Kapasite Planı** ekranı tam bunun için. Her grup için birim "
        "listesini kontenjanıyla gösterir, toplamın grubun öğrenci sayısına "
        "oturup oturmadığını söyler ve her birime bir **doldurma politikası** "
        "verdirir. Bir birimi bir grup için **iptal** ederseniz (elle yaparken "
        "griye boyadığınız gibi) o gruptan kimse oraya verilmez — çözücü de "
        "buna uyar. “Tekrarlı liste” bölümü, elle tuttuğunuz tablonun birebir "
        "kopyalanabilir hâlini verir.",
    ),
    (
        "“Şu öğrenciler şu birimleri görsün” kuralını nasıl kurarım?",
        "🎯 **Gereksinimler** ekranından (Sezon Kurulumu bölümü). Kuralı "
        "olduğu gibi yazarsınız: *kime* (tüm öğrenciler / bir grup / bir sınıf "
        "/ bir program / tek tek seçtikleriniz) — *hangi birimlerden* "
        "(adlarıyla seçersiniz) — *kaç kez*. Örneğin “YB/B, YB/C, YB/D'den en "
        "az 1” ya da “D sınıfı doğum birimlerinden en az 1”. Eskiden bunun "
        "için birimlere branş atayıp branşı zorunlu tutmak gerekiyordu; artık "
        "gerekmiyor. Kaydetmeden önce ekran kuralın **kaç öğrenciyi "
        "kapsadığını** ve her grupta **kaç uygun birim** olduğunu gösterir, "
        "karşılanamayacak bir kural kurarsanız kırmızı uyarır. "
        "Varsayılan katalogdan açılan sezonlarda rotasyon belgelerinizdeki "
        "kurallar hazır gelir; elle kurulmuş sezonlarda **hazır kural setini** "
        "tek düğmeyle kurabilirsiniz. Var olan bir kuralı değiştirmek için "
        "satırındaki **✏️ Düzenle**'ye basın — silip yeniden kurmanız "
        "gerekmez.",
    ),
    (
        "“Şu birimler tam dolsun, kalanlar eşit dağılsın” nasıl kurulur?",
        "📦 **Kapasite Planı** ekranından (Sezon Kurulumu bölümü). Her birime "
        "tek bir politika verirsiniz: **Tam dolmalı** (her ay kontenjanı kadar "
        "öğrenci bulunmak zorunda), **Mümkünse dolsun**, **Havuz** (kalanlar "
        "buralara eşit dağılır), **Yedek** (yalnız başka yer kalmayınca), "
        "**Serbest**. Ekran üstteki dört sayıyla toplamı canlı gösterir: "
        "öğrenci sayısı, tam dolanların çektiği kişi, dağıtılacak kalan ve "
        "havuz birimi başına ortalama. Tam dolanların toplamı grubu aşarsa "
        "ekran uyarır — o kurulumla hiçbir ay üretilemez.",
    ),
    (
        "Bir şubeyi (sınıfı) diğer gruba almam gerekiyor.",
        "Veri Yönetimi ▸ 🎨 Sınıflar sekmesindeki **“Sınıf → grup "
        "eşleştirmesi”** bölümünden şubenin grubunu seçip uygulayın; o "
        "şubedeki tüm öğrenciler birlikte taşınır. İçe aktarımda yaptığınız "
        "seçim kalıcı değildir, istediğiniz zaman değiştirebilirsiniz. "
        "Kayıtlı atamaları olan öğrenciler taşınırsa geçmiş aylar Kural "
        "Kontrolü'nde uyumsuz görünebilir; geçmiş silinmez, değişiklik asıl "
        "olarak sonraki ayları etkiler.",
    ),
    (
        "Zorunluluklar veya çözücünün davranışı değişebilir mi?",
        "Evet. Her öğrencinin görmesi gereken birimleri **Gereksinimler** "
        "ekranından, çözücü ağırlıklarını Veri Yönetimi ▸ ⚙️ Ayarlar "
        "sekmesinden değiştirebilirsiniz. Değişiklik bir sonraki rotasyon "
        "üretiminden itibaren geçerlidir; kayıtlı geçmiş aylar kendiliğinden "
        "değişmez.",
    ),
    (
        "İki öğrenciyi hep ayrı (veya hep birlikte) tutmam gerekiyor.",
        "**Özel Kurallar** ekranından kendi kuralınızı ekleyin. "
        "Kuralın hangi aydan hangi aya geçerli olacağını da seçersiniz — "
        "seçtiğiniz iki ay **dahildir**.",
    ),
    (
        "Yanlışlıkla bir sezonu sildim.",
        "Sezonlar kalıcı silinmez; verinizin bulunduğu klasörün içindeki "
        "**trash** klasörüne taşınır. Uygulamayı size veren kişi geri "
        "getirebilir. Yedeğiniz varsa Veri Yönetimi ▸ 💾 Yedekleme'den "
        "kendiniz de geri yükleyebilirsiniz.",
    ),
    (
        "Verilerim nerede duruyor? Başka bilgisayara nasıl taşırım?",
        "Veri Yönetimi ▸ 💾 Yedekleme'den yedek dosyasını indirin, diğer "
        "bilgisayarda aynı sekmeden geri yükleyin. Geri yükleme mevcut "
        "sezonlarınızın üzerine yazmaz, yeni sezon olarak açar.",
    ),
    (
        "Dışa aktardığım Excel'i tekrar içe aktarabilir miyim?",
        "Evet — **yıllık** görünüm dosyası tekrar içe aktarılabilir; "
        "atamalar, birimler ve sınıflar korunur. Tek ay görünümü ise "
        "yazdırmak/paylaşmak içindir, içe aktarılmaz.",
    ),
]


def _faq() -> None:
    st.subheader("Sık sorulan sorular")
    for question, answer in _FAQ:
        with st.expander(question):
            st.markdown(answer)


# ---------------------------------------------------------------- sorun
def _troubleshooting() -> None:
    st.subheader("Bir şeyler ters giderse")
    st.markdown(
        """
**Sayfa takıldı / garip görünüyor.**
Tarayıcıda **F5** ile sayfayı yenileyin. Kaydedilmiş veriniz kaybolmaz.

**Rotasyon üretimi uzun sürüyor.**
Tüm sezonu birden üretmek birkaç dakika alabilir. Bu sırada başka
sayfalara geçebilir, hatta uygulamayı kapatıp açabilirsiniz; biten taslak
siz onaylayana kadar saklanır.

**Yanlış bir şey kaydettim.**
Yedeğiniz varsa Veri Yönetimi ▸ 💾 Yedekleme'den geri yükleyin. Yedek
yoksa ay sütununu Yıllık Tablo'da elle düzeltip yeniden kaydedin.

**Uygulamayı nasıl kapatırım?**
Tarayıcı sekmesini kapatmak yetmez — uygulamayı başlattığınız **siyah
pencereyi** kapatın. Sekmeyi yanlışlıkla kapattıysanız uygulama hâlâ
açıktır: kısayola tekrar çift tıklayın, sekme yeniden açılır.

**Siyah pencerede uygulama donmuş gibi görünüyor.**
Pencerenin içine tıkladıysanız **Esc** tuşuna basın.

**Uygulama kapanıyor / "modül yüklenemedi" hatası çıkıyor.**
Uygulama klasöründeki **`tanila.bat`** dosyasına çift tıklayın; çıkan
metnin tamamını kopyalayıp uygulamayı size veren kişiye gönderin. Sorunun
nedenini o metin söyler.
        """
    )
    if getattr(sys, "frozen", False):
        st.divider()
        st.subheader("Uygulamayı kapat")
        st.caption(
            "Aşağıdaki düğme uygulamayı tamamen kapatır. Kaydedilmemiş "
            "taslaklarınız varsa önce kaydedin."
        )
        sure = st.checkbox("Uygulamayı kapatmak istiyorum", key="help_quit_sure")
        if st.button("🚪 Uygulamayı kapat", disabled=not sure, key="help_quit"):
            st.success(
                "Uygulama kapatılıyor. Bu tarayıcı sekmesini kapatabilirsiniz."
            )
            threading.Thread(target=_delayed_exit, daemon=True).start()


def _delayed_exit() -> None:
    """Tarayıcı 'kapatılıyor' mesajını gösterebilsin diye kısa gecikme."""
    import os

    time.sleep(1.5)
    os._exit(0)
