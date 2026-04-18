# marmalade-tts Voice Effects Showcase

**160 samples** · Kitten TTS · Kiki (F) & Jasper (M) · phrase:

> _Systems online. Diagnostic scan complete. All 47 subsystems nominal. Proceed with caution, the air feels strange tonight._

Each entry below shows the slug, the sox effect chain, and links to both voice versions.
Play with: `paplay <file>` or your favorite audio player.

---


## BASELINE

### `baseline`

**Chain:** `(no effects — baseline)`

- [F — Kiki](./baseline-F.wav)
- [M — Jasper](./baseline-M.wav)


## ROBOT family (metallic/mechanical)

### `robot-01-preset`

**Chain:** `--effect robot`

- [F — Kiki](./robot-01-preset-F.wav)
- [M — Jasper](./robot-01-preset-M.wav)

### `robot-02-heavy`

**Chain:** `--effect overdrive=40 --effect pitch=-400 --effect reverb=15`

- [F — Kiki](./robot-02-heavy-F.wav)
- [M — Jasper](./robot-02-heavy-M.wav)

### `robot-03-light`

**Chain:** `--effect overdrive=10 --effect pitch=-150 --effect reverb=5`

- [F — Kiki](./robot-03-light-F.wav)
- [M — Jasper](./robot-03-light-M.wav)

### `robot-04-tincan`

**Chain:** `--effect bandpass=400:3000 --effect overdrive=25 --effect pitch=-200`

- [F — Kiki](./robot-04-tincan-F.wav)
- [M — Jasper](./robot-04-tincan-M.wav)

### `robot-05-droid`

**Chain:** `--effect overdrive=15 --effect pitch=-250 --effect flanger --effect reverb=8`

- [F — Kiki](./robot-05-droid-F.wav)
- [M — Jasper](./robot-05-droid-M.wav)

### `robot-06-formant`

**Chain:** `--effect pitch=-600 --effect tempo=1.05 --effect overdrive=15`

- [F — Kiki](./robot-06-formant-F.wav)
- [M — Jasper](./robot-06-formant-M.wav)

### `robot-07-protocol`

**Chain:** `--effect pitch=-350 --effect bandpass=200:5000 --effect overdrive=30 --effect chorus`

- [F — Kiki](./robot-07-protocol-F.wav)
- [M — Jasper](./robot-07-protocol-M.wav)

### `robot-08-vocoder`

**Chain:** `--effect chorus --effect overdrive=20 --effect pitch=-300 --effect treble=6`

- [F — Kiki](./robot-08-vocoder-F.wav)
- [M — Jasper](./robot-08-vocoder-M.wav)

### `robot-09-cold`

**Chain:** `--effect pitch=-200 --effect bass=-6 --effect treble=8 --effect overdrive=12`

- [F — Kiki](./robot-09-cold-F.wav)
- [M — Jasper](./robot-09-cold-M.wav)

### `robot-10-phase`

**Chain:** `--effect flanger --effect flanger --effect overdrive=18`

- [F — Kiki](./robot-10-phase-F.wav)
- [M — Jasper](./robot-10-phase-M.wav)


## GLaDOS family (Portal-style layered synth voice)

### `glados-01-classic`

**Chain:** `--effect pitch=-200 --effect flanger --effect chorus --effect echo=0.8:0.7:40:0.3 --effect reverb=20`

- [F — Kiki](./glados-01-classic-F.wav)
- [M — Jasper](./glados-01-classic-M.wav)

### `glados-02-subtle`

**Chain:** `--effect pitch=-100 --effect flanger --effect chorus --effect reverb=12`

- [F — Kiki](./glados-02-subtle-F.wav)
- [M — Jasper](./glados-02-subtle-M.wav)

### `glados-03-heavy`

**Chain:** `--effect pitch=-300 --effect flanger --effect chorus --effect echo=0.8:0.7:60:0.4 --effect reverb=30`

- [F — Kiki](./glados-03-heavy-F.wav)
- [M — Jasper](./glados-03-heavy-M.wav)

### `glados-04-metallic`

**Chain:** `--effect pitch=-200 --effect flanger --effect chorus --effect overdrive=8 --effect reverb=18`

- [F — Kiki](./glados-04-metallic-F.wav)
- [M — Jasper](./glados-04-metallic-M.wav)

### `glados-05-choral`

**Chain:** `--effect chorus --effect chorus --effect pitch=-150 --effect reverb=25`

- [F — Kiki](./glados-05-choral-F.wav)
- [M — Jasper](./glados-05-choral-M.wav)

### `glados-06-aperture`

**Chain:** `--effect pitch=-250 --effect flanger --effect echo=0.8:0.88:45:0.35 --effect chorus --effect treble=3`

- [F — Kiki](./glados-06-aperture-F.wav)
- [M — Jasper](./glados-06-aperture-M.wav)


## RADIO family (CB/walkie/broadcast)

### `radio-01-cb`

**Chain:** `--effect bandpass=300:3400 --effect overdrive=8 --effect vol=1.5`

- [F — Kiki](./radio-01-cb-F.wav)
- [M — Jasper](./radio-01-cb-M.wav)

### `radio-02-walkie`

**Chain:** `--effect bandpass=500:3000 --effect overdrive=15 --effect vol=1.8`

- [F — Kiki](./radio-02-walkie-F.wav)
- [M — Jasper](./radio-02-walkie-M.wav)

### `radio-03-police`

**Chain:** `--effect bandpass=400:3200 --effect overdrive=10 --effect vol=1.6 --effect treble=4`

- [F — Kiki](./radio-03-police-F.wav)
- [M — Jasper](./radio-03-police-M.wav)

### `radio-04-aircraft`

**Chain:** `--effect bandpass=300:3000 --effect overdrive=6 --effect vol=1.4 --effect bass=-6`

- [F — Kiki](./radio-04-aircraft-F.wav)
- [M — Jasper](./radio-04-aircraft-M.wav)

### `radio-05-shortwave`

**Chain:** `--effect bandpass=500:2800 --effect overdrive=18 --effect vol=1.7 --effect treble=-3`

- [F — Kiki](./radio-05-shortwave-F.wav)
- [M — Jasper](./radio-05-shortwave-M.wav)

### `radio-06-distant`

**Chain:** `--effect bandpass=500:3500 --effect overdrive=5 --effect vol=1.3 --effect reverb=8`

- [F — Kiki](./radio-06-distant-F.wav)
- [M — Jasper](./radio-06-distant-M.wav)

### `radio-07-broadcast`

**Chain:** `--effect bandpass=200:4000 --effect treble=3 --effect overdrive=3 --effect vol=1.4`

- [F — Kiki](./radio-07-broadcast-F.wav)
- [M — Jasper](./radio-07-broadcast-M.wav)


## OLD-TIMEY RADIO (1920s–1940s AM, gramophone)

### `oldtime-01-1920s`

**Chain:** `--effect bandpass=400:2500 --effect overdrive=12 --effect vol=1.5 --effect treble=-6`

- [F — Kiki](./oldtime-01-1920s-F.wav)
- [M — Jasper](./oldtime-01-1920s-M.wav)

### `oldtime-02-1940s-newscaster`

**Chain:** `--effect bandpass=300:3000 --effect overdrive=6 --effect treble=3 --effect vol=1.6`

- [F — Kiki](./oldtime-02-1940s-newscaster-F.wav)
- [M — Jasper](./oldtime-02-1940s-newscaster-M.wav)

### `oldtime-03-gramophone`

**Chain:** `--effect bandpass=500:2200 --effect overdrive=20 --effect treble=-8 --effect vol=1.5`

- [F — Kiki](./oldtime-03-gramophone-F.wav)
- [M — Jasper](./oldtime-03-gramophone-M.wav)

### `oldtime-04-phonograph`

**Chain:** `--effect bandpass=600:2000 --effect overdrive=25 --effect treble=-10 --effect vol=1.6`

- [F — Kiki](./oldtime-04-phonograph-F.wav)
- [M — Jasper](./oldtime-04-phonograph-M.wav)

### `oldtime-05-wax-cylinder`

**Chain:** `--effect bandpass=800:1800 --effect overdrive=30 --effect treble=-12 --effect vol=1.5`

- [F — Kiki](./oldtime-05-wax-cylinder-F.wav)
- [M — Jasper](./oldtime-05-wax-cylinder-M.wav)

### `oldtime-06-tv-news`

**Chain:** `--effect bandpass=400:3500 --effect overdrive=4 --effect treble=-3 --effect vol=1.4`

- [F — Kiki](./oldtime-06-tv-news-F.wav)
- [M — Jasper](./oldtime-06-tv-news-M.wav)


## MONSTER family (deep/distorted/beast)

### `monster-01-deep`

**Chain:** `--effect pitch=-500 --effect overdrive=20 --effect bass=9 --effect reverb=15`

- [F — Kiki](./monster-01-deep-F.wav)
- [M — Jasper](./monster-01-deep-M.wav)

### `monster-02-demon`

**Chain:** `--effect pitch=-700 --effect overdrive=35 --effect bass=10 --effect reverb=30 --effect echo=0.8:0.7:80:0.4`

- [F — Kiki](./monster-02-demon-F.wav)
- [M — Jasper](./monster-02-demon-M.wav)

### `monster-03-ogre`

**Chain:** `--effect pitch=-400 --effect overdrive=18 --effect bass=6 --effect tempo=0.9`

- [F — Kiki](./monster-03-ogre-F.wav)
- [M — Jasper](./monster-03-ogre-M.wav)

### `monster-04-dragon`

**Chain:** `--effect pitch=-600 --effect overdrive=28 --effect bass=8 --effect reverb=25 --effect echo=0.8:0.7:120:0.5`

- [F — Kiki](./monster-04-dragon-F.wav)
- [M — Jasper](./monster-04-dragon-M.wav)

### `monster-05-growl`

**Chain:** `--effect pitch=-550 --effect overdrive=45 --effect bass=5 --effect treble=-4`

- [F — Kiki](./monster-05-growl-F.wav)
- [M — Jasper](./monster-05-growl-M.wav)

### `monster-06-behemoth`

**Chain:** `--effect pitch=-800 --effect overdrive=25 --effect bass=12 --effect reverb=20 --effect tempo=0.85`

- [F — Kiki](./monster-06-behemoth-F.wav)
- [M — Jasper](./monster-06-behemoth-M.wav)

### `monster-07-eldritch`

**Chain:** `--effect pitch=-600 --effect chorus --effect reverb=40 --effect echo=0.8:0.7:150:0.5 --effect bass=6`

- [F — Kiki](./monster-07-eldritch-F.wav)
- [M — Jasper](./monster-07-eldritch-M.wav)

### `monster-08-zombie`

**Chain:** `--effect pitch=-350 --effect overdrive=15 --effect bass=4 --effect tempo=0.75 --effect reverb=10`

- [F — Kiki](./monster-08-zombie-F.wav)
- [M — Jasper](./monster-08-zombie-M.wav)


## GHOST / WHISPER family

### `ghost-01-whisper-preset`

**Chain:** `--effect whisper`

- [F — Kiki](./ghost-01-whisper-preset-F.wav)
- [M — Jasper](./ghost-01-whisper-preset-M.wav)

### `ghost-02-spectral`

**Chain:** `--effect vol=0.5 --effect treble=6 --effect reverb=60 --effect echo=0.8:0.8:200:0.5`

- [F — Kiki](./ghost-02-spectral-F.wav)
- [M — Jasper](./ghost-02-spectral-M.wav)

### `ghost-03-phantom`

**Chain:** `--effect pitch=-100 --effect reverb=80 --effect vol=0.6 --effect chorus`

- [F — Kiki](./ghost-03-phantom-F.wav)
- [M — Jasper](./ghost-03-phantom-M.wav)

### `ghost-04-ethereal`

**Chain:** `--effect vol=0.5 --effect reverb=70 --effect chorus --effect treble=4`

- [F — Kiki](./ghost-04-ethereal-F.wav)
- [M — Jasper](./ghost-04-ethereal-M.wav)

### `ghost-05-crypt`

**Chain:** `--effect pitch=-150 --effect reverb=90 --effect echo=0.8:0.7:180:0.5 --effect vol=0.7`

- [F — Kiki](./ghost-05-crypt-F.wav)
- [M — Jasper](./ghost-05-crypt-M.wav)

### `ghost-06-breathy`

**Chain:** `--effect vol=0.4 --effect treble=8 --effect reverb=30 --effect bass=-4`

- [F — Kiki](./ghost-06-breathy-F.wav)
- [M — Jasper](./ghost-06-breathy-M.wav)


## PHONE family

### `phone-01-preset`

**Chain:** `--effect telephone`

- [F — Kiki](./phone-01-preset-F.wav)
- [M — Jasper](./phone-01-preset-M.wav)

### `phone-02-cell`

**Chain:** `--effect bandpass=300:3400 --effect overdrive=10 --effect vol=1.5 --effect treble=3`

- [F — Kiki](./phone-02-cell-F.wav)
- [M — Jasper](./phone-02-cell-M.wav)

### `phone-03-old-landline`

**Chain:** `--effect bandpass=400:3000 --effect overdrive=6 --effect vol=1.5 --effect treble=-3`

- [F — Kiki](./phone-03-old-landline-F.wav)
- [M — Jasper](./phone-03-old-landline-M.wav)

### `phone-04-answering-machine`

**Chain:** `--effect bandpass=500:3000 --effect overdrive=15 --effect vol=1.4 --effect reverb=5`

- [F — Kiki](./phone-04-answering-machine-F.wav)
- [M — Jasper](./phone-04-answering-machine-M.wav)

### `phone-05-voip-bad-signal`

**Chain:** `--effect bandpass=400:3400 --effect overdrive=20 --effect vol=1.6 --effect flanger`

- [F — Kiki](./phone-05-voip-bad-signal-F.wav)
- [M — Jasper](./phone-05-voip-bad-signal-M.wav)

### `phone-06-speakerphone`

**Chain:** `--effect bandpass=300:3400 --effect reverb=15 --effect vol=1.7 --effect overdrive=5`

- [F — Kiki](./phone-06-speakerphone-F.wav)
- [M — Jasper](./phone-06-speakerphone-M.wav)


## UNDERWATER / MUFFLED

### `underwater-01`

**Chain:** `--effect bandpass=100:1200 --effect reverb=30 --effect vol=1.3`

- [F — Kiki](./underwater-01-F.wav)
- [M — Jasper](./underwater-01-M.wav)

### `underwater-02-deep`

**Chain:** `--effect bandpass=80:800 --effect reverb=50 --effect vol=1.4 --effect bass=6`

- [F — Kiki](./underwater-02-deep-F.wav)
- [M — Jasper](./underwater-02-deep-M.wav)

### `underwater-03-submarine`

**Chain:** `--effect bandpass=150:1500 --effect reverb=25 --effect echo=0.8:0.7:100:0.4 --effect bass=4`

- [F — Kiki](./underwater-03-submarine-F.wav)
- [M — Jasper](./underwater-03-submarine-M.wav)

### `muffled-01-through-wall`

**Chain:** `--effect bandpass=200:1500 --effect vol=1.3 --effect bass=3`

- [F — Kiki](./muffled-01-through-wall-F.wav)
- [M — Jasper](./muffled-01-through-wall-M.wav)

### `muffled-02-behind-door`

**Chain:** `--effect bandpass=300:2000 --effect vol=1.2 --effect reverb=15`

- [F — Kiki](./muffled-02-behind-door-F.wav)
- [M — Jasper](./muffled-02-behind-door-M.wav)


## ALIEN family

### `alien-01-classic`

**Chain:** `--effect pitch=400 --effect flanger --effect chorus --effect reverb=15`

- [F — Kiki](./alien-01-classic-F.wav)
- [M — Jasper](./alien-01-classic-M.wav)

### `alien-02-high`

**Chain:** `--effect pitch=600 --effect flanger --effect reverb=20 --effect echo=0.8:0.7:50:0.3`

- [F — Kiki](./alien-02-high-F.wav)
- [M — Jasper](./alien-02-high-M.wav)

### `alien-03-sinister`

**Chain:** `--effect pitch=-200 --effect flanger --effect chorus --effect echo=0.8:0.7:80:0.4 --effect reverb=25`

- [F — Kiki](./alien-03-sinister-F.wav)
- [M — Jasper](./alien-03-sinister-M.wav)

### `alien-04-swarm`

**Chain:** `--effect chorus --effect chorus --effect flanger --effect pitch=200 --effect reverb=20`

- [F — Kiki](./alien-04-swarm-F.wav)
- [M — Jasper](./alien-04-swarm-M.wav)

### `alien-05-xenomorph`

**Chain:** `--effect pitch=-400 --effect overdrive=25 --effect bass=8 --effect reverb=30 --effect flanger`

- [F — Kiki](./alien-05-xenomorph-F.wav)
- [M — Jasper](./alien-05-xenomorph-M.wav)


## MEGAPHONE / PA

### `megaphone-01-preset`

**Chain:** `--effect megaphone`

- [F — Kiki](./megaphone-01-preset-F.wav)
- [M — Jasper](./megaphone-01-preset-M.wav)

### `megaphone-02-loud`

**Chain:** `--effect bandpass=400:4000 --effect overdrive=40 --effect vol=2.2`

- [F — Kiki](./megaphone-02-loud-F.wav)
- [M — Jasper](./megaphone-02-loud-M.wav)

### `megaphone-03-stadium`

**Chain:** `--effect bandpass=400:4000 --effect overdrive=30 --effect vol=2.0 --effect reverb=40 --effect echo=0.8:0.7:120:0.4`

- [F — Kiki](./megaphone-03-stadium-F.wav)
- [M — Jasper](./megaphone-03-stadium-M.wav)

### `megaphone-04-pa-system`

**Chain:** `--effect bandpass=300:4000 --effect overdrive=20 --effect vol=1.8 --effect reverb=25`

- [F — Kiki](./megaphone-04-pa-system-F.wav)
- [M — Jasper](./megaphone-04-pa-system-M.wav)

### `megaphone-05-drill-sergeant`

**Chain:** `--effect bandpass=500:4000 --effect overdrive=45 --effect vol=2.3 --effect bass=-3`

- [F — Kiki](./megaphone-05-drill-sergeant-F.wav)
- [M — Jasper](./megaphone-05-drill-sergeant-M.wav)


## CAVE / STADIUM (spatial)

### `cave-01-preset`

**Chain:** `--effect cave`

- [F — Kiki](./cave-01-preset-F.wav)
- [M — Jasper](./cave-01-preset-M.wav)

### `cave-02-deep`

**Chain:** `--effect reverb=90 --effect echo=0.8:0.7:200:0.5 --effect bass=3`

- [F — Kiki](./cave-02-deep-F.wav)
- [M — Jasper](./cave-02-deep-M.wav)

### `cave-03-vast`

**Chain:** `--effect reverb=95 --effect echo=0.8:0.7:350:0.6`

- [F — Kiki](./cave-03-vast-F.wav)
- [M — Jasper](./cave-03-vast-M.wav)

### `stadium-01-preset`

**Chain:** `--effect stadium`

- [F — Kiki](./stadium-01-preset-F.wav)
- [M — Jasper](./stadium-01-preset-M.wav)

### `stadium-02-arena`

**Chain:** `--effect reverb=85 --effect echo=0.8:0.7:120:0.4 --effect vol=1.3`

- [F — Kiki](./stadium-02-arena-F.wav)
- [M — Jasper](./stadium-02-arena-M.wav)


## SPEED / PITCH novelties

### `chipmunk-01`

**Chain:** `--effect chipmunk`

- [F — Kiki](./chipmunk-01-F.wav)
- [M — Jasper](./chipmunk-01-M.wav)

### `chipmunk-02-extreme`

**Chain:** `--effect pitch=700 --effect tempo=0.9`

- [F — Kiki](./chipmunk-02-extreme-F.wav)
- [M — Jasper](./chipmunk-02-extreme-M.wav)

### `deep-01`

**Chain:** `--effect deep`

- [F — Kiki](./deep-01-F.wav)
- [M — Jasper](./deep-01-M.wav)

### `slow-deep-01`

**Chain:** `--effect slow_deep`

- [F — Kiki](./slow-deep-01-F.wav)
- [M — Jasper](./slow-deep-01-M.wav)

### `fast-high-01`

**Chain:** `--effect fast_high`

- [F — Kiki](./fast-high-01-F.wav)
- [M — Jasper](./fast-high-01-M.wav)

### `drunk-01`

**Chain:** `--effect tempo=0.8 --effect pitch=-100 --effect reverb=10`

- [F — Kiki](./drunk-01-F.wav)
- [M — Jasper](./drunk-01-M.wav)

### `sped-up-01`

**Chain:** `--effect tempo=1.4 --effect pitch=100`

- [F — Kiki](./sped-up-01-F.wav)
- [M — Jasper](./sped-up-01-M.wav)


## DREAM / HYPNOTIC

### `dream-01`

**Chain:** `--effect reverb=70 --effect chorus --effect echo=0.8:0.8:300:0.5 --effect pitch=-50`

- [F — Kiki](./dream-01-F.wav)
- [M — Jasper](./dream-01-M.wav)

### `dream-02-reverie`

**Chain:** `--effect reverb=80 --effect chorus --effect tempo=0.92 --effect vol=0.8`

- [F — Kiki](./dream-02-reverie-F.wav)
- [M — Jasper](./dream-02-reverie-M.wav)

### `hypnotic-01`

**Chain:** `--effect echo=0.8:0.8:400:0.6 --effect reverb=50 --effect chorus --effect pitch=-100`

- [F — Kiki](./hypnotic-01-F.wav)
- [M — Jasper](./hypnotic-01-M.wav)

