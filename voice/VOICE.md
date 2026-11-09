# Jarvis voice (locked for phase 0)

Engine: Kokoro-82M (Apache 2.0), British English (`lang="en-gb"`), runs on Jarvis's own server, free.

## Base voice ("H")
- Blend: 85% `bm_daniel` + 15% `bm_george`
- Speed: 0.88

## Processing chain ("AI 2.5", ffmpeg filters)
```
highpass=f=90,
equalizer=f=250:t=q:w=1:g=2,
equalizer=f=3000:t=q:w=1.2:g=4,
acompressor=threshold=-20dB:ratio=3:attack=3:release=60:makeup=3,
flanger=delay=1:depth=1.2:regen=5:width=25:speed=0.25,
chorus=0.8:0.9:22:0.32:0.5:1.6,
aecho=0.8:0.7:22|37:0.2|0.11,
loudnorm=I=-13
```

## Adjustable later
AI-tone strength is a setting with three levels:
- **2:** chorus + echo, no flanger
- **2.5:** default
- **3:** stronger flanger and chorus

Planned voice command: "Jarvis, less/more robotic."

## Rule
An original voice blend tuned by ear. It is never trained on or cloned from any real person's recordings.
