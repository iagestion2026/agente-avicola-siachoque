import os
import requests
import json
import time
from datetime import date, datetime
from pathlib import Path

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
if not API_KEY:
    print("ERROR: No se encontro ANTHROPIC_API_KEY")
    exit(1)

print(f"OK: API key encontrada ({API_KEY[:12]}...)")
Path("reportes").mkdir(exist_ok=True)


def claude_buscar(prompt, intento=1):
    """Llama a Claude con web search — reintenta si hay error 429"""
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
            timeout=90
        )
        r.raise_for_status()
        data = r.json()
        return " ".join(
            b["text"] for b in data.get("content", [])
            if b.get("type") == "text"
        )
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429 and intento <= 3:
            espera = intento * 35
            print(f"  Limite de velocidad. Esperando {espera}s...")
            time.sleep(espera)
            return claude_buscar(prompt, intento + 1)
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {e}"


def consultar_api(url, params, nombre):
    """Consulta una API publica con manejo de errores"""
    try:
        r = requests.get(url, params=params, timeout=25,
                        headers={"Accept": "application/json"})
        r.raise_for_status()
        datos = r.json()
        print(f"  {nombre}: {len(datos)} registros")
        return datos
    except Exception as e:
        print(f"  Error {nombre}: {e}")
        return []


def secop_contratos_completo():
    """
    Consulta los 4 datasets SECOP para maximo coverage:
    - SECOP Integrado (I+II): rpmr-utcd  <- el mas completo
    - SECOP II Contratos: jbjy-vk9h
    - SECOP II Activos: p8vk-huva
    - SECOP I Procesos: xvdy-vvsk
    """
    print("Consultando SECOP — multiples fuentes...")
    todos = []

    # Terminos de busqueda
    terminos = ["HUEVO", "AVICOLA", "AVÍCOLA", "PAE", "ALIMENTO", "VIVERES", "VÍVERES"]

    # Dataset 1: SECOP Integrado (el mas completo — I y II juntos)
    print("  [1/3] SECOP Integrado...")
    for termino in ["HUEVO", "AVICOLA", "PAE"]:
        datos = consultar_api(
            "https://www.datos.gov.co/resource/rpmr-utcd.json",
            {
                "$where": f"upper(descripcion_del_proceso) like '%{termino}%' AND upper(departamento) like '%BOYAC%'",
                "$order": "fecha_de_firma DESC",
                "$limit": 15,
                "$select": "nombre_entidad,municipio,nit_entidad,descripcion_del_proceso,proveedor_adjudicado,nit_proveedor,valor_total_adjudicacion,fecha_de_firma,modalidad_de_contratacion"
            },
            f"Integrado '{termino}'"
        )
        todos.extend(datos)

    # Dataset 2: SECOP II Contratos electronicos
    print("  [2/3] SECOP II Contratos...")
    for termino in ["HUEVO", "AVICOLA"]:
        datos = consultar_api(
            "https://www.datos.gov.co/resource/jbjy-vk9h.json",
            {
                "$where": f"upper(descripcion_del_proceso) like '%{termino}%' AND upper(nombre_departamento) like '%BOYAC%'",
                "$order": "fecha_de_firma DESC",
                "$limit": 15,
                "$select": "nombre_entidad,municipio_entidad,descripcion_del_proceso,proveedor_adjudicado,valor_total_adjudicacion,fecha_de_firma"
            },
            f"SECOP II '{termino}'"
        )
        todos.extend(datos)

    # Dataset 3: SECOP I
    print("  [3/3] SECOP I...")
    datos = consultar_api(
        "https://www.datos.gov.co/resource/xvdy-vvsk.json",
        {
            "$where": "upper(descripcion_proceso) like '%HUEVO%' AND upper(departamento_entidad) like '%BOYAC%'",
            "$order": "fecha_adjudicacion DESC",
            "$limit": 10,
            "$select": "nombre_entidad,municipio,descripcion_proceso,nombre_representante_legal,valor_contrato,fecha_adjudicacion"
        },
        "SECOP I 'HUEVO'"
    )
    todos.extend(datos)

    # Normalizar y deduplicar
    normalizados = []
    vistos = set()

    for c in todos:
        # Normalizar nombres de columnas entre datasets
        entidad   = c.get("nombre_entidad", "N/A")
        municipio = c.get("municipio_entidad", c.get("municipio", "N/A"))
        objeto    = str(c.get("descripcion_del_proceso", c.get("descripcion_proceso", "N/A")))[:100]
        proveedor = c.get("proveedor_adjudicado", c.get("nombre_representante_legal", "N/A"))
        nit_prov  = c.get("nit_proveedor", "N/A")
        valor     = c.get("valor_total_adjudicacion", c.get("valor_contrato", "N/A"))
        fecha     = c.get("fecha_de_firma", c.get("fecha_adjudicacion", "N/A"))

        # Clave unica para deduplicar
        clave = f"{entidad[:30]}_{proveedor[:20]}_{valor}"
        if clave in vistos:
            continue
        vistos.add(clave)

        # Clasificar proveedor
        if proveedor and proveedor != "N/A":
            prov_upper = proveedor.upper()
            if any(x in prov_upper for x in ["BOGOTA","MEDELLIN","CALI","BARRANQUILLA",
                                               "ANTIOQUIA","CUNDINAMARCA","SANTANDER"]):
                tipo_prov = "INTERMEDIARIO EXTERNO"
            elif any(x in prov_upper for x in ["BOYACA","BOYACÁ","TUNJA","DUITAMA",
                                                "SOGAMOSO","PAIPA","SIACHOQUE","SORACA"]):
                tipo_prov = "PROVEEDOR LOCAL BOYACA"
            elif any(x in prov_upper for x in ["COOPERATIVA","COOP","ASOCIACION","ASOC"]):
                tipo_prov = "COOPERATIVA"
            else:
                tipo_prov = "EXTERNO (verificar)"
        else:
            tipo_prov = "NO IDENTIFICADO"

        normalizados.append({
            "entidad":    entidad,
            "municipio":  municipio,
            "objeto":     objeto,
            "proveedor":  proveedor,
            "nit":        nit_prov,
            "tipo_prov":  tipo_prov,
            "valor":      valor,
            "fecha":      fecha[:10] if len(str(fecha)) >= 10 else fecha
        })

    # Ordenar: externos primero (son la oportunidad)
    normalizados.sort(key=lambda x: (
        0 if "EXTERNO" in x["tipo_prov"] else
        1 if "LOCAL" in x["tipo_prov"] else 2
    ))

    print(f"  TOTAL contratos unicos: {len(normalizados)}")
    externos = [c for c in normalizados if "EXTERNO" in c["tipo_prov"]]
    locales  = [c for c in normalizados if "LOCAL" in c["tipo_prov"]]
    print(f"  → Externos (TU OPORTUNIDAD): {len(externos)}")
    print(f"  → Locales (competencia directa): {len(locales)}")

    return normalizados


def main():
    fecha = date.today().isoformat()
    inicio = datetime.now()

    print("=" * 55)
    print(f"AGENTE AVICOLA SIACHOQUE - {fecha}")
    print("=" * 55)

    # 1. SECOP completo (sin costo de API)
    print("\n[1/4] Consultando SECOP I + II + Integrado...")
    contratos = secop_contratos_completo()

    externos = [c for c in contratos if "EXTERNO" in c["tipo_prov"]]
    locales  = [c for c in contratos if "LOCAL" in c["tipo_prov"]]

    # 2. Convocatorias
    print("\n[2/4] Buscando convocatorias...")
    time.sleep(15)
    convocatorias = claude_buscar(f"""
Eres agente comercial para avicultor de Siachoque, Boyaca (500-2000 aves ponedoras).
Busca HOY {date.today().strftime('%d/%m/%Y')}:
- alimenteengrande.boyaca.gov.co (PAE Boyaca)
- adr.gov.co/convocatorias (ruedas de negocios avicolas)
- boyaca.gov.co (convocatorias pequenos productores 2026)

Lista convocatorias abiertas para compra de huevos o productores avicolas.
Para cada una: entidad, fecha cierre, como aplicar.
Clasifica: URGENTE (menos 15 dias) / PROXIMA / FUTURA.
""")

    # 3. Precio semanal
    print("\n[3/4] Consultando precio FENAVI...")
    time.sleep(25)
    precio = claude_buscar(f"""
Precio cubeta 30 huevos Colombia semana {date.today().strftime('%d/%m/%Y')}:
1. Precio FENAVI nacional
2. Precio plaza Tunja SIPSA-DANE
Compara con $11.500 productor Siachoque.
Maximo 5 lineas concretas.
""")

    # 4. Resumen ejecutivo
    print("\n[4/4] Generando resumen...")
    time.sleep(25)

    # Preparar contexto de competidores para el resumen
    texto_externos = ""
    for c in externos[:6]:
        texto_externos += f"\n  - {c['entidad']} ({c['municipio']}) compra a: {c['proveedor']} [{c['tipo_prov']}] valor: ${c['valor']}"

    texto_locales = ""
    for c in locales[:4]:
        texto_locales += f"\n  - {c['entidad']} ({c['municipio']}) proveedor local: {c['proveedor']}"

    resumen = claude_buscar(f"""
Eres asesor de avicultor campesino de Siachoque, Boyaca, 500-2000 aves.
Hoy: {date.today().strftime('%d/%m/%Y')}

ANALISIS DE COMPETIDORES SECOP ({len(contratos)} contratos encontrados):
MUNICIPIOS COMPRANDO A INTERMEDIARIOS EXTERNOS (TU OPORTUNIDAD - {len(externos)} casos):
{texto_externos if texto_externos else "  No identificados claramente — ver tabla completa"}

MUNICIPIOS CON PROVEEDOR LOCAL (competencia directa - {len(locales)} casos):
{texto_locales if texto_locales else "  No identificados"}

PRECIO: {precio[:150]}
CONVOCATORIAS: {convocatorias[:300]}

CONTACTOS CLAVE:
- ESE Siachoque: 7319093 (Heidy Johana Correa)
- Alcaldia Siachoque: 7404476 (Jairo Grijalba)
- ESE Soraca: 7404270 (Maricela Guerrero)
- ESE Santiago Tunja: 311 2169007
- PAE Boyaca: 7420150 Ext. 2367

Con base en los municipios donde estan comprando a intermediarios externos,
dame las 3 ACCIONES MAS URGENTES esta semana para desplazarlos.
Se especifico: municipio, entidad, a quien llamar, que argumentar.
Maximo 250 palabras. Solo texto plano.
""")

    duracion = (datetime.now() - inicio).seconds

    # Construir reporte
    reporte = f"""REPORTE AVICOLA SIACHOQUE
{fecha}
{"="*55}

ACCIONES URGENTES ESTA SEMANA:
{resumen}

{"="*55}
PRECIO HUEVO:
{precio}

{"="*55}
CONVOCATORIAS ABIERTAS:
{convocatorias}

{"="*55}
ANALISIS DE COMPETIDORES SECOP
Total contratos encontrados: {len(contratos)}
Intermediarios externos (TU OPORTUNIDAD): {len(externos)}
Proveedores locales (competencia): {len(locales)}
{"="*55}

MUNICIPIOS COMPRANDO A EXTERNOS — ATACAR YA:
"""
    for c in externos[:10]:
        reporte += f"""
  Entidad:    {c['entidad']}
  Municipio:  {c['municipio']}
  Proveedor:  {c['proveedor']}
  Tipo:       {c['tipo_prov']} ← TU OPORTUNIDAD
  Valor:      ${c['valor']}
  Fecha:      {c['fecha']}
  {"─"*45}"""

    reporte += f"""

{"="*55}
PROVEEDORES LOCALES (competencia directa):
"""
    for c in locales[:6]:
        reporte += f"""
  Entidad:    {c['entidad']}
  Municipio:  {c['municipio']}
  Proveedor:  {c['proveedor']}
  Valor:      ${c['valor']}
  {"─"*45}"""

    reporte += f"""

{"="*55}
TODOS LOS CONTRATOS:
"""
    for c in contratos:
        reporte += f"\n  {c['municipio']:15} | {c['proveedor'][:35]:35} | {c['tipo_prov']:25} | ${c['valor']}"

    reporte += f"\n\nGenerado en {duracion} segundos."

    # Guardar archivos
    with open(f"reportes/reporte_{fecha}.txt", "w", encoding="utf-8") as f:
        f.write(reporte)

    with open(f"reportes/contratos_{fecha}.json", "w", encoding="utf-8") as f:
        json.dump(contratos, f, ensure_ascii=False, indent=2)

    # CSV de competidores
    if contratos:
        import csv
        with open(f"reportes/competidores_{fecha}.csv", "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["entidad","municipio","objeto","proveedor","nit","tipo_prov","valor","fecha"])
            writer.writeheader()
            writer.writerows(contratos)
        print(f"\n  CSV competidores guardado: reportes/competidores_{fecha}.csv")

    # Consola
    print()
    print("=" * 55)
    print("ACCIONES URGENTES:")
    print(resumen)
    print()
    print(f"Contratos SECOP: {len(contratos)} ({len(externos)} externos, {len(locales)} locales)")
    print(f"Duracion: {duracion}s")
    print("=" * 55)


if __name__ == "__main__":
    main()
