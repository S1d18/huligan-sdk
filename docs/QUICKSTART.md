# Huligan Antidetect — Quick Start

Два способа запуска — выбери свой:

| Способ | Для кого | Что нужно |
|--------|----------|-----------|
| **[A. Python SDK](#a-python-sdk-рекомендуется)** | Разработчик, автоматизация | Python 3.9+, `pip install` |
| **[B. Вручную](#b-ручной-запуск)** | Минимальная настройка | Только chrome.exe |

---

## A. Python SDK (рекомендуется)

Всё в 5 строк: запуск Chrome, прокси, фингерпринт, GeoIP — автоматически.

### 1. Установить

```bash
pip install huligan[playwright]
# или из GitHub:
pip install "huligan[playwright] @ git+https://github.com/S1d18/huligan-sdk.git"
```

### 2. Запустить

```python
import asyncio
from huligan import Browser

async def main():
    async with Browser(
        proxy="socks5://user:pass@ip:port",
        chrome_path="C:/huligan/chrome.exe",   # или авто-поиск
    ) as browser:
        page = await browser.new_page()
        await page.goto("https://browserscan.net")
        print(await page.title())
        await page.wait_for_timeout(30000)

asyncio.run(main())
```

**Что происходит автоматически:**
- Генерируется уникальный фингерпринт (50+ параметров)
- GeoIP определяет таймзону/язык/координаты по IP прокси
- Поднимается SOCKS5 форвардер (Chrome не поддерживает auth — форвардер решает)
- Chrome запускается с правильными флагами (DNS leak, WebRTC protection)
- CDP порт назначается автоматически

### 3. Свой фингерпринт

```python
from huligan import Browser, FingerprintGenerator

# Генерация с фиксированным seed (воспроизводимый результат)
gen = FingerprintGenerator(seed=12345)
profile = gen.generate(platform="Win32", gpu_vendor_preference="nvidia")

# Сохранить для повторного использования
with open("my_profile.conf", "w") as f:
    f.write(profile.to_conf())

# Запуск с готовым профилем
async with Browser(
    proxy="socks5://user:pass@ip:port",
    profile_path="C:/profiles/my_profile.conf",
) as browser:
    page = await browser.new_page()
```

### 4. Несколько браузеров

```python
async def main():
    proxies = [
        "socks5://user1:pass1@ip1:port1",
        "socks5://user2:pass2@ip2:port2",
    ]
    browsers = []
    for proxy in proxies:
        b = Browser(proxy=proxy)
        await b.start()
        browsers.append(b)

    # Каждый браузер — уникальный фингерпринт + своя геолокация
    for b in browsers:
        page = await b.new_page()
        await page.goto("https://example.com")

    for b in browsers:
        await b.close()
```

### 5. Все параметры Browser()

```python
Browser(
    chrome_path="C:/huligan/chrome.exe",  # авто-поиск если None
    proxy="socks5://user:pass@ip:port",   # или "ip:port:user:pass" или None
    proxy_type="socks5",                  # авто из URL если None
    profile_path="profile.conf",          # авто-генерация если None
    fingerprint={"platform": "Win32", "gpu_vendor_preference": "nvidia"},
    timezone="Europe/Moscow",             # авто из GeoIP если None
    language="ru-RU,ru",                  # авто из GeoIP если None
    cdp_port=9222,                        # авто если None
    headless=False,
    user_data_dir="C:/data/profile1",     # temp dir если None
    extra_args=["--disable-extensions"],
)
```

### 6. Автоматизация (mouse/keyboard)

Человекоподобная мышь и клавиатура — работает через CDP, не использует `page.evaluate()`:

```python
from huligan import Browser, human_like_mouse_click, human_like_type

async with Browser(proxy="socks5://user:pass@ip:port") as browser:
    page = await browser.new_page()
    await page.goto("https://example.com/login")

    # Клик с человекоподобной траекторией
    await human_like_mouse_click(page.locator("#username"), speed_mode="medium")

    # Набор текста с реалистичными задержками
    await human_like_type(page.locator("#username"), "myuser", speed_mode="medium")

    # Пароль — быстрая вставка
    await human_like_type(page.locator("#password"), "secret", speed_mode="paste")

    # Отправить форму
    await human_like_mouse_click(page.locator("button[type=submit]"), speed_mode="fast")
```

| Режим | Что делает |
|-------|-----------|
| `"slow"` | Медленный набор, 150-300мс между клавишами |
| `"medium"` | Средний, 80-150мс |
| `"fast"` | Быстрый, 30-80мс |
| `"paste"` | Мгновенная вставка через `keyboard.insert_text()` |

Больше примеров: [`huligan/examples/`](huligan/examples/)

---

## B. Ручной запуск

Без Python, без скриптов — только chrome.exe и .conf файл.

### 1. Скачать Chrome

ZIP из [Releases](../../releases) → распаковать.

### 2. Создать .conf

```ini
# profile.conf

# === Hardware ===
platform=Win32
cpu_cores=8
device_memory=8

# === Screen ===
screen_width=1920
screen_height=1080
screen_avail_width=1920
screen_avail_height=1040
color_depth=24
device_pixel_ratio=1.0

# === WebGL (GPU) ===
webgl_vendor=Google Inc. (NVIDIA)
webgl_renderer=ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 6GB Direct3D11 vs_5_0 ps_5_0, D3D11)

# === Noise ===
canvas_noise_seed=13549036856797210343
font_noise_seed=12348765902134
audio_noise_seed=0  # Must be 0 — non-zero values detected by BrowserScan as "Audio modified manually"

# === Network ===
connection_effective_type=4g
connection_downlink=10.0
connection_rtt=50

# === Geo / Locale ===
timezone=Europe/Moscow
languages=ru-RU,ru
geolocation_latitude=55.7182
geolocation_longitude=37.6077
geolocation_accuracy=50000

# === Media Devices ===
media_devices_video_input_label=HD WebCam
media_devices_audio_input_label=Microphone (HD WebCam)
media_devices_audio_output_label=Speakers (High Definition Audio)

# === Battery ===
battery_charging=true
battery_level=1.0
battery_charging_time=0
battery_discharging_time=inf
```

### 3. Запустить

```cmd
SET HULIGAN_CONFIG_PATH=C:\huligan\profile.conf
C:\huligan\chrome.exe --no-sandbox --user-data-dir=C:\huligan\data
```

### 4. С прокси (вручную)

```cmd
SET HULIGAN_CONFIG_PATH=C:\huligan\profile.conf
C:\huligan\chrome.exe --no-sandbox ^
  --user-data-dir=C:\huligan\data ^
  --proxy-server=socks5://127.0.0.1:1080 ^
  --host-resolver-rules="MAP * ~NOTFOUND, EXCLUDE 127.0.0.1" ^
  --force-webrtc-ip-handling-policy=disable_non_proxied_udp ^
  --lang=ru
```

### 5. С CDP (для автоматизации)

```cmd
SET HULIGAN_CONFIG_PATH=C:\huligan\profile.conf
C:\huligan\chrome.exe --no-sandbox --user-data-dir=C:\huligan\data --remote-debugging-port=9222 --remote-allow-origins=*
```

```python
browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
```

> **Важно:** `page.evaluate()` заблокирован форком — используйте locator-методы или `huligan.human_like_mouse_click` / `huligan.human_like_type` для автоматизации.

---

## Важные правила

| Правило | Почему |
|---------|--------|
| `--no-sandbox` обязателен | Без него env var `HULIGAN_CONFIG_PATH` не доходит до renderer |
| `HULIGAN_CONFIG_PATH` — абсолютный путь | Chrome меняет CWD при старте, относительный путь сломается |
| `--user-data-dir` уникальный для каждого профиля | Иначе браузеры будут конфликтовать |
| НЕ использовать `--no-geo` с SDK/лаунчером | Флаг отключает авто-настройку таймзоны/языка по GeoIP |

---

## Генерация фингерпринтов

### Через SDK (рекомендуется)

```python
from huligan import FingerprintGenerator

gen = FingerprintGenerator(seed=12345)  # seed для воспроизводимости
profile = gen.generate(
    platform="Win32",                    # или "MacIntel", "Linux x86_64"
    gpu_vendor_preference="nvidia",      # или "amd", "intel", None (случайный)
)
with open("profile.conf", "w") as f:
    f.write(profile.to_conf())
```

Генератор подбирает: экран, CPU, RAM, GPU + WebGL параметры, шрифты (79-159 для Windows), noise seeds, media devices, battery, connection.

### GPU тиры

| Тир | Пример webgl_renderer |
|-----|-----------------------|
| nvidia_high | ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 ... D3D11) |
| nvidia_mid | ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 6GB ... D3D11) |
| amd_discrete | ANGLE (AMD, AMD Radeon RX 7800 XT ... D3D11) |
| amd_integrated | ANGLE (AMD, AMD Radeon(TM) Graphics ... D3D11) |
| intel_integrated | ANGLE (Intel, Intel(R) UHD Graphics 770 ... D3D11) |
| intel_discrete | ANGLE (Intel, Intel(R) Arc(TM) A770 Graphics ... D3D11) |

---

## Проверка

| Сайт | Что проверяет | Ожидание |
|------|-------------|----------|
| [browserscan.net](https://www.browserscan.net/) | Полный fingerprint | **97%+** |
| [sannysoft.com](https://bot.sannysoft.com/) | Webdriver, CDP | **Все зелёные** |
| [rebrowser.net](https://bot-detector.rebrowser.net/) | CDP leaks | **No Detection** |
| [creepjs](https://abrahamjuliot.github.io/creepjs/) | Глубокий fingerprint | **0 lies, 0 bold-fail** |

---

## Полная документация

| Документ | Что внутри |
|----------|------------|
| [README.md](../README.md) | Обзор SDK, API reference |
| [docs/BROWSER_AUTOMATION.md](BROWSER_AUTOMATION.md) | Что работает / заблокировано в Playwright |
| [docs/PROXY_LAUNCH_GUIDE.md](PROXY_LAUNCH_GUIDE.md) | Прокси: форвардер, DNS leak, WebRTC |
| [docs/GEOIP_SETUP.md](GEOIP_SETUP.md) | Настройка MaxMind GeoLite2 |
| [examples/](../examples/) | Примеры SDK |
