# Vosk Integration for Handy (CPU без SSE4)

## Problem
Handy использует Whisper/ONNX модели через `transcribe-rs`, который требует SSE4.1/SSE4.2 инструкций CPU. На процессоре AMD A6-3410MX (SSE3/SSE4a, без SSE4.1) эти модели не запускаются.

## Solution
Добавить Vosk как новый движок распознавания. Vosk использует Kaldi и не требует SSE4.1 — работает на SSE3.

## Архитектура

### 1. Новый EngineType::Vosk
- `model.rs`: добавить `Vosk` в `EngineType` enum
- Новая модель `"vosk-ru"`:
  - Модель: `vosk-model-small-ru-0.22` (~50MB)
  - URL: `https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip`
  - Тип: directory-based (как Parakeet/GigaAM)
  - Язык: только `ru`

### 2. Новая зависимость
- `Cargo.toml`: `vosk = "0.3.1"` — Safe Rust wrapper around Vosk API
- Vosk требует нативную библиотеку `libvosk.dll`. План:
  - Vosk crate уже ищет `VOSK_PATH` или `VOSK_ROOT` env vars
  - Для сборки: можно указать путь к предустановленному Vosk SDK
  - Альтернатива: использовать `vosk-sys` и статическую линковку

### 3. Загрузка модели
- Модель Vosk — `.zip` архив (не `.tar.gz`)
- Нужен новый обработчик распаковки в `model.rs` (или переиспользовать существующий с поддержкой zip)
- Файлы: `vosk-model-small-ru-0.22/`:
  - `am/` — акустическая модель
  - `conf/` — конфиги
  - `graph/` — граф
  - `ivector/` — i-векторы
  - `rescore/` — рескоринг
  - `rnnlm/` — RNNLM

### 4. Транскрипция (transcription.rs)
- Новый `LoadedEngine::Vosk(vosk::Recognizer)`
- Пайплайн:
  1. Audio → VAD (Silero VAD, уже есть)
  2. VAD-сегменты → Vosk Recognizer
  3. Vosk → текст
  4. Пост-обработка (custom words, фильтры) — уже есть

- Vosk работает с `Vec<f32>` PCM audio (совпадает с текущим форматом)
- Параметры: sample_rate = 16000 (как сейчас)

### 5. Конфигурация
- Settings: `selected_language` по умолчанию `ru`
- Vosk модель не поддерживает language selection (только русский)
- Accelarator settings не применяются (Vosk всегда CPU)

### 6. Фронтенд
- Модель появится в списке автоматически
- UI меняться не должен

## Ограничения
- Vosk точнее на чистом русском, хуже на code-switching
- Только русский язык (можно добавить другие Vosk модели позже)
- Vosk медленнее Whisper на современных CPU, но достаточно быстр для A6

## Тестирование
- Собрать Handy с Vosk backend
- Проверить запуск на AMD A6-3410MX
- Проверить запись и распознавание русской речи
- Проверить глобальную клавишу и вставку текста
