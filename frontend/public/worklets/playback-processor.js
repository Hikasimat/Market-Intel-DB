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
