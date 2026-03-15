import os
import requests
import json
import time
import csv
from datetime import date, datetime
from pathlib import Path

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
if not API_KEY:
    print("ERROR: No se encontro ANTHROPIC_API_KEY")
    exit(1)

print(f"OK: API key encontrada ({API_KEY[:12]}...)")
Path("reportes").mkdir(exist_ok=True)


def claude_buscar(prompt, intento=1):
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
        return " ".join(b["text"] for b in data.get("content",[]) if b.get("type")=="text")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429 and intento <= 3:
            espera = intento * 35
            print(f"  Limite API. Esperando {espera}s...")
            time.sleep(espera)
            return claude_buscar(prompt, intento + 1)
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {e}"


def api_get(url, params, nombre):
    """GET a una API publica con reintentos"""
    for intento in range(3):
        try:
            r = requests.get(url, params=params, timeout=30,
                           headers={"Accept":"application/json",
                                    "X-App-Token": ""})
            r.raise_for_status()
            datos = r.json()
            if isinstance(datos, list):
                print(f"  {nombre}: {len(datos)} registros")
                return datos
            else:
                print(f"  {nombre}: respuesta inesperada — {str(datos)[:100]}")
                return []
        except Exception as e:
            if intento < 2:
                time.sleep(5)
            else:
                print(f"  Error {nombre}: {e}")
                return []
    return []


def clasificar_proveedor(nombre_proveedor):
    """Determina si el proveedor es local o externo"""
    if not nombre_proveedor or nombre_proveedor == "N/A":
        return "NO IDENTIFICADO"
    p = nombre_proveedor.upper()
    locales = ["BOYACA","BOYACÁ","TUNJA","DUITAMA","SOGAMOSO","PAIPA",
               "SIACHOQUE","SORACA","SORACÁ","VENTAQUEMADA","SAMACA",
               "COMBITA","JENESANO","RAMIRIQUI","TOCA","CHIVATA"]
    externos = ["BOGOTA","BOGOTÁ","MEDELLIN","MEDELLÍN","CALI","BARRANQUILLA",
                "BUCARAMANGA","ANTIOQUIA","CUNDINAMARCA","SANTANDER","VALLE",
                "ATLANTICO","ATLÁNTICO"]
    cooperativas = ["COOPERATIVA","COOP ","ASOCIACION","ASOC ","FUNDACION","CORP "]
    if any(x in p for x in locales):
        return "PROVEEDOR LOCAL BOYACA"
    if any(x in p for x in externos):
        return "INTERMEDIARIO EXTERNO"
    if any(x in p for x in cooperativas):
        return "COOPERATIVA / ASOCIACION"
    return "EXTERNO (verificar)"


def clasificar_categoria(objeto):
    """Clasifica el tipo de contrato segun su objeto"""
    if not objeto:
        return "GENERAL"
    o = objeto.upper()
    if any(x in o for x in ["FAMI","LACTANTE","GESTANTE","MATERNO","CANASTA NUTRI"]):
        return "ICBF MATERNO INFANTIL"
    if any(x in o for x in ["HOGAR COMUNITARIO","CDI","BIENESTAR","BIENEST"]):
        return "HOGAR COMUNITARIO ICBF"
    if any(x in o for x in ["PAE","ESCOLAR","ESTUDIANTE","RESTAURANTE ESCOLAR","ALIMENTACION ESCOLAR"]):
        return "PAE ESCOLAR"
    if any(x in o for x in ["HOSPITAL","SALUD","ESE ","CLINICA","CENTRO DE SALUD"]):
        return "HOSPITAL / ESE"
    if any(x in o for x in ["ICBF","INFANCIA","PRIMERA INFANCIA"]):
        return "ICBF GENERAL"
    if any(x in o for x in ["HUEVO","AVICOLA","AVÍCOLA","POLLO","ALIMENTO","VIVERE","MERCADO"]):
        return "ALIMENTOS GENERAL"
    return "OTRO"


def secop_contratos():
    """
    Consulta los datasets correctos de SECOP usando los campos exactos.
    Fuente oficial: github.com/ANCP-CCE-Analitica/datos_abiertos
    """
    print("\nConsultando SECOP — usando campos correctos...")
    todos = []

    # ── Dataset 1: SECOP II Contratos Electronicos (jbjy-vk9h) ──
    # Campos correctos: proveedor_adjudicado, valor_del_contrato, ciudad, departamento
    print("  [A] SECOP II Contratos Electronicos...")
    terminos_a = ["HUEVO","AVICOLA","PAE","FAMI","ICBF","CANASTA","ALIMENTO","MATERNO"]
    for t in terminos_a:
        datos = api_get(
            "https://www.datos.gov.co/resource/jbjy-vk9h.json",
            {
                "$select": "nombre_entidad,ciudad,departamento,descripcion_del_proceso,"
                           "proveedor_adjudicado,documento_proveedor,valor_del_contrato,"
                           "fecha_de_firma,modalidad_de_contratacion,estado_contrato",
                "$where": f"upper(descripcion_del_proceso) like '%{t}%' "
                          f"AND upper(departamento) like '%BOYAC%'",
                "$order": "fecha_de_firma DESC",
                "$limit": "15"
            },
            f"SECOP II '{t}'"
        )
        todos.extend(datos)
        time.sleep(1.5)

    # ── Dataset 2: SECOP II Contratos ACTIVOS (p8vk-huva) ──
    # Mismo schema pero solo contratos vigentes
    print("  [B] SECOP II Contratos Activos...")
    for t in ["HUEVO","AVICOLA","PAE","FAMI","ICBF"]:
        datos = api_get(
            "https://www.datos.gov.co/resource/p8vk-huva.json",
            {
                "$select": "nombre_entidad,ciudad,departamento,descripcion_del_proceso,"
                           "proveedor_adjudicado,documento_proveedor,valor_del_contrato,"
                           "fecha_de_firma,estado_contrato",
                "$where": f"upper(descripcion_del_proceso) like '%{t}%' "
                          f"AND upper(departamento) like '%BOYAC%'",
                "$order": "fecha_de_firma DESC",
                "$limit": "10"
            },
            f"SECOP II Activos '{t}'"
        )
        todos.extend(datos)
        time.sleep(1.5)

    # ── Dataset 3: SECOP I Procesos (xvdy-vvsk) ──
    # Campos diferentes: nombre_del_proveedor, valor_contrato
    print("  [C] SECOP I...")
    for t in ["HUEVO","AVICOLA","PAE","FAMI","ICBF"]:
        datos = api_get(
            "https://www.datos.gov.co/resource/xvdy-vvsk.json",
            {
                "$select": "nombre_entidad,municipio,departamento_entidad,"
                           "descripcion_proceso,nombre_del_proveedor,"
                           "nit_del_proveedor,valor_contrato,fecha_adjudicacion",
                "$where": f"upper(descripcion_proceso) like '%{t}%' "
                          f"AND upper(departamento_entidad) like '%BOYAC%'",
                "$order": "fecha_adjudicacion DESC",
                "$limit": "10"
            },
            f"SECOP I '{t}'"
        )
        todos.extend(datos)
        time.sleep(1.5)

    # ── Dataset 4: Tienda Virtual Estado (rgxm-mmea) — acuerdos marco ──
    print("  [D] Tienda Virtual Estado...")
    datos = api_get(
        "https://www.datos.gov.co/resource/rgxm-mmea.json",
        {
            "$select": "nombre_entidad,ciudad,descripcion_del_proceso,"
                       "proveedor_adjudicado,valor_del_contrato,fecha_de_firma",
            "$where": "upper(descripcion_del_proceso) like '%HUEVO%' "
                      "AND upper(departamento) like '%BOYAC%'",
            "$order": "fecha_de_firma DESC",
            "$limit": "10"
        },
        "Tienda Virtual 'HUEVO'"
    )
    todos.extend(datos)

    # ── Normalizar campos entre datasets ──
    normalizados = []
    vistos = set()

    for c in todos:
        entidad   = c.get("nombre_entidad", "N/A")
        municipio = c.get("ciudad", c.get("municipio", "N/A"))
        dpto      = c.get("departamento", c.get("departamento_entidad", "Boyacá"))
        objeto    = str(c.get("descripcion_del_proceso",
                              c.get("descripcion_proceso", "N/A")))[:120]
        proveedor = c.get("proveedor_adjudicado",
                          c.get("nombre_del_proveedor", "N/A"))
        nit_prov  = c.get("documento_proveedor",
                          c.get("nit_del_proveedor", "N/A"))
        valor     = c.get("valor_del_contrato",
                          c.get("valor_contrato", "N/A"))
        fecha     = str(c.get("fecha_de_firma",
                               c.get("fecha_adjudicacion", "N/A")))[:10]
        estado    = c.get("estado_contrato", "N/A")

        # Deduplicar
        clave = f"{entidad[:25]}|{proveedor[:20]}|{valor}"
        if clave in vistos:
            continue
        vistos.add(clave)

        tipo_prov  = clasificar_proveedor(proveedor)
        categoria  = clasificar_categoria(objeto)

        normalizados.append({
            "entidad":    entidad,
            "municipio":  municipio,
            "departamento": dpto,
            "objeto":     objeto,
            "categoria":  categoria,
            "proveedor":  proveedor,
            "nit_prov":   nit_prov,
            "tipo_prov":  tipo_prov,
            "valor":      valor,
            "fecha":      fecha,
            "estado":     estado
        })

    # Ordenar: externos primero (mayor oportunidad)
    normalizados.sort(key=lambda x: (
        0 if "EXTERNO" in x["tipo_prov"] else
        1 if "COOPERATIVA" in x["tipo_prov"] else
        2 if "LOCAL" in x["tipo_prov"] else 3
    ))

    # Estadisticas
    externos  = [c for c in normalizados if "EXTERNO"     in c["tipo_prov"]]
    locales   = [c for c in normalizados if "LOCAL"       in c["tipo_prov"]]
    icbf_c    = [c for c in normalizados if "ICBF"        in c["categoria"]
                                          or "HOGAR"      in c["categoria"]]
    pae_c     = [c for c in normalizados if "PAE"         in c["categoria"]]
    ese_c     = [c for c in normalizados if "HOSPITAL"    in c["categoria"]]

    print(f"\n  ─── RESUMEN SECOP ───")
    print(f"  Total contratos unicos:     {len(normalizados)}")
    print(f"  Externos (TU OPORTUNIDAD):  {len(externos)}")
    print(f"  Locales (competencia):      {len(locales)}")
    print(f"  ICBF / FAMI / Materno:      {len(icbf_c)}")
    print(f"  PAE escolar:                {len(pae_c)}")
    print(f"  Hospitales / ESE:           {len(ese_c)}")

    return normalizados


def guardar_excel_csv(contratos, fecha):
    """
    Genera 4 archivos CSV (abribles en Excel):
    1. competidores_completo  — todos los contratos
    2. oportunidades_externas — donde hay intermediario externo
    3. icbf_materno           — contratos FAMI y materno infantil
    4. pae_escolar            — contratos PAE colegios
    """
    if not contratos:
        print("  Sin contratos para exportar")
        return

    campos = ["entidad","municipio","objeto","categoria","proveedor",
              "nit_prov","tipo_prov","valor","fecha","estado"]

    archivos = {
        f"reportes/1_competidores_completo_{fecha}.csv": contratos,
        f"reportes/2_oportunidades_externas_{fecha}.csv":
            [c for c in contratos if "EXTERNO" in c["tipo_prov"]],
        f"reportes/3_icbf_materno_{fecha}.csv":
            [c for c in contratos if "ICBF" in c["categoria"] or "HOGAR" in c["categoria"]],
        f"reportes/4_pae_escolar_{fecha}.csv":
            [c for c in contratos if "PAE" in c["categoria"]],
    }

    for ruta, datos in archivos.items():
        if datos:
            with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(datos)
            print(f"  Excel/CSV creado: {ruta} ({len(datos)} filas)")
        else:
            print(f"  Sin datos para: {ruta}")


def main():
    fecha = date.today().isoformat()
    inicio = datetime.now()

    print("=" * 60)
    print(f"  AGENTE AVICOLA SIACHOQUE - {fecha}")
    print("=" * 60)

    # 1. SECOP completo
    contratos = secop_contratos()
    externos  = [c for c in contratos if "EXTERNO" in c["tipo_prov"]]
    locales   = [c for c in contratos if "LOCAL"   in c["tipo_prov"]]
    icbf_c    = [c for c in contratos if "ICBF"    in c["categoria"] or "HOGAR" in c["categoria"]]
    pae_c     = [c for c in contratos if "PAE"     in c["categoria"]]

    # Guardar Excels inmediatamente
    print("\nGenerando archivos Excel/CSV...")
    guardar_excel_csv(contratos, fecha)

    # 2. Convocatorias
    print("\n[2/5] Buscando convocatorias...")
    time.sleep(15)
    convocatorias = claude_buscar(f"""
Eres agente comercial para avicultor de Siachoque, Boyaca (500-2000 aves ponedoras).
Busca HOY {date.today().strftime('%d/%m/%Y')} convocatorias abiertas en:
1. alimenteengrande.boyaca.gov.co (PAE Boyaca)
2. icbf.gov.co Regional Boyaca (FAMI, hogares comunitarios, CDI)
3. adr.gov.co/convocatorias (ruedas de negocios avicolas)
4. boyaca.gov.co (pequenos productores 2026)
Para cada una: entidad, objeto, fecha cierre, como aplicar.
Clasifica: URGENTE / PROXIMA / FUTURA.
""")

    # 3. Programas ICBF zona
    print("\n[3/5] Consultando programas ICBF materno infantil...")
    time.sleep(20)
    icbf_info = claude_buscar(f"""
Busca los programas ICBF activos en 2026 en Siachoque, Soraca, Toca y municipios 
cercanos en Boyaca:
1. Hogares FAMI (madres lactantes y gestantes)
2. Hogares Comunitarios de Bienestar (HCB)
3. Centros de Desarrollo Infantil (CDI)
4. Complementacion Alimentaria Materno Infantil

Para cada uno: operador que lo ejecuta, municipio, cuantos beneficiarios,
si incluye huevos en la racion alimentaria.
Centro Zonal ICBF Tunja: (608) 7422929
""")

    # 4. Precio semanal
    print("\n[4/5] Consultando precio FENAVI...")
    time.sleep(20)
    precio = claude_buscar(f"""
Precio cubeta 30 huevos Colombia semana {date.today().strftime('%d/%m/%Y')}:
1. Precio FENAVI nacional
2. Precio plaza Tunja SIPSA-DANE
Compara con $11.500 productor Siachoque. Maximo 5 lineas.
""")

    # 5. Resumen ejecutivo
    print("\n[5/5] Generando resumen ejecutivo...")
    time.sleep(20)

    texto_ext = "\n".join(
        f"  {c['municipio']:15} | {c['entidad'][:40]} | proveedor: {c['proveedor'][:30]} | ${c['valor']}"
        for c in externos[:8]
    ) or "  No identificados en esta busqueda"

    texto_icbf = "\n".join(
        f"  {c['municipio']:15} | {c['entidad'][:40]} | {c['categoria']} | ${c['valor']}"
        for c in icbf_c[:6]
    ) or "  Sin contratos ICBF encontrados"

    resumen = claude_buscar(f"""
Eres asesor de avicultor campesino de Siachoque, Boyaca, 500-2000 aves.
Hoy: {date.today().strftime('%d/%m/%Y')}

INTELIGENCIA SECOP HOY:
Externos que puedes desplazar con Ley 2046 ({len(externos)} casos):
{texto_ext}

Contratos ICBF / FAMI / Materno Infantil ({len(icbf_c)} casos):
{texto_icbf}

Programas ICBF activos en zona: {icbf_info[:400]}
Precio: {precio[:150]}
Convocatorias: {convocatorias[:300]}

CONTACTOS CLAVE:
- ESE Siachoque: 7319093 (Heidy Johana Correa)
- Alcaldia Siachoque: 7404476 (Jairo Grijalba)
- ESE Soraca: 7404270 (Maricela Guerrero)
- ESE Tunja: 311 2169007
- ICBF Tunja: (608) 7422929
- PAE Boyaca: 7420150 Ext. 2367

Dame las 3 ACCIONES MAS URGENTES considerando PAE, ICBF y FAMI.
Para cada accion: municipio, entidad, telefono, que decir exactamente.
Maximo 280 palabras. Solo texto plano.
""")

    duracion = (datetime.now() - inicio).seconds

    # Reporte TXT completo
    reporte = f"""REPORTE AVICOLA SIACHOQUE
{fecha}
{"="*60}

ACCIONES URGENTES ESTA SEMANA:
{resumen}

{"="*60}
PRECIO HUEVO:
{precio}

{"="*60}
CONVOCATORIAS (PAE + ICBF + ADR):
{convocatorias}

{"="*60}
PROGRAMAS ICBF MATERNO INFANTIL EN TU ZONA:
{icbf_info}

{"="*60}
RESUMEN COMPETIDORES SECOP
Contratos encontrados:              {len(contratos)}
Intermediarios externos (atacar):   {len(externos)}
Proveedores locales Boyaca:         {len(locales)}
ICBF / FAMI / Materno:             {len(icbf_c)}
PAE escolar:                        {len(pae_c)}

ARCHIVOS EXCEL GENERADOS:
  1_competidores_completo_{fecha}.csv   — todos los contratos
  2_oportunidades_externas_{fecha}.csv  — donde debes entrar
  3_icbf_materno_{fecha}.csv            — programas madres y bebes
  4_pae_escolar_{fecha}.csv             — colegios PAE
{"="*60}

DETALLE: MUNICIPIOS COMPRANDO A EXTERNOS — ATACAR YA:
"""
    for c in externos[:15]:
        reporte += f"""
  Municipio:  {c['municipio']}
  Entidad:    {c['entidad']}
  Programa:   {c['categoria']}
  Proveedor:  {c['proveedor']}  ({c['tipo_prov']})
  NIT prov:   {c['nit_prov']}
  Valor:      ${c['valor']}
  Fecha:      {c['fecha']}
  {"─"*50}"""

    reporte += f"""

DETALLE: CONTRATOS ICBF / FAMI / MATERNO INFANTIL:
"""
    for c in icbf_c[:10]:
        reporte += f"""
  Municipio:  {c['municipio']}
  Entidad:    {c['entidad']}
  Programa:   {c['categoria']}
  Proveedor:  {c['proveedor']}  ({c['tipo_prov']})
  Valor:      ${c['valor']}
  Fecha:      {c['fecha']}
  {"─"*50}"""

    reporte += f"""

DETALLE: PROVEEDORES LOCALES (competencia):
"""
    for c in locales[:8]:
        reporte += f"""
  Municipio:  {c['municipio']}
  Proveedor:  {c['proveedor']}
  NIT:        {c['nit_prov']}
  Entidad:    {c['entidad']}
  Valor:      ${c['valor']}
  {"─"*50}"""

    reporte += f"\n\nGenerado en {duracion} segundos."

    with open(f"reportes/reporte_{fecha}.txt", "w", encoding="utf-8") as f:
        f.write(reporte)
    with open(f"reportes/contratos_{fecha}.json", "w", encoding="utf-8") as f:
        json.dump(contratos, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 60)
    print("ACCIONES URGENTES:")
    print(resumen)
    print()
    print(f"  Contratos SECOP:     {len(contratos)}")
    print(f"  Externos (atacar):   {len(externos)}")
    print(f"  ICBF/FAMI:          {len(icbf_c)}")
    print(f"  PAE:                 {len(pae_c)}")
    print(f"  Duracion:            {duracion}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
