"""Kural Kontrolü — iki ayrı soru, iki ayrı sekme.

* **Geçmiş**: kayıtlı atamalar kurallara uyuyor mu? (rules.check_all)
* **Gelecek**: kalan sezon hâlâ kurallara uygun TAMAMLANABİLİR mi?
  (risk.forward_risks + istenirse deneme çözümü)

İkincisi bu uygulamada kritik: bazı sorunlar fark edildiğinde telafisi
kalmaz (öğrencinin palyatif görmediği HAZİRAN'da anlaşılırsa yapılacak bir
şey yoktur). O yüzden "gelecek" sekmesi geçmişle eşit ağırlıkta durur.
"""
from __future__ import annotations

import threading

import streamlit as st

from rotasyon.rules import check_all
from .common import (
    RISK_INTRO,
    collect_risks,
    data_fingerprint,
    show_risks,
    season_requirements,
    show_violations_scoped,
)

# ---- arka plan deneme çözümü kaydı ----
# Deneme çözümü dakikalarca sürebilir. ANA AKIŞTA çalıştırılırsa Streamlit'in
# tüm sunucusu bloke olur: tarayıcı sağlık yoklamasına yanıt alamaz ve
# "Is Streamlit still running?" hatası basar — kullanıcı uygulamanın
# çöktüğünü sanar. Bu yüzden iş daemon thread'e taşınır; thread HİÇBİR st.*
# çağrısı yapmaz, sonucu bu modül düzeyindeki kayda yazar (yeniden koşularda
# yaşar). Anahtar: sezon klasörü yolu.
_RISK_JOBS: dict[str, dict] = {}


def render(store) -> None:
    """Tek soruya iki yandan cevap: "sezonum sağlam mı?"

    Önceden iki sekme vardı (geçmiş / gelecek) ve sekme her zaman birini
    gizliyordu — kullanıcı diğer yarıya bakmayı unutabiliyordu. Şimdi üstte
    ikisinin ÖZETİ birlikte duruyor, ayrıntılar altta sırayla; temiz olan
    bölüm tek satıra iniyor.
    """
    st.header("🛡️ Kural Kontrolü")
    students = store.load_students()
    units = store.load_units()
    assignments = store.load_assignments()
    settings = store.load_settings()
    months = settings["months"]
    custom_rules = store.load_custom_rules()
    requirements = season_requirements(store)

    violations = (
        check_all(
            students, units, assignments, months,
            custom_rules=custom_rules, settings=settings,
            requirements=requirements,
        )
        if assignments
        else []
    )
    risks = collect_risks(
        students, units, months, assignments, custom_rules, settings,
        requirements,
    )
    _status_header(violations, risks, bool(assignments))

    st.divider()
    _past_section(store, students, units, assignments, violations)
    st.divider()
    _future_section(store, students, units, assignments, months, custom_rules,
                    settings, risks, str(store.data_dir), requirements)


def _status_header(violations, risks, has_assignments) -> None:
    """Her iki yarının durumu tek bakışta."""
    from rotasyon.risk import risk_counts

    hatalar = sum(1 for v in violations if v.severity == "hata")
    uyarilar = len(violations) - hatalar
    r_err, r_warn = risk_counts(risks)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**📋 Kayıtlı atamalar**")
        if not has_assignments:
            st.caption("Henüz kayıtlı atama yok.")
        elif hatalar:
            st.markdown(f":red[**{hatalar} hata**]"
                        + (f" · {uyarilar} uyarı" if uyarilar else ""))
        elif uyarilar:
            st.markdown(f":orange[{uyarilar} uyarı] · hata yok")
        else:
            st.markdown(":green[Tüm atamalar kurallara uygun ✅]")
    with c2:
        st.markdown("**🔮 Kalan sezon**")
        if r_err:
            st.markdown(f":red[**{r_err} kritik risk**]"
                        + (f" · {r_warn} uyarı" if r_warn else ""))
        elif r_warn:
            st.markdown(f":orange[{r_warn} uyarı] · kritik risk yok")
        else:
            st.markdown(":green[Öngörülen tıkanma yok ✅]")


# ======================= GEÇMİŞ =======================

def _past_section(store, students, units, assignments, violations) -> None:
    st.subheader("📋 Kayıtlı atamalar")
    if not assignments:
        st.caption(
            "Henüz kayıtlı atama yok — rotasyon ürettikçe burada denetlenecek."
        )
        return
    st.caption(
        "Kayıtlı tüm atamalar kurallara karşı denetlenir. Elle "
        "değişikliklerden sonra da çalıştırabilirsiniz."
    )
    with st.expander("ℹ️ Geçmiş aylar neden hata gösterebilir?"):
        st.markdown(
            "Bu denetim **tüm ayları GÜNCEL veriyle** karşılaştırır: bir "
            "birimin kontenjanını düşürür ya da bir kısıt eklerseniz, geçmiş "
            "bir ay artık buna uymuyorsa burada hata olarak görünür. Bu "
            "yalnız **bilgilendirme** amaçlıdır — geçmiş rotasyonlar "
            "kendiliğinden değişmez ve bu eski hatalar yeni ay kaydetmenizi "
            "engellemez. Zamana bağlı kurallar (başlangıç/bitiş ayı olanlar) "
            "yalnız kendi aylarında denetlenir."
        )
    _orphan_cleanup_panel(store, students, units, assignments, violations)
    # Bu ekran tümüyle kayıtlı (tamamlanmış) veriyi denetler; düzenleme kapsamı
    # yoktur → aya/öğrenciye bağlı her ihlal "geçmişe dönük" sayılır. Ayar
    # kapalıyken yalnız yapısal (aysız) ihlaller kalır, gerisi gizlenir.
    show_violations_scoped(
        violations, empty_message="Tüm atamalar kurallara uygun. ✅"
    )


# ======================= GELECEK =======================

def _future_section(store, students, units, assignments, months, custom_rules,
                    settings, risks, key, requirements=None) -> None:
    from rotasyon.risk import risk_counts

    st.subheader("🔮 Kalan sezon (ileriye dönük)")
    st.caption(RISK_INTRO)
    errs, warns = risk_counts(risks)
    if not risks:
        st.success(
            "Kalan sezonda öngörülen bir tıkanma yok. ✅ "
            "(Hesaplanabilir riskler denetlendi.)"
        )
    else:
        if errs:
            st.error(
                f"{errs} kritik risk: giderilmezse rotasyon tamamlanamaz ya da "
                "öğrenci eksik mezun olur."
            )
        if warns:
            st.warning(f"{warns} uyarı: payı dar, dikkatli ilerleyin.")
        show_risks(risks)

    st.divider()
    fingerprint = data_fingerprint(
        students, units, assignments, custom_rules, [settings]
    )
    _deep_panel(students, units, months, assignments, custom_rules, settings,
                key, fingerprint, requirements)


def _run_deep_job(job, students, units, months, assignments, custom_rules,
                  settings, requirements=None) -> None:
    """Daemon thread gövdesi — burada ASLA st.* çağrılmaz."""
    from rotasyon.risk import deep_feasibility

    def _ilerleme(idx, toplam, grup, not_=None):
        # not_ = "zor çıktı — daha uzun deniyor (2/3, 4 sn)" gibi insan-okunur
        # bir ek; uzun süren aşamalarda yazının donmasını engeller
        job["progress"] = (idx, toplam, grup, not_)

    try:
        job["results"] = deep_feasibility(
            students, units, months, assignments, custom_rules, settings,
            on_group=_ilerleme, requirements=requirements,
        )
    except Exception as exc:  # çözücü çökerse uygulama ayakta kalsın
        job["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        job["done"] = True


@st.fragment(run_every=2.0)
def _deep_job_watch(key: str) -> None:
    """Süren denemeyi 2 sn'de bir yoklar; bitince sayfayı tazeler."""
    job = _RISK_JOBS.get(key)
    if job is None or job.get("done"):
        st.rerun(scope="app")
        return
    prog = job.get("progress")
    if prog:
        idx, toplam, grup, not_ = prog
        if not_:
            simge = "🔎" if "sebep" in not_ else "🐢"
            metin = f"{simge} Grup {grup} {not_} ({idx}/{toplam})"
        else:
            metin = f"🔄 Grup {grup} çözülüyor… ({idx}/{toplam})"
        st.progress((idx - 1) / toplam, text=metin)
    else:
        st.progress(0.0, text="🔄 Çözücü hazırlanıyor…")
    st.caption(
        "Analiz **arka planda** sürüyor; başka sayfalara geçebilirsiniz, "
        "hiçbir şey kaydedilmiyor."
    )


def _deep_panel(students, units, months, assignments, custom_rules,
                settings, key, fingerprint, requirements=None) -> None:
    """Deneme çözümü: kalan sezonu gerçekten çözmeyi dener.

    Yukarıdaki aritmetik kontroller kesin çelişkileri bulur ama kombinatorik
    çıkmazları (kuralların birlikte tıkaması) göremez. Bu deneme çözücünün
    kendisini kullandığı için kesin cevap verir — yavaştır, o yüzden hem
    butonla hem arka planda çalışır.
    """
    st.subheader("🔮 Derin risk analizi (deneme çözümü)")
    from rotasyon.models import DEFAULT_SETTINGS

    limit = settings.get("solver", {}).get(
        "season_time_limit_seconds",
        DEFAULT_SETTINGS["solver"]["season_time_limit_seconds"],
    )
    st.caption(
        "Yukarıdaki denetim hesapla bulunabilecek tıkanmaları gösterir. Bu "
        "düğme ise kalan ayları **gerçekten çözmeyi dener** ve kuralların "
        "birlikte tıkanıp tıkanmadığına kesin cevap verir. Kolay sezonlarda "
        f"grup başına ~{limit} saniye; zor çıkarsa uygulama kendiliğinden "
        f"daha uzun deniyor (en çok {limit * 4} saniye). "
        "**Hiçbir şey kaydedilmez**, yalnız denenir."
    )

    job = _RISK_JOBS.get(key)
    calisiyor = job is not None and not job.get("done")

    label = "🔮 Yeniden dene" if job else "🔮 Kalan sezonu şimdi dene"
    if st.button(label, key="deep_risk_run", disabled=calisiyor):
        _RISK_JOBS[key] = {"done": False, "fingerprint": fingerprint}
        threading.Thread(
            target=_run_deep_job,
            args=(_RISK_JOBS[key], students, units, months, assignments,
                  custom_rules, settings, requirements),
            daemon=True,
        ).start()
        st.rerun()

    if calisiyor:
        _deep_job_watch(key)
        return
    if job is None:
        return
    if job.get("error"):
        st.error(
            "Deneme çözümü çalıştırılamadı. Kurulumda bir sorun olabilir; "
            "uygulama klasöründeki `tanila.bat` teşhisini çalıştırın.\n\n"
            + job["error"]
        )
        return

    # Veri, analizden SONRA değiştiyse sonuç bayattır — sessizce göstermek
    # yanıltıcı olur (kullanıcının 4. maddesi). Net damgala.
    if job.get("fingerprint") != fingerprint:
        st.warning(
            "🔄 Veriler bu analizden sonra değişti — aşağıdaki sonuç **güncel "
            "değil**. Yukarıdaki düğmeyle yeniden çalıştırın."
        )

    results = job.get("results") or []
    if not results:
        st.info("Denenecek grup bulunamadı.")
        return
    _deep_results(results)


def _deep_results(results) -> None:
    """Sonuç kartları: üstte özet, altta grup başına neden/öneri."""
    cozulen = sum(1 for r in results if r.ok)
    denenen = [r for r in results if r.status != "ATLANDI"]
    if denenen and cozulen == len(denenen):
        st.success(
            f"✅ Denenen {len(denenen)} grubun tamamı kurallara uygun "
            "tamamlanabiliyor."
        )
    elif denenen:
        st.error(
            f"⚠️ {len(denenen)} gruptan {len(denenen) - cozulen} tanesi bu "
            "haliyle **tamamlanamıyor**. Ayrıntı ve öneriler aşağıda."
        )

    for res in results:
        etiket = f"{res.group}. Grup"
        with st.container(border=True):
            if res.status == "ATLANDI":
                st.markdown(f"**{etiket}** — ⏭️ tüm aylar zaten üretilmiş.")
            elif res.ok:
                st.markdown(
                    f"**{etiket}** — ✅ kalan {len(res.months)} ay "
                    "kurallara uygun tamamlanabiliyor."
                )
                st.caption("Aylar: " + ", ".join(res.months))
            elif res.status == "INFEASIBLE":
                st.markdown(
                    f"**{etiket}** — ❌ kalan {len(res.months)} ay bu haliyle "
                    "**çözülemiyor**."
                )
                if res.reasons:
                    st.markdown("**Neden:**")
                    for reason in res.reasons:
                        st.markdown(f"- {reason}")
                if res.suggestions:
                    st.info(
                        "**Ne yapmalı:**\n"
                        + "\n".join(f"- {s}" for s in res.suggestions)
                    )
                if not res.reasons and not res.suggestions:
                    st.caption(
                        "Çözücü kesin bir sebep ayıklayamadı; genellikle "
                        "kontenjanlar ve kısıtlar birlikte tıkar. Kontenjanları "
                        "ve cinsiyet kısıtlarını gözden geçirin."
                    )
            else:
                # UNKNOWN. Kullanıcıyı bir AYARA yönlendirmiyoruz ("çözüm
                # süresini artırın" teknik bilgi ister ve ne kadar artıracağı
                # belirsizdir). Uygulama zaten kademeli olarak daha uzun
                # denedi; burada YAPILABİLİR şeyler söylenir.
                st.markdown(
                    f"**{etiket}** — ⏳ bu grup bilgisayarın rahat "
                    "çözebileceğinden daha zor."
                )
                st.caption(
                    "Uygulama giderek daha uzun süre denedi ama kesin sonuca "
                    "ulaşamadı. **Bu, çözümü olmadığı anlamına gelmez** — "
                    "kurallar bu grup için çok sıkı demektir."
                )
                if res.reasons:
                    for reason in res.reasons:
                        st.caption(f"• {reason}")
                st.info(
                    "**Ne yapabilirsiniz** (en etkiliden başlayarak):\n"
                    "- 📦 **Kapasite Planı**'nda kontenjanlara bir-iki "
                    "kişilik pay bırakın — “kontenjan öğrenci sayısına tam "
                    "eşit” uyarısı varsa asıl sebep odur.\n"
                    "- 🎯 **Gereksinimler**'de bir zorunluluğu **tercih**'e "
                    "çevirin; tercih karşılanamazsa sezon yine üretilir.\n"
                    "- Yıllık Tablo'dan ayları **tek tek** üretin: tek ay "
                    "çözümü bütün sezonu birlikte çözmekten çok daha kolaydır."
                )


def _orphan_cleanup_panel(store, students, units, assignments, violations) -> None:
    """Sahipsiz atamalar (kural 0) için tek tıkla temizlik.

    Silinmiş öğrenci/birime işaret eden atamalar normal akışta oluşmaz
    (silme akışları korunur) ama eski yedeğin kısmi geri yüklenmesi ya da
    elle düzenlenmiş JSON ile ortaya çıkabilir. Denetleyici bunları hata
    olarak gösterir; kullanıcı JSON'a giremeyeceği için düzeltme de burada
    sunulmalıdır.
    """
    if not any(v.rule_no == 0 for v in violations):
        return
    from rotasyon.maintenance import strip_orphan_assignments

    kept, n_orphans = strip_orphan_assignments(students, units, assignments)
    if not n_orphans:
        return
    st.warning(
        f"🧹 {n_orphans} atama, artık var olmayan bir öğrenci veya birime "
        "işaret ediyor (genelde eski bir yedekten kısmi geri yükleme sonucu). "
        "Bu kayıtlar hiçbir ekranda görünmez ve hiçbir işe yaramaz; güvenle "
        "temizlenebilir."
    )
    if st.button(f"🧹 {n_orphans} sahipsiz atamayı temizle", key="clean_orphans"):
        store.save_assignments(kept)
        st.toast(f"{n_orphans} sahipsiz atama temizlendi ✅", icon="🧹")
        st.rerun()
