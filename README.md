# Meet

Meet records your online meetings on your Mac and turns them into notes you can act on: a short summary, decisions, who does what (each with
the exact quote and timestamp), open questions, and a private coaching note on how the meeting went. Speech recognition runs on your Mac.
Built for Apple silicon. Open source under the MIT license.

## What you can do

- **Automatic recording** of Zoom, Microsoft Teams, Google Meet and FaceTime calls. A small recorder app notices when a call starts and stops
  when it ends; a red dot in the menu bar shows that it is recording. Recurring calls that aren't meetings (a weekly course, say) are learned and
  skipped. You can also record in the browser or upload an audio file.
- **Transcript** with speaker separation; names come from the Chrome extension (captions and participant list) and from voices it has learned.
- **Notes:** summary, decisions, tasks with owners and dates only when someone said them, ideas that were discussed but not decided, open
  questions. Every decision and task carries the quote it is based on, checked against the transcript.
- **During the meeting:** live transcript, reminders of earlier decisions, short coaching cards, your share of the talking (Chrome side panel).
- **Before the meeting:** a prep note from earlier meetings with the same people, also on the join screen when no calendar is connected.
- **After:** ask questions across all your meetings, Word / text / Markdown export, a spoken summary, optional Google Drive filing and Asana tasks.

Interface in English or Turkish.

## Install

Requirements: a Mac with Apple silicon, **macOS 15** or newer, [Homebrew](https://brew.sh), Git and the Xcode Command Line Tools
(`xcode-select --install`).

```bash
git clone https://github.com/yehsohimself/meet.git
cd meet
./kurulum.sh
```

The script installs `ffmpeg` and `uv`, creates `.venv`, builds the recorder app and starts the site and the recorder at login. Then open
http://127.0.0.1:8766 (later: double-click `Meet.command`). A "Getting started" card on the home page lists what is left:

1. **Turn on automatic recording** (Settings → Recording). The first recording asks for *Screen & System Audio Recording* and *Microphone*
   permission in System Settings → Privacy & Security.
2. **Chrome extension** (optional, recommended): `chrome://extensions` → Developer mode → *Load unpacked* → the `uzanti` folder. It reads the
   participant names and captions of Google Meet and Teams on the web, and adds the side panel.
3. **Your name** (Settings → General), so your own tasks are shown first and your voice is recognised.
4. **Calendar** (optional): a private iCal address for meeting names and prep notes.

The speech model (~1.6 GB) downloads on first use.

### Notes need Claude or a local model

Recording, transcription and speaker separation need nothing else. Notes, summaries and the other writing tasks need one of:

- **Claude** through your own subscription: install [Claude Code](https://claude.com/claude-code) and sign in once (`claude auth login`).
  The transcript of that meeting is then sent to Claude for the notes. You can turn this off for meetings only (Settings → General).
- **A local model:** `brew install ollama`, `brew services start ollama`, `ollama pull gemma3:4b`. Nothing leaves your Mac
  (slower; the structured notes are less reliable).

## Recording other people

Meet records everyone's voice in the call. **Tell the people in the meeting that you are recording.** In many countries (Germany, for
example) recording a conversation without consent is illegal. Meet never posts anything into the meeting chat.

## Where your data goes

Audio, transcripts and notes stay in this folder on your Mac. If you chose Claude, the text needed for a task is sent to Claude; with Ollama
nothing is sent. Optional integrations are off until you turn them on: Google Drive (copies notes into a folder you choose), Asana (adds your
own tasks), Mail (sends the notes to yourself), Cloudflare tunnel (invite links for a few friends, your phone).

## Tested on

MacBook Air M4, 16 GB, macOS 26.6, Claude Code signed in; used daily for Google Meet and Microsoft Teams calls in Turkish and English.

## Known limits

- macOS 15+ on Apple silicon only (ScreenCaptureKit, mlx-whisper, Vision).
- The recorder is signed ad hoc on your Mac; after rebuilding it, macOS may ask for the recording permission again.
- The Chrome extension reads the Google Meet and Teams web pages; their layout changes now and then, and names may be missing until it is updated.
- Code identifiers and comments are in Turkish; the interface is bilingual.

## Development

`site.py` is a small loader; the code runs in `sunucu/00_… 30_….py` parts within one namespace. Tests: `.venv/bin/python -m pytest
tests -q` and `duman_testi.py hizli|meet`. After changing the server: `.venv/bin/python yeniden_baslat.py`. Recorder: `kaydedici/kaydedici.swift`
(rebuild with `./kurulum.sh`). Architecture: [docs/MIMARI.md](docs/MIMARI.md). `python sizinti.py` scans the repo for personal data.
This repo is cut from a larger workspace that develops sibling products on the same engine (Studio is public at
[yehsohimself/studio](https://github.com/yehsohimself/studio)); siblings that are not installed are off.

Issues and pull requests are welcome; say which meeting app and which step failed.

---

**Türkçe:** Meet, çevrimiçi toplantılarınızı Mac'inizde kaydeder ve uygulanabilir notlara çevirir: kısa özet, kararlar, kim ne yapacak
(her biri alıntısı ve zamanıyla), açık sorular ve size özel koçluk notu. Ses tanıma Mac'te çalışır; notlar için Claude (kendi hesabınız;
o toplantının metni Claude'a gider) ya da yerel Ollama modeli gerekir. Kurulum: yukarıdaki üç komut, sonra http://127.0.0.1:8766.
Kaydettiğinizi toplantıdakilere söyleyin; birçok ülkede izin gerekir.
