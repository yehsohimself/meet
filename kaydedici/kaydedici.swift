// kaydedici.swift - Toplantı sesini kendiliğinden kaydeden arka plan yardımcısı (macOS 15+).
//
// Nasıl çalışır: her 3 saniyede CoreAudio'dan "mikrofonu hangi uygulamalar kullanıyor" listesini alır
// (kAudioHardwarePropertyProcessObjectList). Zoom, Teams, Chrome/Safari (Meet), FaceTime, Slack gibi bir toplantı
// uygulaması mikrofonu açınca ScreenCaptureKit ile sistem sesi + mikrofonu kaydetmeye başlar; uygulama mikrofonu
// bırakıp 45 sn geçince durur, iki parçayı ffmpeg ile birleştirip m4a yapar ve siteye bildirir
// (POST http://127.0.0.1:8765/api/kayit/dosya). 60 saniyeden kısa kayıtlar atılır.
//
// Komutlar:  kaydedici --izle <ayarlar.json> <kayit_klasoru>   (sürekli; LaunchAgent olarak çalışır)
//            kaydedici --durum                                  (mikrofonu kullanan uygulamaları yazar)
//            kaydedici --kaydet <saniye> <cikti.m4a>            (elle deneme)
// İzinler: ilk çalışmada macOS "Ekran Kaydı" (sistem sesi için) ve "Mikrofon" izni sorar; bildirimler için bir kez "Bildirimler" izni.
// 2026-10-24: kayıt sürerken toplantı penceresinden ekran değiştikçe kare (sunumlar için; yalnız o pencere, `ekran_kareleri` ayarı) ve
// tıklanınca ilgili Meet sayfasını açan bildirimler (site kayitlar/.bildirim/*.json bırakır).
// 2026-10-27: menü çubuğunda kayıt göstergesi; akış koparsa yeniden bağlanır (parçalar sonda birleşir); kayıt sürerken
// kayitlar/.kayit_canli.json (parçalar) → site canlı yazıya dökmeyi toplantı sürerken yapar.

import AppKit
import AVFoundation
import CoreAudio
import Foundation
import ImageIO
import ScreenCaptureKit
import UniformTypeIdentifiers
import UserNotifications

let TOPLANTI_UYG: [String] = ["us.zoom.xos", "com.microsoft.teams", "com.google.Chrome", "com.apple.Safari", "org.mozilla.firefox",
                              "com.brave.Browser", "com.microsoft.edgemac", "company.thebrowser.Browser", "com.apple.FaceTime",
                              "com.tinyspeck.slackmacgap", "com.hnc.Discord", "net.whatsapp.WhatsApp", "com.cisco.webexmeetingsapp",
                              "com.skype.skype", "com.google.meet", "com.apple.MobileSMS"]
let FFMPEG = "/opt/homebrew/bin/ffmpeg"
let SITE = "http://127.0.0.1:8765"

func log(_ m: String) { let f = DateFormatter(); f.dateFormat = "HH:mm:ss"; print("[\(f.string(from: Date()))] \(m)"); fflush(stdout) }

// Askıda kalan sistem çağrılarına karşı (2026-10-30): 29 Ekim 20.28'de izleme döngüsünün ilk turunda bir ScreenCaptureKit çağrısı hiç geri
// dönmedi; süreç "çalışıyor" görünürken döngü 14 saat durdu ve ertesi sabahki toplantı hiç kaydedilmedi. Her çağrı süre sınırlı; ayrıca
// döngü 90 sn ilerlemezse süreç kendini kapatır (giriş ajanı hemen yeniden açar; süren kaydın parçaları açılışta kurtarılır).
final class TekSefer<T>: @unchecked Sendable {
    private let kilit = NSLock(); private var bitti = false; private let c: CheckedContinuation<T?, Never>
    init(_ c: CheckedContinuation<T?, Never>) { self.c = c }
    func ver(_ v: T?) { kilit.lock(); defer { kilit.unlock() }; if bitti { return }; bitti = true; c.resume(returning: v) }
}
func zamanAsimli<T>(_ sn: Double, _ is_: @escaping () async throws -> T) async -> T? {
    await withCheckedContinuation { (c: CheckedContinuation<T?, Never>) in
        let t = TekSefer(c)
        Task.detached { t.ver(try? await is_()) }
        DispatchQueue.global().asyncAfter(deadline: .now() + sn) { t.ver(nil) }
    }
}
struct ZamanAsimi: LocalizedError { let ne: String; var errorDescription: String? { "\(ne) yanıt vermedi" } }
func paylasilan(_ masaustuHaric: Bool, onScreenWindowsOnly: Bool) async throws -> SCShareableContent {
    guard let ic = await zamanAsimli(8, { try await SCShareableContent.excludingDesktopWindows(masaustuHaric, onScreenWindowsOnly: onScreenWindowsOnly) })
    else { log("Pencere listesi 8 sn'de gelmedi; atlandı"); throw ZamanAsimi(ne: "Pencere listesi") }
    return ic
}
let nabizKilit = NSLock(); var nabizZamani = Date()
/// İzleme döngüsü her turda çağırır; uzun işten (kaydı birleştirme) önce `ileri` ile bekçiye süre tanınır.
func nabizAt(ileri: Double = 0, klasor: URL? = nil) {
    nabizKilit.lock(); nabizZamani = Date().addingTimeInterval(ileri); nabizKilit.unlock()
    if let k = klasor { try? String(Int(Date().timeIntervalSince1970)).write(to: k.appendingPathComponent(".kaydedici_nabiz"), atomically: true, encoding: .utf8) }
}
var bekci: DispatchSourceTimer?
func bekciKur() {
    let t = DispatchSource.makeTimerSource(queue: .global()); t.schedule(deadline: .now() + 30, repeating: 15)
    t.setEventHandler {
        nabizKilit.lock(); let gecen = Date().timeIntervalSince(nabizZamani); nabizKilit.unlock()
        if gecen > 90 { log("İzleme döngüsü \(Int(gecen)) sn'dir ilerlemiyor; kaydedici yeniden açılıyor"); exit(3) }
    }
    t.resume(); bekci = t
}

// ----------------------------------------------------------------------------- mikrofonu kim kullanıyor?
func mikrofonKullananlar() -> [String] {
    var adr = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyProcessObjectList, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    var boyut: UInt32 = 0
    guard AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &adr, 0, nil, &boyut) == noErr, boyut > 0 else { return [] }
    var idler = [AudioObjectID](repeating: 0, count: Int(boyut) / MemoryLayout<AudioObjectID>.size)
    guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &adr, 0, nil, &boyut, &idler) == noErr else { return [] }
    let benimPid = Int32(ProcessInfo.processInfo.processIdentifier)
    var sonuc: [String] = []
    for oid in idler {
        var aPid = AudioObjectPropertyAddress(mSelector: kAudioProcessPropertyPID, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
        var pid: pid_t = 0; var sPid = UInt32(MemoryLayout<pid_t>.size)
        guard AudioObjectGetPropertyData(oid, &aPid, 0, nil, &sPid, &pid) == noErr, pid != benimPid else { continue }
        var aRun = AudioObjectPropertyAddress(mSelector: kAudioProcessPropertyIsRunningInput, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
        var calisiyor: UInt32 = 0; var sRun = UInt32(MemoryLayout<UInt32>.size)
        guard AudioObjectGetPropertyData(oid, &aRun, 0, nil, &sRun, &calisiyor) == noErr, calisiyor != 0 else { continue }
        var aB = AudioObjectPropertyAddress(mSelector: kAudioProcessPropertyBundleID, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
        var cf: CFString = "" as CFString; var sB = UInt32(MemoryLayout<CFString>.size)
        let st = withUnsafeMutablePointer(to: &cf) { AudioObjectGetPropertyData(oid, &aB, 0, nil, &sB, $0) }
        var ad = st == noErr ? (cf as String) : ""
        if ad.isEmpty, let app = NSRunningApplication(processIdentifier: pid) { ad = app.bundleIdentifier ?? app.localizedName ?? "pid\(pid)" }
        if ad.isEmpty { ad = "pid\(pid)" }
        sonuc.append(ad)
    }
    return sonuc
}

func toplantiUygulamasi(_ liste: [String]) -> String? {
    for b in liste {
        for t in TOPLANTI_UYG where b.lowercased().hasPrefix(t.lowercased()) { return b }
    }
    return nil
}

// ----------------------------------------------------------------------------- kayıt (ScreenCaptureKit)
final class SesYazici {
    let yazici: AVAssetWriter
    var girdi: AVAssetWriterInput?
    var basladi = false, bitti = false
    let url: URL
    init(url: URL) throws { self.url = url; try? FileManager.default.removeItem(at: url); yazici = try AVAssetWriter(outputURL: url, fileType: .m4a); yazici.movieFragmentInterval = CMTime(seconds: 10, preferredTimescale: 600) }   // yarıda kesilse de dosya okunabilsin
    func yaz(_ sb: CMSampleBuffer) {
        guard CMSampleBufferDataIsReady(sb) else { return }
        if girdi == nil {
            guard let fd = CMSampleBufferGetFormatDescription(sb), let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(fd) else { return }
            let kanal = max(1, Int(asbd.pointee.mChannelsPerFrame)); let hiz = asbd.pointee.mSampleRate > 0 ? asbd.pointee.mSampleRate : 48000
            let g = AVAssetWriterInput(mediaType: .audio, outputSettings: [AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: hiz, AVNumberOfChannelsKey: kanal, AVEncoderBitRateKey: 96000])
            g.expectsMediaDataInRealTime = true
            guard yazici.canAdd(g) else { return }
            yazici.add(g); girdi = g
            yazici.startWriting(); yazici.startSession(atSourceTime: CMSampleBufferGetPresentationTimeStamp(sb)); basladi = true
        }
        if let g = girdi, g.isReadyForMoreMediaData { g.append(sb) }
    }
    /// Tekrar çağrılabilir (2026-10-28): 27 Ekim akşamı yeniden bağlanma başarısız olunca kapanmış dosya 10 sn sonra bir daha kapatılmaya
    /// çalışıldı; AVAssetWriter "finishWriting" istisnası uygulamayı üç kez düşürdü ve kayıt dosyaya hiç çevrilmedi.
    func bitir(_ tamam: @escaping () -> Void) {
        guard basladi, !bitti, yazici.status == .writing else { tamam(); return }
        bitti = true
        girdi?.markAsFinished(); yazici.finishWriting(completionHandler: tamam)
    }
}

final class Cikti: NSObject, SCStreamOutput, SCStreamDelegate, AVCaptureAudioDataOutputSampleBufferDelegate {
    let sistem: SesYazici, mikrofon: SesYazici
    var sonSes = Date()               // son ses parçasının geldiği an (sessizlikte de parça gelir; gelmiyorsa yakalama kopmuştur)
    var durdu = false
    init(sistem: SesYazici, mikrofon: SesYazici) { self.sistem = sistem; self.mikrofon = mikrofon }
    func stream(_ stream: SCStream, didOutputSampleBuffer sb: CMSampleBuffer, of type: SCStreamOutputType) {
        sonSes = Date()
        if type == .audio { sistem.yaz(sb) } else if type == .microphone { mikrofon.yaz(sb) }
    }
    // 2026-10-27: 12.05'te "Failed to find any displays" ile akış durdu, kaydedici fark etmedi; toplantının son 26 dakikası kaydedilmedi.
    // Artık ana döngü bu bayrağı görüp yeni bir parçayla yeniden bağlanıyor; parçalar sonda zamanlarına göre birleştiriliyor.
    func stream(_ stream: SCStream, didStopWithError error: Error) { log("Akış durdu: \(error.localizedDescription)"); durdu = true }
    /// Yalnız mikrofon yedeği (ekran yokken AVCaptureSession): örnekler aynı yazıcıya
    func captureOutput(_ output: AVCaptureOutput, didOutput sb: CMSampleBuffer, from connection: AVCaptureConnection) { sonSes = Date(); mikrofon.yaz(sb) }
}

// ----------------------------------------------------------------------------- ekran kareleri (yalnız toplantı penceresi)
func toplantiBasligiMi(_ t: String) -> Bool {
    let k = t.lowercased()
    // 2026-10-27 incelemesi: "fix-auth-bug" gibi sekme adları kod kalıbına, "How to set up a Zoom meeting - YouTube" "zoom meeting"e uyuyordu
    if ["youtube", "github", "gmail", "jira", "linear", "notion", "google docs", "wikipedia"].contains(where: { k.contains($0) }) { return false }
    if k.hasPrefix("meet - ") || k.hasPrefix("meet – ") { return true }
    if k.range(of: #"^(\(\d+\) )?[a-z]{3}-[a-z]{4}-[a-z]{3}\b"#, options: .regularExpression) != nil { return true }
    let kaliplar = ["meet - ", "meet – ", "zoom meeting", "zoom toplantı", "zoom webinar", "whereby.com/", "webex meeting"]
    let teamsGorusme = ["meeting", "toplantı", "call", "arama", "görüşme", "calling", "aranıyor"]
    if kaliplar.contains(where: { k.contains($0) }) { return true }
    return k.contains("microsoft teams") && teamsGorusme.contains(where: { k.contains($0) })
}

/// Kaydedilen toplantının penceresi: tarayıcıda başlığı toplantı olan pencere (başka sekmeye geçilmişse yok), masaüstü uygulamasında en büyük pencere.
func toplantiPenceresiNesne(_ uygulama: String) async -> SCWindow? {
    guard let ic = try? await paylasilan(true, onScreenWindowsOnly: true) else { return nil }
    let u = uygulama.lowercased().components(separatedBy: ".helper").first ?? uygulama.lowercased()
    let L = ic.windows.filter { w in
        guard let b = w.owningApplication?.bundleIdentifier.lowercased(), b.hasPrefix(u) || u.hasPrefix(b) else { return false }
        return w.frame.width > 500 && w.frame.height > 300 && !(w.title ?? "").lowercased().contains("backstop")
    }
    if ["chrome", "safari", "firefox", "browser", "edge"].contains(where: { u.contains($0) }) { return L.first { toplantiBasligiMi($0.title ?? "") } }
    return L.max { $0.frame.width * $0.frame.height < $1.frame.width * $1.frame.height }
}

final class EkranKaydi {
    let klasor: URL; let uygulama: String; let baslangic: Date
    var calisiyor = true; var son: [UInt8]? = nil; var sayi = 0
    init(kok: URL, uygulama: String, baslangic: Date) {
        self.uygulama = uygulama; self.baslangic = baslangic
        klasor = kok.appendingPathComponent(".ekran").appendingPathComponent(String(Int(baslangic.timeIntervalSince1970)))
        try? FileManager.default.createDirectory(at: klasor, withIntermediateDirectories: true)
    }
    func baslat() {
        Task.detached { [weak self] in
            while let s = self, s.calisiyor {
                await s.bir()
                try? await Task.sleep(nanoseconds: 8_000_000_000)
            }
        }
    }
    static func imza(_ img: CGImage) -> [UInt8] {
        var px = [UInt8](repeating: 0, count: 32 * 18)
        px.withUnsafeMutableBytes { p in
            if let ctx = CGContext(data: p.baseAddress, width: 32, height: 18, bitsPerComponent: 8, bytesPerRow: 32, space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGImageAlphaInfo.none.rawValue) {
                ctx.interpolationQuality = .medium; ctx.draw(img, in: CGRect(x: 0, y: 0, width: 32, height: 18))
            }
        }
        return px
    }
    func bir() async {
        guard sayi < 300, let w = await toplantiPenceresiNesne(uygulama) else { return }
        let ayar = SCStreamConfiguration()
        let oran = min(1.0, 1280.0 / max(1.0, Double(w.frame.width)))
        ayar.width = Int(Double(w.frame.width) * oran); ayar.height = Int(Double(w.frame.height) * oran); ayar.showsCursor = false
        guard let img = await zamanAsimli(8, { try await SCScreenshotManager.captureImage(contentFilter: SCContentFilter(desktopIndependentWindow: w), configuration: ayar) }) else { return }
        let im = EkranKaydi.imza(img)
        if let o = son {
            var fark = 0; for i in 0..<im.count { fark += abs(Int(im[i]) - Int(o[i])) }
            if Double(fark) / Double(im.count) < 7 { return }            // ekran değişmedi
        }
        son = im
        let sn = Int(Date().timeIntervalSince(baslangic))
        let url = klasor.appendingPathComponent("\(sn).jpg")
        guard let hedef = CGImageDestinationCreateWithURL(url as CFURL, UTType.jpeg.identifier as CFString, 1, nil) else { return }
        CGImageDestinationAddImage(hedef, img, [kCGImageDestinationLossyCompressionQuality: 0.7] as CFDictionary)
        if CGImageDestinationFinalize(hedef) { sayi += 1 }
    }
}

final class Kayit {
    var ekran: EkranKaydi?
    var stream: SCStream?
    var cikti: Cikti?
    let klasor: URL
    var baslangic = Date()
    var sistemURL: URL, mikURL: URL
    var parcalar: [(sistem: URL, mik: URL, ofset: Double)] = []
    var hedef: URL? = nil              // kayıt bitince yazılacak dosya (başta belirlenir; canlı yazıya dökme bu adı kullanır)
    var sonBaglanma = Date.distantPast
    var sorun = ""
    var yedek: AVCaptureSession?      // ekran yokken yalnız mikrofon (2026-10-30)
    var yalnizMik = false
    let uygulama: String
    var pencere: String = ""          // toplantı uygulamasının pencere başlığı (Teams/Zoom masaüstü: toplantı adı)
    func pencereBasligi(_ icerik: SCShareableContent) {
        let genel: [String] = ["microsoft teams", "zoom", "zoom meeting", "zoom workplace", "meeting", "google chrome", "safari", "facetime", "", "teams"]
        let adaylar = icerik.windows.filter { w in
            guard let b = w.owningApplication?.bundleIdentifier.lowercased() else { return false }
            let u = uygulama.lowercased()
            return b == u || u.hasPrefix(b) || b.hasPrefix(u.components(separatedBy: ".helper").first ?? u)
        }.compactMap { $0.title }.map { $0.trimmingCharacters(in: .whitespaces) }
         .filter { !genel.contains($0.lowercased()) && $0.count >= 3 && !$0.lowercased().contains("backstop") }   // macOS tam ekran arka planı ("Display 3 Backstop")
        if let en = adaylar.max(by: { $0.count < $1.count }) { pencere = en }
    }
    init(klasor: URL, uygulama: String = "") { self.klasor = klasor; self.uygulama = uygulama; sistemURL = klasor.appendingPathComponent(".kayit_0_sistem.m4a"); mikURL = klasor.appendingPathComponent(".kayit_0_mikrofon.m4a") }

    func baslat() async throws {
        sistemURL = klasor.appendingPathComponent(".kayit_\(parcalar.count)_sistem.m4a"); mikURL = klasor.appendingPathComponent(".kayit_\(parcalar.count)_mikrofon.m4a")
        ekraniUyanikTut(true)
        try await akisBaslat()
        parcalar.append((sistemURL, mikURL, Date().timeIntervalSince(baslangic)))
    }

    /// Akış koptuysa ya da 15 sn'dir ses gelmiyorsa eski parçayı kapatıp yenisini açar (en çok 10 sn'de bir dener).
    func gerekirseYenidenBaglan() async {
        if yalnizMik {                                                      // ekran geri geldi mi? (30 sn'de bir bakılır)
            guard Date().timeIntervalSince(sonBaglanma) >= ekranBakAraligi else { return }
            sonBaglanma = Date()
            if let ic = try? await paylasilan(false, onScreenWindowsOnly: false), !ekranlar(ic).isEmpty { log("Ekran geri geldi; tam kayda geçiliyor"); await yenidenBaglan() }
            return
        }
        guard let c = cikti, c.durdu || Date().timeIntervalSince(c.sonSes) > 15 else { if sorun.hasPrefix("Ses") || sorun.hasPrefix("Kayıt") { sorun = "" }; return }
        sorun = c.durdu ? "Kayıt koptu; yeniden bağlanıyor" : "Ses gelmiyor; yeniden bağlanıyor"
        guard Date().timeIntervalSince(sonBaglanma) >= 10 else { return }
        sonBaglanma = Date()
        await yenidenBaglan()
    }
    private func yenidenBaglan() async {
        if let s = stream { _ = await zamanAsimli(6) { try await s.stopCapture() }; stream = nil }
        if let o = yedek { o.stopRunning(); yedek = nil }
        if let c = cikti { let g = DispatchGroup(); g.enter(); c.sistem.bitir { g.leave() }; g.enter(); c.mikrofon.bitir { g.leave() }; _ = g.wait(timeout: .now() + 30) }
        do { try await baslat(); if !yalnizMik { sorun = "" }; log("Kayıt yeniden bağlandı (parça \(parcalar.count)\(yalnizMik ? ", yalnız mikrofon" : ""))") }
        catch { log("Yeniden bağlanılamadı: \(error.localizedDescription)") }
    }

    /// Canlı yazıya dökme ve göstergeler için durum (kayitlar/.kayit_canli.json): parçalar ve kayıt başından ofsetleri.
    func durumYaz(kayit: Bool) {
        let d: [String: Any] = ["kayit": kayit, "ad": hedef?.deletingPathExtension().lastPathComponent ?? "", "hedef": hedef?.path ?? "",
                                "baslangic": baslangic.timeIntervalSince1970, "uygulama": uygulama, "pencere": pencere, "sorun": sorun,
                                "son_ses": (cikti?.sonSes ?? baslangic).timeIntervalSince1970, "guncelleme": Date().timeIntervalSince1970,
                                "parcalar": parcalar.map { ["sistem": $0.sistem.path, "mik": $0.mik.path, "ofset": $0.ofset] }]
        if let v = try? JSONSerialization.data(withJSONObject: d) {
            let u = klasor.appendingPathComponent(".kayit_canli.json"); let t = klasor.appendingPathComponent(".kayit_canli.json.tmp")
            if (try? v.write(to: t)) != nil { _ = rename(t.path, u.path) }
        }
    }

    /// Kayıt sürerken ekran uyumasın (2026-10-28): ekran uykuya geçince ScreenCaptureKit "Failed to find any displays" ile duruyor, kayıt kopuyordu.
    /// caffeinate -d -i -w <pid>: kaydedici kapanırsa (çökse bile) kendiliğinden biter.
    var uyanik: Process?
    func ekraniUyanikTut(_ ac: Bool) {
        if ac, uyanik == nil {
            let p = Process(); p.executableURL = URL(fileURLWithPath: "/usr/bin/caffeinate")
            p.arguments = ["-d", "-i", "-w", String(ProcessInfo.processInfo.processIdentifier)]
            if (try? p.run()) != nil { uyanik = p }
        } else if !ac, let p = uyanik { p.terminate(); uyanik = nil }
    }

    private func akisBaslat() async throws {
        var icerik = try await paylasilan(false, onScreenWindowsOnly: false)
        if ekranlar(icerik).isEmpty {                                        // ekran uykuda: uyandırıp bir kez daha bak
            ekranUyandir(); try? await Task.sleep(nanoseconds: 2_500_000_000)
            icerik = try await paylasilan(false, onScreenWindowsOnly: false)
            if !ekranlar(icerik).isEmpty { log("Ekran uykudaydı; uyandırıldı") }
        }
        guard let ekran = ekranlar(icerik).first else { try mikrofonYedegi(); return }
        yalnizMik = false
        pencereBasligi(icerik)
        // Yalnızca toplantı uygulamasının sesi: başka sekme/uygulamadaki video karışmaz (Chrome yardımcı süreci → ana uygulama)
        let kok = uygulama.lowercased()
        let hedefler = icerik.applications.filter { a in
            let b = a.bundleIdentifier.lowercased()
            return !kok.isEmpty && (kok.hasPrefix(b) || b.hasPrefix(kok)) && !b.isEmpty
        }
        let filtre = hedefler.isEmpty ? SCContentFilter(display: ekran, excludingWindows: []) : SCContentFilter(display: ekran, including: hedefler, exceptingWindows: [])
        if !hedefler.isEmpty { log("Ses yalnızca şu uygulamadan alınıyor: \(hedefler.map { $0.applicationName }.joined(separator: ", "))") }
        let ayar = SCStreamConfiguration()
        ayar.capturesAudio = true; ayar.excludesCurrentProcessAudio = true; ayar.sampleRate = 48000; ayar.channelCount = 2
        ayar.captureMicrophone = true
        ayar.width = 8; ayar.height = 8; ayar.minimumFrameInterval = CMTime(value: 1, timescale: 1); ayar.queueDepth = 3
        let c = Cikti(sistem: try SesYazici(url: sistemURL), mikrofon: try SesYazici(url: mikURL))
        let s = SCStream(filter: filtre, configuration: ayar, delegate: c)
        let q = DispatchQueue(label: "kaydedici.ses")
        try s.addStreamOutput(c, type: .audio, sampleHandlerQueue: q)
        try s.addStreamOutput(c, type: .microphone, sampleHandlerQueue: q)
        guard (await zamanAsimli(15) { try await s.startCapture(); return true }) == true else { throw ZamanAsimi(ne: "Kaydı başlatma") }
        stream = s; cikti = c
    }

    /// Ekran yokken (kapak kapalı, uyku, dış ekran koptu; 28 Ekim 22.42'de 16 dakika "Ekran bulunamadı" ile toplantı hiç kaydedilmedi) ScreenCaptureKit
    /// çalışmaz; toplantı büsbütün kaçmasın diye yalnız mikrofon kaydedilir (2026-10-30). Ekran dönünce gerekirseYenidenBaglan tam kayda geçer.
    private func mikrofonYedegi() throws {
        let yok = NSError(domain: "kaydedici", code: 1, userInfo: [NSLocalizedDescriptionKey: "Ekran bulunamadı"])
        guard let cihaz = AVCaptureDevice.default(for: .audio) else { throw yok }
        let o = AVCaptureSession(); let g = try AVCaptureDeviceInput(device: cihaz)
        guard o.canAddInput(g) else { throw yok }
        o.addInput(g)
        let c = Cikti(sistem: try SesYazici(url: sistemURL), mikrofon: try SesYazici(url: mikURL))
        let cikis = AVCaptureAudioDataOutput(); cikis.setSampleBufferDelegate(c, queue: DispatchQueue(label: "kaydedici.mik"))
        guard o.canAddOutput(cikis) else { throw yok }
        o.addOutput(cikis); o.startRunning()
        yedek = o; cikti = c; stream = nil; yalnizMik = true
        sorun = "Ekran bulunamadı; yalnız mikrofon kaydediliyor"
        log("Ekran bulunamadı; yalnız mikrofon kaydediliyor (ekran dönünce tam kayda geçilir)")
    }

    /// Durdurur, iki parçayı birleştirir; döner: m4a yolu (çok kısaysa nil)
    var sonMik: URL? = nil
    func durdur(hedef hedef0: URL, enAzSn: Double) async -> URL? {
        // Kayıt başında seçilen ad bu arada (telefondan yükleme vb.) alınmışsa yenisi (2026-10-27 incelemesi: -y ile üzerine yazılıyordu)
        let hedef = FileManager.default.fileExists(atPath: hedef0.path) ? dosyaAdi(klasor, baslangic) : hedef0
        ekraniUyanikTut(false)
        if let ic = try? await paylasilan(false, onScreenWindowsOnly: false) { pencereBasligi(ic) }   // toplantı adı sonradan belirmiş olabilir
        ekran?.calisiyor = false
        if let s = stream { _ = await zamanAsimli(6) { try await s.stopCapture() } }
        if let o = yedek { o.stopRunning(); yedek = nil }
        let sem = DispatchGroup()
        if let c = cikti { sem.enter(); c.sistem.bitir { sem.leave() }; sem.enter(); c.mikrofon.bitir { sem.leave() } }
        _ = sem.wait(timeout: .now() + 30)
        let sure = Date().timeIntervalSince(baslangic)
        let fm = FileManager.default
        if parcalar.isEmpty { parcalar = [(sistemURL, mikURL, 0)] }
        // Ham parçalar yalnız kayıt başarıyla yazılınca (ya da kısa kayıt bilerek atılınca) silinir; kodlama başarısızsa (disk dolu, bozuk parça)
        // .kayit_kurtar/<zaman>/ altında saklanır (2026-10-27 incelemesi: her durumda siliniyordu, toplantının sesi kaybolabilirdi)
        var sakla = true
        defer {
            if sakla {
                let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd HH.mm.ss"
                let kurtar = klasor.appendingPathComponent(".kayit_kurtar").appendingPathComponent(f.string(from: baslangic))
                try? fm.createDirectory(at: kurtar, withIntermediateDirectories: true)
                for p in parcalar { for u in [p.sistem, p.mik] where fm.fileExists(atPath: u.path) { try? fm.moveItem(at: u, to: kurtar.appendingPathComponent(u.lastPathComponent)) } }
                log("Kayıt dosyası yazılamadı; ham ses saklandı: \(kurtar.path)")
            } else {
                for p in parcalar { try? fm.removeItem(at: p.sistem); try? fm.removeItem(at: p.mik) }
            }
        }
        // Birden çok parça (akış koptu, yeniden bağlandı): her kanal kendi parçalarından, kayıt başına göre zamanlanarak tek dosyaya
        if parcalar.count > 1 {
            let bir = { (urls: [(URL, Double)], cikis: URL) -> Bool in
                let var_ = urls.filter { ((try? self.sisVarBoyut($0.0)) ?? 0) > 2000 }
                guard !var_.isEmpty else { return false }
                var a = ["-y", "-v", "error"]; var f = ""
                for (i, u) in var_.enumerated() { a += ["-i", u.0.path]; f += "[\(i):a]adelay=\(Int(u.1 * 1000)):all=1[p\(i)];" }
                f += var_.indices.map { "[p\($0)]" }.joined() + "amix=inputs=\(var_.count):duration=longest:normalize=0[o]"
                a += ["-filter_complex", f, "-map", "[o]", "-c:a", "aac", "-b:a", "128k", cikis.path]
                let p = Process(); p.executableURL = URL(fileURLWithPath: FFMPEG); p.arguments = a
                guard (try? p.run()) != nil else { return false }; p.waitUntilExit(); return p.terminationStatus == 0
            }
            let s1 = klasor.appendingPathComponent(".kayit_birlesik_sistem.m4a"), m1 = klasor.appendingPathComponent(".kayit_birlesik_mikrofon.m4a")
            let sOk = bir(parcalar.map { ($0.sistem, $0.ofset) }, s1), mOk = bir(parcalar.map { ($0.mik, $0.ofset) }, m1)
            log("Kayıt \(parcalar.count) parçadan birleştirildi")
            parcalar.append((s1, m1, 0))                                      // defer bunları da siler
            if !sOk { try? fm.removeItem(at: s1) }; if !mOk { try? fm.removeItem(at: m1) }
            sistemURL = s1; mikURL = m1
        }
        let sisVar = (try? sisVarBoyut(sistemURL)) ?? 0 > 2000, mikVar = (try? sisVarBoyut(mikURL)) ?? 0 > 2000
        if sure < enAzSn || (!sisVar && !mikVar) { sakla = false; log("Kayıt kısa ya da boş (\(Int(sure)) sn), atıldı"); return nil }
        // Mikrofon kanalı ayrıca saklanır: site bu kanaldan "ben kimim" (kullanıcının kendi sesi) bulur
        sonMik = nil
        if sisVar && mikVar {
            let mikHedef = hedef.deletingPathExtension().appendingPathExtension("mik.m4a")
            let pm = Process(); pm.executableURL = URL(fileURLWithPath: FFMPEG)
            pm.arguments = ["-y", "-v", "error", "-i", mikURL.path, "-c:a", "aac", "-b:a", "64k", mikHedef.path]
            if (try? pm.run()) != nil { pm.waitUntilExit(); if pm.terminationStatus == 0 { sonMik = mikHedef } }
        }
        let p = Process(); p.executableURL = URL(fileURLWithPath: FFMPEG)
        var args = ["-y", "-v", "error"]
        if sisVar && mikVar {
            args += ["-i", sistemURL.path, "-i", mikURL.path, "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95", "-c:a", "aac", "-b:a", "128k", hedef.path]
        } else {
            args += ["-i", (sisVar ? sistemURL : mikURL).path, "-c:a", "aac", "-b:a", "128k", hedef.path]
        }
        p.arguments = args
        do { try p.run(); p.waitUntilExit() } catch { log("ffmpeg çalışmadı: \(error)"); return nil }
        let tamam = p.terminationStatus == 0 && ((try? sisVarBoyut(hedef)) ?? 0) > 2000
        if tamam { sakla = false }
        return tamam ? hedef : nil
    }
    func sisVarBoyut(_ u: URL) throws -> Int { (try FileManager.default.attributesOfItem(atPath: u.path)[.size] as? Int) ?? 0 }
}

// ----------------------------------------------------------------------------- siteye bildir
/// Uyuyan ekranı uyandırır (kullanıcı etkinliği bildirir; caffeinate -u). Ekran uykudayken ScreenCaptureKit ekran bulamıyor.
/// Kayıt başlatılamayınca nedeni siteye (kayitlar/.kayit_hata.json): site size "kayıt başlatılamadı" bildirimi gönderir (2026-10-30).
/// Deneme için ekran yokmuş gibi davranma (--kaydet ... --ekransiz N): mikrofon yedeği ve ekran dönünce tam kayda geçiş gerçek sesle sınanır.
var sahteEkransiz: Date? = nil
var ekranBakAraligi = 30.0
func ekranlar(_ ic: SCShareableContent) -> [SCDisplay] { if let t = sahteEkransiz, Date() < t { return [] }; return ic.displays }

/// İzinler (kayitlar/.kaydedici_izin.json): Ekran Kaydı ve Mikrofon izni düşmüşse site bunu toplantı başlamadan görür ve söyler (2026-10-30).
func izinDurumu() -> [String: Any] {
    let mik: String
    switch AVCaptureDevice.authorizationStatus(for: .audio) { case .authorized: mik = "var"; case .notDetermined: mik = "sorulmadi"; default: mik = "yok" }
    return ["ekran": CGPreflightScreenCaptureAccess(), "mikrofon": mik, "zaman": Date().timeIntervalSince1970]
}
func izinYaz(_ k: URL) {
    let d = izinDurumu()
    if let v = try? JSONSerialization.data(withJSONObject: d) { try? v.write(to: k.appendingPathComponent(".kaydedici_izin.json")) }
}

func kayitHatasiYaz(_ k: URL, _ hata: String?) {
    let u = k.appendingPathComponent(".kayit_hata.json")
    guard let h = hata else { try? FileManager.default.removeItem(at: u); return }
    if let v = try? JSONSerialization.data(withJSONObject: ["zaman": Date().timeIntervalSince1970, "hata": h]) { try? v.write(to: u) }
}

func ekranUyandir() {
    let p = Process(); p.executableURL = URL(fileURLWithPath: "/usr/bin/caffeinate"); p.arguments = ["-u", "-t", "3"]
    try? p.run()
}

func siteyeBildir(dosya: URL, uygulama: String, baslangic: Date, mik: URL? = nil, pencere: String = "", hemen: Bool = false) {
    var req = URLRequest(url: URL(string: SITE + "/api/kayit/dosya")!)
    req.httpMethod = "POST"; req.setValue("application/json", forHTTPHeaderField: "Content-Type")
    var govde: [String: Any] = ["dosya": dosya.path, "uygulama": uygulama, "baslangic": baslangic.timeIntervalSince1970]
    if let m = mik { govde["mik_dosya"] = m.path }
    if !pencere.isEmpty { govde["pencere"] = pencere }
    req.httpBody = try? JSONSerialization.data(withJSONObject: govde)
    // Site o an kapalıysa (yeniden başlıyorsa) kayıt sahipsiz kalıyordu (2026-10-27 incelemesi): arka planda 6 kez artan arayla dener;
    // hepsi başarısızsa site açılışta kayitlar/ içindeki işlenmemiş toplantı kayıtlarını kendisi bulur.
    let calis = {
        for deneme in 0..<(hemen ? 1 : 6) {
            let sem = DispatchSemaphore(value: 0); var tamam = false
            URLSession.shared.dataTask(with: req) { d, r, e in
                let kod = (r as? HTTPURLResponse)?.statusCode ?? 0
                if let e = e { log("Siteye bildirilemedi (\(deneme + 1). deneme): \(e.localizedDescription)") } else { log("Siteye bildirildi: \(kod)"); tamam = kod < 500 }
                sem.signal()
            }.resume()
            _ = sem.wait(timeout: .now() + 30)
            if tamam || hemen { return }
            Thread.sleep(forTimeInterval: Double(10 * (deneme + 1)))
        }
    }
    if hemen { calis() } else { DispatchQueue.global().async(execute: calis) }   // kapanırken (SIGTERM) beklenir, yoksa arka planda
}

func ayarOku(_ yol: String) -> [String: Any] {
    guard let d = FileManager.default.contents(atPath: yol), let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return [:] }
    return j
}

func dosyaAdi(_ klasor: URL, _ tarih: Date) -> URL {
    let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd HH.mm"
    var u = klasor.appendingPathComponent("Toplantı \(f.string(from: tarih)).m4a"); var n = 2
    while FileManager.default.fileExists(atPath: u.path) { u = klasor.appendingPathComponent("Toplantı \(f.string(from: tarih)) (\(n)).m4a"); n += 1 }
    return u
}

/// Tarayıcı kaydı için toplantı sinyali (biri yeter): 1) Chrome uzantısı "aramadayım" (.uzanti_arama, 30 sn), 2) site takvimde şu an süren
/// çevrimiçi görüşme görüyor (.takvim_arama, 90 sn), 3) ekranda Meet/Teams/Zoom penceresi (Chrome'da pencere başlığı = öndeki sekme).
/// 16-20 Ekim 2026'da uzantı bozuktu ve kapı yalnız ona bağlı olduğu için toplantılar kaydedilmedi. Döner: neden ya da nil.
func tarayiciKapisi(_ uygulama: String, _ klasor: URL) async -> String? {
    func taze(_ ad: String, _ sn: Double) -> Bool {
        guard let at = try? FileManager.default.attributesOfItem(atPath: klasor.appendingPathComponent(ad).path), let m = at[.modificationDate] as? Date else { return false }
        return Date().timeIntervalSince(m) < sn
    }
    if taze(".uzanti_arama", 30) { return "Chrome uzantısı: toplantıda" }
    if taze(".takvim_arama", 90) { return "Takvimde süren bir görüşme var" }
    if let p = await toplantiPenceresi(uygulama) { return "Ekranda toplantı penceresi: \(p)" }
    return nil
}

/// Tarayıcının ekrandaki pencere başlıkları (öndeki sekmeler); mikrofonu tutan sekmeyi bulmaya yardım için.
func tarayiciPencereleri(_ uygulama: String) async -> [String] {
    guard let ic = try? await paylasilan(true, onScreenWindowsOnly: false) else { return [] }
    let u = uygulama.lowercased().components(separatedBy: ".helper").first ?? uygulama.lowercased()
    return Array(Set(ic.windows.filter { w in
        guard let b = w.owningApplication?.bundleIdentifier.lowercased(), b.hasPrefix(u) || u.hasPrefix(b), w.frame.width > 300 else { return false }
        return !(w.title ?? "").isEmpty
    }.compactMap { $0.title })).sorted().prefix(6).map { $0 }
}

/// Mikrofon kapalıyken görüşme (2026-10-27: internet kopup Meet'e sessizde geri dönülünce Chrome mikrofonu açmadı, kayıt hiç başlamadı):
/// ekranda toplantı başlıklı tarayıcı penceresi. Döner: (uygulama kimliği, başlık, sekmeden ses geliyor mu (Chrome başlıkta 🔊)) ya da nil.
let TARAYICILAR = ["com.google.chrome", "com.brave.browser", "com.microsoft.edgemac", "company.thebrowser.browser"]
func sesliToplantiPenceresi(_ haric: [String] = []) async -> (String, String, Bool)? {
    guard let ic = try? await paylasilan(true, onScreenWindowsOnly: true) else { return nil }
    var bulunan: (String, String, Bool)? = nil
    for w in ic.windows {
        guard let b = w.owningApplication?.bundleIdentifier, TARAYICILAR.contains(where: { b.lowercased().hasPrefix($0) }), let t = w.title, w.frame.width > 300,
              toplantiBasligiMi(t), !kayitDisiMi(t, haric) else { continue }
        let ses = t.contains("🔊")
        if ses { return (b + ".helper", t, true) }
        if bulunan == nil { bulunan = (b + ".helper", t, false) }
    }
    return bulunan
}

var sonKapi = ""
func kapiYaz(_ m: String) { if m != sonKapi { log(m); sonKapi = m } }

/// Tarayıcının ekrandaki pencerelerinden biri toplantı sayfası mı (Meet/Teams/Zoom/Whereby/Webex başlığı). Döner: başlık ya da nil.
func toplantiPenceresi(_ uygulama: String) async -> String? {
    guard let ic = try? await paylasilan(true, onScreenWindowsOnly: true) else { return nil }
    let u = uygulama.lowercased().components(separatedBy: ".helper").first ?? uygulama.lowercased()
    // Yalnızca GÖRÜŞME sayfası başlıkları. 20 Ekim: "(1) IK 18 | Microsoft Teams" (Teams SOHBET sayfası) eşleşti, arka planda futbol yayını
    // toplantı diye kaydedildi. Teams'te ancak toplantı/arama sözcüğü varsa; Meet'te toplantı kodu (abc-defg-hij) ya da "Meet - ".
    for w in ic.windows {
        guard let b = w.owningApplication?.bundleIdentifier.lowercased(), b.hasPrefix(u) || u.hasPrefix(b), let t = w.title, w.frame.width > 300 else { continue }
        if toplantiBasligiMi(t) { return t }
    }
    return nil
}

// ----------------------------------------------------------------------------- kaydedilmeyen toplantılar (2026-10-29)
// Kullanıcı: "Kurs meetlerini kaydetmeye gerek yok. Her hafta tekrar ediyor." Liste ayarlar.json `kayit_disi` ([{ad, desenler}]; site öğrenir,
// Ayarlar → Kayıt'tan düzenlenir). Adı listeye uyan görüşmede kayda başlanmaz; sürerken uyarsa kayıt kapanır (site de dosyayı yazıya dökmez).
func kayitDisiDesenler(_ ay: [String: Any]) -> [String] {
    var d: [String] = []
    for x in (ay["kayit_disi"] as? [Any]) ?? [] {
        if let s = x as? String { d.append(s) }
        else if let m = x as? [String: Any] { d += ((m["desenler"] as? [String]) ?? [m["ad"] as? String].compactMap { $0 }) }
    }
    return d.map { $0.trimmingCharacters(in: .whitespaces) }.filter { $0.count >= 3 }
}

func kayitDisiMi(_ baslik: String, _ desenler: [String]) -> Bool {
    let b = baslik.lowercased().replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
    for d in desenler {
        let k = NSRegularExpression.escapedPattern(for: d.lowercased()).replacingOccurrences(of: #"\\? +"#, with: #"\\s+"#, options: .regularExpression)
        if b.range(of: "(?<![\\p{L}\\p{N}_])" + k + "(?![\\p{L}\\p{N}_])", options: .regularExpression) != nil { return true }
    }
    return false
}

/// Mikrofonu kullanan uygulamanın görüşmesi kaydedilmeyenlerden mi: Chrome uzantısı bu görüşmeyi bildirdiyse (.kayit_disi_arama, 30 sn) ya da
/// ekrandaki toplantı pencerelerinin hepsi listeye uyuyorsa. Döner: neden ya da nil.
func kayitDisiToplanti(_ uygulama: String, _ klasor: URL, _ desenler: [String]) async -> String? {
    func yas(_ ad: String) -> Double {
        guard let at = try? FileManager.default.attributesOfItem(atPath: klasor.appendingPathComponent(ad).path), let m = at[.modificationDate] as? Date else { return 1e9 }
        return Date().timeIntervalSince(m)
    }
    let kd = yas(".kayit_disi_arama")
    if kd < 30 && kd <= yas(".uzanti_arama") { return "Chrome uzantısı bildirdi" }
    guard let ic = try? await paylasilan(true, onScreenWindowsOnly: true) else { return nil }
    let u = uygulama.lowercased().components(separatedBy: ".helper").first ?? uygulama.lowercased()
    let tarayici = ["chrome", "safari", "firefox", "browser", "edge"].contains(where: { u.contains($0) })
    let basliklar = ic.windows.compactMap { w -> String? in
        guard let b = w.owningApplication?.bundleIdentifier.lowercased(), b.hasPrefix(u) || u.hasPrefix(b), let t = w.title, !t.isEmpty, w.frame.width > 300 else { return nil }
        return (!tarayici || toplantiBasligiMi(t)) ? t : nil
    }
    let uyan = basliklar.filter { kayitDisiMi($0, desenler) }
    if !uyan.isEmpty && (!tarayici || uyan.count == basliklar.count) { return uyan[0] }
    return nil
}

// ----------------------------------------------------------------------------- üst çubuk göstergesi (2026-10-27)
// Kullanıcı: "toplantı kayda alınıyor mu göremiyorum, bu beni strese sokuyor". Kayıt sürerken menü çubuğunda kırmızı "● 12:34";
// ses kopunca turuncu uyarı; menüde durum, son canlı öneri ve Meet'i aç. Kayıt yokken görünmez.
final class Gosterge: NSObject {
    static let shared = Gosterge()
    var item: NSStatusItem?
    let menu = NSMenu()
    let durumOge = NSMenuItem(title: "", action: nil, keyEquivalent: "")
    let kartOge = NSMenuItem(title: "", action: nil, keyEquivalent: "")
    func kur() {
        DispatchQueue.main.async {
            let it = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
            it.isVisible = false
            self.durumOge.isEnabled = false; self.kartOge.isEnabled = false; self.kartOge.isHidden = true
            self.menu.addItem(self.durumOge); self.menu.addItem(self.kartOge); self.menu.addItem(.separator())
            let ac = NSMenuItem(title: "Meet'i aç", action: #selector(Gosterge.meetAc), keyEquivalent: ""); ac.target = self; self.menu.addItem(ac)
            it.menu = self.menu; self.item = it
        }
    }
    @objc func meetAc() { if let u = URL(string: "http://127.0.0.1:8766/") { NSWorkspace.shared.open(u) } }
    /// Son canlı öneri (kayitlar/.canli/<ad>.asistan.json): (metin, zaman)
    func sonKart(_ kok: URL, _ ad: String) -> (String, Double)? {
        let u = kok.appendingPathComponent(".canli").appendingPathComponent(ad + ".asistan.json")
        guard let d = try? Data(contentsOf: u), let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
              let L = j["kartlar"] as? [[String: Any]], let k = L.last else { return nil }
        let tur = k["tur"] as? String ?? ""
        let m = tur == "mentor" ? (k["yap"] as? String ?? k["gozlem"] as? String ?? "") : tur == "oneri" ? (k["soyle"] as? String ?? "") : (k["metin"] as? String ?? "")
        return m.isEmpty ? nil : (m, k["zaman"] as? Double ?? 0)
    }
    func guncelle(_ kayit: Kayit?, kok: URL, yuzen: Bool = true) {
        var baslik: NSAttributedString? = nil; var durum = ""; var kart: String? = nil
        if let k = kayit, yuzen {
            let sn = Int(Date().timeIntervalSince(k.baslangic))
            let sure = sn >= 3600 ? String(format: "%d:%02d:%02d", sn / 3600, (sn / 60) % 60, sn % 60) : String(format: "%d:%02d", sn / 60, sn % 60)
            YuzenGosterge.shared.goster(k.sorun.isEmpty ? "\(sure)  Kaydediliyor" : "\(sure)  \(k.sorun)", sorun: !k.sorun.isEmpty)
        } else { YuzenGosterge.shared.gizle() }
        if let k = kayit {
            let sn = Int(Date().timeIntervalSince(k.baslangic))
            let sure = sn >= 3600 ? String(format: "%d:%02d:%02d", sn / 3600, (sn / 60) % 60, sn % 60) : String(format: "%d:%02d", sn / 60, sn % 60)
            let uyg = NSWorkspace.shared.runningApplications.first { ($0.bundleIdentifier ?? "").lowercased().hasPrefix(k.uygulama.lowercased().components(separatedBy: ".helper").first ?? "") }?.localizedName ?? k.uygulama
            let font = NSFont.monospacedDigitSystemFont(ofSize: 13, weight: .semibold)
            let t = NSMutableAttributedString()
            if k.sorun.isEmpty {
                t.append(NSAttributedString(string: "● ", attributes: [.foregroundColor: NSColor.systemRed, .font: font]))
                t.append(NSAttributedString(string: sure, attributes: [.font: font]))
                durum = "Kaydediliyor · \(sure) · \(uyg)"
            } else {
                t.append(NSAttributedString(string: "⚠︎ ", attributes: [.foregroundColor: NSColor.systemOrange, .font: font]))
                t.append(NSAttributedString(string: sure, attributes: [.font: font]))
                durum = k.sorun
            }
            if let ad = k.hedef?.deletingPathExtension().lastPathComponent, let (m, z) = sonKart(kok, ad) {
                kart = "Son öneri: " + (m.count > 90 ? String(m.prefix(88)) + "…" : m)
                if Date().timeIntervalSince1970 - z < 120 { t.append(NSAttributedString(string: "  💡", attributes: [.font: font])) }
            }
            baslik = t
        }
        DispatchQueue.main.async {
            guard let it = self.item else { return }
            if let b = baslik { it.button?.attributedTitle = b; it.isVisible = true } else { it.isVisible = false }
            self.durumOge.title = durum
            self.kartOge.title = kart ?? ""; self.kartOge.isHidden = kart == nil
        }
    }
}

// ----------------------------------------------------------------------------- yüzen kayıt göstergesi (2026-10-30)
// Menü çubuğu öğesi çentikli Mac'te sağ taraf doluyken macOS tarafından gizleniyor (öğe oluşuyor, "görünür" sayılmıyor; bu Mac'te öyle).
// "Toplantı kaydediliyor mu?" sorusu hiç akla gelmesin diye kayıt sürerken ekranın sağ üstünde, her uygulamanın ve tam ekranın üstünde
// küçük bir hap durur: kırmızı nokta + süre (+ sorun varsa turuncu uyarı). Sürüklenebilir; tıklayınca Meet açılır. Ayar `kayit_gostergesi` (varsayılan açık).
final class YuzenGosterge: NSObject {
    static let shared = YuzenGosterge()
    var panel: NSPanel?
    let etiket = NSTextField(labelWithString: "")
    let nokta = NSView()
    var sorunda = false
    private func kur() {
        let p = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 120, height: 30), styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        p.level = .statusBar; p.isOpaque = false; p.backgroundColor = .clear; p.hasShadow = true; p.hidesOnDeactivate = false
        p.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        p.isMovableByWindowBackground = true; p.ignoresMouseEvents = false
        let v = TiklanirGorunum(); v.wantsLayer = true
        v.layer?.backgroundColor = NSColor(calibratedWhite: 0.07, alpha: 0.86).cgColor; v.layer?.cornerRadius = 15; v.layer?.borderWidth = 1
        v.layer?.borderColor = NSColor(calibratedWhite: 1, alpha: 0.12).cgColor
        nokta.wantsLayer = true; nokta.layer?.cornerRadius = 4; nokta.layer?.backgroundColor = NSColor.systemRed.cgColor
        nokta.frame = NSRect(x: 12, y: 11, width: 8, height: 8)
        etiket.font = NSFont.monospacedDigitSystemFont(ofSize: 12.5, weight: .semibold); etiket.textColor = .white
        etiket.frame = NSRect(x: 27, y: 6, width: 300, height: 18); etiket.lineBreakMode = .byClipping
        v.addSubview(nokta); v.addSubview(etiket); p.contentView = v
        let a = CABasicAnimation(keyPath: "opacity"); a.fromValue = 1; a.toValue = 0.25; a.duration = 0.9; a.autoreverses = true; a.repeatCount = .infinity
        nokta.layer?.add(a, forKey: "nabiz")
        panel = p
    }
    func goster(_ metin: String, sorun: Bool) {
        DispatchQueue.main.async {
            if self.panel == nil { self.kur() }
            guard let p = self.panel else { return }
            self.etiket.stringValue = metin
            if sorun != self.sorunda { self.sorunda = sorun; self.nokta.layer?.backgroundColor = (sorun ? NSColor.systemOrange : NSColor.systemRed).cgColor }
            let gen = min(360, max(100, self.etiket.attributedStringValue.size().width + 40))
            let onceki = p.frame
            if !p.isVisible, let e = NSScreen.main {                                // ilk gösterim: sağ üst, menü çubuğunun hemen altı
                p.setFrame(NSRect(x: e.visibleFrame.maxX - gen - 14, y: e.visibleFrame.maxY - 30 - 10, width: gen, height: 30), display: true)
                p.orderFrontRegardless()
            } else if abs(onceki.width - gen) > 2 {
                p.setFrame(NSRect(x: onceki.maxX - gen, y: onceki.minY, width: gen, height: 30), display: true)
            }
            self.etiket.frame.size.width = gen - 36
        }
    }
    func gizle() { DispatchQueue.main.async { self.panel?.orderOut(nil) } }
}
final class TiklanirGorunum: NSView {
    override func mouseUp(with event: NSEvent) {
        if event.clickCount == 1, let u = URL(string: "http://127.0.0.1:8766/") { NSWorkspace.shared.open(u) }
    }
}

// ----------------------------------------------------------------------------- tıklanınca sayfa açan bildirimler
final class Bildirici: NSObject, UNUserNotificationCenterDelegate {
    static let shared = Bildirici()
    var izin = false
    func kur() {
        let m = UNUserNotificationCenter.current(); m.delegate = self
        m.requestAuthorization(options: [.alert, .sound]) { ok, _ in self.izin = ok; log(ok ? "Bildirim izni var" : "Bildirim izni yok; site eski bildirim yolunu kullanır") }
    }
    func userNotificationCenter(_ c: UNUserNotificationCenter, willPresent n: UNNotification, withCompletionHandler h: @escaping (UNNotificationPresentationOptions) -> Void) { h([.banner, .list, .sound]) }
    func userNotificationCenter(_ c: UNUserNotificationCenter, didReceive r: UNNotificationResponse, withCompletionHandler h: @escaping () -> Void) {
        if let s = r.notification.request.content.userInfo["url"] as? String, let u = URL(string: s), !s.isEmpty { NSWorkspace.shared.open(u) }
        h()
    }
    /// Sitenin bıraktığı bildirimleri gösterir; `.destek` dosyasını tazeler (site buna bakarak bu yolu seçer).
    var sonBakis = Date()
    func tara(_ kok: URL) {
        let kl = kok.appendingPathComponent(".bildirim"); let fm = FileManager.default
        if !izin && Date().timeIntervalSince(sonBakis) > 300 {           // izin Sistem Ayarları'ndan sonradan açılırsa yeniden başlatmadan fark et
            sonBakis = Date()
            UNUserNotificationCenter.current().getNotificationSettings { a in if a.authorizationStatus == .authorized { self.izin = true; log("Bildirim izni verildi") } }
        }
        try? fm.createDirectory(at: kl, withIntermediateDirectories: true)
        guard izin else { try? fm.removeItem(at: kl.appendingPathComponent(".destek")); return }
        fm.createFile(atPath: kl.appendingPathComponent(".destek").path, contents: Data("1".utf8))
        guard let L = try? fm.contentsOfDirectory(at: kl, includingPropertiesForKeys: nil) else { return }
        for f in L where f.pathExtension == "json" {
            defer { try? fm.removeItem(at: f) }
            guard let d = try? Data(contentsOf: f), let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { continue }
            let c = UNMutableNotificationContent()
            c.title = (j["baslik"] as? String) ?? "Meet"; c.body = (j["metin"] as? String) ?? ""; c.userInfo = ["url": (j["url"] as? String) ?? ""]; c.sound = .default
            UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: f.lastPathComponent, content: c, trigger: nil))
        }
    }
}

// ----------------------------------------------------------------------------- ana döngü
let args = CommandLine.arguments
if args.count >= 2 && args[1] == "--durum" {
    let l = mikrofonKullananlar()
    print(l.isEmpty ? "Mikrofonu kullanan uygulama yok." : "Mikrofonu kullananlar: " + l.joined(separator: ", "))
    if let t = toplantiUygulamasi(l) { print("Toplantı uygulaması: \(t)") }
    let bitti = DispatchSemaphore(value: 0)
    Task.detached {
        if let ic = try? await paylasilan(true, onScreenWindowsOnly: true) {
            let tarayici = ic.windows.filter { ($0.owningApplication?.bundleIdentifier ?? "").lowercased().contains("chrome") && ($0.frame.width > 300) }
            print("Ekrandaki Chrome pencereleri: \(tarayici.count), başlığı okunan: \(tarayici.filter { ($0.title ?? "").count > 0 }.count)")
        } else { print("Pencere listesi alınamadı (Ekran Kaydı izni?)") }
        print("Toplantı penceresi: \(await toplantiPenceresi("com.google.Chrome") ?? "yok")")
        bitti.signal()
    }
    bitti.wait()
    exit(0)
}
if args.count >= 4 && args[1] == "--kaydet" {
    let sn = Double(args[2]) ?? 5; let hedef = URL(fileURLWithPath: args[3])
    let k = Kayit(klasor: hedef.deletingLastPathComponent())
    Task {
        k.hedef = hedef
        do {
            if let i = args.firstIndex(of: "--ekransiz"), i + 1 < args.count, let e = Double(args[i + 1]) { sahteEkransiz = Date().addingTimeInterval(e); ekranBakAraligi = 3 }
            Gosterge.shared.kur()
            try await k.baslat(); log("Kayıt başladı (\(Int(sn)) sn)"); Gosterge.shared.guncelle(k, kok: k.klasor)
            if sahteEkransiz != nil {                                      // deneme: ilk N sn ekran yokmuş gibi; sonra tam kayda geçiş (menü çubuğu göstergesi de görünür)
                let bas = Date()
                while Date().timeIntervalSince(bas) < sn { try await Task.sleep(nanoseconds: 1_000_000_000); await k.gerekirseYenidenBaglan(); k.durumYaz(kayit: true); Gosterge.shared.guncelle(k, kok: k.klasor) }
            } else if args.contains("--kopuk") {                              // deneme: yarıda akış kopmuş gibi yeniden bağlan
                try await Task.sleep(nanoseconds: UInt64(sn * 500_000_000)); k.cikti?.durdu = true
                await k.gerekirseYenidenBaglan(); k.durumYaz(kayit: true)
                try await Task.sleep(nanoseconds: UInt64(sn * 500_000_000))
            } else { try await Task.sleep(nanoseconds: UInt64(sn * 1_000_000_000)) }
        }
        catch { log("Kayıt başlatılamadı: \(error.localizedDescription)"); exit(2) }
        let u = await k.durdur(hedef: hedef, enAzSn: 0)
        log(u == nil ? "Kayıt oluşmadı" : "Bitti: \(u!.path)"); exit(u == nil ? 3 : 0)
    }
    let uyg = NSApplication.shared; uyg.setActivationPolicy(.accessory); uyg.run()
}
if args.count >= 4 && args[1] == "--izle" {
    let ayarYolu = args[2]; let kayitKlasoru = URL(fileURLWithPath: args[3], isDirectory: true)
    try? FileManager.default.createDirectory(at: kayitKlasoru, withIntermediateDirectories: true)
    log("İzleme başladı. Toplantı uygulaması mikrofonu açınca kayıt başlar.")
    let izin = izinDurumu(); izinYaz(kayitKlasoru)
    log("İzinler: ekran kaydı \((izin["ekran"] as? Bool) == true ? "var" : "YOK"), mikrofon \(izin["mikrofon"] as? String ?? "?")")
    var sonIzinYazma = Date()
    // Yarım kalmış kayıt (2026-10-28): kaydedici kayıt sürerken kapandıysa (çökme, yeniden başlatma) ham parçalar .kayit_N_*.m4a olarak kalır ve
    // sonraki kayıt aynı adlara YAZIP siliyordu (27 Ekim akşamı 37 dakikalık bir kayıt böyle kayboldu). Açılışta önce onlar dosyaya çevrilip siteye verilir.
    if let veri = try? Data(contentsOf: kayitKlasoru.appendingPathComponent(".kayit_canli.json")),
       let d = try? JSONSerialization.jsonObject(with: veri) as? [String: Any], (d["kayit"] as? Bool) == true,
       let P = d["parcalar"] as? [[String: Any]], !P.isEmpty {
        let parcalar = P.compactMap { x -> (sistem: URL, mik: URL, ofset: Double)? in
            guard let si = x["sistem"] as? String, let mi = x["mik"] as? String else { return nil }
            let fm = FileManager.default
            guard fm.fileExists(atPath: si) || fm.fileExists(atPath: mi) else { return nil }
            return (URL(fileURLWithPath: si), URL(fileURLWithPath: mi), (x["ofset"] as? Double) ?? 0)
        }
        if !parcalar.isEmpty {
            let k = Kayit(klasor: kayitKlasoru, uygulama: (d["uygulama"] as? String) ?? "")
            if let b = d["baslangic"] as? Double { k.baslangic = Date(timeIntervalSince1970: b) }
            k.parcalar = parcalar; k.pencere = (d["pencere"] as? String) ?? ""
            let hedef = (d["hedef"] as? String).map { URL(fileURLWithPath: $0) } ?? dosyaAdi(kayitKlasoru, k.baslangic)
            log("Yarım kalmış kayıt bulundu (\(parcalar.count) parça); dosyaya çevriliyor")
            nabizAt(ileri: 1800); let u = await k.durdur(hedef: hedef, enAzSn: 60)
            k.durumYaz(kayit: false)
            if let u = u { log("Yarım kalmış kayıt kurtarıldı: \(u.lastPathComponent)"); siteyeBildir(dosya: u, uygulama: k.uygulama, baslangic: k.baslangic, mik: k.sonMik, pencere: k.pencere) }
        }
    }
    Bildirici.shared.kur()
    Gosterge.shared.kur()
    nabizAt(klasor: kayitKlasoru); bekciKur()
    var aktif: Kayit? = nil; var aktifUyg = ""; var sonGorulme = Date(); var ilkGorulme: Date? = nil; var aramaUyarildi = false; var sonKapiZamani = Date(); var kayitDisiUyarildi = ""
    var bosMikBas: Date? = nil; var bosMikSimdi = false; var sonMikYazma = Date.distantPast
    var sonPencereBakis = Date.distantPast; var sonSesliToplanti = Date.distantPast; var sesliUyarildi = ""
    let PENCERE_SURE = 300.0          // kayıt sürerken ses/mikrofon gitse de toplantı penceresi açıksa bu kadar beklenir (bağlantı kopup gelebilir)
    let KAPI_SURE = 600.0
    let BEKLE_BASLA = 6.0, BEKLE_DUR = 45.0, EN_AZ = 60.0, EN_COK = 4 * 3600.0
    // Kapatılırken (yeniden başlatma, oturum kapatma) süren kaydı düzgün bitir ve siteye ver
    let sinyal = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
    signal(SIGTERM, SIG_IGN)
    sinyal.setEventHandler {
        guard let a = aktif else { exit(0) }
        log("Kapatılıyor; süren kayıt bitiriliyor")
        Task { let u = await a.durdur(hedef: a.hedef ?? dosyaAdi(kayitKlasoru, a.baslangic), enAzSn: EN_AZ); a.durumYaz(kayit: false); if let u = u { siteyeBildir(dosya: u, uygulama: aktifUyg, baslangic: a.baslangic, mik: a.sonMik, pencere: a.pencere, hemen: true) }; exit(0) }
    }
    sinyal.resume()
    Task {
        while true {
            nabizAt(klasor: kayitKlasoru)
            if Date().timeIntervalSince(sonIzinYazma) >= 300 { sonIzinYazma = Date(); izinYaz(kayitKlasoru) }
            let ay = ayarOku(ayarYolu)
            let acik = (ay["oto_kayit"] as? Bool) ?? true
            Bildirici.shared.tara(kayitKlasoru)
            let liste = mikrofonKullananlar()
            var uyg = toplantiUygulamasi(liste)
            let haric = kayitDisiDesenler(ay); var haricte = false
            if let u = uyg, !haric.isEmpty, let neden = await kayitDisiToplanti(u, kayitKlasoru, haric) {
                haricte = true
                if kayitDisiUyarildi != neden { log("Kaydedilmeyen toplantı (\(neden)); \(aktif == nil ? "kayıt başlatılmadı" : "kayıt kapatılıyor")"); kayitDisiUyarildi = neden }
                uyg = nil
                if aktif != nil { sonGorulme = Date().addingTimeInterval(-BEKLE_DUR) }
            } else if uyg != nil { kayitDisiUyarildi = "" }
            // Chrome uzantısı Meet'i kendi kaydediyorsa (bayrak dosyası 30 sn içinde yenilenmişse) tarayıcıyı atla
            if let u = uyg, u.lowercased().contains("chrome") || u.lowercased().contains("safari") || u.lowercased().contains("firefox") || u.lowercased().contains("browser") || u.lowercased().contains("edge") {
                let bayrak = kayitKlasoru.appendingPathComponent(".uzanti_aktif").path
                if let at = try? FileManager.default.attributesOfItem(atPath: bayrak), let m = at[.modificationDate] as? Date, Date().timeIntervalSince(m) < 30 { uyg = nil }
                // Tarayıcı mikrofonu kullanıyor diye kayda BAŞLAMA ya da kaydı SÜRDÜRME; toplantı sinyali şart (bkz. tarayiciKapisi).
                // (YouTube izlerken arka planda açık bir Meet sekmesi mikrofonu tutuyor ve video toplantı sanılıyordu; ayrıca Chrome
                //  toplantı bitince de mikrofonu bırakmayabiliyor: 20 Ekim akşamı toplantı yokken saatlerce tutuyordu.)
                if uyg != nil {
                    if let neden = await tarayiciKapisi(u, kayitKlasoru) {
                        sonKapiZamani = Date(); aramaUyarildi = false; kapiYaz(neden)
                    } else if aktif == nil {
                        if !aramaUyarildi { log("Tarayıcı mikrofonda ama toplantı sinyali yok (uzantı, takvim ve pencere sessiz); kayıt başlatılmadı"); aramaUyarildi = true }
                        sonKapi = ""; uyg = nil
                        if bosMikBas == nil { bosMikBas = Date() }; bosMikSimdi = true
                    } else if Date().timeIntervalSince(sonKapiZamani) >= KAPI_SURE {
                        log("10 dakikadır toplantı sinyali yok (Chrome mikrofonu bırakmasa da); kayıt kapatılıyor"); sonKapi = ""; uyg = nil
                        sonGorulme = Date().addingTimeInterval(-BEKLE_DUR)
                    }
                }
            }
            // Mikrofon kapalı (sessizde katılım, bağlantı kopup geri dönüş) ama ekranda sesli toplantı penceresi: kayıt başlar ya da sürer.
            if acik && uyg == nil && !haricte && (aktif != nil || Date().timeIntervalSince(sonPencereBakis) >= 6) {
                sonPencereBakis = Date()
                if let (b, t, ses) = await sesliToplantiPenceresi(haric) {
                    if ses {
                        sonSesliToplanti = Date()
                        if aktif == nil && sesliUyarildi != t { log("Mikrofon kapalı ama ekranda sesli toplantı penceresi: \(t)"); sesliUyarildi = t }
                        uyg = aktif == nil ? b : aktifUyg
                    } else if aktif != nil && Date().timeIntervalSince(sonSesliToplanti) < PENCERE_SURE {
                        uyg = aktifUyg                                        // pencere açık, ses yok: kopukluk ya da sessizlik; bir süre daha beklenir
                    }
                }
            } else if uyg != nil { sonSesliToplanti = Date() }
            // Toplantı yokken tarayıcı mikrofonu tutuyorsa (2026-10-20: Chrome saatlerce tuttu, kullanıcı hangi sekme bulamadı) siteye yaz;
            // Transcript sayfası 20 dk'yı geçince uyarır ve açık tarayıcı pencerelerinin adlarını gösterir.
            if !bosMikSimdi { bosMikBas = nil }
            if Date().timeIntervalSince(sonMikYazma) >= 30 {
                sonMikYazma = Date()
                let sn = bosMikBas.map { Int(Date().timeIntervalSince($0)) } ?? 0
                var pencereler: [String] = []
                if sn >= 600, let u = toplantiUygulamasi(liste) { pencereler = await tarayiciPencereleri(u) }
                let d: [String: Any] = ["zaman": Date().timeIntervalSince1970, "bos_mik_sn": sn, "uygulama": sn > 0 ? (toplantiUygulamasi(liste) ?? "") : "", "pencereler": pencereler]
                if let veri = try? JSONSerialization.data(withJSONObject: d) { try? veri.write(to: kayitKlasoru.appendingPathComponent(".mik_durum.json")) }
            }
            bosMikSimdi = false
            if let a = aktif {
                await a.gerekirseYenidenBaglan()
                a.durumYaz(kayit: true)
                if uyg != nil { sonGorulme = Date() }
                let sessiz = Date().timeIntervalSince(sonGorulme)
                if sessiz >= BEKLE_DUR || Date().timeIntervalSince(a.baslangic) >= EN_COK || !acik {
                    log("Toplantı bitti görünüyor (\(aktifUyg)); kayıt kapatılıyor")
                    let hedef = a.hedef ?? dosyaAdi(kayitKlasoru, a.baslangic)
                    nabizAt(ileri: 1800); let u = await a.durdur(hedef: hedef, enAzSn: EN_AZ)
                    a.durumYaz(kayit: false)
                    if let u = u { siteyeBildir(dosya: u, uygulama: aktifUyg, baslangic: a.baslangic, mik: a.sonMik, pencere: a.pencere) }
                    aktif = nil; aktifUyg = ""; ilkGorulme = nil
                }
            } else if acik, let u = uyg {
                if ilkGorulme == nil { ilkGorulme = Date() }
                if Date().timeIntervalSince(ilkGorulme!) >= BEKLE_BASLA {
                    let k = Kayit(klasor: kayitKlasoru, uygulama: u)
                    k.hedef = dosyaAdi(kayitKlasoru, k.baslangic)
                    do {
                        try await k.baslat(); aktif = k; aktifUyg = u; sonGorulme = Date(); log("Kayıt başladı: \(u)"); k.durumYaz(kayit: true); kayitHatasiYaz(kayitKlasoru, nil)
                        if (ay["ekran_kareleri"] as? Bool) ?? true { let e = EkranKaydi(kok: kayitKlasoru, uygulama: u, baslangic: k.baslangic); k.ekran = e; e.baslat() }
                    }
                    catch { log("Kayıt başlatılamadı: \(error.localizedDescription) (izinleri kontrol edin)"); ilkGorulme = Date().addingTimeInterval(30); kayitHatasiYaz(kayitKlasoru, error.localizedDescription) }
                }
            } else { ilkGorulme = nil }
            Gosterge.shared.guncelle(aktif, kok: kayitKlasoru, yuzen: (ay["kayit_gostergesi"] as? Bool) ?? true)
            try? await Task.sleep(nanoseconds: 3_000_000_000)
        }
    }
    let uygulama = NSApplication.shared; uygulama.setActivationPolicy(.accessory)   // bildirim tıklamaları ancak uygulama döngüsüyle gelir
    uygulama.run()
}
print("Kullanım: kaydedici --izle <ayarlar.json> <kayit_klasoru> | --durum | --kaydet <sn> <cikti.m4a>")
exit(1)
