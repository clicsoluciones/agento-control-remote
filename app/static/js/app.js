// agento-control-remote PWA controller
let ws = null;
let isRecording = false;
let wantRecording = false;
let audioCtx = null;
let scriptNode = null;
let mediaStream = null;
let lastAssistantText = "";

// DOM Elements
const badgeRobot = document.getElementById("badge-robot");
const badgeCloud = document.getElementById("badge-cloud");
const muteToggle = document.getElementById("mute-toggle");
const muteLabel = document.getElementById("mute-label");
const btnPtt = document.getElementById("btn-ptt");
const btnStop = document.getElementById("btn-stop");
const pttText = document.getElementById("ptt-text");
const transcriptFeed = document.getElementById("transcript-feed");
const emotionButtons = document.querySelectorAll(".btn-emotion");

// Initialize WebSocket Connection
function connectWS() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/remote`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("Connected to agento-control-remote gateway");
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleServerMessage(msg);
    } catch (err) {
      console.warn("Non-JSON message received:", event.data);
    }
  };

  ws.onclose = () => {
    badgeRobot.className = "badge off";
    badgeCloud.className = "badge off";
    setTimeout(connectWS, 2000);
  };

  ws.onerror = (err) => {
    console.error("WebSocket error:", err);
  };
}

function handleServerMessage(msg) {
  if (msg.type === "status") {
    updateUIStatus(msg.data);
  } else if (msg.type === "state_update") {
    if (msg.status) {
      updateUIStatus(msg.status);
    }
  } else if (msg.type === "speech_stopped") {
    lastAssistantText = "";
    transcriptFeed.innerHTML = `<span class="placeholder">⏹️ ${msg.message || "Respuesta detenida por el operador"}. Listo para hablar.</span>`;
  } else if (msg.type === "cloud_event") {
    handleCloudEvent(msg.payload);
  }
}

function updateUIStatus(status) {
  if (!status) return;

  if (status.robot_connected) {
    badgeRobot.className = "badge on";
    badgeRobot.textContent = "Robot OK";
  } else {
    badgeRobot.className = "badge off";
    badgeRobot.textContent = "Robot OFF";
  }

  if (status.upstream_connected) {
    badgeCloud.className = "badge on";
    badgeCloud.textContent = "xiaozhi.me OK";
  } else {
    badgeCloud.className = "badge off";
    badgeCloud.textContent = "xiaozhi.me ESPERA";
  }

  if (status.robot_mic_muted !== undefined) {
    muteToggle.checked = status.robot_mic_muted;
    if (status.robot_mic_muted) {
      muteLabel.className = "toggle-status active";
      muteLabel.textContent = "Mic Robot: SILENCIADO";
    } else {
      muteLabel.className = "toggle-status inactive";
      muteLabel.textContent = "Mic Robot: ACTIVO";
    }
  }

  if (status.current_emotion) {
    emotionButtons.forEach((btn) => {
      if (btn.dataset.emotion === status.current_emotion) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
  }
}

function handleCloudEvent(payload) {
  if (!payload) return;

  if (payload.type === "stt" && payload.text) {
    lastAssistantText = "";
    transcriptFeed.innerHTML = `<span class="text-speaking">🎙️ Escuchado: "${payload.text}"</span>`;
  } else if (payload.type === "tts" && payload.state === "start") {
    lastAssistantText = "";
    transcriptFeed.innerHTML = `<span class="text-speaking">🗣️ El robot está respondiendo...</span>`;
  } else if (payload.type === "tts" && payload.state === "sentence_start" && payload.text) {
    lastAssistantText = (lastAssistantText ? lastAssistantText + " " : "") + payload.text;
    transcriptFeed.innerHTML = `<span class="text-speaking">🤖 ${lastAssistantText}</span>`;
  } else if (payload.type === "tts" && payload.state === "stop") {
    if (lastAssistantText) {
      transcriptFeed.innerHTML = `<span class="text-speaking">🤖 ${lastAssistantText}</span>`;
    } else {
      transcriptFeed.innerHTML = `<span class="placeholder">Listo para la siguiente frase. Mantén presionado para hablar.</span>`;
    }
  } else if (payload.type === "llm" && payload.emotion) {
    emotionButtons.forEach((btn) => {
      if (btn.dataset.emotion === payload.emotion) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
  }
}

// Emotion Button Handlers
emotionButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    const emotion = btn.dataset.emotion;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "set_emotion",
        emotion: emotion
      }));
    }
    emotionButtons.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
  });
});

// Mute Toggle Handler
muteToggle.addEventListener("change", () => {
  const isMuted = muteToggle.checked;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: "set_mic_muted",
      muted: isMuted
    }));
  }
  if (isMuted) {
    muteLabel.className = "toggle-status active";
    muteLabel.textContent = "Mic Robot: SILENCIADO";
  } else {
    muteLabel.className = "toggle-status inactive";
    muteLabel.textContent = "Mic Robot: ACTIVO";
  }
});

function downsampleTo16k(float32Input, inputSampleRate) {
  if (inputSampleRate === 16000) {
    return float32Input;
  }
  const ratio = inputSampleRate / 16000;
  const newLength = Math.round(float32Input.length / ratio);
  const result = new Float32Array(newLength);
  for (let i = 0; i < newLength; i++) {
    const idx = Math.min(float32Input.length - 1, Math.floor(i * ratio));
    result[i] = float32Input[idx];
  }
  return result;
}

// Push-To-Talk (Walkie-Talkie) Handlers using Web Audio API PCM
async function startRecording() {
  if (isRecording) return;
  wantRecording = true;

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    wantRecording = false;
    transcriptFeed.innerHTML = `<span style="color: #ff1744; font-weight: bold; font-size: 0.8rem;">⚠️ El navegador requiere HTTPS para el micrófono.<br>Ingresá por: <u>https://${window.location.hostname}:8443/</u></span>`;
    return;
  }

  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 16000,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    });

    if (!wantRecording) {
      mediaStream.getTracks().forEach((track) => track.stop());
      mediaStream = null;
      return;
    }

    audioCtx = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: 16000
    });
    const actualSampleRate = audioCtx.sampleRate || 16000;
    const source = audioCtx.createMediaStreamSource(mediaStream);

    isRecording = true;
    btnPtt.classList.add("recording");
    pttText.textContent = "HABLANDO...";
    transcriptFeed.innerHTML = `<span class="text-speaking">🎙️ Transmitiendo voz limpia al robot...</span>`;

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ptt_start" }));
    }

    scriptNode = audioCtx.createScriptProcessor(2048, 1, 1);
    scriptNode.onaudioprocess = (e) => {
      if (!isRecording) return;
      const rawInput = e.inputBuffer.getChannelData(0);
      const input = downsampleTo16k(rawInput, actualSampleRate);
      const pcm16 = new Int16Array(input.length);
      for (let i = 0; i < input.length; i++) {
        const s = Math.max(-1, Math.min(1, input[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(pcm16.buffer);
      }
    };

    source.connect(scriptNode);
    scriptNode.connect(audioCtx.destination);
  } catch (err) {
    console.error("Microphone error:", err);
    transcriptFeed.innerHTML = `<span style="color: #ff1744;">Error de micrófono: ${err.message}</span>`;
    stopRecording();
  }
}

function stopRecording() {
  wantRecording = false;
  if (!isRecording) return;
  isRecording = false;
  btnPtt.classList.remove("recording");
  pttText.textContent = "MANTENER PARA HABLAR";
  transcriptFeed.innerHTML = `<span class="placeholder">Procesando voz en xiaozhi.me...</span>`;

  if (scriptNode) {
    scriptNode.disconnect();
    scriptNode = null;
  }
  if (audioCtx && audioCtx.state !== "closed") {
    audioCtx.close();
    audioCtx = null;
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "ptt_stop" }));
  }
}

// Pointer events support mobile touch and desktop mouse seamlessly
btnPtt.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  startRecording();
});

window.addEventListener("pointerup", () => {
  if (wantRecording || isRecording) {
    stopRecording();
  }
});

btnPtt.addEventListener("pointercancel", () => {
  if (wantRecording || isRecording) {
    stopRecording();
  }
});

// Stop / Interruption Handler
function triggerStopSpeech() {
  lastAssistantText = "";
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "stop_speech" }));
  } else {
    fetch("/api/robot/stop", { method: "POST" }).catch(() => {});
  }
  if (btnStop) {
    btnStop.classList.add("active-stop");
    setTimeout(() => btnStop.classList.remove("active-stop"), 350);
  }
  transcriptFeed.innerHTML = `<span class="placeholder">⏹️ Respuesta detenida. Listo para hablar.</span>`;
}

if (btnStop) {
  btnStop.addEventListener("click", (e) => {
    e.preventDefault();
    triggerStopSpeech();
  });
}

// Start WebSocket connection on load
connectWS();
