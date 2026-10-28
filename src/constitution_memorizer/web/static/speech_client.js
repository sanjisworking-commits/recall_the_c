/* Microphone capture + unit-scoped transcription. No expected words, no aligner. */
(function (global) {
  function preferredMime() {
    if (!global.MediaRecorder) {
      return "";
    }
    const types = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
    for (let i = 0; i < types.length; i += 1) {
      if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(types[i])) {
        return types[i];
      }
    }
    return "";
  }

  const SpeechClient = {
    isSupported() {
      return !!(
        navigator.mediaDevices &&
        navigator.mediaDevices.getUserMedia &&
        global.MediaRecorder
      );
    },

    async startRecording() {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = preferredMime();
      const recorder = mime
        ? new MediaRecorder(stream, { mimeType: mime })
        : new MediaRecorder(stream);
      const chunks = [];
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size) {
          chunks.push(event.data);
        }
      });
      recorder.start();
      let stopped = false;
      function stopTracks() {
        stream.getTracks().forEach((track) => {
          try {
            track.stop();
          } catch (_err) {
            /* ignore */
          }
        });
      }
      return {
        mimeType: recorder.mimeType || mime || "audio/webm",
        stop() {
          if (stopped) {
            return Promise.resolve(new Blob([], { type: recorder.mimeType || "audio/webm" }));
          }
          stopped = true;
          return new Promise((resolve, reject) => {
            recorder.addEventListener(
              "stop",
              () => {
                stopTracks();
                resolve(
                  new Blob(chunks, {
                    type: recorder.mimeType || mime || "audio/webm",
                  }),
                );
              },
              { once: true },
            );
            recorder.addEventListener(
              "error",
              () => {
                stopTracks();
                reject(new Error("recorder-error"));
              },
              { once: true },
            );
            if (recorder.state !== "inactive") {
              try {
                recorder.stop();
              } catch (_err) {
                stopTracks();
                resolve(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
              }
            } else {
              stopTracks();
              resolve(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
            }
          });
        },
        cancel() {
          stopped = true;
          try {
            if (recorder.state !== "inactive") {
              recorder.stop();
            }
          } catch (_err) {
            /* ignore */
          }
          stopTracks();
        },
      };
    },

    /*
     * Live word-by-word recognition. Streams MediaRecorder chunks over a
     * WebSocket; the server relays to the speech provider and pushes
     * alignment frames back while the user is still speaking.
     *
     * Resolves to a handle {stop(), cancel()} once the server says "ready".
     * Rejects (after releasing the mic) if the socket or provider fails to
     * start, so callers can fall back to the record-then-check flow.
     */
    async startLive(options) {
      if (!this.isSupported() || !global.WebSocket) {
        const err = new Error("live-unsupported");
        err.code = "unsupported";
        throw err;
      }
      const unitId = options.unitId || "";
      const fromIndex = typeof options.fromIndex === "number" ? options.fromIndex : 0;
      const onUpdate = options.onUpdate || function () {};
      const onEnd = options.onEnd || function () {};

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      function stopTracks() {
        stream.getTracks().forEach((track) => {
          try {
            track.stop();
          } catch (_err) {
            /* ignore */
          }
        });
      }

      const scheme = global.location.protocol === "https:" ? "wss://" : "ws://";
      const url =
        scheme +
        global.location.host +
        "/learn/" +
        encodeURIComponent(unitId) +
        "/speech/live?mode=letters&from_index=" +
        encodeURIComponent(String(fromIndex));

      return new Promise((resolve, reject) => {
        let ws;
        try {
          ws = new WebSocket(url);
        } catch (err) {
          stopTracks();
          reject(err);
          return;
        }
        ws.binaryType = "arraybuffer";
        let recorder = null;
        let settled = false;
        let ended = false;

        function cleanup() {
          if (recorder && recorder.state !== "inactive") {
            try {
              recorder.stop();
            } catch (_err) {
              /* ignore */
            }
          }
          recorder = null;
          stopTracks();
        }

        function finish(code) {
          if (ended) {
            return;
          }
          ended = true;
          cleanup();
          try {
            ws.close();
          } catch (_err) {
            /* ignore */
          }
          onEnd(code || null);
        }

        ws.addEventListener("message", (event) => {
          let payload;
          try {
            payload = JSON.parse(event.data);
          } catch (_err) {
            return;
          }
          if (payload.type === "ready") {
            const mime = preferredMime();
            try {
              recorder = mime
                ? new MediaRecorder(stream, { mimeType: mime })
                : new MediaRecorder(stream);
            } catch (err) {
              settled = true;
              finish("recorder-error");
              reject(err);
              return;
            }
            recorder.addEventListener("dataavailable", (evt) => {
              if (evt.data && evt.data.size && ws.readyState === WebSocket.OPEN) {
                evt.data.arrayBuffer().then((buf) => {
                  if (ws.readyState === WebSocket.OPEN) {
                    ws.send(buf);
                  }
                });
              }
            });
            recorder.start(250);
            settled = true;
            resolve({
              stop() {
                if (recorder && recorder.state !== "inactive") {
                  try {
                    recorder.requestData();
                    recorder.stop();
                  } catch (_err) {
                    /* ignore */
                  }
                }
                stopTracks();
                // Give the last chunk a beat to flush before CloseStream.
                setTimeout(() => {
                  if (ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: "stop" }));
                  }
                }, 120);
              },
              cancel() {
                finish("cancelled");
              },
            });
          } else if (payload.type === "alignment") {
            onUpdate(payload);
          } else if (payload.type === "done") {
            finish(null);
          } else if (payload.type === "error") {
            const code = payload.error || "provider_error";
            if (!settled) {
              settled = true;
              cleanup();
              const err = new Error("live-failed");
              err.code = code;
              reject(err);
            } else {
              finish(code);
            }
          }
        });
        ws.addEventListener("error", () => {
          if (!settled) {
            settled = true;
            cleanup();
            const err = new Error("live-failed");
            err.code = "socket";
            reject(err);
          } else {
            finish("socket");
          }
        });
        ws.addEventListener("close", () => {
          if (!settled) {
            settled = true;
            cleanup();
            const err = new Error("live-failed");
            err.code = "socket";
            reject(err);
          } else {
            finish(null);
          }
        });
      });
    },

    async transcribe(options) {
      const unitId = options.unitId || "";
      const body = new FormData();
      body.append("mode", options.mode || "letters");
      if (typeof options.fromIndex === "number") {
        body.append("from_index", String(options.fromIndex));
      }
      if (options.text) {
        body.append("text", options.text);
      }
      if (options.csrf) {
        body.append("csrf_token", options.csrf);
      }
      if (options.blob && options.blob.size) {
        const type = options.blob.type || "audio/webm";
        const name = type.indexOf("mp4") >= 0 ? "utterance.mp4" : "utterance.webm";
        body.append("audio", options.blob, name);
      }
      const headers = {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
      };
      if (options.csrf) {
        headers["X-CSRF-Token"] = options.csrf;
      }
      const endpoint =
        options.url ||
        "/learn/" + encodeURIComponent(unitId) + "/speech/transcribe";
      const response = await fetch(endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers,
        body,
        signal: options.signal,
      });
      const contentType = response.headers.get("content-type") || "";
      if (!contentType.includes("application/json")) {
        const error = new Error("speech-failed");
        error.code = "provider_error";
        error.status = response.status;
        throw error;
      }
      const payload = await response.json();
      if (!response.ok || !payload || payload.ok !== true) {
        const error = new Error("speech-failed");
        error.code = (payload && payload.error) || "provider_error";
        error.status = response.status;
        throw error;
      }
      return payload;
    },
  };

  global.RecallSpeech = SpeechClient;
})(window);
