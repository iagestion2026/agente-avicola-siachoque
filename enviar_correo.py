import requests, csv, os, glob, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import date
from pathlib import Path

API_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_PASS = os.environ.get("GMAIL_PASSWORD", "").replace(" ", "")
fecha      = date.today().isoformat()
NIT        = "900514813"

Path("reportes").mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# PASO 1: Buscar Dando Pasos de Vida en la web
# ─────────────────────────────────────────────
print("Buscando Fundacion Dando Pasos de Vida en web...")

prompt = (
    "Busca informacion sobre la Fundacion Dando Pasos de Vida, NIT 900514813, Colombia. "
    "1. Busca en community.secop.gov.co contratos donde aparezca como proveedor "
    "con NIT 900514813 o nombre Dando Pasos de Vida. "
    "2. Busca en datos.gov.co contratos con ese NIT. "
    "3. Busca en Google: Dando Pasos de Vida Boyaca contratos ICBF PAE municipios. "
    "Para cada contrato encontrado reporta: municipio, entidad contratante, "
    "objeto del contrato, valor, fecha. "
    "Tambien reporta en cuantos municipios de Boyaca opera y que programas maneja."
)

texto_web = "Sin resultados de busqueda web."
if API_KEY:
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": API_KEY,
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 2000,
                "tools": [{"type": "web_search_20250305", "name": "web_search"}],
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=90
        )
        r.raise_for_status()
        texto_web = " ".join(
            b["text"] for b in r.json().get("content", [])
            if b.get("type") == "text"
        )
        print("Busqueda completada.")
        print(texto_web[:500])
    except Exception as e:
        texto_web = f"Error en busqueda web: {e}"
        print(texto_web)

# Guardar investigacion como TXT
ruta_investigacion = f"reportes/dando_pasos_investigacion_{fecha}.txt"
with open(ruta_investigacion, "w", encoding="utf-8") as f:
    f.write("INVESTIGACION: FUNDACION DANDO PASOS DE VIDA\n")
    f.write(f"NIT: {NIT}\n")
    f.write(f"Fecha: {fecha}\n")
    f.write("=" * 50 + "\n\n")
    f.write(texto_web)
print(f"Investigacion guardada: {ruta_investigacion}")

# Verificar CSV de Dando Pasos del agente
csv_dando = f"reportes/6_DANDO_PASOS_{fecha}.csv"
n_filas = 0
if os.path.exists(csv_dando):
    with open(csv_dando, "r", encoding="utf-8-sig") as f:
        n_filas = max(0, len(f.readlines()) - 1)

print(f"CSV Dando Pasos desde SECOP: {n_filas} contratos")

# Si SECOP no encontró nada, enriquecer CSV con datos de la web
if n_filas == 0:
    campos = ["fuente", "municipio", "entidad", "objeto", "categoria",
              "proveedor", "nit_prov", "valor", "fecha", "notas"]
    with open(csv_dando, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerow({
            "fuente":    "Busqueda Web",
            "municipio": "Ver archivo de investigacion adjunto",
            "entidad":   "Ver dando_pasos_investigacion.txt",
            "objeto":    "Contratos Fundacion Dando Pasos de Vida",
            "categoria": "Ver investigacion",
            "proveedor": "FUNDACION DANDO PASOS DE VIDA",
            "nit_prov":  NIT,
            "valor":     "Ver investigacion",
            "fecha":     fecha,
            "notas":     texto_web[:800]
        })
    print("CSV enriquecido con datos de busqueda web.")

# ─────────────────────────────────────────────
# PASO 2: Enviar correo con todos los adjuntos
# ─────────────────────────────────────────────
if not GMAIL_USER or not GMAIL_PASS:
    print("Credenciales Gmail no configuradas. Omitiendo envio.")
else:
    print(f"\nPreparando correo para {GMAIL_USER}...")

    # Cuerpo del correo
    cuerpo = f"Reporte Avicola Siachoque - {fecha}\n\nVer archivos adjuntos Excel."
    txt_files = glob.glob("reportes/reporte_*.txt")
    if txt_files:
        with open(txt_files[0], "r", encoding="utf-8") as f:
            cuerpo = f.read()

    msg = MIMEMultipart()
    msg["From"]    = GMAIL_USER
    msg["To"]      = GMAIL_USER
    msg["Subject"] = f"Reporte Avicola Siachoque - {fecha}"
    msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

    # Recopilar todos los archivos a adjuntar
    adjuntos = (
        sorted(glob.glob("reportes/*.csv")) +
        sorted(glob.glob("reportes/dando_pasos_*.txt"))
    )

    # Excluir el JSON grande para no sobrecargar el correo
    # (queda disponible en GitHub Artifacts)

    print(f"Archivos a adjuntar: {len(adjuntos)}")
    for archivo in adjuntos:
        nombre = os.path.basename(archivo)
        try:
            with open(archivo, "rb") as f:
                contenido = f.read()
            if len(contenido) < 5:
                print(f"  Omitiendo (vacio): {nombre}")
                continue
            part = MIMEBase("application", "octet-stream")
            part.set_payload(contenido)
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{nombre}"'
            )
            msg.attach(part)
            print(f"  Adjunto: {nombre} ({len(contenido):,} bytes)")
        except Exception as e:
            print(f"  Error adjuntando {nombre}: {e}")

    # Enviar
    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(GMAIL_USER, GMAIL_PASS)
        server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        server.close()
        print(f"\nCorreo enviado exitosamente a {GMAIL_USER}")
        print(f"Archivos adjuntos: {len(adjuntos)}")
    except Exception as e:
        print(f"Error enviando correo: {e}")
        raise
