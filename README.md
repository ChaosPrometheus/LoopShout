# LoopShout

**Простой open-source клиент для вещания системного звука Windows на Shoutcast-сервер.**

Лёгкий аналог [BUTT](https://danielnoethen.de/butt/), созданный только для работы с протоколом Shoutcast.

![Python](https://img.shields.io/badge/Python-3.8+-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## Скриншот

<img width="519" height="670" alt="1" src="https://github.com/user-attachments/assets/33b959e8-ce4c-41e8-84c0-7ad888291301" />

## Возможности

- Захват системного звука Windows (WASAPI Loopback)
- Вещание на Shoutcast v1 и v2
- Выбор битрейта (64–320 kbps)
- Автоматическое восстановление захвата при переключении треков
- Сохранение настроек
- Простой и понятный интерфейс
- Индикатор уровня звука

## Установка

1. Установите Python 3.8 или новее
2. Установите зависимости:
pip install pyaudiowpatch lameenc numpy
