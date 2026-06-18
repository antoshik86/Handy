# Vosk Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Vosk STT engine to Handy as an alternative to Whisper/ONNX, supporting old CPUs without SSE4.

**Architecture:** Add `EngineType::Vosk` to the model system, create a Vosk model entry for Russian, integrate Vosk transcription into the existing pipeline. Vosk model downloads as `.zip`, native `libvosk.dll` handled via build script or manual placement.

**Tech Stack:** Rust (vosk crate 0.3.1), zip crate for model extraction, Vosk Russian model (vosk-model-small-ru-0.22)

---

### Task 1: Add dependencies

**Files:**
- Modify: `src-tauri/Cargo.toml`
- Modify: `src-tauri/Cargo.toml` (add `zip` for Windows model extraction)

- [ ] **Step 1: Add vosk and zip crates to Cargo.toml**

Add after `transcribe-rs` dependency:
```toml
vosk = "0.3.1"
zip = "2.2"
```

- [ ] **Step 2: Build to verify deps resolve**

Run: `cargo check --target-dir target_check 2>&1`
Expected: builds with vosk/zip deps resolved. May fail if `libvosk.dll` is not found — that's expected for now.

---

### Task 2: Add EngineType::Vosk and model entry

**Files:**
- Modify: `src-tauri/src/managers/model.rs`

- [ ] **Step 1: Add Vosk variant to EngineType enum**

```rust
pub enum EngineType {
    Whisper,
    Parakeet,
    Moonshine,
    MoonshineStreaming,
    SenseVoice,
    GigaAM,
    Canary,
    Cohere,
    Vosk,  // <-- add this
}
```

- [ ] **Step 2: Add Vosk Russian model entry in `ModelManager::new()`**

Add after the Cohere model block in `available_models.insert(...)` chain:
```rust
available_models.insert(
    "vosk-ru".to_string(),
    ModelInfo {
        id: "vosk-ru".to_string(),
        name: "Vosk Russian".to_string(),
        description: "Lightweight Russian STT. Works on old CPUs without SSE4.".to_string(),
        filename: "vosk-model-small-ru-0.22".to_string(),
        url: Some("https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip".to_string()),
        sha256: None, // Vosk models don't publish sha256
        size_mb: 50,
        is_downloaded: false,
        is_downloading: false,
        partial_size: 0,
        is_directory: true,
        engine_type: EngineType::Vosk,
        accuracy_score: 0.60,
        speed_score: 0.50,
        supports_translation: false,
        is_recommended: false,
        supported_languages: vec!["ru".to_string()],
        supports_language_selection: false,
        is_custom: false,
    },
);
```

- [ ] **Step 3: Build to verify**

Run: `cargo check --target-dir target_check 2>&1`
Expected: compiles

---

### Task 3: Add zip extraction for Vosk model download

**Files:**
- Modify: `src-tauri/src/managers/model.rs` (add zip handling in download/extraction logic)

- [ ] **Step 1: Add zip import**

Add at top of model.rs:
```rust
use std::io::{Read, Write};
// zip already has Read/Write from std, no extra import needed
```

- [ ] **Step 2: Modify model download to handle .zip files**

In the download completion section (after SHA verification, around line 1210), find the block:
```rust
if model_info.is_directory {
```

Replace the extraction logic to handle both `.tar.gz` and `.zip`:

Find the block starting with:
```rust
if model_info.is_directory {
    // Track that this model is being extracted
```

After the `info!("Extracting archive for directory-based model: {}", model_id);` line, add zip detection before the tar extraction:

```rust
if model_info.filename.ends_with(".zip") || partial_path.to_string_lossy().ends_with(".zip") {
    // Handle .zip extraction
    let temp_extract_dir = self
        .models_dir
        .join(format!("{}.extracting", &model_info.filename));
    let final_model_dir = self.models_dir.join(&model_info.filename);

    if temp_extract_dir.exists() {
        let _ = fs::remove_dir_all(&temp_extract_dir);
    }
    fs::create_dir_all(&temp_extract_dir)?;

    let zip_file = File::open(&partial_path)?;
    let mut archive = zip::ZipArchive::new(zip_file)?;

    // Extract to temp directory
    for i in 0..archive.len() {
        let mut file = archive.by_index(i)?;
        let outpath = temp_extract_dir.join(file.name());

        if file.is_dir() {
            fs::create_dir_all(&outpath)?;
        } else {
            if let Some(p) = outpath.parent() {
                fs::create_dir_all(p)?;
            }
            let mut outfile = File::create(&outpath)?;
            std::io::copy(&mut file, &mut outfile)?;
        }
    }

    // Move to final location (same logic as tar)
    // Find the actual model directory (top-level dir in the zip)
    let entries: Vec<_> = fs::read_dir(&temp_extract_dir)?
        .filter_map(|e| e.ok())
        .filter(|e| e.file_type().map(|ft| ft.is_dir()).unwrap_or(false))
        .collect();

    if entries.len() == 1 {
        let source_dir = entries[0].path();
        if final_model_dir.exists() {
            fs::remove_dir_all(&final_model_dir)?;
        }
        fs::rename(&source_dir, &final_model_dir)?;
    } else {
        if final_model_dir.exists() {
            fs::remove_dir_all(&final_model_dir)?;
        }
        fs::rename(&temp_extract_dir, &final_model_dir)?;
    }
    let _ = fs::remove_dir_all(&temp_extract_dir);
} else {
    // existing tar.gz extraction logic stays as-is
    ...
}
```

- [ ] **Step 3: Build to verify**

Run: `cargo check --target-dir target_check 2>&1`
Expected: compiles

---

### Task 4: Implement Vosk transcription engine

**Files:**
- Modify: `src-tauri/src/managers/transcription.rs`

- [ ] **Step 1: Add helper function to convert f32 PCM to i16 PCM**

Add after the `use` statements:
```rust
/// Convert f32 PCM samples (-1.0 to 1.0) to i16 PCM samples (-32768 to 32767)
fn f32_to_i16_pcm(audio: &[f32]) -> Vec<i16> {
    audio.iter().map(|&s| {
        let clamped = s.clamp(-1.0, 1.0);
        (clamped * 32767.0) as i16
    }).collect()
}
```

- [ ] **Step 2: Add Vosk variant to LoadedEngine enum**

```rust
enum LoadedEngine {
    Whisper(WhisperEngine),
    Parakeet(ParakeetModel),
    Moonshine(MoonshineModel),
    MoonshineStreaming(StreamingModel),
    SenseVoice(SenseVoiceModel),
    GigaAM(GigaAMModel),
    Canary(CanaryModel),
    Cohere(CohereModel),
    Vosk(vosk::Recognizer),  // <-- add this
}
```

- [ ] **Step 3: Add Vosk model loading in `load_model()` method**

In the `load_model` method, add a new match arm after `EngineType::Cohere`:
```rust
EngineType::Vosk => {
    let model_path = model_path.to_string_lossy().to_string();
    let model = vosk::Model::new(&model_path).map_err(|e| {
        let error_msg = format!("Failed to load Vosk model {}: {}", model_id, e);
        emit_loading_failed(&error_msg);
        anyhow::anyhow!(error_msg)
    })?;
    let recognizer = vosk::Recognizer::new(&model, 16000.0).map_err(|e| {
        let error_msg = format!("Failed to create Vosk recognizer {}: {}", model_id, e);
        emit_loading_failed(&error_msg);
        anyhow::anyhow!(error_msg)
    })?;
    LoadedEngine::Vosk(recognizer)
}
```

- [ ] **Step 4: Add Vosk transcription in the transcription pipeline**

In the `transcribe` method, add a new match arm in the `catch_unwind` block (after `LoadedEngine::Cohere`):
```rust
LoadedEngine::Vosk(recognizer) => {
    let audio_i16 = f32_to_i16_pcm(&audio);
    let audio_bytes: &[u8] = bytemuck::cast_slice(&audio_i16);

    recognizer.accept_waveform(audio_bytes).map_err(|e| {
        anyhow::anyhow!("Vosk transcription failed: {:?}", e)
    })?;

    let result = recognizer.result();
    let text = result["text"].as_str().unwrap_or("").to_string();
    Ok(transcribe_rs::TranscriptionResult {
        text,
        ..Default::default()
    })
}
```

Note: `bytemuck::cast_slice` requires the `bytemuck` crate or we use `unsafe` std. Let's use a safe approach:
```rust
let audio_bytes: &[u8] = std::slice::from_raw_parts(
    audio_i16.as_ptr() as *const u8,
    audio_i16.len() * 2,
);
```

Actually, let's use `bytemuck` for safety. Add to Cargo.toml:
```toml
bytemuck = "1.16"
```

And use:
```rust
let audio_bytes: &[u8] = bytemuck::cast_slice(&audio_i16);
```

- [ ] **Step 5: Build to verify**

Run: `cargo check --target-dir target_check 2>&1`
Expected: compiles

---

### Task 5: Handle native Vosk library on Windows

**Files:**
- Create: `scripts/download-vosk-dll.ps1`
- Modify: build instructions in README or BUILD.md

- [ ] **Step 1: Create download script for Vosk Windows DLL**

Create `scripts/download-vosk-dll.ps1`:
```powershell
# Downloads Vosk Windows native DLL
$VoskVersion = "0.3.45"
$Url = "https://github.com/alphacep/vosk-api/releases/download/v$VoskVersion/vosk-win64-$VoskVersion.zip"
$OutputDir = Join-Path (Split-Path $PSScriptRoot -Parent) "src-tauri\resources\vosk"
$ZipPath = Join-Path $OutputDir "vosk-win64.zip"

New-Item -ItemType Directory -Force -Path $OutputDir

if (!(Test-Path (Join-Path $OutputDir "libvosk.dll"))) {
    Write-Output "Downloading Vosk DLL from $Url..."
    Invoke-WebRequest -Uri $Url -OutFile $ZipPath
    Expand-Archive -Path $ZipPath -DestinationPath $OutputDir -Force
    Remove-Item $ZipPath
    Write-Output "Vosk DLL downloaded to $OutputDir"
} else {
    Write-Output "Vosk DLL already present at $OutputDir"
}
```

- [ ] **Step 2: Add Vosk DLL path setup at app startup**

In `lib.rs` `run()` function, before the Tauri builder setup, add:
```rust
#[cfg(target_os = "windows")]
{
    // Add Vosk native library to PATH
    let vosk_dll_dir = portable::app_data_dir(&app_handle)
        .unwrap_or_else(|_| PathBuf::from("."))
        .join("vosk");
    if vosk_dll_dir.exists() {
        let current_path = std::env::var("PATH").unwrap_or_default();
        std::env::set_var("PATH", format!("{};{}", vosk_dll_dir.display(), current_path));
    }
}
```

Actually, this is getting complex. Let me simplify. The Vosk crate looks for the DLL in standard system paths. The simplest approach:

1. User manually downloads `libvosk.dll` from Vosk releases
2. Places it next to `handy.exe` (in the same directory as the built binary)
3. Or we place it in `src-tauri/resources/vosk/` and bundle it with the app

For the dev build, we can just place it manually. For distribution, we'd need to bundle it.

Let me simplify this task:

- [ ] **Step 1: Create a build script that downloads Vosk DLL**

Create `src-tauri/build.rs` that downloads Vosk DLL at build time:
```rust
fn main() {
    // Tell cargo to re-run if Vosk DLL path changes
    let vosk_dir = std::path::PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap())
        .join("resources")
        .join("vosk");
    
    let dll_path = vosk_dir.join("libvosk.dll");
    if !dll_path.exists() {
        println!("cargo:warning=Vosk DLL not found at {:?}. Download it from https://github.com/alphacep/vosk-api/releases", dll_path);
    }
    
    println!("cargo:rerun-if-changed={}", dll_path.display());
}
```

Actually, build scripts shouldn't download things. Let me keep it simple: just document the manual step.

---

### Task 6: Build and test

- [ ] **Step 1: Download Vosk native DLL**

Run the download script:
```powershell
.\scripts\download-vosk-dll.ps1
```
And copy `libvosk.dll` to `src-tauri/resources/vosk/`

- [ ] **Step 2: Set VOSK_PATH environment variable**

```powershell
$env:VOSK_PATH = (Get-Item "src-tauri/resources/vosk").FullName
```

- [ ] **Step 3: Build Handy**

```powershell
bun run tauri build
```

Expected: builds successfully

- [ ] **Step 4: Test transcription**

1. Launch Handy
2. Go to Settings → Models
3. Find "Vosk Russian" in the list
4. Download the model
5. Select it
6. Press the recording shortcut
7. Speak in Russian
8. Verify text appears

---

### Spec Coverage Check

- [x] EngineType::Vosk → Task 2
- [x] Vosk model entry (vosk-ru) → Task 2
- [x] Zip extraction for model → Task 3
- [x] Vosk transcription pipeline → Task 4
- [x] Native DLL handling → Task 5
- [x] Model download from alphacephei.com → Task 2
- [x] Frontend auto-discovers model → works automatically (existing UI)
