# Feature: agento-control-remote
Gateway & Remote Control for Xiaozhi ESP32 Robot integrating with official xiaozhi.me cloud.

## Specs
- S1: "va a tener el control remoto para cambiarle el rostro a la gente cuando nosotros lo queramos, que eso está integrado en el proyecto que te estoy presentando."
- S2: "Va a tener la posibilidad de desactivar el micrófono desde el control remoto. Me interesaría muchísimo hacer eso, como te estoy diciendo."
- S3: "Y al desactivar el micrófono poder activar el micrófono desde un teléfono, desde el control remoto que en este caso va a ser un dispositivo y a través del teléfono se enviaría la voz para el audio con el que tiene que interactuar el robot. ... se debe conectar a las apis de https://xiaozhi.me/"
- S4: "Vamos a crear una imagen que permita hacer los siguientes aspectos" - Mobile-first PWA / Web UI with emotion buttons, mute toggle, and Push-To-Talk streaming.
- S5: Standalone container Dockerfile & docker-compose configuration for easy deployment and event execution.

## Tasks
- T1 (S1, S2, S3): Core async gateway server with Xiaozhi protocol bridge, emotion injector, mic mute gate, and phone audio forwarder.
- T2 (S4): Mobile-first Web UI / PWA with Push-To-Talk, emotion selector, and status dashboard.
- T3 (S5): Container image build (Dockerfile, docker-compose.yml), automated test suite, and run documentation.

## Log
- L1: User requested a dedicated project named `agento-control-remote` connecting to `https://xiaozhi.me/` to control faces, mute the robot mic, and use a phone mic for noisy venue interaction.
