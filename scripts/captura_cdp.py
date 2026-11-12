"""Saca una captura de pantalla de una página con Edge (headless) y muestra los errores de consola.

Habla con Edge por el protocolo de depuración (CDP) usando solo la biblioteca estándar, así espera de
verdad a que la página esté lista (algo que `--screenshot` no hace) y puede leer la consola.

Se corre con el Python de WINDOWS (Edge es de Windows). Desde WSL:
  "/mnt/c/Users/<usuario>/AppData/Local/Programs/Python/Python313/python.exe" scripts/captura_cdp.py \\
      http://localhost:8001/mapa.html "C:\\ruta\\salida.png" --espera "window.cadeteMapa?.loaded()"
"""
import argparse
import base64
import json
import os
import random
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


class WebSocket:
    """Cliente WebSocket mínimo (lo justo para hablar con CDP)."""

    def __init__(self, url: str):
        host_port, _, ruta = url.removeprefix("ws://").partition("/")
        host, _, puerto = host_port.partition(":")
        self.sock = socket.create_connection((host, int(puerto)), timeout=30)
        clave = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            f"GET /{ruta} HTTP/1.1\r\nHost: {host_port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {clave}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        respuesta = b""
        while b"\r\n\r\n" not in respuesta:
            respuesta += self.sock.recv(4096)
        if b" 101 " not in respuesta.split(b"\r\n")[0]:
            raise RuntimeError(f"El WebSocket no se abrió: {respuesta[:200]!r}")

    def _leer(self, n: int) -> bytes:
        datos = b""
        while len(datos) < n:
            trozo = self.sock.recv(n - len(datos))
            if not trozo:
                raise ConnectionError("conexión cerrada")
            datos += trozo
        return datos

    def enviar(self, texto: str) -> None:
        carga = texto.encode()
        n = len(carga)
        cabecera = b"\x81" + (bytes([0x80 | n]) if n < 126 else b"\xfe" + struct.pack(">H", n) if n < 65536
                              else b"\xff" + struct.pack(">Q", n))
        mascara = os.urandom(4)
        self.sock.sendall(cabecera + mascara + bytes(b ^ mascara[i % 4] for i, b in enumerate(carga)))

    def recibir(self, espera: float) -> str | None:
        self.sock.settimeout(espera)
        try:
            partes = b""
            while True:
                b1, b2 = self._leer(2)
                n = b2 & 0x7F
                if n == 126:
                    n = struct.unpack(">H", self._leer(2))[0]
                elif n == 127:
                    n = struct.unpack(">Q", self._leer(8))[0]
                carga = self._leer(n)
                opcode = b1 & 0x0F
                if opcode == 0x8:
                    raise ConnectionError("Edge cerró la conexión")
                if opcode == 0x9:  # ping: se responde pong
                    continue
                partes += carga
                if b1 & 0x80:  # último fragmento
                    return partes.decode()
        except socket.timeout:
            return None


class CDP:
    def __init__(self, ws: WebSocket):
        self.ws, self.n, self.eventos = ws, 0, []

    def llamar(self, metodo: str, **params):
        self.n += 1
        mi_id = self.n
        self.ws.enviar(json.dumps({"id": mi_id, "method": metodo, "params": params}))
        limite = time.time() + 60
        while time.time() < limite:
            texto = self.ws.recibir(5)
            if texto is None:
                continue
            msg = json.loads(texto)
            if msg.get("id") == mi_id:
                if "error" in msg:
                    raise RuntimeError(f"{metodo}: {msg['error']}")
                return msg.get("result", {})
            self.eventos.append(msg)
        raise TimeoutError(metodo)

    def esperar_evento(self, nombre: str, segundos: float) -> bool:
        limite = time.time() + segundos
        while time.time() < limite:
            if any(e.get("method") == nombre for e in self.eventos):
                return True
            texto = self.ws.recibir(1)
            if texto:
                self.eventos.append(json.loads(texto))
        return False

    def evaluar(self, expresion: str):
        r = self.llamar("Runtime.evaluate", expression=expresion, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("url")
    a.add_argument("salida")
    a.add_argument("--ancho", type=int, default=1100)
    a.add_argument("--alto", type=int, default=760)
    a.add_argument("--escala", type=float, default=1.0)
    a.add_argument("--oscuro", action="store_true", help="emula prefers-color-scheme: dark")
    a.add_argument("--movil", action="store_true", help="emula un teléfono (táctil)")
    a.add_argument("--espera", default="true", help="JS que debe dar true para sacar la foto")
    a.add_argument("--tras", default="", help="JS a ejecutar una vez cargada la página")
    a.add_argument("--timeout", type=float, default=40)
    a.add_argument("--puerto", type=int, default=0, help="puerto de depuración (0 = uno al azar)")
    a.add_argument("--gracia", type=float, default=1.0, help="segundos extra antes de la foto")
    args = a.parse_args()
    args.puerto = args.puerto or random.randint(9300, 9899)   # uno distinto cada vez: no reusar un Edge viejo

    perfil = tempfile.mkdtemp(prefix="edge-cdp-")
    edge = subprocess.Popen([
        EDGE, "--headless=new", "--disable-gpu", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
        "--ignore-gpu-blocklist", "--hide-scrollbars", "--no-first-run", f"--user-data-dir={perfil}",
        f"--remote-debugging-port={args.puerto}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        destino = None
        for _ in range(60):
            try:
                paginas = json.load(urllib.request.urlopen(f"http://127.0.0.1:{args.puerto}/json/list", timeout=2))
                destino = next(p for p in paginas if p["type"] == "page")["webSocketDebuggerUrl"]
                break
            except Exception:
                time.sleep(0.5)
        if not destino:
            print("No se pudo conectar con Edge", file=sys.stderr)
            return 2
        cdp = CDP(WebSocket(destino))
        for dominio in ("Page", "Runtime"):
            cdp.llamar(f"{dominio}.enable")
        cdp.llamar("Emulation.setDeviceMetricsOverride", width=args.ancho, height=args.alto,
                   deviceScaleFactor=args.escala, mobile=args.movil)
        if args.movil:
            cdp.llamar("Emulation.setTouchEmulationEnabled", enabled=True)
        if args.oscuro:
            cdp.llamar("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
        cdp.llamar("Page.navigate", url=args.url)
        cdp.esperar_evento("Page.loadEventFired", 30)
        if args.tras:
            cdp.evaluar(args.tras)
        limite, listo = time.time() + args.timeout, False
        while time.time() < limite:
            try:
                listo = bool(cdp.evaluar(args.espera))
            except RuntimeError:
                listo = False
            if listo:
                break
            time.sleep(0.5)
        time.sleep(args.gracia)
        foto = cdp.llamar("Page.captureScreenshot", format="png")["data"]
        with open(args.salida, "wb") as f:
            f.write(base64.b64decode(foto))
        print(f"captura guardada: {args.salida} (condición cumplida: {listo})")
        for e in cdp.eventos:
            if e.get("method") == "Runtime.exceptionThrown":
                d = e["params"]["exceptionDetails"]
                print("EXCEPCIÓN:", d.get("exception", {}).get("description", d.get("text", ""))[:300])
            elif e.get("method") == "Runtime.consoleAPICalled" and e["params"]["type"] in ("error", "warning"):
                print("CONSOLA", e["params"]["type"].upper() + ":", " ".join(str(x.get("value", x.get("description", ""))) for x in e["params"]["args"])[:300])
        return 0 if listo else 1
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(edge.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        shutil.rmtree(perfil, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
