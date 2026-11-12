import asyncio
import os
import logging
import uvicorn

SSL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ssl")
KEY_PATH = os.path.join(SSL_DIR, "key.pem")
CERT_PATH = os.path.join(SSL_DIR, "cert.pem")


async def main():
    # 1. Plain HTTP server on port 8080 (For ESP32 Robot WebSockets & HTTP OTA)
    config_http = uvicorn.Config(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        log_level="info"
    )
    server_http = uvicorn.Server(config_http)

    # 2. HTTPS server on port 8443 (For Mobile Phones: enables navigator.mediaDevices microphone)
    if os.path.exists(KEY_PATH) and os.path.exists(CERT_PATH):
        config_https = uvicorn.Config(
            "app.main:app",
            host="0.0.0.0",
            port=8443,
            ssl_keyfile=KEY_PATH,
            ssl_certfile=CERT_PATH,
            log_level="info"
        )
        server_https = uvicorn.Server(config_https)
        print("Starting dual servers: HTTP on :8080 (Robot) and HTTPS on :8443 (Mobile Phone Mic)")
        await asyncio.gather(server_http.serve(), server_https.serve())
    else:
        print("SSL certificates not found. Starting single HTTP server on :8080")
        await server_http.serve()


if __name__ == "__main__":
    asyncio.run(main())
