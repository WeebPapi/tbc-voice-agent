import { useEffect, useMemo, useRef, useState } from "react";

type EventItem = {
  event_id: string;
  sequence: number;
  type: string;
  source: string;
  payload: Record<string, unknown>;
};

type TranscriptItem = {
  who: "customer" | "assistant" | "partial";
  text: string;
};

type ProviderInfo = {
  configured: boolean;
  stt: string;
  tts: string;
  language?: string;
  stt_model?: string | null;
  tts_model?: string | null;
  language_code?: string | null;
  audio_format?: string | null;
};

const CUSTOMERS = [
  { id: "cust-001", label: "Alex Morgan — PTP" },
  { id: "cust-002", label: "Jordan Lee — payment plan" },
  { id: "cust-003", label: "Casey Brown — already paid" },
  { id: "cust-004", label: "Taylor Smith — hardship" },
  { id: "cust-005", label: "Morgan Reed — stop contact" },
  { id: "cust-006", label: "Jamie Wilson — wrong party / ID fail" },
  { id: "cust-007", label: "Riley Davis — technical failure" },
];

const FAILURES = [
  "outcome_fail_once",
  "outcome_permanent_failure",
  "context_500",
  "identity_timeout",
  "transfer_queue_unavailable",
  "payment_link_rejected",
];

const API = "";
const SAMPLE_RATE = 16000;
/** Bytes of PCM16 for the given duration at SAMPLE_RATE. */
const pcmBytesForSeconds = (seconds: number) => Math.floor(SAMPLE_RATE * 2 * seconds);
/**
 * Prefer a short silent wait over start-of-utterance chopping.
 * Wait for a deep preroll, then schedule that whole block at once.
 */
const PREROLL_BYTES = pcmBytesForSeconds(0.45);
const TARGET_AHEAD_BYTES = pcmBytesForSeconds(0.35);
const SLICE_BYTES = pcmBytesForSeconds(0.12);

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

function escapeText(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function floatTo16BitPCM(input: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(input.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

function downsampleBuffer(buffer: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate) return buffer;
  const ratio = fromRate / toRate;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLength);
  for (let i = 0; i < newLength; i++) {
    result[i] = buffer[Math.round(i * ratio)] ?? 0;
  }
  return result;
}

export default function KaApp() {
  const [customerRef, setCustomerRef] = useState("cust-001");
  const [mode, setMode] = useState<"text" | "voice">("text");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [state, setState] = useState("created");
  const [disposition, setDisposition] = useState<string | null>(null);
  const [policy, setPolicy] = useState<string>("—");
  const [input, setInput] = useState("");
  const [transcript, setTranscript] = useState<TranscriptItem[]>([]);
  const [partialText, setPartialText] = useState("");
  const [events, setEvents] = useState<EventItem[]>([]);
  const [failures, setFailures] = useState<Record<string, string>>({});
  const [transfers, setTransfers] = useState<unknown[]>([]);
  const [health, setHealth] = useState("unknown");
  const [error, setError] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<"idle" | "connecting" | "connected" | "error">(
    "idle"
  );
  const [provider, setProvider] = useState<ProviderInfo | null>(null);
  const [playbackState, setPlaybackState] = useState("idle");
  const [cancelledByInterrupt, setCancelledByInterrupt] = useState(false);
  const [sttLatency, setSttLatency] = useState<string>("—");
  const [ttsLatency, setTtsLatency] = useState<string>("—");
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const seqRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const playCtxRef = useRef<AudioContext | null>(null);
  const playTimeRef = useRef(0);
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const pcmPartsRef = useRef<Uint8Array[]>([]);
  const pcmBytesRef = useRef(0);
  const pcmOddRef = useRef<number | null>(null);
  const playGenerationRef = useRef<string | null>(null);
  const streamOpenRef = useRef(false);
  const playbackStartedRef = useRef(false);
  const speakingRef = useRef(false);

  const latestLatency = useMemo(() => {
    const done = [...events].reverse().find((e) => e.type === "integration.completed");
    return done ? `retry=${String(done.payload.retry_count ?? 0)}` : "—";
  }, [events]);

  async function refreshAdmin() {
    const [f, t] = await Promise.all([
      api<{ failures: Record<string, string> }>("/v1/admin/failures"),
      api<{ transfers: unknown[] }>("/v1/admin/transfers"),
    ]);
    setFailures(f.failures || {});
    setTransfers(t.transfers || []);
  }

  async function pollEvents(id: string) {
    const data = await api<{ events: EventItem[] }>(
      `/v1/sessions/${id}/events?after_sequence=${seqRef.current}`
    );
    if (!data.events.length) return;
    setEvents((prev) => [...prev, ...data.events]);
    seqRef.current = data.events[data.events.length - 1].sequence;
    for (const event of data.events) {
      if (event.type === "policy.decided") {
        setPolicy(`${event.payload.action} (${event.payload.reason_code})`);
      }
      if (event.type === "state.changed") {
        setState(String(event.payload.next));
      }
      if (event.type === "session.ended") {
        setDisposition(String(event.payload.disposition ?? disposition));
      }
      if (event.type === "stt.final_received" && event.payload.time_to_final_transcript_ms != null) {
        setSttLatency(`${event.payload.time_to_final_transcript_ms} ms`);
      }
      if (event.type === "tts.first_audio" && event.payload.time_to_first_audio_ms != null) {
        setTtsLatency(`${event.payload.time_to_first_audio_ms} ms`);
      }
      if (event.type === "tts.cancelled") {
        setCancelledByInterrupt(true);
        setPlaybackState("cancelled");
      }
    }
  }

  useEffect(() => {
    api<{ status: string; elevenlabs_configured?: boolean }>("/health")
      .then((h) => setHealth(h.status))
      .catch(() => setHealth("down"));
    api<Record<string, unknown>>("/v1/providers")
      .then((p) => {
        const geo = (p.georgian || {}) as Record<string, unknown>;
        setProvider({
          configured: Boolean(geo.configured),
          stt: String(geo.stt || "unconfigured"),
          tts: String(geo.tts || "unconfigured"),
          stt_model: (geo.stt_model as string) || null,
          tts_model: (geo.tts_model as string) || null,
          language_code: (geo.language_code as string) || null,
          audio_format: (geo.audio_format as string) || null,
        });
      })
      .catch(() => undefined);
    refreshAdmin().catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    const timer = setInterval(() => {
      pollEvents(sessionId).catch(() => undefined);
    }, 700);
    return () => clearInterval(timer);
  }, [sessionId]);

  function resetPcmBuffer() {
    pcmPartsRef.current = [];
    pcmBytesRef.current = 0;
    pcmOddRef.current = null;
  }

  function stopActiveSourcesOnly() {
    for (const src of activeSourcesRef.current) {
      try {
        src.stop();
      } catch {
        /* ignore */
      }
    }
    activeSourcesRef.current = [];
  }

  function stopPlayback() {
    streamOpenRef.current = false;
    playbackStartedRef.current = false;
    speakingRef.current = false;
    stopActiveSourcesOnly();
    playTimeRef.current = 0;
    playGenerationRef.current = null;
    resetPcmBuffer();
    setSpeaking(false);
    setPlaybackState("idle");
  }

  function ensurePlayContext(): AudioContext {
    const ctx = playCtxRef.current || new AudioContext();
    playCtxRef.current = ctx;
    if (ctx.state === "suspended") {
      ctx.resume().catch(() => undefined);
    }
    return ctx;
  }

  /** Drain up to maxBytes (even) from the queue; leave residual for the next flush. */
  function takeAlignedPcm(maxBytes: number): Int16Array | null {
    if (pcmBytesRef.current < 2) return null;
    const take = Math.min(pcmBytesRef.current, maxBytes) & ~1;
    if (take < 2) return null;

    const merged = new Uint8Array(pcmBytesRef.current);
    let offset = 0;
    for (const part of pcmPartsRef.current) {
      merged.set(part, offset);
      offset += part.length;
    }

    const copy = new ArrayBuffer(take);
    new Uint8Array(copy).set(merged.subarray(0, take));

    const leftover = merged.subarray(take);
    if (leftover.length) {
      pcmPartsRef.current = [leftover.slice()];
      pcmBytesRef.current = leftover.length;
    } else {
      resetPcmBuffer();
    }
    return new Int16Array(copy);
  }

  function queuedAheadSeconds(ctx: AudioContext): number {
    if (!playbackStartedRef.current || playTimeRef.current <= 0) return 0;
    return Math.max(0, playTimeRef.current - ctx.currentTime);
  }

  function schedulePcmSamples(int16: Int16Array, fadeIn: boolean, fadeOut: boolean) {
    if (!int16.length) return;
    const ctx = ensurePlayContext();
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 32768;
    }
    const buffer = ctx.createBuffer(1, float32.length, SAMPLE_RATE);
    buffer.copyToChannel(float32, 0);
    const source = ctx.createBufferSource();
    const gain = ctx.createGain();
    if (playTimeRef.current < ctx.currentTime + 0.01) {
      // Fresh start after preroll (or re-preroll); tiny lead avoids clipping the first sample.
      playTimeRef.current = ctx.currentTime + 0.02;
    }
    const startAt = playTimeRef.current;
    const fade = Math.min(0.008, buffer.duration / 6);
    if (fadeIn) {
      gain.gain.setValueAtTime(0, startAt);
      gain.gain.linearRampToValueAtTime(1, startAt + fade);
    } else {
      gain.gain.setValueAtTime(1, startAt);
    }
    if (fadeOut) {
      const endAt = startAt + buffer.duration;
      gain.gain.setValueAtTime(1, Math.max(startAt, endAt - fade));
      gain.gain.linearRampToValueAtTime(0.0001, endAt);
    }
    source.buffer = buffer;
    source.connect(gain);
    gain.connect(ctx.destination);
    source.start(startAt);
    playTimeRef.current = startAt + buffer.duration;
    activeSourcesRef.current.push(source);
    const becameSpeaking = !speakingRef.current;
    speakingRef.current = true;
    if (becameSpeaking) {
      setSpeaking(true);
      setPlaybackState("playing");
    }
    source.onended = () => {
      activeSourcesRef.current = activeSourcesRef.current.filter((s) => s !== source);
      if (!streamOpenRef.current && !activeSourcesRef.current.length) {
        speakingRef.current = false;
        setSpeaking(false);
        setPlaybackState("idle");
      }
    };
  }

  function flushScheduled(finalFlush: boolean) {
    const ctx = ensurePlayContext();

    // Underrun while stream still open: pause (silence) and re-accumulate a full preroll.
    // Prefer a gap of silence over chopped audio at the start of each resume.
    if (
      playbackStartedRef.current &&
      streamOpenRef.current &&
      playTimeRef.current > 0 &&
      playTimeRef.current < ctx.currentTime + 0.02
    ) {
      playbackStartedRef.current = false;
      playTimeRef.current = 0;
      speakingRef.current = false;
      setSpeaking(false);
      setPlaybackState("buffering");
    }

    if (finalFlush) {
      while (pcmBytesRef.current >= 2) {
        const remaining = pcmBytesRef.current;
        const aligned = takeAlignedPcm(remaining);
        if (!aligned) break;
        const fadeIn = !playbackStartedRef.current;
        playbackStartedRef.current = true;
        schedulePcmSamples(aligned, fadeIn, pcmBytesRef.current < 2);
      }
      return;
    }

    if (!playbackStartedRef.current) {
      // Stay silent until we have a deep enough buffer, then play that block continuously.
      if (pcmBytesRef.current < PREROLL_BYTES) return;
      const aligned = takeAlignedPcm(PREROLL_BYTES);
      if (!aligned) return;
      playbackStartedRef.current = true;
      schedulePcmSamples(aligned, true, false);
    }

    // Keep a healthy lookahead with larger slices so the timeline does not go dry mid-phrase.
    while (
      pcmBytesRef.current >= SLICE_BYTES &&
      queuedAheadSeconds(ctx) * SAMPLE_RATE * 2 < TARGET_AHEAD_BYTES
    ) {
      const aligned = takeAlignedPcm(SLICE_BYTES);
      if (!aligned) break;
      schedulePcmSamples(aligned, false, false);
    }
  }

  function enqueuePcmChunk(pcm: ArrayBuffer, generationId?: string) {
    const gen = generationId || "default";
    if (playGenerationRef.current !== gen) {
      stopActiveSourcesOnly();
      resetPcmBuffer();
      playGenerationRef.current = gen;
      playTimeRef.current = 0;
      playbackStartedRef.current = false;
      streamOpenRef.current = true;
      setPlaybackState("buffering");
    }

    let bytes = new Uint8Array(pcm);
    if (pcmOddRef.current !== null) {
      const bridged = new Uint8Array(bytes.length + 1);
      bridged[0] = pcmOddRef.current;
      bridged.set(bytes, 1);
      bytes = bridged;
      pcmOddRef.current = null;
    }
    if (bytes.length % 2 === 1) {
      pcmOddRef.current = bytes[bytes.length - 1]!;
      bytes = bytes.subarray(0, bytes.length - 1);
    }
    if (!bytes.length) return;

    pcmPartsRef.current.push(bytes.slice());
    pcmBytesRef.current += bytes.length;
    flushScheduled(false);
  }

  function finishPcmStream(interrupted: boolean) {
    streamOpenRef.current = false;
    if (interrupted) {
      stopPlayback();
      setCancelledByInterrupt(true);
      setPlaybackState("cancelled");
      return;
    }
    pcmOddRef.current = null;
    flushScheduled(true);
    playGenerationRef.current = null;
    if (!playbackStartedRef.current && !activeSourcesRef.current.length) {
      speakingRef.current = false;
      setSpeaking(false);
      setPlaybackState("idle");
    }
  }

  function handleWsMessage(msg: MessageEvent) {
    if (typeof msg.data !== "string") {
      // Binary frames unused — PCM arrives as assistant.audio_chunk base64.
      return;
    }
    const data = JSON.parse(msg.data);
    if (data.type === "provider.status") {
      setProvider({
        configured: Boolean(data.configured),
        stt: String(data.stt || "unconfigured"),
        tts: String(data.tts || "unconfigured"),
        language: data.language,
        stt_model: data.stt_model,
        tts_model: data.tts_model,
        language_code: data.language_code,
        audio_format: data.audio_format,
      });
      setConnectionStatus(data.configured ? "connected" : "error");
      if (!data.configured && mode === "voice") {
        setError(
          "ElevenLabs provider not configured. Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID, or use text mode."
        );
      }
    }
    if (data.type === "transcript.partial") {
      setPartialText(String(data.text || ""));
    }
    if (data.type === "transcript.final") {
      setPartialText("");
      setTranscript((prev) => [...prev, { who: "customer", text: data.text }]);
    }
    if (data.type === "assistant.text") {
      setTranscript((prev) => [...prev, { who: "assistant", text: data.text }]);
      setState(data.state);
    }
    if (data.type === "assistant.audio_chunk" && data.data) {
      const binary = atob(data.data);
      const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
      enqueuePcmChunk(
        bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
        String(data.generation_id || "default")
      );
      return;
    }
    if (data.type === "assistant.audio_end") {
      finishPcmStream(Boolean(data.interrupted));
    }
    if (data.type === "error") {
      setError(String(data.message || "Voice error"));
      if (data.code === "provider_not_configured") {
        setConnectionStatus("error");
      }
    }
    if (data.type === "session.ended" && data.disposition) {
      setDisposition(data.disposition);
    }
    // Rely on the 700ms poller during audio chunks; refresh timeline for other events.
    if (sessionId) pollEvents(sessionId).catch(() => undefined);
  }

  function ensureVoiceSocket(id: string, greeting?: string): WebSocket {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      if (greeting) {
        wsRef.current.send(JSON.stringify({ type: "speak_text", text: greeting }));
      }
      return wsRef.current;
    }
    setConnectionStatus("connecting");
    const ws = new WebSocket(`ws://127.0.0.1:8000/v1/sessions/${id}/voice`);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      setConnectionStatus("connected");
      if (greeting) {
        ws.send(JSON.stringify({ type: "speak_text", text: greeting }));
      }
    };
    ws.onerror = () => setConnectionStatus("error");
    ws.onclose = () => setConnectionStatus("idle");
    ws.onmessage = handleWsMessage;
    wsRef.current = ws;
    return ws;
  }

  async function resetDemo() {
    setError(null);
    stopListening();
    stopPlayback();
    wsRef.current?.close();
    wsRef.current = null;
    await api("/v1/admin/reset", { method: "POST" });
    setSessionId(null);
    setState("created");
    setDisposition(null);
    setPolicy("—");
    setTranscript([]);
    setPartialText("");
    setEvents([]);
    setCancelledByInterrupt(false);
    setSttLatency("—");
    setTtsLatency("—");
    seqRef.current = 0;
    await refreshAdmin();
  }

  async function startCall() {
    setError(null);
    setTranscript([]);
    setPartialText("");
    setEvents([]);
    setDisposition(null);
    setCancelledByInterrupt(false);
    seqRef.current = 0;
    const created = await api<{ session_id: string }>("/v1/sessions", {
      method: "POST",
      body: JSON.stringify({
        campaign_id: "campaign-en-001",
        customer_ref: customerRef,
        transport: mode === "voice" ? "browser" : "text",
        language: "ka-GE",
      }),
    });
    setSessionId(created.session_id);
    const started = await api<{ assistant_text: string; state: string }>(
      `/v1/sessions/${created.session_id}/start`,
      { method: "POST" }
    );
    setState(started.state);
    setTranscript([{ who: "assistant", text: started.assistant_text }]);
    await pollEvents(created.session_id);
    if (mode === "voice") {
      ensureVoiceSocket(created.session_id, started.assistant_text);
    }
  }

  async function sendText(text: string) {
    if (!sessionId || !text.trim()) return;
    setError(null);
    stopPlayback();
    setTranscript((prev) => [...prev, { who: "customer", text }]);
    if (mode === "voice" && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({ type: "text.turn", text, client_turn_id: crypto.randomUUID() })
      );
    } else {
      const result = await api<{
        assistant_text: string;
        state: string;
        disposition: string | null;
      }>(`/v1/sessions/${sessionId}/turns`, {
        method: "POST",
        body: JSON.stringify({ text, client_turn_id: crypto.randomUUID() }),
      });
      setState(result.state);
      if (result.assistant_text) {
        setTranscript((prev) => [...prev, { who: "assistant", text: result.assistant_text }]);
      }
      if (result.disposition) setDisposition(result.disposition);
    }
    setInput("");
    await pollEvents(sessionId);
    await refreshAdmin();
  }

  async function injectFailure(modeName: string) {
    await api("/v1/admin/failures", {
      method: "POST",
      body: JSON.stringify({
        mode: modeName,
        scope: sessionId ? "session" : "global",
        session_id: sessionId,
      }),
    });
    await refreshAdmin();
  }

  async function clearFailures() {
    await api("/v1/admin/failures", { method: "DELETE" });
    await refreshAdmin();
  }

  async function startListening() {
    if (!sessionId) return;
    setError(null);
    setCancelledByInterrupt(false);
    stopPlayback();
    const ws = ensureVoiceSocket(sessionId);
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        channelCount: 1,
      },
    });
    mediaStreamRef.current = stream;
    const ctx = new AudioContext();
    audioCtxRef.current = ctx;
    const source = ctx.createMediaStreamSource(stream);
    const processor = ctx.createScriptProcessor(4096, 1, 1);
    processorRef.current = processor;
    // Mute monitoring path — connecting to destination causes feedback and
    // confuses barge-in / STT with speaker bleed.
    const mute = ctx.createGain();
    mute.gain.value = 0;
    processor.onaudioprocess = (ev) => {
      if (speakingRef.current || streamOpenRef.current) return;
      const inputData = ev.inputBuffer.getChannelData(0);
      const down = downsampleBuffer(inputData, ctx.sampleRate, SAMPLE_RATE);
      const pcm = floatTo16BitPCM(down);
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(pcm);
      }
    };
    source.connect(processor);
    processor.connect(mute);
    mute.connect(ctx.destination);
    const arm = () => ws.send(JSON.stringify({ type: "media.start" }));
    if (ws.readyState === WebSocket.OPEN) arm();
    else ws.addEventListener("open", arm, { once: true });
    setListening(true);
  }

  function stopListening() {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "media.stop" }));
    }
    processorRef.current?.disconnect();
    processorRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    mediaStreamRef.current = null;
    audioCtxRef.current?.close().catch(() => undefined);
    audioCtxRef.current = null;
    setListening(false);
  }

  function interrupt() {
    stopPlayback();
    setCancelledByInterrupt(true);
    wsRef.current?.send(JSON.stringify({ type: "user.interrupt" }));
  }

  function buildConversationExport(): string {
    const lines: string[] = [
      "TBC Voice Agent — Georgian /ka conversation export",
      `Customer: ${customerRef}`,
      `Mode: ${mode}`,
      `Session: ${sessionId ?? "none"}`,
      `State: ${state}`,
      `Policy: ${policy}`,
      `Disposition: ${disposition ?? "none"}`,
      `Active failures: ${Object.keys(failures).length ? JSON.stringify(failures) : "none"}`,
      `Provider: ${provider ? `${provider.stt}/${provider.tts} (${provider.audio_format ?? "?"})` : "none"}`,
      "",
      "## Transcript",
    ];
    if (!transcript.length) {
      lines.push("(empty)");
    } else {
      for (const item of transcript) {
        lines.push(`${item.who}: ${item.text}`);
      }
    }
    lines.push("", "## Recent timeline (last 30 events)");
    const recent = events.slice(-30);
    if (!recent.length) {
      lines.push("(empty)");
    } else {
      for (const event of recent) {
        lines.push(
          `#${event.sequence} ${event.type} · ${event.source} · ${JSON.stringify(event.payload)}`
        );
      }
    }
    return lines.join("\n");
  }

  async function copyConversation() {
    const text = buildConversationExport();
    try {
      await navigator.clipboard.writeText(text);
      setCopyStatus("Copied — paste into chat");
    } catch {
      const area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.left = "-9999px";
      document.body.appendChild(area);
      area.select();
      try {
        document.execCommand("copy");
        setCopyStatus("Copied — paste into chat");
      } catch {
        setCopyStatus("Copy failed — select text manually");
        setError(text);
      }
      document.body.removeChild(area);
    }
    window.setTimeout(() => setCopyStatus(null), 2500);
  }

  return (
    <div className="app">
      <header className="hero">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h1>TBC Voice Agent — ქართული (/ka)</h1>
          <a className="pill" href="/">
            English console →
          </a>
        </div>
        <p>
          Isolated Georgian demo with ElevenLabs streaming STT/TTS. Same orchestrator and policy as
          English. Synthetic content only — not production Georgian readiness.
        </p>
        <div className="row">
          <span className="pill">API health: {health}</span>
          <span className={`pill ${connectionStatus === "connected" ? "active" : ""}`}>
            voice WS: {connectionStatus}
          </span>
          <span className={`pill ${Object.keys(failures).length ? "active" : ""}`}>
            failures: {Object.keys(failures).length ? JSON.stringify(failures) : "none"}
          </span>
        </div>
      </header>

      <div className="grid">
        <section className="panel">
          <h2>Call controls</h2>
          <div className="meta">
            <div>
              <strong>STT</strong>
              {provider?.stt ?? "—"}
              {provider?.stt_model ? ` · ${provider.stt_model}` : ""}
            </div>
            <div>
              <strong>TTS</strong>
              {provider?.tts ?? "—"}
              {provider?.tts_model ? ` · ${provider.tts_model}` : ""}
            </div>
            <div>
              <strong>Language</strong>
              {provider?.language_code ?? "kat"} / ka-GE
            </div>
            <div>
              <strong>Format</strong>
              {provider?.audio_format ?? "pcm_16000"}
            </div>
            <div>
              <strong>Configured</strong>
              {provider?.configured ? "yes" : "no (text mode still works)"}
            </div>
            <div>
              <strong>STT latency</strong>
              {sttLatency}
            </div>
            <div>
              <strong>TTS TTFB</strong>
              {ttsLatency}
            </div>
            <div>
              <strong>Playback</strong>
              {playbackState}
              {cancelledByInterrupt ? " · interrupted" : ""}
            </div>
          </div>
          <div className="row">
            <label>
              Synthetic customer
              <select value={customerRef} onChange={(e) => setCustomerRef(e.target.value)}>
                {CUSTOMERS.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Mode
              <select value={mode} onChange={(e) => setMode(e.target.value as "text" | "voice")}>
                <option value="text">Text</option>
                <option value="voice">Voice (ElevenLabs)</option>
              </select>
            </label>
          </div>
          <div className="row">
            <button className="primary" onClick={() => startCall().catch((e) => setError(String(e)))}>
              Start call
            </button>
            <button className="danger" onClick={() => resetDemo().catch((e) => setError(String(e)))}>
              Reset demo
            </button>
            <button disabled={!speaking} onClick={stopPlayback}>
              Stop speaking
            </button>
          </div>
          <div className="meta">
            <div>
              <strong>Session</strong>
              {sessionId ?? "—"}
            </div>
            <div>
              <strong>State</strong>
              {state}
            </div>
            <div>
              <strong>Policy</strong>
              {policy}
            </div>
            <div>
              <strong>Disposition</strong>
              {disposition ?? "—"}
            </div>
            <div>
              <strong>Integration</strong>
              {latestLatency}
            </div>
          </div>

          <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ margin: 0 }}>Conversation</h3>
            <div className="row">
              <button
                disabled={!transcript.length && !events.length}
                onClick={() => copyConversation().catch((e) => setError(String(e)))}
              >
                Copy conversation
              </button>
              {copyStatus && <span className="pill">{copyStatus}</span>}
            </div>
          </div>
          <div className="transcript">
            {transcript.map((item, idx) => (
              <div key={idx} className={`bubble ${item.who}`}>
                <div className="who">{item.who}</div>
                <div dangerouslySetInnerHTML={{ __html: escapeText(item.text) }} />
              </div>
            ))}
            {partialText && (
              <div className="bubble partial">
                <div className="who">partial</div>
                <div dangerouslySetInnerHTML={{ __html: escapeText(partialText) }} />
              </div>
            )}
          </div>

          {mode === "text" ? (
            <div className="row">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="აკრიფეთ მომხმარებლის პასუხი (ქართული ან ინგლისური)"
                style={{ flex: 1 }}
              />
              <button
                className="primary"
                disabled={!sessionId}
                onClick={() => sendText(input).catch((e) => setError(String(e)))}
              >
                Send
              </button>
            </div>
          ) : (
            <>
              <div className="row">
                <button
                  disabled={!sessionId || listening}
                  onClick={() => startListening().catch((e) => setError(String(e)))}
                >
                  Hold to talk (start mic)
                </button>
                <button disabled={!listening} onClick={stopListening}>
                  Stop mic & send
                </button>
                <button disabled={!sessionId} onClick={interrupt}>
                  Interrupt
                </button>
              </div>
              <p style={{ margin: 0, color: "var(--muted)", fontSize: "0.85rem" }}>
                Push-to-talk: start mic, speak, then Stop mic & send. Partials update live; the turn
                commits when you stop.
              </p>
            </>
          )}
          {error && <p style={{ color: "var(--danger)", margin: 0 }}>{error}</p>}
        </section>

        <section className="panel">
          <h2>Operator timeline</h2>
          <div className="row">
            {FAILURES.map((f) => (
              <button key={f} onClick={() => injectFailure(f).catch((e) => setError(String(e)))}>
                {f}
              </button>
            ))}
            <button onClick={() => clearFailures().catch((e) => setError(String(e)))}>
              Clear failures
            </button>
          </div>
          <div className="timeline">
            {events.map((event) => (
              <div key={event.event_id} className="event">
                #{event.sequence} {event.type} · {event.source}
                <pre style={{ margin: "0.25rem 0 0", whiteSpace: "pre-wrap" }}>
                  {JSON.stringify(event.payload)}
                </pre>
              </div>
            ))}
          </div>
          <h3>Mock human transfers</h3>
          <pre
            style={{ margin: 0, whiteSpace: "pre-wrap", fontFamily: "var(--mono)", fontSize: "0.8rem" }}
          >
            {JSON.stringify(transfers, null, 2)}
          </pre>
        </section>
      </div>
    </div>
  );
}
