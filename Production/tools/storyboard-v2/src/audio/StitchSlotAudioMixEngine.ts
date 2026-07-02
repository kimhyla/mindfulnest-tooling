/**
 * FF-042 STITCH_DRY_AUTHORITY_CLIENT_MIX_V1 — ambient + SFX layered on dry <video>.
 * Speech bytes come from the dry MP4 via MediaElementSource (not a rebaked mix).
 */

import { resolveServerMediaUrl } from '../utils/stitchSlotVideo';
import { STITCH_DRY_AUTHORITY_CLIENT_MIX_V1 } from '../utils/stitchSlotMuxAudioSig';

export interface StitchClientMixSfxCue {
  id?: string;
  offset_ms?: number;
  duration_ms?: number;
  volume?: number;
  fadein_ms?: number;
  fadeout_ms?: number;
  source_path?: string;
}

export interface StitchClientMixSlotInput {
  ambient_bed_path?: string;
  ambient_volume?: number;
  video_dur_ms?: number;
  sfx_cues?: StitchClientMixSfxCue[];
}

export interface StitchClientMixJobContext {
  jobName: string;
  slotKey: string;
}

const DRIFT_RESYNC_MS = 80;

export class StitchSlotAudioMixEngine {
  private ctx: AudioContext | null = null;

  private speechNode: MediaElementAudioSourceNode | null = null;

  private ambientSource: AudioBufferSourceNode | null = null;

  private ambientGain: GainNode | null = null;

  private sfxSources: AudioBufferSourceNode[] = [];

  private video: HTMLVideoElement | null = null;

  private slotInput: StitchClientMixSlotInput | null = null;

  private jobCtx: StitchClientMixJobContext | null = null;

  private ambientBuffer: AudioBuffer | null = null;

  private sfxBufferCache = new Map<string, AudioBuffer>();

  private playEpoch = 0;

  private bound = false;

  private onPlay = () => {
    void this.handlePlay();
  };

  private onPause = () => {
    this.stopAmbient();
    this.stopSfx();
  };

  private onSeeked = () => {
    void this.resyncFromVideo();
  };

  private onTimeUpdate = () => {
    if (!this.video || this.video.paused) return;
    const driftMs = Math.abs(this.video.currentTime - this.lastScheduledVideoT) * 1000;
    if (driftMs > DRIFT_RESYNC_MS) {
      void this.resyncFromVideo();
    }
  };

  private lastScheduledVideoT = 0;

  get marker(): string {
    return STITCH_DRY_AUTHORITY_CLIENT_MIX_V1;
  }

  async attach(
    video: HTMLVideoElement,
    slot: StitchClientMixSlotInput,
    jobCtx: StitchClientMixJobContext,
  ): Promise<void> {
    this.detach();
    this.video = video;
    this.slotInput = slot;
    this.jobCtx = jobCtx;
    this.ctx = new AudioContext();
    this.speechNode = this.ctx.createMediaElementSource(video);
    const speechGain = this.ctx.createGain();
    speechGain.gain.value = 1;
    this.speechNode.connect(speechGain);
    speechGain.connect(this.ctx.destination);
    await this.loadAmbient();
    this.bindVideoEvents();
    if (!video.paused) {
      await this.handlePlay();
    }
  }

  async rebuildGeometry(slot: StitchClientMixSlotInput): Promise<void> {
    if (!this.video || !this.ctx || !this.jobCtx) return;
    this.slotInput = slot;
    this.stopAmbient();
    this.stopSfx();
    await this.loadAmbient();
    if (!this.video.paused) {
      await this.resyncFromVideo();
    }
  }

  detach(): void {
    this.unbindVideoEvents();
    this.stopAmbient();
    this.stopSfx();
    if (this.speechNode) {
      try {
        this.speechNode.disconnect();
      } catch {
        /* already disconnected */
      }
      this.speechNode = null;
    }
    if (this.ctx) {
      void this.ctx.close();
      this.ctx = null;
    }
    this.video = null;
    this.slotInput = null;
    this.jobCtx = null;
    this.ambientBuffer = null;
  }

  private bindVideoEvents(): void {
    if (!this.video || this.bound) return;
    this.video.addEventListener('play', this.onPlay);
    this.video.addEventListener('pause', this.onPause);
    this.video.addEventListener('seeked', this.onSeeked);
    this.video.addEventListener('timeupdate', this.onTimeUpdate);
    this.bound = true;
  }

  private unbindVideoEvents(): void {
    if (!this.video || !this.bound) return;
    this.video.removeEventListener('play', this.onPlay);
    this.video.removeEventListener('pause', this.onPause);
    this.video.removeEventListener('seeked', this.onSeeked);
    this.video.removeEventListener('timeupdate', this.onTimeUpdate);
    this.bound = false;
  }

  private async handlePlay(): Promise<void> {
    if (!this.ctx || !this.video) return;
    if (this.ctx.state === 'suspended') {
      await this.ctx.resume();
    }
    this.playEpoch += 1;
    await this.resyncFromVideo();
  }

  private async resyncFromVideo(): Promise<void> {
    if (!this.ctx || !this.video || this.video.paused) return;
    this.stopAmbient();
    this.stopSfx();
    this.lastScheduledVideoT = this.video.currentTime;
    this.startAmbientLoop();
    await this.scheduleSfxFromCurrentTime();
  }

  private async loadAmbient(): Promise<void> {
    this.ambientBuffer = null;
    if (!this.slotInput || !this.jobCtx) return;
    const bed = (this.slotInput.ambient_bed_path ?? '').trim();
    if (!bed) return;
    const url = `/api/stitch_editor/slot_ambient_loop?job_name=${encodeURIComponent(
      this.jobCtx.jobName,
    )}&slot_key=${encodeURIComponent(this.jobCtx.slotKey)}`;
    const res = await fetch(resolveServerMediaUrl(url));
    if (!res.ok) return;
    const buf = await res.arrayBuffer();
    if (!this.ctx) return;
    this.ambientBuffer = await this.ctx.decodeAudioData(buf.slice(0));
  }

  private startAmbientLoop(): void {
    if (!this.ctx || !this.ambientBuffer || !this.video) return;
    this.ambientGain = this.ctx.createGain();
    this.ambientGain.gain.value = 1;
    this.ambientSource = this.ctx.createBufferSource();
    this.ambientSource.buffer = this.ambientBuffer;
    this.ambientSource.loop = true;
    const offsetInLoop = this.video.currentTime % this.ambientBuffer.duration;
    this.ambientSource.connect(this.ambientGain);
    this.ambientGain.connect(this.ctx.destination);
    const when = this.ctx.currentTime;
    this.ambientSource.start(when, offsetInLoop);
  }

  private stopAmbient(): void {
    if (this.ambientSource) {
      try {
        this.ambientSource.stop();
      } catch {
        /* already stopped */
      }
      this.ambientSource.disconnect();
      this.ambientSource = null;
    }
    if (this.ambientGain) {
      this.ambientGain.disconnect();
      this.ambientGain = null;
    }
  }

  private async scheduleSfxFromCurrentTime(): Promise<void> {
    if (!this.ctx || !this.video || !this.slotInput) return;
    const cues = this.slotInput.sfx_cues ?? [];
    const videoT = this.video.currentTime;
    const epoch = this.playEpoch;
    for (const cue of cues) {
      const offsetS = (cue.offset_ms ?? 0) / 1000;
      const delayS = offsetS - videoT;
      if (delayS < -0.05) continue;
      const srcPath = (cue.source_path ?? '').trim();
      if (!srcPath) continue;
      const buffer = await this.loadSfxBuffer(srcPath);
      if (!this.ctx || epoch !== this.playEpoch || this.video.paused) return;
      const source = this.ctx.createBufferSource();
      source.buffer = buffer;
      const gain = this.ctx.createGain();
      gain.gain.value = cue.volume ?? 0.45;
      source.connect(gain);
      gain.connect(this.ctx.destination);
      const playMs = cue.duration_ms ?? Math.round(buffer.duration * 1000);
      const playS = Math.min(buffer.duration, playMs / 1000);
      const when = this.ctx.currentTime + Math.max(0, delayS);
      source.start(when, 0, playS);
      this.sfxSources.push(source);
    }
  }

  private async loadSfxBuffer(sourcePath: string): Promise<AudioBuffer> {
    const cached = this.sfxBufferCache.get(sourcePath);
    if (cached) return cached;
    const url = resolveServerMediaUrl(`/files?path=${encodeURIComponent(sourcePath)}`);
    const res = await fetch(url);
    if (!res.ok) throw new Error(`SFX fetch failed: ${sourcePath}`);
    const buf = await res.arrayBuffer();
    if (!this.ctx) throw new Error('AudioContext missing');
    const decoded = await this.ctx.decodeAudioData(buf.slice(0));
    this.sfxBufferCache.set(sourcePath, decoded);
    return decoded;
  }

  private stopSfx(): void {
    for (const src of this.sfxSources) {
      try {
        src.stop();
      } catch {
        /* already stopped */
      }
      src.disconnect();
    }
    this.sfxSources = [];
  }
}
