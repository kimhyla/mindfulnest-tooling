# Universal Container Implementation Plan
**For Consolidating MindfulNest Production Tools**

---

## Vision

Replace 4 hand-built, 70%-duplicated HTML builders with a shared Python base class and API client library. Reduce code from ~4,300 lines (with duplication) to ~1,500 lines (base + client shared, tools inherit). Enable consistent CLI, state management, audit patterns, and Directus registration across all current and future tools.

---

## Phase 1: Foundation (2–3 hours)

### 1.1 Create `/Production/base.py` — BaseHTMLBuilder Class

**Core responsibilities:**
- Scaffold HTML head + body structure (DOCTYPE, meta, CSS reset, dark theme)
- Manage asset embedding (images, audio, video)
- Generate canonical localStorage keys
- Provide standard export/import JSON pattern
- Handle feature metadata (version, generated_at, features dict)
- Implement standard CLI argument parser

**Key methods to implement:**

```python
class BaseHTMLBuilder:
    
    # Constructor & lifecycle
    def __init__(self, title, subtitle, module_id=None, event_number=None):
        self.title = title
        self.subtitle = subtitle
        self.module_id = module_id
        self.event_number = event_number
        self.assets = {}          # {key: data_uri}
        self.metadata = {}        # For feature extraction
    
    # Asset management (inherited by all tools)
    def embed_asset(self, key: str, file_path: str, asset_type: str) -> str:
        """Encode file, store in self.assets, return data URI."""
        # asset_type in ["image", "audio", "video"]
        # Calls shared encode_asset() from assets.py
        pass
    
    def embed_assets_batch(self, mapping: dict) -> None:
        """Embed multiple assets: {"key1": ("path1", "audio"), ...}"""
        pass
    
    # HTML generation (base scaffold, tool-specific content overridden by subclass)
    def build(self) -> str:
        """Return complete HTML string."""
        parts = [
            self._head(),
            self._body(),
            self._script()
        ]
        return ''.join(parts)
    
    def _head(self) -> str:
        """Standard head: meta, title, base CSS."""
        # Inject tool-specific CSS via _get_tool_css() override
        pass
    
    def _body(self) -> str:
        """Standard body structure. Subclasses override to add content."""
        # Provides: <h1>, <p.subtitle>, <div.controls>, <div.content>, <div.export>
        # Subclasses fill .controls and .content
        raise NotImplementedError("Subclass must override _body()")
    
    def _script(self) -> str:
        """Standard script: asset injection, state, localStorage, export."""
        # Injects: API_KEY, MODEL, SETTINGS, AUDIO_DATA, TH, VID, etc.
        # Provides: showToast(), saveToLocalStorage(), exportJSON()
        # Subclasses override to add playback/interaction logic
        raise NotImplementedError("Subclass must override _script()")
    
    # File I/O
    def save(self, output_path: str) -> str:
        """Build HTML and write to file. Return path."""
        html = self.build()
        with open(output_path, 'w') as f:
            f.write(html)
        self.metadata['file_path'] = output_path
        self.metadata['file_size_kb'] = len(html) // 1024
        return output_path
    
    # Feature extraction (standard for all tools)
    def extract_features(self) -> dict:
        """Return feature manifest for audit/regression check."""
        features = {
            'version': 1,
            'tool': self.__class__.__name__,
            'generated_at': datetime.now().isoformat(),
            'file_path': self.metadata.get('file_path'),
            'file_size_kb': self.metadata.get('file_size_kb', 0),
            'asset_count': len(self.assets),
        }
        # Subclasses override to add tool-specific features
        return {**features, **self.metadata}
    
    # Directus integration (same for all tools)
    def register_in_directus(self, directus_client) -> bool:
        """Auto-register in Directus. Return True if success."""
        # Calls: directus_client.register_visual_asset()
        # directus_client.patch_modules()
        # directus_client.log_activity()
        # All use self.module_id, self.event_number, self._get_asset_type(), etc.
        pass
    
    # Subclass hooks (override in subclasses)
    def _get_asset_type(self) -> str:
        """e.g., "storyboard_html", "cropper_html", etc."""
        raise NotImplementedError
    
    def _get_tracking_field(self) -> str:
        """e.g., "storyboard_status", "cropper_status", etc."""
        raise NotImplementedError
    
    def _get_tool_css(self) -> str:
        """Tool-specific CSS overrides. Base provides dark theme."""
        return ""
    
    # CLI helpers (standard argparse setup)
    @classmethod
    def create_arg_parser(cls) -> argparse.ArgumentParser:
        """Standard argument parser with common args."""
        parser = argparse.ArgumentParser()
        # Common args: --title, --subtitle, --module-id, --event-number, --smoke-test, --audit, --output
        # Subclasses add tool-specific args
        return parser
```

**Deliverables:**
- `production/base.py` (~400 lines)
- Unit tests for base class (smoke test, feature extraction, file I/O)

---

### 1.2 Create `/Production/api_client.py` — DirectusClient Class

**Core responsibilities:**
- Consolidated credential reading (API_KEYS_MASTER.md + env vars fallback)
- Directus authentication (token caching)
- Unified registration flow (visual_assets, modules, activity_log)
- Query wrappers (registry images, module data, activity history)

**Key methods:**

```python
class DirectusClient:
    
    def __init__(self, use_api_keys_master=True):
        """Initialize with credentials from API_KEYS_MASTER.md or env vars."""
        self.base_url = "https://directus-production-3460.up.railway.app"
        self.token = None
        if use_api_keys_master:
            self.email, self.password = read_credentials_from_api_keys_master()
        else:
            self.email = os.environ.get('DIRECTUS_EMAIL')
            self.password = os.environ.get('DIRECTUS_PASSWORD')
    
    def authenticate(self) -> str:
        """Get and cache auth token."""
        resp = requests.post(
            f"{self.base_url}/auth/login",
            json={"email": self.email, "password": self.password}
        )
        self.token = resp.json()['data']['access_token']
        return self.token
    
    # Visual assets registration
    def register_visual_asset(self, filename: str, filepath: str, module_id: int,
                            event_number: int, asset_type: str, status: str,
                            build_mode: str, feature_summary: dict) -> int:
        """Register or update in prod_visual_assets. Return asset_id."""
        # Check if exists (filter by filename)
        # POST if new, PATCH if exists
        # Return asset_id
        pass
    
    # Module tracking
    def patch_modules(self, module_id: int, tracking_updates: dict) -> bool:
        """Update module tracking fields (e.g., storyboard_status, tts_audition_status)."""
        # PATCH {base_url}/items/prod_modules/{module_id}
        # Return True if success
        pass
    
    # Activity log
    def log_activity(self, action: str, details: dict) -> int:
        """Log build action to prod_activity_log. Return log_id."""
        # POST {base_url}/items/prod_activity_log
        # Return log_id
        pass
    
    # Registry queries
    def query_visual_assets(self, module_id: int, event_number: int) -> list:
        """Query prod_visual_assets for module+event. Return asset list."""
        pass
    
    def query_modules(self, module_id: int) -> dict:
        """Query prod_modules for single module. Return module dict."""
        pass
    
    # Helper: smoke test (check connectivity + schema)
    def smoke_test(self) -> dict:
        """Verify connectivity and schema. Return {directus_ok, prod_visual_assets_ok, ...}."""
        pass
```

**Deliverables:**
- `production/api_client.py` (~300 lines)
- Unit tests for credential reading, auth, registration flow
- Integration test with staging Directus instance

---

### 1.3 Create `/Production/assets.py` — Shared Asset Encoding

**Consolidate:**
- `encode_image()` (used by storyboard + cropper)
- `encode_audio()` (used by storyboard + tts_review + animation_review)
- `encode_video()` (used by animation_review)

```python
def encode_asset(file_path: str, asset_type: str, additional_params: dict = None) -> str:
    """
    Unified asset encoder. Returns data URI.
    
    asset_type in ["image", "audio", "video"]
    additional_params: tool-specific (e.g., {"thumb_size": 80} for storyboard)
    """
    pass

def encode_image(path: str, thumb_size: int = 80, ref_size: int = 200) -> tuple:
    """Return (thumbnail_b64, reference_b64)."""
    pass

def encode_audio(path: str) -> str:
    """Return base64 audio data URI."""
    pass

def encode_video(path: str) -> str:
    """Return base64 video data URI."""
    pass
```

**Deliverables:**
- `production/assets.py` (~100 lines)
- Unit tests for each encoding function

---

## Phase 2: Refactor Existing Tools (3–4 hours)

### 2.1 Refactor `build_storyboard.py`

**Changes:**
1. Inherit from `BaseHTMLBuilder`
2. Remove credential reading (use `DirectusClient`)
3. Remove registration code (inherit from base)
4. Remove asset encoding (use `encode_image()`, `encode_audio()` from assets.py)
5. Override: `_body()`, `_script()`, `_get_asset_type()`, `_get_tracking_field()`, `extract_features()`
6. Keep: registry query, feature comparison, image map export (tool-specific logic)

**Expected reduction:** 1,427 → ~600 lines (60% reduction)

```python
class StoryboardBuilder(BaseHTMLBuilder):
    
    def _body(self) -> str:
        """Storyboard-specific body: controls, timeline, export panel."""
        pass
    
    def _script(self) -> str:
        """Storyboard-specific script: render engine, playback, drag-drop."""
        pass
    
    def _get_asset_type(self) -> str:
        return "storyboard_html"
    
    def _get_tracking_field(self) -> str:
        return "storyboard_status"
    
    def extract_features(self) -> dict:
        features = super().extract_features()
        # Add storyboard-specific: image_count, line_count, has_drag_drop, etc.
        return features
```

---

### 2.2 Refactor `build_cropper.py`

**Changes:**
1. Inherit from `BaseHTMLBuilder`
2. Remove credential reading, asset encoding
3. Override: `_body()`, `_script()`, `_get_asset_type()`, `_get_tracking_field()`
4. Keep: canvas crop logic (tool-specific)

**Expected reduction:** 797 → ~350 lines (56% reduction)

---

### 2.3 Refactor `build_tts_review.py`

**Changes:**
1. Inherit from `BaseHTMLBuilder`
2. Remove credential reading, asset encoding, registration code
3. Override: `_body()`, `_script()`, `_get_asset_type()`, `_get_tracking_field()`
4. Keep: ElevenLabs regeneration logic (tool-specific)

**⚠️ Security fix during refactor:** Move API key to backend proxy or secure token exchange (out of scope for this refactor, but flag it).

**Expected reduction:** 655 → ~300 lines (54% reduction)

---

### 2.4 Refactor `build_animation_review.py`

**Changes:**
1. Inherit from `BaseHTMLBuilder`
2. Remove credential reading, asset encoding
3. Override: `_body()`, `_script()`, `_get_asset_type()`, `_get_tracking_field()`, `extract_features()`
4. Keep: manifest reading, smoke-test validation (tool-specific)

**Expected reduction:** 1,424 → ~600 lines (58% reduction)

---

## Phase 3: Add Shared HTML Components (2 hours)

### 3.1 Create `/Production/html_templates/` Directory

**Base components:**
- `base_style.css` — Dark theme reset, layout grid, button styles
- `base_script.js` — Utility functions (showToast, saveToLocalStorage, exportJSON)
- `components/play_button.html` — Reusable play button component
- `components/selector.html` — Reusable select/dropdown component
- `components/export_panel.html` — Reusable export panel component

**Usage in tools:**
```python
def _body(self) -> str:
    # Import standard components
    from html_templates import render_export_panel, render_selector
    
    parts = []
    parts.append(f"<h1>{self.title}</h1>")
    parts.append(render_export_panel(id="export_panel"))
    # ... tool-specific content
    return ''.join(parts)
```

---

## Phase 4: Standardize CLI Interface (1 hour)

### 4.1 Unified CLI Pattern for All Tools

```bash
# All tools support:
python3 build_tool.py --help

# Standard args (all tools):
python3 build_tool.py \
  --input data.json \
  --output tool.html \
  --title "Event 1" \
  --subtitle "Arc 1" \
  --module-id M1 \
  --event-number 1 \
  --smoke-test \
  --audit previous.html

# Tool-specific args (documented per tool):
python3 build_storyboard.py --registry --lines lines.json  # registry mode
python3 build_animation_review.py --manifest beats.json    # manifest mode
```

**Implementation:**
```python
# In base.py:
class BaseHTMLBuilder:
    
    @classmethod
    def create_arg_parser(cls, tool_name: str) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            description=f"Build MindfulNest {tool_name} HTML tool"
        )
        # Common args
        parser.add_argument("--input", help="Input JSON/config file")
        parser.add_argument("--output", required=True, help="Output HTML path")
        parser.add_argument("--title", default="", help="Page title")
        parser.add_argument("--subtitle", default="", help="Page subtitle")
        parser.add_argument("--module-id", type=int, help="Module ID for Directus registration")
        parser.add_argument("--event-number", type=int, help="Event number for Directus registration")
        parser.add_argument("--smoke-test", action="store_true", help="Connectivity test only")
        parser.add_argument("--audit", help="Extract features from existing HTML")
        parser.add_argument("--audit-previous", help="Compare current vs previous for regressions")
        # Subclass adds tool-specific args via parser.add_argument()
        return parser
```

---

## Phase 5: Add Metadata to HTML (1 hour)

### 5.1 Embed Feature Metadata in HTML Comment

**Add to every built HTML:**
```html
<!-- MINDFULNEST METADATA:
{
  "version": "1",
  "tool": "build_storyboard.py",
  "generated_at": "2026-04-14T10:30:00Z",
  "module_id": 1,
  "event_number": 1,
  "build_mode": "registry",
  "features": {
    "images": 8,
    "lines": 42,
    "audio": 15,
    "drag_drop": true,
    "play_all": true,
    "export": true
  }
}
-->
```

**Benefits:**
- Feature extraction no longer needs regex parsing
- Version history can be tracked
- Metadata human-readable in file itself

---

## Phase 6: Unified Approval Format (1 hour)

### 6.1 Standard Verdict JSON Schema

All approval/review tools should export:

```json
{
  "tool": "build_tts_review.py" | "build_animation_review.py",
  "event_id": "m1_event_1",
  "generated_at": "2026-04-14T10:30:00Z",
  "items": [
    {
      "id": "line_02" | "beat_01",
      "verdict": "approved" | "redo" | "pending" | "selected",
      "value": "approved" | 2 | null,
      "metadata": {
        "speaker": "Guide Bird",
        "text": "Are you OK?",
        "regenerations": 0,
        "saved": true
      }
    }
  ]
}
```

---

## Phase 7: Testing & Validation (2–3 hours)

### 7.1 Unit Tests

- `test_base.py`: BaseHTMLBuilder lifecycle, build(), save(), extract_features()
- `test_api_client.py`: Credential reading, auth, registration, queries
- `test_assets.py`: encode_image(), encode_audio(), encode_video()
- `test_storyboard.py`: StoryboardBuilder overrides, registry mode
- `test_cropper.py`: CropperBuilder, min_dimension validation
- `test_tts_review.py`: TTSReviewBuilder, ElevenLabs integration
- `test_animation_review.py`: AnimationReviewBuilder, manifest validation

### 7.2 Integration Tests

- Full build→register→audit→compare cycle for each tool
- Multi-tool consistency (same Directus output format)
- Credential reading (API_KEYS_MASTER.md vs env vars)
- Feature regression detection (break a feature, audit catches it)

### 7.3 Manual Testing

- Build each tool with sample data
- Verify Directus registration (check all 4 collections)
- Test audit + compare for regressions
- Test CLI modes (--smoke-test, --audit, --audit-previous)
- Test on multiple browsers (Chrome, Safari, Firefox)

---

## Phase 8: Documentation (1 hour)

### 8.1 Update Existing Docs

- `TOOLS_ARCHITECTURE_AUDIT.md`: Add "Universal Container Implementation" section
- `TOOLS_QUICK_REFERENCE.md`: Update CLI examples to show inherited patterns
- `PIPELINE_BRAIN_v1.md`: Update references to new base class

### 8.2 Create New Docs

- `production/BASE_BUILDER_API.md`: BaseHTMLBuilder class reference
- `production/DIRECTUS_CLIENT_API.md`: DirectusClient class reference
- `production/ASSETS_REFERENCE.md`: Asset encoding functions reference
- `production/HTML_COMPONENTS.md`: Reusable component library
- `production/TOOL_DEVELOPMENT_GUIDE.md`: How to build a new tool (inherit from base, override 3 methods, done)

---

## Implementation Timeline & Effort Estimate

| Phase | Task | Hours | Effort | Owner |
|-------|------|-------|--------|-------|
| **1.1** | base.py | 2 | Medium | Claude |
| **1.2** | api_client.py | 2 | Medium | Claude |
| **1.3** | assets.py | 0.5 | Low | Claude |
| **2.1** | Refactor storyboard.py | 1 | Low | Claude |
| **2.2** | Refactor cropper.py | 0.5 | Low | Claude |
| **2.3** | Refactor tts_review.py | 0.5 | Low | Claude |
| **2.4** | Refactor animation_review.py | 1 | Low | Claude |
| **3.1** | HTML templates + components | 1.5 | Low | Claude |
| **4.1** | Unified CLI | 0.5 | Low | Claude |
| **5.1** | Metadata embedding | 0.5 | Low | Claude |
| **6.1** | Unified verdict format | 0.5 | Low | Claude |
| **7** | Testing + validation | 3 | High | Claude + Manual |
| **8** | Documentation | 1.5 | Low | Claude |
| **Total** | | **16** | **~2 days** | |

---

## Success Criteria

✅ All 4 tools refactored and passing existing functionality tests
✅ Code duplication reduced from ~4,300 lines to ~1,500 lines (65% reduction)
✅ All 4 tools share same CLI interface (--input, --output, --smoke-test, --audit, etc.)
✅ All registration flows identical (same Directus payload structure, same activity log format)
✅ Feature extraction no longer requires regex parsing (embedded metadata)
✅ A 5th tool (future) can be built in <2 hours by inheriting BaseHTMLBuilder + implementing 3 methods
✅ All tests passing (unit + integration)
✅ Documentation complete + reviewed

---

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Refactoring breaks existing tools | Medium | High | Comprehensive test suite before refactor; keep old tools runnable in parallel during transition |
| BaseHTMLBuilder too rigid, tools need custom overrides | Medium | Medium | Make base methods more granular (e.g., separate _build_head_css() + _build_head_meta()); provide plenty of hooks |
| Directus schema changes during refactor | Low | Medium | Pin DirectusClient to known schema version; handle 5xx errors gracefully (fallback warning) |
| Kim's workflows disrupted | Low | High | Test new tools with Kim's actual workflows before rollout; coordinate timing around production events |
| Asset encoding performance regresses | Low | Low | Profile new encode_asset() against old functions; PIL vs Pillow version differences |

---

## Post-Implementation Follow-Up

### Quick Wins (Future)
1. **Server-side sync layer:** Backend endpoint for localStorage state sync + multi-tab coordination
2. **TTS_Review security fix:** Move ElevenLabs API key to backend proxy
3. **Batch operations:** Add --batch-regenerate, --batch-export flags to tools
4. **Composite review tool:** 5th tool that combines storyboard + animation + TTS in tabbed interface

### Long-Term (Q2/Q3 2026)
1. **Mobile-responsive HTML builders:** Redesign for iPad editing workflows
2. **Real-time collaboration:** WebSocket sync for multiple editors on same storyboard
3. **Asset versioning in Directus:** Track which image version (v1, v2, v3) is used in each storyboard
4. **Automated feature regression detection:** Hook into CI/CD; reject builds that lose features

---

## Conclusion

This refactoring pays for itself in the first new tool. By implementing a shared BaseHTMLBuilder + DirectusClient + assets library, we unlock:
- 60% code reduction across 4 tools
- Consistent UX/UI/API across all tools
- Easier testing and debugging
- 2-hour turnaround for future tools
- Platform for advanced features (batch ops, server sync, versioning)

**Recommended start date:** After Kim approves Phase 2 refactoring impact assessment (request code review of 1–2 refactored tools).

