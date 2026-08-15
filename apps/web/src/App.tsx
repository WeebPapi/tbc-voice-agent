import { useEffect, useMemo, useRef, useState } from "react";

type EventItem = {
  event_id: string;
  sequence: number;
  type: string;
  source: string;
  payload: Record<string, unknown>;
};

type TranscriptItem = { who: "customer" | "assistant"; text: string };

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

export default function App() {
  const [customerRef, setCustomerRef] = useState("cust-001");
  const [mode, setMode] = useState<"text" | "voice">("text");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [state, setState] = useState("created");
  const [disposition, setDisposition] = useState<string | null>(null);
  const [policy, setPolicy] = useState<string>("—");
  const [input, setInput] = useState("");
  const [transcript, setTranscript] = useState<TranscriptItem[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [failures, setFailures] = useState<Record<string, string>>({});
  const [transfers, setTransfers] = useState<unknown[]>([]);
  const [health, setHealth] = useState("unknown");
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [speakEnabled, setSpeakEnabled] = useState(true);
  const [speaking, setSpeaking] = useState(false);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const seqRef = useRef(0);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

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
    }
  }

  useEffect(() => {
    api<{ status: string }>("/health")
      .then((h) => setHealth(h.status))
      .catch(() => setHealth("down"));
    refreshAdmin().catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    const timer = setInterval(() => {
      pollEvents(sessionId).catch(() => undefined);
    }, 700);
    return () => clearInterval(timer);
  }, [sessionId]);

  function stopSpeaking() {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    setSpeaking(false);
  }

  function speakWithBrowser(text: string) {
    if (!window.speechSynthesis) return;
    stopSpeaking();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "en-US";
    utter.rate = 1;
    utter.onend = () => setSpeaking(false);
    utter.onerror = () => setSpeaking(false);
    setSpeaking(true);
    window.speechSynthesis.speak(utter);
  }

  async function speakAssistant(session: string, text: string) {
    if (!speakEnabled || !text.trim()) return;
    stopSpeaking();
    try {
      const res = await fetch(`${API}/v1/sessions/${session}/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (res.status === 204 || !res.ok) {
        speakWithBrowser(text);
        return;
      }
      const blob = await res.blob();
      if (!blob.size) {
        speakWithBrowser(text);
        return;
      }
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;
      setSpeaking(true);
      audio.onended = () => {
        setSpeaking(false);
        URL.revokeObjectURL(url);
      };
      audio.onerror = () => {
        setSpeaking(false);
        URL.revokeObjectURL(url);
        speakWithBrowser(text);
      };
      await audio.play();
    } catch {
      speakWithBrowser(text);
    }
  }

  async function resetDemo() {
    setError(null);
    stopSpeaking();
    await api("/v1/admin/reset", { method: "POST" });
    setSessionId(null);
    setState("created");
    setDisposition(null);
    setPolicy("—");
    setTranscript([]);
    setEvents([]);
    seqRef.current = 0;
    await refreshAdmin();
  }

  async function startCall() {
    setError(null);
    setTranscript([]);
    setEvents([]);
    setDisposition(null);
    seqRef.current = 0;
    const created = await api<{ session_id: string }>("/v1/sessions", {
      method: "POST",
      body: JSON.stringify({
        campaign_id: "campaign-en-001",
        customer_ref: customerRef,
        transport: mode,
        language: "en-US",
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
    await speakAssistant(created.session_id, started.assistant_text);
  }

  async function sendText(text: string) {
    if (!sessionId || !text.trim()) return;
    setError(null);
    stopSpeaking();
    setTranscript((prev) => [...prev, { who: "customer", text }]);
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
      await speakAssistant(sessionId, result.assistant_text);
    }
    if (result.disposition) setDisposition(result.disposition);
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

  async function startVoice() {
    if (!sessionId) return;
    setError(null);
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    chunksRef.current = [];
    recorder.ondataavailable = (ev) => {
      if (ev.data.size) chunksRef.current.push(ev.data);
    };
    recorder.onstop = async () => {
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      const buffer = await blob.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      let binary = "";
      bytes.forEach((b) => {
        binary += String.fromCharCode(b);
      });
      const b64 = btoa(binary);
      const ws =
        wsRef.current ||
        new WebSocket(`ws://127.0.0.1:8000/v1/sessions/${sessionId}/stream`);
      wsRef.current = ws;
      const send = () => {
        ws.send(JSON.stringify({ type: "media.start" }));
        ws.send(JSON.stringify({ type: "media.chunk", data: b64 }));
        ws.send(JSON.stringify({ type: "media.stop" }));
      };
      if (ws.readyState === WebSocket.OPEN) send();
      else ws.onopen = send;
      ws.onmessage = async (msg) => {
        // Binary TTS frames are ignored here; we play via /speak for consistent mp3 audio.
        if (typeof msg.data !== "string") {
          return;
        }
        const data = JSON.parse(msg.data);
        if (data.type === "transcript.final") {
          setTranscript((prev) => [...prev, { who: "customer", text: data.text }]);
        }
        if (data.type === "error") {
          setError(String(data.message || "Voice error"));
        }
        if (data.type === "assistant.text") {
          setTranscript((prev) => [...prev, { who: "assistant", text: data.text }]);
          setState(data.state);
          if (sessionId) {
            speakAssistant(sessionId, data.text).catch(() => undefined);
          }
        }
        if (data.type === "session.ended" && data.disposition) {
          setDisposition(data.disposition);
        }
        if (sessionId) await pollEvents(sessionId);
      };
      stream.getTracks().forEach((t) => t.stop());
      setRecording(false);
    };
    mediaRef.current = recorder;
    recorder.start();
    setRecording(true);
  }

  function stopVoice() {
    mediaRef.current?.stop();
  }

  function interrupt() {
    stopSpeaking();
    wsRef.current?.send(JSON.stringify({ type: "user.interrupt" }));
  }

  function buildConversationExport(): string {
    const lines: string[] = [
      "TBC Voice Agent — conversation export",
      `Customer: ${customerRef}`,
      `Mode: ${mode}`,
      `Session: ${sessionId ?? "none"}`,
      `State: ${state}`,
      `Policy: ${policy}`,
      `Disposition: ${disposition ?? "none"}`,
      `Active failures: ${Object.keys(failures).length ? JSON.stringify(failures) : "none"}`,
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
      // Fallback for older / restricted clipboard contexts
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
          <h1>TBC Voice Agent</h1>
          <a className="pill" href="/ka">
            Georgian /ka →
          </a>
        </div>
        <p>
          Local synthetic outbound collections demo. Identity is verified before any account
          disclosure. Text mode works without provider credentials.
        </p>
        <div className="row">
          <span className="pill">API health: {health}</span>
          <span className={`pill ${Object.keys(failures).length ? "active" : ""}`}>
            failures: {Object.keys(failures).length ? JSON.stringify(failures) : "none"}
          </span>
        </div>
      </header>

      <div className="grid">
        <section className="panel">
          <h2>Call controls</h2>
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
                <option value="voice">Voice</option>
              </select>
            </label>
            <label>
              Assistant speech
              <select
                value={speakEnabled ? "on" : "off"}
                onChange={(e) => {
                  const on = e.target.value === "on";
                  setSpeakEnabled(on);
                  if (!on) stopSpeaking();
                }}
              >
                <option value="on">On (TTS)</option>
                <option value="off">Off</option>
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
            <button disabled={!speaking} onClick={stopSpeaking}>
              Stop speaking
            </button>
          </div>
          <div className="row">
            <span className={`pill ${speaking ? "active" : ""}`}>
              {speaking ? "assistant speaking…" : "assistant idle"}
            </span>
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
          </div>

          {mode === "text" ? (
            <div className="row">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Type the customer reply"
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
            <div className="row">
              <button disabled={!sessionId || recording} onClick={() => startVoice().catch((e) => setError(String(e)))}>
                Record
              </button>
              <button disabled={!recording} onClick={stopVoice}>
                Stop & send
              </button>
              <button disabled={!sessionId} onClick={interrupt}>
                Interrupt
              </button>
            </div>
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
          <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontFamily: "var(--mono)", fontSize: "0.8rem" }}>
            {JSON.stringify(transfers, null, 2)}
          </pre>
        </section>
      </div>
    </div>
  );
}
