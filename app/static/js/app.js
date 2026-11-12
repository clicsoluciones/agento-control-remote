// agento-control-remote PWA controller
let ws = null;
let mediaRecorder = null;
let audioStream = null;
let isRecording = false;

// DOM Elements
const badgeRobot = document.getElementById("badge-robot");
const badgeCloud = document.getElementById("badge-cloud");
const muteToggle = document.getElementById("mute-toggle");
const muteLabel = document.getElementById("mute-label");
const btnPtt = document.getElementById("btn-ptt");
const pttText = document.getElementById("ptt-text");
const transcriptFeed = document.getElementById("transcript-feed");
const emotionButtons = document.querySelectorAll(".btn-emotion");

// Initialize WebSocket Connection
function connectWS() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/remote`;
  
  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("Conectado al Gateway agento-control-remote");
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleServerMessage(msg);
    } catch (err) {
      console.warn("Mensaje no-JSON recibido:", event.data);
    }
  };

  ws.onclose = () => {
    console.log("Desconectado del Gateway. Reintentando en 2s...");
    badgeRobot.className = "badge off";
    badgeCloud.className = "badge off";
    setTimeout(connectWS, 2000);
  };

  ws.onerror = (err) => {
    console.error("Error en WebSocket:", err);
  };
}

function handleServerMessage(msg) {
  if (msg.type === "status") {
    updateUIStatus(msg.data);
  } else if (msg.type === "state_update") {
    if (msg.status) {
      updateUIStatus(msg.status);
    }
  } else if (msg.type === "cloud_event") {
    handleCloudEvent(msg.payload);
  }
}

function updateUIStatus(status) {
  if (!status) return;

  // Update robot badge
  if (status.robot_connected) {
    badgeRobot.className = "badge on";
    badgeRobot.textContent = "Robot OK";
  } else {
    badgeRobot.className = "badge off";
    badgeRobot.textContent = "Robot OFF";
  }

  // Update cloud badge
  if (status.upstream_connected) {
    badgeCloud.className = "badge on";
    badgeCloud.textContent = "xiaozhi.me OK";
  } else {
    badgeCloud.className = "badge off";
    badgeCloud.textContent = "xiaozhi.me ESPERA";
  }

  // Update mic mute toggle
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

  // Update active emotion button
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

  if (payload.type === "tts" && payload.state === "start") {
    transcriptFeed.innerHTML = `<span class="text-speaking">🗣️ El robot está respondiendo por su altavoz...</span>`;
  } else if (payload.type === "tts" && payload.state === "stop") {
    transcriptFeed.innerHTML = `<span class="placeholder">Listo para la siguiente frase. Mantén presionado para hablar.</span>`;
  } else if (payload.type === "llm" && payload.text) {
    transcriptFeed.innerHTML = `<span class="text-speaking">${payload.text}</span>`;
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

// Push-To-Talk (Walkie-Talkie) Handlers
async function startRecording() {
  if (isRecording) return;
  try {
    if (!audioStream) {
      audioStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
    }

    isRecording = true;
    btnPtt.classList.add("recording");
    pttText.textContent = "HABLANDO...";
    transcriptFeed.innerHTML = `<span class="text-speaking">🎙️ Grabando voz limpia del teléfono...</span>`;

    // Notify Gateway that PTT started
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ptt_start" }));
    }

    // Use MediaRecorder to stream opus chunks
    let mimeType = "audio/webm;codecs=opus";
    if (!MediaRecorder.isTypeSupported(mimeType)) {
      mimeType = "audio/ogg;codecs=opus";
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        mimeType = "";
      }
    }

    const options = mimeType ? { mimeType } : {};
    mediaRecorder = new MediaRecorder(audioStream, options);

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0 && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(e.data);
      }
    };

    // Request chunks every 60ms for low-latency streaming
    mediaRecorder.start(60);

  } catch (err) {
    console.error("Error al acceder al micrófono:", err);
    transcriptFeed.innerHTML = `<span style="color: #ff1744;">Error al activar micrófono: ${err.message}</span>`;
    stopRecording();
  }
}

function stopRecording() {
  if (!isRecording) return;
  isRecording = false;
  btnPtt.classList.remove("recording");
  pttText.textContent = "MANTENER PARA HABLAR";
  transcriptFeed.innerHTML = `<span class="placeholder">Enviando a xiaozhi.me... Generando respuesta...</span>`;

  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }

  // Notify Gateway that PTT stopped
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "ptt_stop" }));
  }
}

// Pointer events support mobile touch and desktop mouse seamlessly
btnPtt.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  startRecording();
});

window.addEventListener("pointerup", (e) => {
  if (isRecording) {
    stopRecording();
  }
});

btnPtt.addEventListener("pointercancel", (e) => {
  if (isRecording) {
    stopRecording();
  }
});

// Start WebSocket connection on load
connectWS();
