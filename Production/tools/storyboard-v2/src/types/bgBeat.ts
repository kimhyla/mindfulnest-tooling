/** Shared Beat Generator beat row types (session store + BgTab). */

export type BeatGenerationMode = 'still_insert' | 'avatar_pro' | 'voice_first' | 'element_native';

export interface GptOption {
  key?: string;
  label?: string;
  generation?: number;
  local_path?: string;
  video_path?: string;
  video_path_exists?: boolean;
  source?: string;
  slot_index?: number;
  cut_start_s?: number;
  cut_end_s?: number;
  trim_start_s?: number;
  trim_back_s?: number;
  thumb_b64?: string;
  gallery_b64?: string;
  cost_usd?: number;
  error?: string;
}

export type BgBeatDerived = {
  generation_mode?: BeatGenerationMode | string;
  display_prompt?: string;
  still_scene_display?: { key?: string; abs_path?: string; thumb_b64?: string; filename?: string } | null;
  char_ref_display?: { key?: string; abs_path?: string; thumb_b64?: string; filename?: string } | null;
  bg_ref_display?: { key?: string; abs_path?: string; thumb_b64?: string; filename?: string } | null;
  option_slots?: (GptOption | null)[];
  element_char_ref_ok?: boolean;
  element_char_ref_error?: string;
};

export interface BgBeat {
  beat_id: string;
  beat_plan_source?: string;
  speaker?: string;
  pipeline?: string;
  beat_render_mode?: string;
  o3_generate_mode?: string;
  generation_mode?: BeatGenerationMode | string;
  dialogue_text?: string;
  scene_notes?: string;
  emotion?: string;
  status?: string;
  accepted_image_key?: string | null;
  reference_image?: { key?: string; abs_path?: string; thumb_b64?: string } | null;
  reference_image_locked?: boolean;
  bg_ref_image?: { key?: string; abs_path?: string; thumb_b64?: string } | null;
  bg_ref_image_locked?: boolean;
  element_char_ref_ok?: boolean;
  element_char_ref_error?: string;
  flux_options?: GptOption[];
  gpt_options?: GptOption[];
  bg_gpt_batch_job_id?: string | null;
  kling_o3_status?: string;
  kling_o3_still_stitch_approved?: boolean;
  kling_o3_prompt?: string;
  kling_o3_prompt_still?: string;
  o3_prompt_box_law?: boolean;
  kling_o3_video_path?: string;
  kling_o3_video_path_exists?: boolean;
  kling_o3_selected_at?: string;
  kling_o3_selection_pipeline_mismatch?: boolean;
  kling_o3_active_clip_pipeline?: string;
  kling_o3_options?: GptOption[];
  kling_o3_clips_dir?: string;
  kling_o3_disk_delivery_count?: number;
  kling_o3_element_delivery_count?: number;
  kling_o3_orphan_delivery_count?: number;
  kling_o3_replace_slot_index?: number;
  kling_o3_trim_start?: number;
  kling_o3_trim_back?: number | null;
  kling_o3_trim_end?: number | null;
  /** Trim/cut WYSIWYG path for magic-on-video path picker (server-enriched). */
  kling_o3_magic_video_source_path?: string;
  kling_o3_cut_start_s?: number;
  kling_o3_cut_end_s?: number;
  kling_o3_voice_fix_ui_job_id?: string | null;
  kling_o3_voice_fix_status?: string | null;
  kling_o3_voice_fix_error?: string | null;
  job_busy?: boolean;
  o3_current_job_id?: string | null;
  _derived?: BgBeatDerived;
  kling_native_lipsync_experiment_ui_job_id?: string | null;
  kling_native_lipsync_experiment_status?: string | null;
  kling_native_lipsync_experiment_route?: string | null;
  kling_native_lipsync_experiment_error?: string | null;
  kling_native_lipsync_experiment_error_code?: string | null;
  kling_native_lipsync_experiment_output_path?: string | null;
  kling_native_lipsync_experiment_passed_gate?: boolean | null;
  kling_native_lipsync_experiment_output_profile?: {
    width?: number;
    height?: number;
    min_dimension?: number;
    has_audio?: boolean;
  } | null;
  magic_still_path?: string | null;
  magic_video_path?: string | null;
  magic_still_path_exists?: boolean;
  magic_video_path_exists?: boolean;
  magic_canonical_kind?: 'still' | 'video' | null;
  magic_video_applies_to_active?: boolean;
  magic_still_applies_to_active?: boolean;
  storyboard_beat_id?: string | null;
  audio_file?: string | null;
  audio_file_exists?: boolean;
  start_frame_image?: { abs_path?: string } | null;
  end_frame_image?: { abs_path?: string } | null;
}

export interface BgSegment {
  event_id: string;
  phase: string;
  name?: string;
  arc_number?: number;
}
