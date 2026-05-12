# Effect samples

A curated set of audio samples showing what marmalade-tts can do with the
built-in audio effects. All samples use the **Kitten** engine with the
**Kiki** voice (`-F` = female).

Play with any audio tool:

```sh
paplay samples/effects/cave-01-F.wav
aplay  samples/effects/cave-01-F.wav
ffplay samples/effects/cave-01-F.wav
```

| File | Command to reproduce |
|------|---------------------|
| `baseline-F.wav` | `marmalade-tts kitten Kiki "<text>" --out baseline-F.wav` |
| `cave-01-F.wav` | `marmalade-tts kitten Kiki "<text>" --effect cave --out cave-01-F.wav` |
| `robot-01-F.wav` | `marmalade-tts kitten Kiki "<text>" --effect robot --out robot-01-F.wav` |
| `chipmunk-01-F.wav` | `marmalade-tts kitten Kiki "<text>" --effect chipmunk --out chipmunk-01-F.wav` |
| `deep-01-F.wav` | `marmalade-tts kitten Kiki "<text>" --effect deep --out deep-01-F.wav` |
| `alien-01-classic-F.wav` | Custom chain — see below |
| `ghost-02-echo-F.wav` | Custom chain — see below |

## Custom chains

Custom effect chains used for the more elaborate samples:

```sh
# alien-01-classic
marmalade-tts kitten Kiki "<text>" \
  --effect "pitch=400" --effect "echo=0.8:0.6:80:0.5" --effect "reverb=40"

# ghost-02-echo
marmalade-tts kitten Kiki "<text>" \
  --effect "echo=0.9:0.7:200:0.6" --effect "reverb=60" --effect "vol=0.7"
```

The full grid of 124 samples across many effect categories lives on the
[`effect-samples`](https://github.com/maxwhipw/marmalade-tts/tree/effect-samples)
branch.

The 10 built-in preset demos live on the
[`preset-demos`](https://github.com/maxwhipw/marmalade-tts/tree/preset-demos)
branch.
