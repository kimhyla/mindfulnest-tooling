export type O3GenerationIntentPoll = {
  intent_id?: string;
  job_id?: string;
  beat_id?: string;
  prompt?: { verbatim?: string; sha256?: string };
  visual?: {
    char_ref_abs_path?: string;
    bg_ref_abs_path?: string;
    element_char_ref_gate?: { refer_images_resolved?: string[] };
  };
  voice?: { element_id?: string; element_name?: string; kling_voice_id?: string };
  generation?: { slot?: string; slot_index?: number };
};

export type O3SubmitAudit = {
  prompt_excerpt?: string;
  char_ref?: string;
  element_id?: string;
  refer_images?: string[];
  generation_slot?: string;
};

export type O3IntentTerminal = {
  status?: 'done' | 'failed' | 'done_with_warning';
  warning?: { code?: string; message?: string; recovered_from?: string };
  submitted?: O3SubmitAudit;
  delivered?: { video_path?: string; generation?: number };
  failure?: { message?: string };
  sidecar_persist_ok?: boolean;
};

export type ArloO3SubmitResponse = {
  ok?: boolean;
  job_id?: string;
  beat_id?: string;
  intent_id?: string;
  o3_generate_mode?: 'voice_first' | 'element_native' | string;
  pipeline_script?: string;
  generation_slot?: string;
  submitted?: O3SubmitAudit;
  intent?: O3GenerationIntentPoll;
  deduped?: boolean;
  message?: string;
  log_path?: string;
};

export type O3PollBeatPatch = {
  beat_id: string;
  [key: string]: unknown;
};

export type ArloO3PollResponse = {
  status?: string;
  job_id?: string;
  beat_id?: string;
  intent?: O3GenerationIntentPoll;
  terminal?: O3IntentTerminal;
  warning?: O3IntentTerminal['warning'];
  beat?: O3PollBeatPatch;
  result?: { video?: string; duration_s?: number } | null;
  error?: string;
};

export function intentBoundPrompt(
  activeJobId: string | undefined,
  intent: O3GenerationIntentPoll | undefined,
  submitted: O3SubmitAudit | undefined,
  fallback: string,
): string {
  if (!activeJobId) return fallback;
  return intent?.prompt?.verbatim ?? submitted?.prompt_excerpt ?? fallback;
}

export function isO3TerminalWithWarning(status: string | undefined): boolean {
  return status === 'done_with_warning';
}
