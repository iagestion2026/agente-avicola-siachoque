import os
import requests
import json
from datetime import date, datetime
from pathlib import Path

# API key desde variable de entorno (GitHub Secret)
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

if not API_KEY:
    print("ERROR: No se encontro ANTHROPIC_API_KEY")
    exit(1)

print(f"OK: API key encontrada ({API_KEY[:10]}...)")

# Crear carpeta de reportes
Path("reportes").mkdir(exist_ok=True)

def claude_buscar(prompt):
    """Llama a Claude con web search"""
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
                "max_tokens": 1500,
                "tools": [{"type": "web_search_20250305", "name": "web_search"}],
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        r.raise_for_status()
        data = r.json()
        return " ".join(
            b["text"] for b in data.get("content", [])
            if b.get("type") == "text"
        )
    except Exception as e:
        return f"Error: {e}"

def secop_contratos():
    """Consulta SECOP II directamente"""
    print("Consultando SECOP II...")
    try:
        r = requests.get(
            "https://www.datos.gov.co/resource/jbjy-vk9h.json",
            params={
                "$where": "upper(descripcion_del_proceso) like '%HUEVO%' AND upper(nombre_departamento) like '%BOYAC%'",
                "$order": "fecha_de_firma DESC",
                "$limit": 10
            },
            timeout=20
        )
        r.raise_for_status()
        datos = r.json()
        print(f"  SECOP: {len(datos)} contratos encontrados")
        return datos
    except Exception as e:
        print(f"  Error SECOP: {e}")
        return []

def main():
    fecha = date.today().isoformat()
    inicio = datetime.now()

    print("=" * 50)
    print(f"AGENTE AVICOLA SIACHOQUE - {fecha}")
    print("=" * 50)

    # 1. Contratos SECOP
    contratos = secop_contratos()

    # 2. Convocatorias abiertas
    print("Buscando convocatorias...")
    convocatorias = claude_buscar(f"""
Eres agente comercial para avicultor de Siachoque, Boyaca (500-2000 aves).
Busca HOY {date.today().strftime('%d/%m/%Y')}:
1. Convocatorias abiertas PAE Boyaca (alimenteengrande.boyaca.gov.co)
2. Ruedas de negocios ADR para avicultores (adr.gov.co)
3. Convocatorias Gobernacion Boyaca pequenos productores

Para cada una: entidad, fecha cierre, como aplicar.
Clasifica: URGENTE (menos 15 dias) / PROXIMA / FUTURA.
""")

    # 3. Precio semanal
    print("Consultando precio huevo...")
    precio = claude_buscar(f"""
Busca el precio cubeta 30 huevos en Colombia esta semana {date.today().strftime('%d/%m/%Y')}:
- FENAVI precio nacional
- Plaza mercado Tunja
Compara con $11.500 (productor Siachoque). Maximo 4 lineas.
""")

    # 4. Resumen de acciones
    print("Generando resumen...")
    resumen = claude_buscar(f"""
Eres asesor de un avicultor campesino de Siachoque, Boyaca.
Con base en estos datos del {date.today().strftime('%d/%m/%Y')}:

CONTRATOS SECOP: {len(contratos)} encontrados en Boyaca
PRECIO: {precio[:200]}
CONVOCATORIAS: {convocatorias[:300]}

Dame las 3 acciones MAS URGENTES que debe hacer esta semana.
Se especifico: nombres, telefonos, fechas si aplica.
Maximo 200 palabras.
""")

    # Guardar reporte TXT
    reporte_txt = f"""REPORTE AVICOLA SIACHOQUE
{fecha}
{"="*50}

RESUMEN EJECUTIVO - ACCIONES ESTA SEMANA:
{resumen}

PRECIO HUEVO:
{precio}

CONVOCATORIAS ABIERTAS:
{convocatorias}

CONTRATOS SECOP II ENCONTRADOS ({len(contratos)}):
"""
    for c in contratos[:8]:
        reporte_txt += f"\n- {c.get('nombre_entidad','N/A')} ({c.get('municipio_entidad','N/A')})"
        reporte_txt += f"\n  Proveedor: {c.get('proveedor_adjudicado','N/A')}"
        reporte_txt += f"\n  Objeto: {str(c.get('descripcion_del_proceso','N/A'))[:80]}"
        reporte_txt += "\n"

    duracion = (datetime.now() - inicio).seconds
    reporte_txt += f"\nGenerado en {duracion} segundos."

    # Guardar archivos
    with open(f"reportes/reporte_{fecha}.txt", "w", encoding="utf-8") as f:
        f.write(reporte_txt)

    with open(f"reportes/contratos_{fecha}.json", "w", encoding="utf-8") as f:
        json.dump(contratos, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 50)
    print("RESUMEN EJECUTIVO:")
    print("=" * 50)
    print(resumen)
    print()
    print(f"Reportes guardados en carpeta /reportes/")
    print(f"Duracion: {duracion}s")

if __name__ == "__main__":
    main()
