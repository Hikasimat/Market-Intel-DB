import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import api from '../services/api';
import {
  Phone,
  PhoneCall,
  PhoneOff,
  Mic,
  MicOff,
  Disc,
  ShieldAlert,
} from 'lucide-react';

const CallContext = createContext(null);

export const useCall = () => {
  const ctx = useContext(CallContext);
  if (!ctx) {
    throw new Error('useCall must be used within a CallProvider');
  }
  return ctx;
};

// PCM format conversion helpers
function int16LEToFloat32(buffer) {
  const bytes = new Uint8Array(buffer);
  const floats = new Float32Array(bytes.length / 2);
  for (let i = 0; i < floats.length; i += 1) {
    let int16 = bytes[i * 2] | (bytes[i * 2 + 1] << 8);
    if (int16 >= 0x8000) int16 -= 0x10000;
    floats[i] = int16 / 32768;
  }
  return floats;
}

function float32ToInt16LE(floats) {
  const bytes = new Uint8Array(floats.length * 2);
  for (let i = 0; i < floats.length; i += 1) {
    const s = Math.max(-1, Math.min(1, floats[i]));
    const int16 = s < 0 ? s * 0x8000 : s * 0x7fff;
    bytes[i * 2] = int16 & 0xff;
    bytes[i * 2 + 1] = (int16 >> 8) & 0xff;
  }
  return bytes.buffer;
}

const CAPTURE_WORKLET_CODE = `
class CaptureProcessor extends AudioWorkletProcessor {
  process(inputs, outputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) {
      this.port.postMessage(channel.slice(0));
    }
    return true;
  }
}
registerProcessor("capture-processor", CaptureProcessor);
`;

const PLAYBACK_WORKLET_CODE = `
const RING_SIZE = 16000 * 2;
class PlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ring = new Float32Array(RING_SIZE);
    this.read = 0;
    this.write = 0;
    this.available = 0;
    this.blocks = 0;
    this.port.onmessage = (e) => {
      const data = e.data;
      if (!data) return;
      if (data.type === "clear") {
        this.ring.fill(0);
        this.read = 0;
        this.write = 0;
        this.available = 0;
        return;
      }
      if (!data.length) return;
      for (let i = 0; i < data.length; i += 1) {
        this.ring[this.write] = data[i];
        this.write = (this.write + 1) % RING_SIZE;
        if (this.available < RING_SIZE) {
          this.available += 1;
        } else {
          this.read = (this.read + 1) % RING_SIZE;
        }
      }
    };
  }
  process(_inputs, outputs) {
    const output = outputs[0];
    if (!output || !output[0]) return true;
    const channelCount = output.length;
    const frameCount = output[0].length;
    for (let i = 0; i < frameCount; i += 1) {
      let sample = 0;
      if (this.available > 0) {
        sample = this.ring[this.read];
        this.ring[this.read] = 0;
        this.read = (this.read + 1) % RING_SIZE;
        this.available -= 1;
      }
      for (let ch = 0; ch < channelCount; ch += 1) {
        output[ch][i] = sample;
      }
    }
    this.blocks = (this.blocks + 1) % 8;
    if (this.blocks === 0) {
      this.port.postMessage({ type: "status", available: this.available });
    }
    return true;
  }
}
registerProcessor("playback-processor", PlaybackProcessor);
`;

export const CallProvider = ({ children }) => {
  const [callState, setCallState] = useState({
    active: false,
    status: 'idle', // 'calling' | 'connected' | 'ended'
    callId: null,
    sessionName: null,
    peerName: '',
    peerPhone: '',
    duration: 0,
    isMuted: false,
    error: null,
    isIncoming: false,
  });

  const [incomingCall, setIncomingCall] = useState(null);
  const [isCallingPaired, setIsCallingPaired] = useState(false);
  const [isRecordingCall, setIsRecordingCall] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [showConsentModal, setShowConsentModal] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);

  const showToast = useCallback((msg, type = 'info') => {
    setToastMessage({ msg, type });
    setTimeout(() => setToastMessage(null), 4000);
  }, []);

  const callMediaRef = useRef({
    peerConnection: null,
    dataChannel: null,
    audioWs: null,
    audioCtx: null,
    micStream: null,
    recordDest: null,
    mediaRecorder: null,
    recordChunks: [],
    isRecording: false,
    recordingStartTime: 0,
    reconnectCount: 0,
    timerInterval: null,
    captureBlobUrl: null,
    playbackBlobUrl: null,
  });

  const handledCallIdsRef = useRef(
    (() => {
      try {
        const saved = sessionStorage.getItem('wa_handled_call_ids');
        return saved ? new Set(JSON.parse(saved)) : new Set();
      } catch (_) {
        return new Set();
      }
    })()
  );

  const markCallIdHandled = useCallback((rawCallId) => {
    const clean = String(rawCallId || '').replace(/^call_/, '').trim();
    if (!clean) return;
    handledCallIdsRef.current.add(clean);
    try {
      const arr = Array.from(handledCallIdsRef.current).slice(-200);
      sessionStorage.setItem('wa_handled_call_ids', JSON.stringify(arr));
    } catch (_) {}
  }, []);

  const cleanupCallSession = useCallback(() => {
    if (callMediaRef.current.timerInterval) {
      clearInterval(callMediaRef.current.timerInterval);
    }
    if (callMediaRef.current.mediaRecorder && callMediaRef.current.isRecording) {
      try {
        callMediaRef.current.mediaRecorder.stop();
      } catch (_) {}
      callMediaRef.current.isRecording = false;
      setIsRecordingCall(false);
    }
    if (callMediaRef.current.micStream) {
      callMediaRef.current.micStream.getTracks().forEach((track) => track.stop());
    }
    if (callMediaRef.current.audioWs) {
      try {
        callMediaRef.current.audioWs.onclose = null;
        callMediaRef.current.audioWs.close();
      } catch (_) {}
    }
    if (callMediaRef.current.remoteAudioEl) {
      try {
        callMediaRef.current.remoteAudioEl.pause();
        callMediaRef.current.remoteAudioEl.srcObject = null;
      } catch (_) {}
    }
    if (callMediaRef.current.dataChannel) {
      try {
        callMediaRef.current.dataChannel.close();
      } catch (_) {}
    }
    if (callMediaRef.current.peerConnection) {
      try {
        callMediaRef.current.peerConnection.close();
      } catch (_) {}
    }
    if (callMediaRef.current.audioCtx) {
      callMediaRef.current.audioCtx.close().catch(() => {});
    }
    if (callMediaRef.current.captureBlobUrl) {
      try {
        URL.revokeObjectURL(callMediaRef.current.captureBlobUrl);
      } catch (_) {}
    }
    if (callMediaRef.current.playbackBlobUrl) {
      try {
        URL.revokeObjectURL(callMediaRef.current.playbackBlobUrl);
      } catch (_) {}
    }
    callMediaRef.current = {
      peerConnection: null,
      dataChannel: null,
      audioWs: null,
      remoteAudioEl: null,
      audioCtx: null,
      micStream: null,
      timerInterval: null,
      captureBlobUrl: null,
      playbackBlobUrl: null,
    };
    setCallState({
      active: false,
      status: 'idle',
      callId: null,
      sessionName: null,
      peerName: '',
      peerPhone: '',
      duration: 0,
      isMuted: false,
      error: null,
      isIncoming: false,
    });
  }, []);

  const endedPollCountRef = useRef(0);

  const checkCallingStatus = useCallback(async () => {
    try {
      const res = await api.get('/whatsapp/calls/status/');
      if (res.data?.calling?.paired || res.data?.paired || res.data?.connected) {
        setIsCallingPaired(true);
      } else {
        setIsCallingPaired(false);
      }

      const activeCallData = res.data?.active_call;
      if (activeCallData && callState.active) {
        const endedCallId = String(activeCallData.call_id || '').replace(/^call_/, '').trim();
        const currentCallId = String(callState.callId || '').replace(/^call_/, '').trim();
        if (endedCallId && currentCallId && endedCallId === currentCallId) {
          if (activeCallData.status === 'ended') {
            endedPollCountRef.current = (endedPollCountRef.current || 0) + 1;
            if (endedPollCountRef.current >= 2) {
              endedPollCountRef.current = 0;
              cleanupCallSession();
            }
          } else {
            endedPollCountRef.current = 0;
            if (activeCallData.status === 'active' && callState.status === 'calling') {
              setCallState((prev) => ({ ...prev, status: 'connected' }));
            }
          }
        }
      } else {
        endedPollCountRef.current = 0;
      }

      const incoming = res.data?.incoming_call;
      if (incoming && incoming.call_id) {
        const cleanIncId = String(incoming.call_id).replace(/^call_/, '').trim();
        let isHandledAlready = handledCallIdsRef.current.has(cleanIncId);
        if (!isHandledAlready) {
          try {
            const saved = sessionStorage.getItem('wa_handled_call_ids');
            if (saved && JSON.parse(saved).includes(cleanIncId)) {
              handledCallIdsRef.current.add(cleanIncId);
              isHandledAlready = true;
            }
          } catch (_) {}
        }
        if (
          !cleanIncId ||
          incoming.status !== 'ringing' ||
          callState.active ||
          isHandledAlready
        ) {
          setIncomingCall(null);
        } else {
          setIncomingCall((prev) => {
            if (prev && String(prev.call_id).replace(/^call_/, '').trim() === cleanIncId) return prev;
            return { ...incoming, call_id: cleanIncId };
          });
        }
      } else {
        setIncomingCall(null);
      }
    } catch (_) {
      setIsCallingPaired(false);
    }
  }, [callState.active, callState.callId, callState.status, cleanupCallSession]);

  useEffect(() => {
    checkCallingStatus();
    const interval = setInterval(checkCallingStatus, 1200);
    return () => clearInterval(interval);
  }, [checkCallingStatus]);

  // Audible Ringing Chime for Incoming WhatsApp Calls
  useEffect(() => {
    if (!incomingCall) return;
    let ringInterval = null;
    let ringCtx = null;
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      ringCtx = new AudioCtx();
      const playTone = () => {
        if (!ringCtx || ringCtx.state === 'closed') return;
        if (ringCtx.state === 'suspended') ringCtx.resume().catch(() => {});
        const now = ringCtx.currentTime;
        const osc = ringCtx.createOscillator();
        const gain = ringCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(440, now);
        osc.frequency.setValueAtTime(480, now + 0.1);
        gain.gain.setValueAtTime(0.12, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.8);
        osc.connect(gain);
        gain.connect(ringCtx.destination);
        osc.start(now);
        osc.stop(now + 0.8);
      };
      playTone();
      ringInterval = setInterval(playTone, 2000);
    } catch (_) {}
    return () => {
      if (ringInterval) clearInterval(ringInterval);
      if (ringCtx) ringCtx.close().catch(() => {});
    };
  }, [incomingCall]);

  // Call duration counter
  useEffect(() => {
    let timer = null;
    if (callState.active && callState.status === 'connected') {
      timer = setInterval(() => {
        setCallState((prev) => ({ ...prev, duration: prev.duration + 1 }));
      }, 1000);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [callState.active, callState.status]);

  // Recording duration counter
  useEffect(() => {
    let timer = null;
    if (isRecordingCall) {
      timer = setInterval(() => {
        setRecordingDuration((prev) => prev + 1);
      }, 1000);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [isRecordingCall]);

  const initWebRTCAudioChannel = useCallback(async (callId, callSessionName, audioWsUrl = '') => {
    try {
      if (callMediaRef.current.audioWs) {
        try {
          callMediaRef.current.audioWs.onclose = null;
          callMediaRef.current.audioWs.close();
        } catch (_) {}
        callMediaRef.current.audioWs = null;
      }
      if (callMediaRef.current.dataChannel) {
        try { callMediaRef.current.dataChannel.close(); } catch (_) {}
        callMediaRef.current.dataChannel = null;
      }
      if (callMediaRef.current.peerConnection) {
        try { callMediaRef.current.peerConnection.close(); } catch (_) {}
        callMediaRef.current.peerConnection = null;
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          googEchoCancellation: true,
          googAutoGainControl: true,
          googNoiseSuppression: true,
          googHighpassFilter: true,
          channelCount: 1,
        },
      });
      callMediaRef.current.micStream = stream;
      callMediaRef.current.isMuted = false;

      const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
      const ctx = new AudioCtxClass({ sampleRate: 16000 });
      callMediaRef.current.audioCtx = ctx;

      const captureBlob = new Blob([CAPTURE_WORKLET_CODE], { type: 'application/javascript' });
      const playbackBlob = new Blob([PLAYBACK_WORKLET_CODE], { type: 'application/javascript' });
      const captureUrl = URL.createObjectURL(captureBlob);
      const playbackUrl = URL.createObjectURL(playbackBlob);
      callMediaRef.current.captureBlobUrl = captureUrl;
      callMediaRef.current.playbackBlobUrl = playbackUrl;

      try {
        await ctx.audioWorklet.addModule(captureUrl);
        await ctx.audioWorklet.addModule(playbackUrl);
      } catch (workletErr) {
        console.warn('Blob worklet load fallback to /worklets/:', workletErr);
        await ctx.audioWorklet.addModule('/worklets/capture-processor.js');
        await ctx.audioWorklet.addModule('/worklets/playback-processor.js');
      }

      await ctx.resume();

      const playbackNode = new AudioWorkletNode(ctx, 'playback-processor');
      playbackNode.connect(ctx.destination);
      playbackNode.port.onmessage = (e) => {
        if (e.data && e.data.type === 'status') {
          callMediaRef.current.playbackAvailableSamples = e.data.available || 0;
        }
      };

      const sendRawPcm = (pcmBytes) => {
        const ws = callMediaRef.current.audioWs;
        const dc = callMediaRef.current.dataChannel;
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(pcmBytes);
        } else if (dc && dc.readyState === 'open') {
          dc.send(pcmBytes);
        }
      };

      const playIncomingBuffer = async (rawData) => {
        if (ctx.state === 'suspended') {
          ctx.resume().catch(() => {});
        }
        let buf = rawData;
        if (buf instanceof Blob) {
          buf = await buf.arrayBuffer();
        }
        const floats = int16LEToFloat32(buf);
        if (!floats || !floats.length) return;
        playbackNode.port.postMessage(floats);
      };

      const micSource = ctx.createMediaStreamSource(stream);
      const captureNode = new AudioWorkletNode(ctx, 'capture-processor');
      captureNode.port.onmessage = (e) => {
        const samples = e.data;
        if (!samples || !samples.length) return;

        if (callMediaRef.current.isMuted) {
          const silenceBytes = new Int16Array(samples.length).buffer;
          sendRawPcm(silenceBytes);
          return;
        }

        sendRawPcm(float32ToInt16LE(samples));
      };
      micSource.connect(captureNode);

      try {
        const recordDest = ctx.createMediaStreamDestination();
        micSource.connect(recordDest);
        playbackNode.connect(recordDest);
        callMediaRef.current.recordDest = recordDest;
      } catch (recErr) {
        console.warn('Could not initialize recording destination:', recErr);
      }

      const silenceGain = ctx.createGain();
      silenceGain.gain.setValueAtTime(0, ctx.currentTime);
      captureNode.connect(silenceGain);
      silenceGain.connect(ctx.destination);

      let normalizedWsUrl = audioWsUrl || '';
      if (normalizedWsUrl && callSessionName && callSessionName !== 'default') {
        normalizedWsUrl = normalizedWsUrl.replace(
          '/api/calling/sessions/default/calls/',
          `/api/calling/sessions/${encodeURIComponent(callSessionName)}/calls/`
        );
      }

      let wsConnected = false;
      if (normalizedWsUrl) {
        wsConnected = await new Promise((resolve) => {
          let settled = false;
          let openVerifyTimer = null;
          const finish = (ok) => {
            if (openVerifyTimer) {
              clearTimeout(openVerifyTimer);
              openVerifyTimer = null;
            }
            if (!settled) {
              settled = true;
              resolve(ok);
            }
          };
          const connectSocket = (isReconnect = false) => {
            try {
              const ws = new WebSocket(normalizedWsUrl);
              ws.binaryType = 'arraybuffer';
              callMediaRef.current.audioWs = ws;

              ws.onopen = () => {
                if (ctx.state === 'suspended') {
                  ctx.resume().catch(() => {});
                }
                if (!isReconnect) {
                  openVerifyTimer = setTimeout(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                      finish(true);
                    }
                  }, 180);
                }
              };
              ws.onmessage = (e) => {
                if (!settled) finish(true);
                playIncomingBuffer(e.data);
              };
              ws.onerror = () => {
                if (!isReconnect) finish(false);
              };
              ws.onclose = (ev) => {
                if (!isReconnect && !settled) {
                  finish(false);
                  return;
                }
                const isServerEnded = ev.reason === 'call ended';
                const reconnectCount = callMediaRef.current.reconnectCount || 0;
                if (isServerEnded || reconnectCount >= 3) {
                  markCallIdHandled(callId);
                  setIncomingCall(null);
                  setCallState((prev) => (prev.active ? { ...prev, status: 'ended', error: 'Call ended' } : prev));
                  setTimeout(() => cleanupCallSession(), 1000);
                  return;
                }
                callMediaRef.current.reconnectCount = reconnectCount + 1;
                if (callMediaRef.current.audioCtx && callMediaRef.current.audioCtx.state !== 'closed') {
                  setTimeout(() => {
                    if (callMediaRef.current.audioCtx && callMediaRef.current.audioCtx.state !== 'closed') {
                      connectSocket(true);
                    }
                  }, 500);
                }
              };
            } catch (_) {
              finish(false);
            }
          };
          connectSocket(false);
          setTimeout(() => finish(false), 2500);
        });
      }

      if (!wsConnected) {
        const pc = new RTCPeerConnection({
          iceServers: [
            { urls: ['stun:stun.l.google.com:19302', 'stun:stun1.l.google.com:19302'] }
          ]
        });
        callMediaRef.current.peerConnection = pc;

        const bindDataChannel = (channel) => {
          if (!channel) return;
          callMediaRef.current.dataChannel = channel;
          channel.binaryType = 'arraybuffer';
          channel.onopen = () => {
            if (ctx.state === 'suspended') {
              ctx.resume().catch(() => {});
            }
          };
          channel.onmessage = (e) => {
            playIncomingBuffer(e.data);
          };
        };

        const dc = pc.createDataChannel('pcm', { ordered: true });
        bindDataChannel(dc);

        pc.ondatachannel = (event) => {
          bindDataChannel(event.channel);
        };

        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        await new Promise((resolve) => {
          if (pc.iceGatheringState === 'complete') resolve();
          else {
            const checkIce = () => {
              if (pc.iceGatheringState === 'complete') {
                pc.removeEventListener('icegatheringstatechange', checkIce);
                resolve();
              }
            };
            pc.addEventListener('icegatheringstatechange', checkIce);
            setTimeout(resolve, 2000);
          }
        });

        const sdpOffer = pc.localDescription?.sdp || '';
        try {
          const webrtcRes = await api.post(`/whatsapp/calls/${encodeURIComponent(callId)}/webrtc/`, {
            sdp_offer: sdpOffer,
            session_name: callSessionName,
          });
          const sdpAnswer = webrtcRes.data?.sdp_answer || webrtcRes.data?.sdpAnswer;
          if (sdpAnswer) {
            await pc.setRemoteDescription({ type: 'answer', sdp: sdpAnswer });
          }
        } catch (webrtcErr) {
          console.warn('WebRTC SDP negotiation warning:', webrtcErr);
        }
      }

      setCallState((prev) => ({
        ...prev,
        status: 'connected',
      }));
    } catch (err) {
      console.warn('Audio Channel initialization warning:', err);
      setCallState((prev) => ({
        ...prev,
        status: 'connected',
      }));
    }
  }, [cleanupCallSession, markCallIdHandled]);

  const handleEndCall = useCallback(async () => {
    const activeCallId = callState.callId;
    if (activeCallId) {
      markCallIdHandled(activeCallId);
      setIncomingCall(null);
      try {
        await api.post(`/whatsapp/calls/${encodeURIComponent(activeCallId)}/end/`, {
          session_name: callState.sessionName,
        });
      } catch (err) {
        console.warn('End call API notification failed:', err);
      }
    }
    cleanupCallSession();
  }, [callState.callId, callState.sessionName, markCallIdHandled, cleanupCallSession]);

  const handleToggleMute = useCallback(() => {
    const nextMuted = !callState.isMuted;
    if (callMediaRef.current.micStream) {
      callMediaRef.current.micStream.getAudioTracks().forEach((track) => {
        track.enabled = !nextMuted;
      });
    }
    callMediaRef.current.isMuted = nextMuted;
    setCallState((prev) => ({ ...prev, isMuted: nextMuted }));
  }, [callState.isMuted]);

  const startVoiceCall = useCallback(async ({ phone, name, chatId, sessionName }) => {
    const cleanPhone = (phone || '').replace(/\D+/g, '');
    if (!cleanPhone) {
      showToast('No valid phone number provided for calling.', 'error');
      return;
    }

    try {
      setCallState({
        active: true,
        status: 'calling',
        callId: null,
        peerName: name || `+${cleanPhone}`,
        peerPhone: `+${cleanPhone}`,
        duration: 0,
        isMuted: false,
        error: null,
        isIncoming: false,
      });

      const startRes = await api.post('/whatsapp/calls/start/', {
        phone: cleanPhone,
        chat_id: chatId,
        session_name: sessionName || undefined,
      });

      const newCallId = startRes.data?.call_id || startRes.data?.callId;
      const resolvedSession = startRes.data?.session_name || sessionName;
      const audioWsUrl = startRes.data?.audio_ws_url || '';
      if (!newCallId) {
        throw new Error(startRes.data?.error || 'No call ID returned by WhatsApp calling service');
      }

      setCallState((prev) => ({
        ...prev,
        callId: newCallId,
        sessionName: resolvedSession,
      }));

      await initWebRTCAudioChannel(newCallId, resolvedSession, audioWsUrl);
    } catch (err) {
      console.error('Start voice call failed:', err.response?.data || err);
      const isNotPaired = err.response?.data?.error === 'calling_not_paired' || (err.response?.data?.detail || '').includes('calling device') || (err.response?.data?.error || '').includes('not paired');
      if (isNotPaired) {
        cleanupCallSession();
        showToast('Voice calling is initializing with your connected WhatsApp session. Please try again.', 'info');
        return;
      }
      const errDetail = err.response?.data?.detail || err.response?.data?.error || err.message || 'Failed to initiate WhatsApp call';
      showToast(`Call failed: ${errDetail}`, 'error');
      setCallState((prev) => ({
        ...prev,
        status: 'ended',
        error: errDetail,
      }));
      setTimeout(() => {
        cleanupCallSession();
      }, 4000);
    }
  }, [initWebRTCAudioChannel, cleanupCallSession, showToast]);

  const handleAcceptIncomingCall = useCallback(async (explicitCall = null) => {
    const targetCall = explicitCall || incomingCall;
    if (!targetCall) return;
    const rawId = targetCall.call_id || targetCall.callId || targetCall.id || '';
    const cleanCallId = String(rawId).replace(/^call_/, '').trim();
    if (!cleanCallId) return;

    markCallIdHandled(cleanCallId);
    const sessionToUse = targetCall.session_name || 'default';

    setIncomingCall(null);
    setCallState({
      active: true,
      status: 'connected',
      callId: cleanCallId,
      peerName: targetCall.caller_name || targetCall.peerName || 'WhatsApp Contact',
      peerPhone: targetCall.caller_phone || targetCall.peerPhone || '',
      duration: 0,
      isMuted: false,
      error: null,
      sessionName: sessionToUse,
      isIncoming: true,
    });

    let resolvedSession = sessionToUse;
    let audioWsUrl = targetCall.audio_ws_url || '';

    if (!targetCall.alreadyAccepted) {
      try {
        const acceptRes = await api.post(`/whatsapp/calls/${encodeURIComponent(cleanCallId)}/accept/`, {
          session_name: sessionToUse,
        });
        if (acceptRes.data?.session_name) {
          resolvedSession = acceptRes.data.session_name;
          setCallState((prev) => ({ ...prev, sessionName: resolvedSession }));
        }
        if (acceptRes.data?.audio_ws_url) {
          audioWsUrl = acceptRes.data.audio_ws_url;
        }
      } catch (acceptErr) {
        console.warn('Accept call error (may already be accepted):', acceptErr);
      }
    }

    try {
      await initWebRTCAudioChannel(cleanCallId, resolvedSession, audioWsUrl);
    } catch (audioErr) {
      console.error('WebRTC Audio connect error:', audioErr);
      showToast('Connected, but audio channel initialization failed.', 'error');
    }
  }, [incomingCall, markCallIdHandled, initWebRTCAudioChannel, showToast]);

  const handleRejectIncomingCall = useCallback(async (explicitCall = null) => {
    const targetCall = explicitCall || incomingCall;
    if (!targetCall) return;
    const rawId = targetCall.call_id || targetCall.callId || targetCall.id || '';
    const cleanCallId = String(rawId).replace(/^call_/, '').trim();
    const sessionToUse = targetCall.session_name || 'default';
    if (cleanCallId) {
      markCallIdHandled(cleanCallId);
    }
    setIncomingCall(null);
    if (!cleanCallId) return;
    try {
      await api.post(`/whatsapp/calls/${encodeURIComponent(cleanCallId)}/reject/`, {
        session_name: sessionToUse,
      });
      showToast('Call declined', 'info');
    } catch (err) {
      console.warn('Decline call error:', err);
    }
  }, [incomingCall, markCallIdHandled, showToast]);

  const startCallRecording = useCallback(() => {
    if (!callMediaRef.current.recordDest || !callState.active) {
      showToast('Cannot start recording: No active call audio available', 'error');
      return;
    }
    try {
      const stream = callMediaRef.current.recordDest.stream;
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : (MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/ogg');

      const recorder = new MediaRecorder(stream, { mimeType });
      callMediaRef.current.recordChunks = [];
      callMediaRef.current.mediaRecorder = recorder;
      callMediaRef.current.recordingStartTime = Date.now();

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          callMediaRef.current.recordChunks.push(e.data);
        }
      };

      recorder.onstop = async () => {
        const chunks = callMediaRef.current.recordChunks;
        if (!chunks || !chunks.length) return;
        const blob = new Blob(chunks, { type: mimeType });
        const durationSec = Math.max(1, Math.round((Date.now() - (callMediaRef.current.recordingStartTime || Date.now())) / 1000));

        const formData = new FormData();
        const filename = `call_${callState.callId || 'rec'}_${Date.now()}.webm`;
        formData.append('audio_file', blob, filename);
        formData.append('call_id', callState.callId || '');
        formData.append('session_name', callState.sessionName || 'default');
        formData.append('chat_id', callState.peerPhone || '');
        formData.append('direction', callState.isIncoming ? 'inbound' : 'outbound');
        formData.append('duration_seconds', durationSec);
        formData.append('consent_obtained', 'true');

        try {
          await api.post('/whatsapp/calls/recordings/upload/', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
          });
          showToast('Call recording saved securely', 'success');
        } catch (err) {
          console.error('Failed to upload call recording:', err);
          showToast('Failed to upload call recording', 'error');
        }
      };

      recorder.start(1000);
      callMediaRef.current.isRecording = true;
      setIsRecordingCall(true);
      setRecordingDuration(0);
      showToast('Call recording started (Dual-channel audio)', 'info');
    } catch (err) {
      console.error('Failed to start MediaRecorder:', err);
      showToast(`Failed to record call: ${err.message}`, 'error');
    }
  }, [callState.active, callState.callId, callState.sessionName, callState.isIncoming, callState.peerPhone, showToast]);

  const stopCallRecording = useCallback(() => {
    if (callMediaRef.current.mediaRecorder && callMediaRef.current.isRecording) {
      try {
        callMediaRef.current.mediaRecorder.stop();
      } catch (_) {}
      callMediaRef.current.isRecording = false;
    }
    setIsRecordingCall(false);
    setRecordingDuration(0);
  }, []);

  return (
    <CallContext.Provider
      value={{
        callState,
        incomingCall,
        isCallingPaired,
        isRecordingCall,
        recordingDuration,
        showConsentModal,
        setShowConsentModal,
        startVoiceCall,
        handleAcceptIncomingCall,
        handleRejectIncomingCall,
        handleEndCall,
        handleToggleMute,
        startCallRecording,
        stopCallRecording,
        showToast,
      }}
    >
      {children}

      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed top-5 right-5 z-[9999] flex items-center gap-2 px-4 py-2.5 rounded-xl text-white text-xs font-semibold shadow-2xl animate-in fade-in duration-200 bg-slate-900 border border-slate-700">
          <span>{toastMessage.msg}</span>
        </div>
      )}

      {/* Floating Active / Incoming Voice Call Widget */}
      {(callState.active || (incomingCall && !callState.active)) && (
        <div className="fixed bottom-6 right-6 z-[100] animate-in fade-in slide-in-from-bottom-5 duration-300">
          <div className="bg-slate-900/95 backdrop-blur-md border border-emerald-500/30 text-white rounded-3xl p-5 shadow-2xl shadow-emerald-950/40 w-80 flex flex-col items-center">
            {/* Call Header */}
            <div className="flex items-center justify-between w-full mb-3 text-xs text-slate-400">
              <span className="flex items-center gap-1.5 text-emerald-400 font-semibold uppercase tracking-wider text-[11px]">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping inline-block" />
                {incomingCall && !callState.active ? 'Incoming Call' : 'WhatsApp Voice'}
              </span>
              <span className="font-mono text-slate-300 text-xs">
                {incomingCall && !callState.active ? (
                  <span className="text-emerald-400 font-sans font-semibold animate-pulse">Ringing...</span>
                ) : (
                  `${String(Math.floor(callState.duration / 60)).padStart(2, '0')}:${String(
                    callState.duration % 60
                  ).padStart(2, '0')}`
                )}
              </span>
            </div>

            {/* Avatar with Animated Pulse */}
            <div className="relative mb-3">
              {incomingCall && !callState.active && (
                <>
                  <span className="absolute -inset-2 rounded-full bg-emerald-500/30 animate-ping pointer-events-none" />
                  <span className="absolute -inset-4 rounded-full bg-emerald-500/15 animate-pulse pointer-events-none" />
                </>
              )}
              <div className="w-16 h-16 rounded-full bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center text-white text-2xl font-bold shadow-lg shadow-emerald-900/40 relative z-10">
                {(incomingCall?.caller_name || callState.peerName) ? (
                  (incomingCall?.caller_name || callState.peerName).charAt(0).toUpperCase()
                ) : (
                  <Phone className="w-7 h-7" />
                )}
              </div>
            </div>

            {/* Contact Name & Phone */}
            <h3 className="font-semibold text-base text-slate-100 text-center truncate w-full px-2">
              {incomingCall?.caller_name || callState.peerName || 'WhatsApp Contact'}
            </h3>
            <p className="text-xs text-slate-400 font-mono mb-3 truncate w-full text-center px-2">
              {incomingCall?.caller_phone || callState.peerPhone || 'WhatsApp Voice Call'}
            </p>

            {/* Call Status Badge */}
            <div className="mb-4">
              {incomingCall && !callState.active ? (
                <span className="px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-300 text-xs font-semibold border border-emerald-500/40 flex items-center gap-1.5 animate-pulse">
                  <PhoneCall className="w-3.5 h-3.5 text-emerald-400" /> Incoming WhatsApp Call...
                </span>
              ) : callState.status === 'calling' ? (
                <span className="px-3 py-1 rounded-full bg-amber-500/20 text-amber-300 text-xs font-medium border border-amber-500/30 flex items-center gap-1.5 animate-pulse">
                  <PhoneCall className="w-3 h-3" /> Calling / Ringing...
                </span>
              ) : callState.status === 'connected' ? (
                <span className="px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-300 text-xs font-medium border border-emerald-500/30 flex items-center gap-1.5">
                  <Phone className="w-3 h-3" /> Audio Connected
                </span>
              ) : callState.status === 'ended' ? (
                <span className="px-3 py-1 rounded-full bg-rose-500/20 text-rose-300 text-xs font-medium border border-rose-500/30">
                  {callState.error || 'Call Ended'}
                </span>
              ) : null}
            </div>

            {/* Action Buttons: Incoming (Decline + Attend) vs Active (Mute + Hangup) */}
            {incomingCall && !callState.active ? (
              <div className="flex items-center gap-8 w-full justify-center pt-1 pb-1">
                <div className="flex flex-col items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => handleRejectIncomingCall(incomingCall)}
                    className="w-12 h-12 rounded-full bg-rose-600 hover:bg-rose-700 text-white transition-all shadow-lg shadow-rose-900/50 flex items-center justify-center cursor-pointer hover:scale-110 active:scale-95"
                    title="Decline Call"
                  >
                    <PhoneOff className="w-6 h-6" />
                  </button>
                  <span className="text-[11px] font-medium text-slate-300">Decline</span>
                </div>

                <div className="flex flex-col items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => handleAcceptIncomingCall(incomingCall)}
                    className="w-12 h-12 rounded-full bg-emerald-500 hover:bg-emerald-600 text-white transition-all shadow-lg shadow-emerald-900/50 flex items-center justify-center cursor-pointer ring-4 ring-emerald-400/40 animate-bounce hover:scale-110 active:scale-95"
                    title="Attend Call"
                  >
                    <PhoneCall className="w-6 h-6" />
                  </button>
                  <span className="text-[11px] font-semibold text-emerald-400">Attend Call</span>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-3 w-full">
                {isRecordingCall && (
                  <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-rose-500/20 text-rose-300 text-xs font-mono font-medium border border-rose-500/40 animate-pulse">
                    <span className="w-2 h-2 rounded-full bg-rose-500" />
                    <span>REC {String(Math.floor(recordingDuration / 60)).padStart(2, '0')}:{String(recordingDuration % 60).padStart(2, '0')}</span>
                  </div>
                )}

                <div className="flex items-center gap-4 w-full justify-center">
                  <button
                    type="button"
                    onClick={handleToggleMute}
                    className={`p-3 rounded-full transition shadow-md flex items-center justify-center cursor-pointer hover:scale-105 active:scale-95 ${
                      callState.isMuted
                        ? 'bg-rose-500 text-white hover:bg-rose-600'
                        : 'bg-slate-800 text-slate-200 hover:bg-slate-700'
                    }`}
                    title={callState.isMuted ? 'Unmute microphone' : 'Mute microphone'}
                  >
                    {callState.isMuted ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
                  </button>

                  <button
                    type="button"
                    onClick={isRecordingCall ? stopCallRecording : () => setShowConsentModal(true)}
                    className={`p-3 rounded-full transition shadow-md flex items-center justify-center cursor-pointer hover:scale-105 active:scale-95 ${
                      isRecordingCall
                        ? 'bg-rose-600 text-white hover:bg-rose-700 ring-2 ring-rose-400/50 animate-pulse'
                        : 'bg-slate-800 text-slate-200 hover:bg-slate-700 hover:text-rose-400'
                    }`}
                    title={isRecordingCall ? 'Stop Recording' : 'Record Call (Dual-Channel)'}
                  >
                    <Disc className="w-5 h-5" />
                  </button>

                  <button
                    type="button"
                    onClick={handleEndCall}
                    className="p-3.5 rounded-full bg-rose-600 hover:bg-rose-700 text-white transition shadow-lg shadow-rose-900/50 flex items-center justify-center cursor-pointer hover:scale-105 active:scale-95"
                    title="Hang up call"
                  >
                    <PhoneOff className="w-5 h-5" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Call Recording Consent Modal */}
      {showConsentModal && (
        <div className="fixed inset-0 z-[120] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6 border border-slate-200 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center gap-3 mb-4 text-amber-600">
              <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center">
                <ShieldAlert className="w-6 h-6 text-amber-600" />
              </div>
              <div>
                <h3 className="font-bold text-slate-900 text-base">Call Recording Consent</h3>
                <p className="text-xs text-slate-500">Dual-Channel Audio Capture</p>
              </div>
            </div>
            <p className="text-sm text-slate-600 leading-relaxed mb-4">
              Recording this WhatsApp call will capture both your microphone and the remote caller's audio into an encrypted, isolated call recording.
            </p>
            <div className="p-3 bg-amber-50 rounded-xl border border-amber-200/80 mb-5 text-xs text-amber-800 leading-normal">
              Compliance Notice: Confirm that both parties consent to call recording under applicable communication privacy regulations.
            </div>
            <div className="flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setShowConsentModal(false)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100 transition cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowConsentModal(false);
                  startCallRecording();
                }}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-rose-600 hover:bg-rose-700 text-white transition shadow-sm cursor-pointer flex items-center gap-1.5"
              >
                <Disc className="w-3.5 h-3.5" />
                <span>Confirm & Start Recording</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </CallContext.Provider>
  );
};

