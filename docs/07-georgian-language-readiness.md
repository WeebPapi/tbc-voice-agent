# Georgian language readiness

## 1. Objective

Move from an English architecture demo to a Georgian soft-collections pilot candidate without changing the policy engine or Bank integration contracts.

Georgian support is not complete when prompts are translated. It requires telephone-audio recognition, spoken-value normalization, natural synthesis, culturally appropriate scripts, and scenario testing with native speakers.

## 2. Architecture requirements now

The English POC must already:

- Pass a BCP 47 language code through session, STT, LLM, content, and TTS interfaces.
- Store content by stable key and language, rather than embedding English strings in orchestration code.
- Keep text normalization behind a language-specific interface.
- Avoid English-only regular expressions for dates, amounts, affirmations, and negations.
- Preserve original transcript plus normalized structured values.
- Allow different STT and TTS providers for each language.
- Record provider, model, language, and confidence in voice-quality events.

Suggested interface:

```python
class LanguagePack(Protocol):
    language_code: str
    def normalize_slots(self, text: str, hints: SlotHints) -> NormalizedSlots: ...
    def classify_confirmation(self, text: str) -> ConfirmationResult: ...
    def render_template(self, key: str, values: dict[str, object]) -> str: ...
```

## 3. Georgian workstreams

### 3.1 Approved content

Create a Georgian content pack with Bank-approved versions of greetings, identity questions, disclosure wording, reminders, confirmations, hardship/dispute responses, stop-contact handling, transfer language, and technical-failure closings.

Translation should be performed or reviewed by a native Georgian speaker familiar with customer-service and collections language. Avoid literal translation where it sounds unnatural or overly harsh.

### 3.2 Speech recognition benchmark

Compare the proposed primary and fallback STT providers using the same labeled corpus. Candidate providers from the proposal include ElevenLabs Scribe and Google Chirp 2 for `ka-GE`, subject to current capability and Bank approval.

The corpus should cover:

- Telephone-quality and compressed audio.
- Multiple regions, ages, speaking speeds, and voice characteristics.
- Background noise and interruptions.
- Georgian names and surnames.
- GEL amounts, including whole and fractional values.
- Calendar dates and relative dates.
- Customer/account reference fragments.
- Short affirmations, negations, corrections, and uncertainty.
- Code-switching between Georgian, English, and common borrowed financial terms.
- Dispute, hardship, and stop-contact phrases.

Do not rely only on overall word error rate. Measure exact field accuracy for identity answers, amount, date, yes/no confirmation, and scenario intent.

### 3.3 Georgian normalization

Implement and test:

- Georgian number words to decimal values.
- GEL/თეთრი expressions and mixed numeric forms.
- Day, month, and relative-date expressions.
- Alternative pronunciations of names and identifiers.
- Affirmative, negative, hesitant, and corrective phrases.
- Normalization of code-switched values.

Critical values must still be read back and explicitly confirmed. Normalization never replaces policy validation.

### 3.4 Speech synthesis benchmark

Evaluate:

- Naturalness and intelligibility over telephone audio.
- Pronunciation of names, GEL values, dates, abbreviations, and borrowed words.
- Stability of voice, pace, and tone across long sessions.
- Time to first audio and interruption behavior.
- Whether approved compliance wording remains understandable.

Use SSML or provider pronunciation dictionaries only inside the TTS adapter. Do not contaminate the canonical transcript or CRM values with speech markup.

### 3.5 Conversation tuning

Georgian turn-taking may require different pause, endpointing, and clarification thresholds than English. Keep these values in the language/campaign configuration:

```text
end_of_turn_silence_ms
maximum_user_silence_ms
barge_in_minimum_ms
low_confidence_threshold
critical_slot_confidence_threshold
clarification_limit
speech_rate
```

## 4. Suggested delivery stages

1. **Text localization:** native-reviewed Georgian content and typed scenario tests.
2. **Recorded-turn mode:** Georgian prerecorded audio through STT and the full policy flow.
3. **Push-to-talk demo:** live Georgian microphone turns without full duplex.
4. **Streaming conversation:** natural turn-taking, interruption, and latency tuning.
5. **Telephone benchmark:** run the same corpus through telephony codecs/media conditions.
6. **Controlled pilot readiness:** Bank approval of content, providers, thresholds, data handling, and acceptance results.

## 5. Initial quality gates

Final thresholds must be agreed with TBC. Before stakeholder review, the team should at least report:

- Overall and scenario-specific word error rate.
- Exact accuracy for amount, date, identity fragment, and confirmation.
- False-positive rate for explicit PTP confirmation.
- Intent recall for dispute, hardship, and stop-contact.
- P50/P95 end-of-turn to first-audio latency.
- Native-speaker ratings for intelligibility, naturalness, tone, and appropriateness.
- Failure rate and provider fallback behavior.

Safety-critical scenario intent and explicit confirmation should be evaluated separately and held to a higher standard than general transcript fluency.

## 6. Georgian acceptance corpus format

Each item should include:

```yaml
id: ka-ptp-001
audio_file: synthetic/ka-ptp-001.wav
speaker_tags: [native, telephone_codec, moderate_noise]
expected_transcript: "..."
expected_intent: promise_to_pay
expected_slots:
  amount: "275.40"
  currency: GEL
  date: "2026-08-28"
critical_fields: [amount, date]
allowed_variants: []
```

Use consented or professionally produced test audio. Do not use customer call recordings in the POC corpus.

## 7. Provider portability

Provider names in the proposal are candidates, not permanent dependencies. A Georgian provider is production-eligible only after quality, processing location, retention, training-data use, security, commercial, and fallback requirements are approved. Store provider-specific options only inside adapters.
