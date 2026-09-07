# CathSim LA - Claude Code Ana Gelistirme Komutu

> Bu dosya projenin **sozlesmesidir**. Kod, dokumantasyon ve testler bu dosyaya
> uymak zorundadir. Sapma varsa `docs/assumptions.md` icinde gerekcesiyle
> yazilmalidir.

**Research prototype - Not for clinical use.**

## ROLUN

Hesaplamali mekanik, geometrik modelleme, medikal simulasyon, kateter mekanigi,
C++/Python, WebGL ve yazilim dogrulama alanlarinda uzman kidemli bir Ar-Ge
yazilim muhendisi.

Bu depoda CathSim LA adli, hastaya ozel sol atriyum geometrisi uzerinde
ablasyon kateterlerinin 3D hareketini, bukulmesini, sekil degistirmesini ve
doku ile mekanik temasini simule eden bir arastirma prototipi gelistirilir.

Urun klinik karar vermek icin kullanilmaz. Tum ekranlarda ve raporlarda su
ifade gorunur olmali:

> Research prototype - Not for clinical use.

## ANA AMAC

Ilk calisan surumde kullanici:

1. Bir sol atriyum STL/OBJ modeli yukleyebilmeli.
2. Sahneye parametrik bir steerable kateter ekleyebilmeli.
3. Kateteri ileri-geri itebilmeli, dondurebilmeli ve distal ucunu iki eksende
   bukebilmeli.
4. Kateterin ani kirilan bir poliline degil, surekli ve fiziksel olarak tutarli
   bir elastik cisim gibi davrandigini gorebilmeli.
5. Kateter ile atriyum yuzeyi arasindaki temasi, penetrasyonu, temas kuvvetini
   ve bosluklari renkli olarak inceleyebilmeli.
6. Simulasyonu durdurabilmeli, tek adim ilerletebilmeli, sifirlayabilmeli ve
   sonuclari JSON/CSV olarak disari aktarabilmeli.

Mimari daha sonra kriyobalon, halka kateter, lattice kateter ve
FARAWAVE-benzeri cok spline'li PFA kateterine genisleyebilmeli.

## ONEMLI BILIMSEL SINIR

* Ureticiye ait bilinmeyen geometri, malzeme veya mekanik degerleri uydurma.
* Ticari urun isimlerini ilk fizik dogrulamasi tamamlanmadan birebir dogrulanmis
  model gibi sunma.
* Baslangic modellerini `GenericSteerableRF`, `GenericBalloon`, `GenericLoop` ve
  `GenericPentasplinePFA` olarak adlandir.
* Tum boyut, elastisite, bukulme rijitligi, torsiyon rijitligi, damping, tendon
  kazanimi ve temas parametreleri acik bir yapilandirma dosyasindan okunmali.
* Bilinmeyen parametreleri `CALIBRATION_REQUIRED` olarak isaretle.
* Geometri benzerligi, mekanik dogruluk anlamina gelmez. Bu ayrimi
  dokumantasyonda acikca belirt.
* Ilk surum lezyon, elektrik alani, PFA esigi veya termal hasar tahmini
  yapmayacak. Bunlar ayri bir gelecek moduludur.

## GELISTIRME YAKLASIMI

Once depo durumunu incele. Var olan dosyalari, kullanici degisikliklerini veya
Git gecmisini silme. Bos depo ise asagidaki monorepo yapisini olustur.

```text
cathsim-la/
  README.md
  CLAUDE.md
  LICENSE
  .gitignore
  docs/
    architecture.md
    physics-model.md
    validation-plan.md
    catheter-parameter-guide.md
    regulatory-boundary.md
  apps/
    viewer/
  services/
    simulation-api/
  packages/
    physics-core/
    geometry-core/
    shared-schema/
  assets/
    demo/
  configs/
    generic-steerable-rf.json
    generic-pentaspline-pfa.json
  tests/
    reference-data/
  scripts/
```

## TEKNOLOJI SECIMI

* UI: React + TypeScript + Vite
* 3D goruntuleme: Three.js veya React Three Fiber
* State: Zustand
* UI testleri: Vitest + React Testing Library
* Uctan uca test: Playwright
* API: Python 3.12 + FastAPI + Pydantic
* Sayisal prototip: NumPy + SciPy
* Mesh islemleri: trimesh; gerekiyorsa pyvista/VTK
* Performans cekirdegi: C++20 + CMake + Eigen
* Python baglantisi: pybind11
* C++ testleri: Catch2 veya GoogleTest
* Kod kalitesi: Ruff, mypy, ESLint, Prettier, clang-format, clang-tidy
* Paketleme: Docker Compose; yerel gelistirme Docker olmadan da calismali

Ilk dikey dilimde fizik algoritmasinin referans uygulamasini Python ile dogrula.
Ardindan ayni arayuzu koruyarak performans-kritik cozumleyiciyi C++'a tasi.
Python ve C++ sonuclari tolerans icinde karsilastirilsin.

## BIRIM SISTEMI

* uzunluk: mm
* zaman: s
* kuvvet: N
* gerilme/modul: MPa (N/mm^2)
* aci: radyan; UI'da dereceye cevrilebilir

Her fizik parametresinin birimi semada ve arayuzde acikca yazmali. Kod icinde
birimsiz sihirli sayi kullanma.

## FIZIK MODELI

Kateter hareketi klinik manipulasyon hizlarinda agir dampingli ve buyuk olcude
quasi-static kabul edilebilir. Ancak animasyon icin zaman adimli cozum
desteklenmeli.

### 1. Steerable kateter govdesi

Kateteri merkez cizgisi boyunca dugumler ve segmentlerden olusan, uzayda
bukulebilen ve burulabilen bir rod olarak modelle.

Tercih sirasi:

1. Discrete Elastic Rods veya geometrik olarak tam Cosserat rod yaklasimi.
2. Gercek zaman kararliligi icin XPBD constraint cozumleyici.
3. Basit mass-spring yalnizca gecici debug karsilastirmasi olabilir; nihai fizik
   modeli olamaz.

Model en az su davranislari icermeli:

* eksenel uzama/sikisma direnci
* bukulme rijitligi
* torsiyon rijitligi
* kayma kisiti veya yeterince guclu shear rijitligi
* yapisal damping
* yercekimi acilip kapatilabilir olmali
* proksimal itme/cekme
* proksimal eksenel rotasyon
* iki eksenli distal steering
* kateterin kendi uzerine ve anatomiye temasi

Surekli rod enerjisinin dokumantasyonda temel formu:

```text
E = integral [
  1/2 (kappa-kappa0)^T B (kappa-kappa0)
  + 1/2 (tau-tau0)^T C (tau-tau0)
  + 1/2 (epsilon-epsilon0)^T S (epsilon-epsilon0)
] ds
```

Kodda kullanilan ayriklastirma ile bu denklemin baglantisini
`docs/physics-model.md` icinde acikla.

### 2. Steering/aktuasyon modeli

Kateter sapindaki knob hareketini distal bolgede hedef/rest curvature olusturan
parametrik bir aktuasyon olarak modelle.

* `steer_x` ve `steer_y` girisleri normalize `[-1, 1]` araliginda olsun.
* Aktuasyon yalnizca yapilandirmada tanimli distal `active_length_mm` bolgesine
  etki etsin.
* Ilk modelde tendon kuvvetini dogrudan klinik kuvvet olarak iddia etme.
* `steer_gain_rad_per_mm` veya esdeger katsayi kalibrasyon parametresi olsun.
* Steering serbest bir teleport islemi degil, rod cozumleyicisinin rest
  curvature girdisi olmali.
* Histerezis ilk MVP'de kapali olabilir; arayuz ve veri modeli gelecek
  Preisach/Bouc-Wen benzeri model icin genisleyebilir olmali.

### 3. Proksimal hareket ve sheath

* Insert/retract hareketi proksimal sinir kosulu veya sheath cikis noktasindan
  beslenen uzunluk olarak temsil edilmeli.
* Rotate hareketi proksimal orientation sinir kosuluna uygulanmali.
* Sheath icindeki segmentler icin konumsal ve yonelimsel kisit uygulanabilmeli.
* Kullanici sheath cikis noktasini ve eksenini sahnede gorebilmeli.

### 4. Temas modeli

Atriyum modeli sabit bir triangle mesh olarak kabul edilsin. Ilk surumde doku
deformasyonu opsiyonel ve kapali olabilir.

* BVH/AABB hizlandirmasi
* rod kapsulu ile triangle mesh arasinda en yakin nokta
* penetrasyon onleme
* penalty veya tercihen XPBD unilateral contact constraint
* ayarlanabilir surtunme
* temas normali
* dugum/segment bazli temas kuvveti tahmini
* maksimum penetrasyon metrigi
* kararsizlik ve patlama durumlarinda guvenli durdurma

Temas kuvvetinin sayisal modelden turetilen bir tahmin oldugunu UI'da belirt.
Kalibre edilmeden klinik contact-force degeri olarak adlandirma.

### 5. GenericPentasplinePFA modeli

Steerable rod dogrulandiktan sonra ikinci kateter olarak bes spline'li
parametrik bir PFA geometri modeli ekle.

* Merkezi shaft ve distal spline dugumleri tek bir constraint graph ile
  baglansin.
* Spline sayisi, uzunlugu, kalinligi, elektrot sayisi ve elektrot konumlari
  config'ten gelsin.
* `deployment` parametresi `[0,1]` olsun.
* Basket ve flower durumlarini iki farkli sabit mesh dosyasi arasinda lineer
  vertex morph ile gecistirme. Bunun yerine rest geometry/rest curvature ve
  mekanik kisitlari degistirerek fiziksel gecis uret.
* UI'da basket/flower isimleri gosterilebilir; ara konfigurasyonlar surekli
  olmali.
* Yeterli veri yoksa modeli acikca `kinematic-mechanical hybrid, calibration
  required` olarak etiketle.
* Elektrotlar spline ile birlikte hareket etmeli ve her elektrodun mesh'e
  uzakligi hesaplanmali.

### 6. Sonraki kateter aileleri icin arayuz

```text
CatheterModel
  loadParameters(config)
  initialize(scene, entryPose)
  setInsertion(mm)
  setAxialRotation(rad)
  setSteering(x, y)
  setDeployment(value)
  step(dt)
  getRenderGeometry()
  getElectrodePoses()
  getContactMetrics()
  reset()
```

Planlanan turevler: `GenericSteerableRF`, `GenericBalloon`, `GenericLoop`,
`GenericLatticeSphere`, `GenericPentasplinePFA`.

## GEOMETRI VE GORSELLESTIRME

### Atriyum mesh islemleri

* STL ve OBJ import et.
* Mesh manifold kontrolu yap.
* Ters normal, duplicate vertex, degenerate face ve olcek sorunlarini raporla.
* Kaynak dosyada birim bilgisi yoksa kullanicidan mm/cm secmesini iste; sessiz
  varsayim yapma.
* Orijinal mesh ile islemede kullanilan mesh'i ayri tut.
* Otomatik repair islemleri geri alinabilir ve raporlanabilir olmali.

### Render gereksinimleri

* Atriyum yari saydam ve depth-correct gorunsun.
* Kateter shaft, spline ve elektrotlar farkli materyallerle gosterilsin.
* Temas bolgeleri mavi-sari-kirmizi heatmap ile gosterilsin.
* Collision debug, rod frame, node, tangent, normal ve BVH gorunumleri acilip
  kapatilabilsin.
* Kamera orbit, pan, zoom ve odaklama desteklesin.
* Sagittal/coronal/axial preset gorunumleri olsun.
* FPS, solver iteration, residual, max penetration ve simulation time ekranda
  gorunsun.
* Renkler tek basina bilgi tasimasin; tooltip/sayisal deger de kullan.

## API VE VERI SEMASI

Pydantic ve TypeScript tipleri tek bir JSON Schema/OpenAPI kaynagindan
turetilsin.

Minimum varliklar: `CatheterParameters`, `MaterialParameters`,
`ActuationInput`, `SimulationSettings`, `MeshMetadata`, `SimulationFrame`,
`ElectrodePose`, `ContactSample`, `ContactMetrics`, `ValidationResult`.

Bir `SimulationFrame` en az sunlari tasimali:

```json
{
  "time_s": 0.0,
  "centerline_mm": [[0.0, 0.0, 0.0]],
  "orientations_xyzw": [[0.0, 0.0, 0.0, 1.0]],
  "electrodes": [],
  "contacts": [],
  "solver": {
    "iterations": 0,
    "residual": 0.0,
    "max_penetration_mm": 0.0,
    "converged": true
  }
}
```

Canli kontrol icin WebSocket kullan. Komutlari timestamp ve sequence number ile
isle; gecikmis komutlari deterministik bicimde ele al.

## PARAMETRE DOSYASI

`configs/generic-steerable-rf.json` icin tam sema ve aciklama olustur. En az su
alanlari icersin:

```json
{
  "schema_version": "0.1.0",
  "model_type": "GenericSteerableRF",
  "display_name": "Generic steerable RF catheter",
  "status": "RESEARCH_ONLY_CALIBRATION_REQUIRED",
  "geometry": {
    "total_length_mm": 1100.0,
    "outer_diameter_mm": 2.5,
    "tip_length_mm": 3.5,
    "active_length_mm": 70.0,
    "node_spacing_mm": 2.0
  },
  "material": {
    "youngs_modulus_mpa": null,
    "poisson_ratio": null,
    "bending_stiffness_n_mm2": null,
    "torsional_stiffness_n_mm2": null,
    "axial_stiffness_n": null,
    "damping_n_s_per_mm": null
  },
  "actuation": {
    "steer_gain_rad_per_mm": null,
    "max_steering_input": 1.0,
    "bidirectional": true
  },
  "contact": {
    "friction_coefficient": null,
    "compliance_mm_per_n": null,
    "catheter_collision_radius_mm": 1.25
  },
  "provenance": {
    "geometry_source": "USER_MEASUREMENT_REQUIRED",
    "material_source": "CALIBRATION_REQUIRED",
    "last_calibrated_at": null
  }
}
```

`null` olan zorunlu fizik degerlerinde uygulama sessizce gercek simulasyon
baslatmasin. Kullanici demo parametreleriyle calismayi secerek onay verebilsin.
Demo degerleri ayri demo profiline konulsun ve klinik deger gibi sunulmasin.

## DOGRULAMA TESTLERI

Gorsel olarak guzel gorunmesi kabul kriteri degildir.

1. Konsol kiris testi: `delta = F L^3 / (3 E I)`.
2. Saf bukulme testi: sabit moment altinda hedef curvature.
3. Saf torsiyon testi: analitik rod sonucu.
4. Rigid-body invariance.
5. Zaman adimi duyarliligi.
6. Mesh temas testi.
7. Enerji/damping testi.
8. Determinism testi.
9. Python-C++ parity.
10. NaN/Inf testi.

Her test toleransi gerekceli bicimde `docs/validation-plan.md` icinde yazilsin.
Basarisiz testi es gecme, toleransi rastgele genisletme veya testi silme.

### Sonraki fiziksel bench kalibrasyonu icin hazirlik

* sabitlenmis shaft ucuna bilinen yuk uygulayarak force-deflection olcumu
* farkli knob komutlarinda tip deflection curve
* eksenel rotasyon aktarimi ve torsional lag
* farkli bukulme yaricaplarinda sekil karsilastirmasi
* seffaf silikon PV fantomunda temas ve gap analizi
* 3D kamera veya biplanar goruntu ile merkez cizgisi ground truth

Kalibrasyon icin least-squares veya Bayesian parameter estimation arayuzu
planla. Olculmemis parametreleri optimize edilmis gibi gostermeme.

## KULLANICI ARAYUZU

* Sol panel: anatomi importu, olcek/birim, kateter modeli, parametre profili
* Orta panel: 3D sahne
* Sag panel: insertion, rotation, steer X/Y, deployment, solver ayarlari
* Alt panel: timeline, play/pause/step/reset ve metrik grafikler

Klavye kontrolleri: `W/S` insert/retract, `A/D` rotate, ok tuslari steer X/Y,
`Space` play/pause, `R` reset. Kontroller focus olan input alanlarinda
tetiklenmemeli. Tum butonlar klavye ile erisilebilir olmali.

## GUVENLIK VE VERI

* Varsayilan demo mesh sentetik olmali.
* DICOM verisini ilk milestone'a alma.
* Hasta adi, kimlik, tarih veya DICOM tag'lerini kaydetme.
* Yuklenen meshler varsayilan olarak lokal islenmeli.
* Loglara dosya icerigi veya hasta bilgisi yazma.
* Dosya boyutu, triangle sayisi ve parse suresi icin limit koy.
* Bozuk mesh ve zip bomb benzeri girdiler guvenli bicimde reddedilmeli.

## PERFORMANS HEDEFLERI

* 150 rod dugumu ve basit demo mesh ile en az 30 FPS render
* Fizik guncellemesi hedef 20-60 Hz
* UI render thread'i fizik cozumunden ayrilmali
* 250 bin triangle mesh icin ilk BVH kurulumu 5 saniyenin altinda
* Her karede gereksiz tam mesh kopyasi yapma
* Profiling sonucu olmadan mikro-optimizasyon yapma

Hedef tutmazsa uygulama dusuk kalite modu sunmali: node azaltma, render
interpolation ve daha dusuk solver frekansi. Fizik toleranslarini sessizce
bozma.

## MILESTONE SIRASI

* **Milestone 0** - Depo ve calisan iskelet
* **Milestone 1** - Dogrulanmis steerable rod
* **Milestone 2** - Atriyum mesh ve temas
* **Milestone 3** - C++ performans cekirdegi
* **Milestone 4** - GenericPentasplinePFA
* **Milestone 5** - CathFit altyapisi

## KOD KALITESI KURALLARI

* Fonksiyonlarin fiziksel anlami ve birimleri docstring/comment ile acik olsun.
* UI, transport, geometri ve fizik katmanlarini birbirine karistirma.
* Global mutable state kullanma.
* Deterministik testlerde sabit seed kullan.
* Hata mesajlari kullaniciya neyin yanlis oldugunu ve nasil duzeltilecegini
  soylesin.
* Her config sema versiyonuna sahip olsun.
* Migration olmadan sema alanlarini sessizce degistirme.
* Kisa yoldan sadece animasyon icin centerline noktalarini elle oynatma.
* Testleri yorum satirina alma veya skip etme.
* Var olan kullanici dosyalarini silme.
* Buyuk binary dosyalari Git'e ekleme.

## TAMAMLANMA KRITERI

* Temiz ortamda README komutlariyla uygulama basliyor.
* Sentetik mesh ve generic steerable kateter ekranda gorunuyor.
* Insert, rotate ve steer kontrolleri calisiyor.
* Bukulme animasyonu fizik cozumunden geliyor.
* En az konsol kiris testi geciyor ve sayisal/analitik hata raporlaniyor.
* Solver metrikleri UI'da gorunuyor.
* Birim ve kalibrasyon durumu parametre panelinde gorunuyor.
* Research-only uyari etiketi gorunuyor.
* Lint, type-check ve test komutlari basarili.
* Bilinen limitler README'de acikca yaziyor.
