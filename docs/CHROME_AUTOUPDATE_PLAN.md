# Plan: manifest-driven Chrome resolution (развязка «браузер vs SDK-релиз»)

Status: proposed (2026-07-15). Do after the thin-app migration settles.

## Problem

Пропатченный Chrome обновляется ~ежемесячно, но сейчас каждый билд требует правки
кода SDK и нового релиза SDK:

- версия зашита в `version.py:CHROME_VERSION`;
- sha256 дублируется руками в `installer.py:_KNOWN_SHA256`;
- `find_chrome()` (chrome.py:57,66) резолвит кэш и авто-download только под `CHROME_VERSION`.

При этом `huligan-releases/manifest.json` **уже существует** и несёт всё нужное
(`latest`, `versions.{ver}.win64.{asset,size,sha256}`), а `installer.latest_version()`
уже умеет его читать — но никуда не подключён. То есть 80% инфраструктуры есть,
не хватает только резолва «из манифеста, а не из хардкода».

Что НЕ проблема (уже правильно by design):
- UA / GREASE / XBV / sec-ch-ua живут в **бинарнике**, не в SDK (`version.py` docstring).
  Обновление бинарника само подтягивает корректный UA. В SDK тут делать нечего.
- Оффлайн-first уже работает: `ensure_chrome()` при горячем кэше — O(1), сеть не трогает.
- Кэш хранит все версии и не чистит → откат = передать старую версию. Rollback де-факто есть.

## Goal

Месячный билд = обновил `manifest.json` в huligan-releases → клиенты подхватывают.
**Релиз SDK не нужен**, пока не менялась схема `.conf` или API запуска.

---

## Phase 1 — manifest-driven `ensure_chrome` (ядро, обязательно)

Единственное изменение с реальной отдачей. Всё остальное — опционально поверх него.

1. **`installer.py`: резолв версии + sha из манифеста.**
   - Новый `resolve_version(channel="pinned") -> (version, sha256)`:
     - `pinned` → `(CHROME_VERSION, _KNOWN_SHA256[CHROME_VERSION])` — сеть не нужна.
     - `stable`/`latest` → тянет `manifest.json`, берёт `versions[latest].win64.sha256`.
   - `ensure_chrome(version=None, channel="pinned")`: если `version` явно задан — как сейчас;
     иначе резолвит через `resolve_version(channel)`.
   - **sha256 берётся из манифеста**, `_KNOWN_SHA256` остаётся только оффлайн-фолбэком
     (для `pinned` без сети). Больше не редактируем словарь на каждый билд.

2. **Кэш манифеста с TTL.** `~/.huligan/manifest.json` + `manifest.json.ts`.
   TTL по умолчанию 24ч. `resolve_version` для non-pinned читает кэш, ходит в сеть
   только если протух. `pinned` в сеть не ходит никогда (воспроизводимость ферм/чекера).

3. **`chrome.py:find_chrome`: канал вместо хардкода.**
   - Читать канал из `HULIGAN_CHROME_CHANNEL` (env), дефолт `pinned`.
   - Шаг 5 (cache probe) и шаг 7 (auto_install) резолвят версию через канал,
     а не `CHROME_VERSION` напрямую. `pinned` → поведение байт-в-байт как сейчас.

**Совместимость / безопасность дефолта:**
- Дефолт `pinned` — фермы и чекер воспроизводимы, ничего само не апдейтится.
- `latest` двигается в манифесте **вручную оператором** после валидации
  (BrowserScan 100%×2 — визуальный read авторитетнее скрейпера). SDK ничему не «доверяет»
  автоматически: он лишь читает уже-подписанный оператором `latest`.

---

## Phase 2 — compat-гейт по схеме `.conf` (не по min/max_sdk) — DONE (2026-07-15)

Ось совместимости у нас — **схема `.conf`** (`conf_spec.py`) и флаги запуска,
а не «SDK↔браузер» вообще (история `version.py`: почти все мажоры — «no new .conf key»).

- [x] `CONF_SCHEMA_VERSION` в `conf_spec.py` (=1 baseline; bump только при новом .conf-ключе).
- [x] В `manifest.json`: на версию добавлено `min_conf_schema` (все 147–150 = 1).
- [x] `resolve_version`/`ensure_chrome` кидают `IncompatibleBuildError`, если
  `min_conf_schema > CONF_SCHEMA_VERSION`, с текстом «обнови huligan-sdk».
- [x] `find_chrome` при несовместимости деградирует к pinned-билду (гарантированно
  совместимому) с предупреждением, а не роняет запуск.
- [x] Гейт не трогает `pinned` и baked-in версии (`_KNOWN_SHA256`) — они офлайн и
  совместимы by construction. Манифест без `min_conf_schema` не гейтится (старые манифесты).
- Экспортированы `IncompatibleBuildError`, `CONF_SCHEMA_VERSION`.

**Контракт на будущее:** при добавлении нового ключа в `render_conf()` — в том же
изменении bump `CONF_SCHEMA_VERSION`, а в манифесте у билдов, которые этот ключ
требуют, ставить новый `min_conf_schema`.

---

## Phase 3 — CLI (`huligan chrome ...`) — DONE (2026-07-15)

- [x] `pyproject.toml`: `[project.scripts] huligan = "huligan.__main__:main"`.
- [x] `huligan chrome list` — кэш + effective channel + манифест (latest/channels/published).
- [x] `huligan chrome update [--channel pinned|stable|latest] [--check]` — резолв+download;
  `--channel` также персистит канал; `--check` только сверяет, ничего не качает; несовместимый билд → rc 2.
- [x] `huligan chrome pin <ver>` / `--clear` / без арг (показать) — персист в `config.json` под cache-root.
- [x] `huligan chrome prune [--keep N]` — удаляет старые версии, защищает pinned default + текущий target.
- [x] `huligan version`.
- Персист (channel/pinned_version) в `_cache_root()/config.json`; `HULIGAN_CHROME_CHANNEL` (env) всегда перекрывает.
- `find_chrome` теперь резолвит через `installer.resolve_launch_target()` (env → config → default).

Для чекера/ферм: `pinned` + ежемесячный осознанный `huligan chrome update --channel stable`.

---

## Phase 4 — автоматизация ПУБЛИКАЦИИ манифеста (не сборки)

Сборку GHA не потянет (локальная Windows-машина 192.168.1.120, ~100 ГБ исходников,
часы ninja). Автоматизируем только метаданные:

- Скрипт `huligan-releases/tools/publish.py`: после локальной сборки+валидации
  считает sha256/size, дописывает запись в `versions`, двигает `latest`, коммитит.
- Убирает ручное редактирование JSON и рассинхрон sha256 между манифестом и релизом.
- (Опц.) GHA-валидатор манифеста на PR: схема + что каждый asset реально существует в релизе.

---

## Порядок и объём

- **Phase 1** — единственное, что реально надо; ~полдня, покрыто юнит-тестами
  (мокать urlopen как в `tests/test_persistent.py`). После него месячный билд не трогает SDK.
- Phase 2–4 — инкрементально, каждая независимая, по необходимости.

## Не делать

- Не выводить UA/sec-ch-ua из версии в SDK — это делает бинарник.
- Не строить GHA-пересборку Chromium.
- Не менять дефолт на `latest` — фермы/чекер должны оставаться `pinned`.
- Не ходить в сеть на каждом `Browser()` — только по TTL/каналу non-pinned.
