# Georgian smoke corpus (synthetic POC only)

This is a **manual / opt-in** smoke set for ElevenLabs STT/TTS on `/ka`.
It is **not** a production Georgian readiness gate. See
[`docs/07-georgian-language-readiness.md`](../../docs/07-georgian-language-readiness.md)
for the full benchmark requirements.

**Warning:** Live runs consume ElevenLabs quota.

## Phrases

| Category | Synthetic text |
|---|---|
| Greeting | გამარჯობა, ეს არის TBC დემო ასისტენტი. |
| First / last name | ალექს მორგანი / თეა ბერიძე |
| Spoken date | თხუთმეტი მარტი / 15 მარტი |
| GEL amount | ორას სამოცდათხუთმეტი ლარი და ორმოცი თეთრი / 275.40 ლარი |
| Last four digits | ნული ნული ნული ერთი / 0001 |
| Payment-date sentence | გადავიხდი 275.40 ლარი ოცდარვა აგვისტოს. |
| Stop-contact | აღარ დამირეკოთ, შეაჩერეთ კონტაქტი. |
| Hardship | მანქანა დამიტეხა, რთული მდგომარეობაა. |
| Code-switch | I can pay 275.40 ლარი on 28 აგვისტო. |

## How to run

1. Set `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` in `.env`.
2. Start the stack (`scripts/dev.ps1`).
3. Open http://127.0.0.1:5173/ka — choose Voice mode.
4. Speak each phrase; confirm partial vs final transcripts and playback.
5. Or run the opt-in test: `pytest tests/integration/test_elevenlabs_smoke.py -q`

Do not claim production Georgian readiness from this corpus.
