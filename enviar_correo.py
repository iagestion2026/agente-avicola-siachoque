"""
enviar_correo.py — Envía correo + publica reporte en GitHub Gist
El Gist es público y Claude puede leerlo directamente por URL.
"""
import requests, csv, os, glob, smtplib, json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import date
from pathlib import Path

API_KEY       = os.environ.get("ANTHROPIC_API_KEY","")
GMAIL_USER    = os.environ.get("GMAIL_USER","")
GMAIL_PASS    = os.environ.get("GMAIL_PASSWORD","").replace(" ","")
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN","")   # nuevo secret
fecha         = date.today().isoformat()
NIT           = "900514813"

Path("reportes").mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# PASO 1: Buscar Dando Pasos en web
# ─────────────────────────────────────────────
print("Buscando Fundacion Dando Pasos de Vida en web...")

prompt = (
    "Busca informacion sobre la Fundacion Dando Pasos de Vida, NIT 900514813, Colombia. "
    "1. Busca en community.secop.gov.co contratos donde aparezca como proveedor. "
    "2. En cuantos municipios de Boyaca opera y que programas maneja. "
    "Reporta: municipio, entidad, programa, valor, fecha para cada contrato."
)

texto_web = "Sin resultados."
if API_KEY:
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type":"application/json",
                     "x-api-key":API_KEY,
                     "anthropic-version":"2023-06-01"},
            json={"model":"claude-sonnet-4-20250514","max_tokens":1500,
                  "tools":[{"type":"web_search_20250305","name":"web_search"}],
                  "messages":[{"role":"user","content":prompt}]},
            timeout=90
        )
        r.raise_for_status()
        texto_web = " ".join(b["text"] for b in r.json().get("content",[])
                             if b.get("type")=="text")
        print("Busqueda Dando Pasos completada.")
    except Exception as e:
        texto_web = f"Error: {e}"

# Guardar investigación
ruta_inv = f"reportes/dando_pasos_investigacion_{fecha}.txt"
with open(ruta_inv,"w",encoding="utf-8") as f:
    f.write(f"INVESTIGACION: FUNDACION DANDO PASOS DE VIDA\n")
    f.write(f"NIT: {NIT}\nFecha: {fecha}\n{'='*50}\n\n")
    f.write(texto_web)

# Verificar CSV Dando Pasos
csv_dando = f"reportes/6_DANDO_PASOS_{fecha}.csv"
n_filas = 0
if os.path.exists(csv_dando):
    with open(csv_dando,"r",encoding="utf-8-sig") as f:
        n_filas = max(0, len(f.readlines())-1)

if n_filas == 0:
    campos = ["fuente","municipio","entidad","objeto","categoria",
              "proveedor","nit_prov","valor","fecha","notas"]
    with open(csv_dando,"w",newline="",encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerow({"fuente":"Busqueda Web","municipio":"Ver investigacion",
                    "entidad":"Ver dando_pasos_investigacion.txt",
                    "objeto":"Fundacion Dando Pasos de Vida","categoria":"Ver investigacion",
                    "proveedor":"FUNDACION DANDO PASOS DE VIDA","nit_prov":NIT,
                    "valor":"Ver investigacion","fecha":fecha,"notas":texto_web[:500]})

# ─────────────────────────────────────────────
# PASO 2: Publicar reporte en GitHub Gist
# ─────────────────────────────────────────────
gist_url = ""
if GITHUB_TOKEN:
    print("\nPublicando reporte en GitHub Gist...")
    try:
        # Leer el reporte TXT
        txt_files = glob.glob("reportes/reporte_*.txt")
        contenido_reporte = "Sin reporte generado."
        if txt_files:
            with open(txt_files[0],"r",encoding="utf-8") as f:
                contenido_reporte = f.read()

        # Leer JSON de contratos para incluir en el Gist
        json_files = glob.glob("reportes/contratos_*.json")
        contenido_json = "[]"
        if json_files:
            with open(json_files[0],"r",encoding="utf-8") as f:
                contenido_json = f.read()

        # Preparar archivos del Gist
        archivos_gist = {
            f"reporte_{fecha}.txt": {
                "content": contenido_reporte
            },
            f"contratos_{fecha}.json": {
                "content": contenido_json[:500000]  # máximo 500KB
            },
            "LEEME.md": {
                "content": f"""# Agente Avícola Siachoque — Reporte Semanal

**Fecha:** {fecha}
**Productor:** Avicultor campesino de Siachoque, Boyacá
**Aves:** 500-2.000 gallinas ponedoras

## Archivos en este Gist
- `reporte_{fecha}.txt` — Reporte completo con acciones urgentes, precios y contratos
- `contratos_{fecha}.json` — Todos los contratos encontrados en SECOP II

## Cómo usar con Claude
Abre una conversación con Claude y escribe:
> "Lee el reporte avícola de esta semana: https://gist.github.com/iagestion2026/[ID]"

Claude leerá el reporte y podrás hacerle preguntas sobre contratos,
precios, FUPAVID, convocatorias y oportunidades.

## Contexto clave
- Operador PAE Siachoque: FUPAVID (NIT 901432698)
- Precio objetivo para FUPAVID: $11.000/cubeta
- Contacto ESE Siachoque: 7319093
- Contacto Alcaldía: 7404476
"""
            }
        }

        # Buscar si ya existe un Gist del agente para actualizarlo
        headers_gh = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        # Listar gists existentes
        r_list = requests.get("https://api.github.com/gists",
                              headers=headers_gh, timeout=15)
        gist_id = None
        if r_list.status_code == 200:
            for g in r_list.json():
                if "agente-avicola" in g.get("description","").lower() or \
                   "reporte_avicola" in " ".join(g.get("files",{}).keys()).lower():
                    gist_id = g["id"]
                    break

        if gist_id:
            # Actualizar gist existente
            r_gist = requests.patch(
                f"https://api.github.com/gists/{gist_id}",
                headers=headers_gh,
                json={"description": f"Agente Avícola Siachoque — {fecha}",
                      "files": archivos_gist},
                timeout=30
            )
        else:
            # Crear gist nuevo
            r_gist = requests.post(
                "https://api.github.com/gists",
                headers=headers_gh,
                json={"description": f"Agente Avícola Siachoque — {fecha}",
                      "public": True,
                      "files": archivos_gist},
                timeout=30
            )

        if r_gist.status_code in (200, 201):
            gist_url = r_gist.json().get("html_url","")
            print(f"✅ Gist publicado: {gist_url}")

            # Guardar URL del Gist para referencia
            with open("reportes/gist_url.txt","w") as f:
                f.write(f"{fecha}: {gist_url}\n")
        else:
            print(f"Error Gist: {r_gist.status_code} — {r_gist.text[:200]}")

    except Exception as e:
        print(f"Error publicando Gist: {e}")
else:
    print("GITHUB_TOKEN no configurado — saltando Gist")

# ─────────────────────────────────────────────
# PASO 3: Enviar correo con todos los adjuntos
# ─────────────────────────────────────────────
if not GMAIL_USER or not GMAIL_PASS:
    print("Credenciales Gmail no configuradas.")
else:
    print(f"\nPreparando correo para {GMAIL_USER}...")

    cuerpo = f"Reporte Avícola Siachoque — {fecha}\n\n"
    if gist_url:
        cuerpo += f"📊 REPORTE EN LÍNEA (para consultar con Claude):\n{gist_url}\n\n"
        cuerpo += "Para analizar con Claude escribe:\n"
        cuerpo += f'"Lee el reporte avícola: {gist_url}"\n\n'
        cuerpo += "─"*50 + "\n\n"

    txt_files = glob.glob("reportes/reporte_*.txt")
    if txt_files:
        with open(txt_files[0],"r",encoding="utf-8") as f:
            cuerpo += f.read()

    msg = MIMEMultipart()
    msg["From"]    = GMAIL_USER
    msg["To"]      = GMAIL_USER
    msg["Subject"] = f"🥚 Reporte Avícola Siachoque — {fecha}"
    msg.attach(MIMEText(cuerpo,"plain","utf-8"))

    # Adjuntar todos los CSV y el TXT de investigación
    adjuntos = (
        sorted(glob.glob("reportes/*.csv")) +
        sorted(glob.glob("reportes/dando_pasos_*.txt"))
    )

    print(f"Adjuntando {len(adjuntos)} archivos...")
    for archivo in adjuntos:
        nombre = os.path.basename(archivo)
        try:
            with open(archivo,"rb") as f:
                contenido = f.read()
            if len(contenido) < 5:
                continue
            part = MIMEBase("application","octet-stream")
            part.set_payload(contenido)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition",
                            f'attachment; filename="{nombre}"')
            msg.attach(part)
            print(f"  ✓ {nombre} ({len(contenido):,} bytes)")
        except Exception as e:
            print(f"  Error {nombre}: {e}")

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com",465)
        server.login(GMAIL_USER, GMAIL_PASS)
        server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        server.close()
        print(f"\n✅ Correo enviado a {GMAIL_USER}")
        if gist_url:
            print(f"✅ Gist publicado: {gist_url}")
            print(f"\nPara analizar con Claude:")
            print(f'  "Lee el reporte avícola: {gist_url}"')
    except Exception as e:
        print(f"Error enviando correo: {e}")
        raise
