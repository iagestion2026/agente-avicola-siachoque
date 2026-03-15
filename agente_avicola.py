import os, requests, json, time, csv
from datetime import date, datetime
from pathlib import Path

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
if not API_KEY:
    print("ERROR: No se encontro ANTHROPIC_API_KEY")
    exit(1)
print(f"OK: API key encontrada ({API_KEY[:12]}...)")
Path("reportes").mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════
# UTILIDADES
# ═══════════════════════════════════════════════════════

def api_get(url, params, nombre):
    for intento in range(3):
        try:
            r = requests.get(url, params=params, timeout=30,
                             headers={"Accept": "application/json"})
            r.raise_for_status()
            datos = r.json()
            if isinstance(datos, list):
                print(f"    {nombre}: {len(datos)} registros")
                return datos
            print(f"    {nombre}: respuesta inesperada")
            return []
        except Exception as e:
            if intento < 2:
                time.sleep(5)
            else:
                print(f"    Error {nombre}: {e}")
                return []
    return []


def claude_buscar(prompt, intento=1):
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json",
                     "x-api-key": API_KEY,
                     "anthropic-version": "2023-06-01"},
            json={"model": "claude-sonnet-4-20250514",
                  "max_tokens": 1500,
                  "tools": [{"type": "web_search_20250305", "name": "web_search"}],
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=90
        )
        r.raise_for_status()
        return " ".join(b["text"] for b in r.json().get("content", [])
                        if b.get("type") == "text")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429 and intento <= 3:
            espera = intento * 30
            print(f"    Limite API. Esperando {espera}s...")
            time.sleep(espera)
            return claude_buscar(prompt, intento + 1)
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {e}"


def clasificar_proveedor(nombre):
    if not nombre or nombre == "N/A":
        return "NO IDENTIFICADO"
    p = nombre.upper()
    if any(x in p for x in ["BOYACA","BOYACÁ","TUNJA","DUITAMA","SOGAMOSO",
                              "PAIPA","SIACHOQUE","SORACA","SORACÁ",
                              "VENTAQUEMADA","SAMACA","TOCA","CHIVATA",
                              "JENESANO","COMBITA","RAMIRIQUI"]):
        return "PROVEEDOR LOCAL BOYACA"
    if any(x in p for x in ["BOGOTA","BOGOTÁ","MEDELLIN","MEDELLÍN","CALI",
                              "BARRANQUILLA","BUCARAMANGA","ANTIOQUIA",
                              "CUNDINAMARCA","SANTANDER","VALLE","ATLANTICO"]):
        return "INTERMEDIARIO EXTERNO"
    if any(x in p for x in ["COOPERATIVA","COOP ","ASOCIACION","ASOC ",
                              "FUNDACION","FUNDACIÓN","CORP ","CORPORACION"]):
        return "FUNDACION / COOPERATIVA"
    return "EXTERNO (verificar)"


def clasificar_categoria(objeto):
    if not objeto:
        return "GENERAL"
    o = objeto.upper()
    if any(x in o for x in ["FAMI","LACTANTE","GESTANTE","MATERNO","CANASTA NUTRI"]):
        return "ICBF MATERNO INFANTIL"
    if any(x in o for x in ["HOGAR COMUNITARIO","CDI","BIENESTAR","PRIMERA INFANCIA"]):
        return "HOGAR COMUNITARIO ICBF"
    if any(x in o for x in ["PAE","ESCOLAR","ESTUDIANTE","RESTAURANTE ESCOLAR",
                              "ALIMENTACION ESCOLAR","COMPLEMENTO NUTRICIONAL"]):
        return "PAE ESCOLAR"
    if any(x in o for x in ["HOSPITAL","SALUD","ESE ","CLINICA","CENTRO DE SALUD"]):
        return "HOSPITAL / ESE"
    if any(x in o for x in ["EJERCITO","EJÉRCITO","BATALLON","BATALLÓN","TROPA",
                              "MILITAR","FUERZAS MILITARES","RANCHO MILITAR",
                              "ALFM","SOLDADO"]):
        return "FUERZAS MILITARES"
    if any(x in o for x in ["ICBF","INFANCIA","BIENESTAR FAMILIAR"]):
        return "ICBF GENERAL"
    if any(x in o for x in ["HUEVO","AVICOLA","AVÍCOLA","POLLO","ALIMENTO",
                              "VIVERE","MERCADO","CANASTA"]):
        return "ALIMENTOS GENERAL"
    return "OTRO"


# ═══════════════════════════════════════════════════════
# MÓDULO SECOP — 5 DATASETS
# ═══════════════════════════════════════════════════════

def secop_dataset(url, campo_entidad, campo_municipio, campo_objeto,
                  campo_proveedor, campo_nit, campo_valor, campo_fecha,
                  terminos, nombre_ds, limite=10):
    """Consulta genérica a cualquier dataset SECOP"""
    resultados = []
    for t in terminos:
        datos = api_get(url, {
            "$where": f"upper({campo_objeto}) like '%{t}%' "
                      f"AND upper({campo_municipio}) like '%BOYAC%'",
            "$order": f"{campo_fecha} DESC",
            "$limit": str(limite),
            "$select": f"{campo_entidad},{campo_municipio},{campo_objeto},"
                       f"{campo_proveedor},{campo_nit},{campo_valor},{campo_fecha}"
        }, f"{nombre_ds} '{t}'")
        resultados.extend(datos)
        time.sleep(1)
    return resultados, (campo_entidad, campo_municipio, campo_objeto,
                        campo_proveedor, campo_nit, campo_valor, campo_fecha)


def normalizar(raw_list, campos_map, fuente):
    """Normaliza registros de distintos datasets al mismo esquema"""
    (ce, cm, co, cp, cn, cv, cf) = campos_map
    normalizados = []
    for c in raw_list:
        entidad   = str(c.get(ce, "N/A"))
        municipio = str(c.get(cm, "N/A"))
        objeto    = str(c.get(co, "N/A"))[:130]
        proveedor = str(c.get(cp, "N/A"))
        nit       = str(c.get(cn, "N/A"))
        valor     = str(c.get(cv, "N/A"))
        fecha     = str(c.get(cf, "N/A"))[:10]
        normalizados.append({
            "fuente":    fuente,
            "entidad":   entidad,
            "municipio": municipio,
            "objeto":    objeto,
            "categoria": clasificar_categoria(objeto),
            "proveedor": proveedor,
            "nit_prov":  nit,
            "tipo_prov": clasificar_proveedor(proveedor),
            "valor":     valor,
            "fecha":     fecha
        })
    return normalizados


def secop_completo():
    print("\n[1/5] Consultando SECOP — 5 fuentes de datos...")
    todos_raw = []

    # Términos por categoría
    t_alimentos  = ["HUEVO","AVICOLA","AVÍCOLA","ALIMENTO","VIVERES","VÍVERES"]
    t_icbf       = ["FAMI","ICBF","MATERNO","CANASTA","LACTANTE",
                    "HOGAR COMUNITARIO","CDI","COMPLEMENTACION"]
    t_pae        = ["PAE","ESCOLAR","ALIMENTACION ESCOLAR"]
    t_militar    = ["EJERCITO","EJÉRCITO","BATALLON","ALFM","MILITAR","RANCHO"]
    t_fundacion  = ["DANDO PASOS","DANDO PASOS DE VIDA"]  # buscar proveedor especifico

    todos_terminos = t_alimentos + t_icbf + t_pae + t_militar + t_fundacion

    # ── DS1: SECOP II Contratos (jbjy-vk9h) — campos correctos ──
    print("  [DS1] SECOP II Contratos...")
    raw1, m1 = secop_dataset(
        url="https://www.datos.gov.co/resource/jbjy-vk9h.json",
        campo_entidad="nombre_entidad",
        campo_municipio="ciudad",         # campo correcto en este dataset
        campo_objeto="descripcion_del_proceso",
        campo_proveedor="proveedor_adjudicado",
        campo_nit="documento_proveedor",
        campo_valor="valor_del_contrato",
        campo_fecha="fecha_de_firma",
        terminos=t_alimentos + t_icbf + t_pae,
        nombre_ds="SECOP II"
    )
    todos_raw.extend(normalizar(raw1, m1, "SECOP II"))

    # ── DS2: SECOP Integrado (rpmr-utcd) — más histórico ──
    print("  [DS2] SECOP Integrado...")
    raw2, m2 = secop_dataset(
        url="https://www.datos.gov.co/resource/rpmr-utcd.json",
        campo_entidad="nombre_entidad",
        campo_municipio="municipio",
        campo_objeto="descripcion_del_proceso",
        campo_proveedor="proveedor_adjudicado",
        campo_nit="nit_proveedor",
        campo_valor="valor_total_adjudicacion",
        campo_fecha="fecha_de_firma",
        terminos=["HUEVO","PAE","FAMI","ICBF","EJERCITO","BATALLON"],
        nombre_ds="Integrado"
    )
    todos_raw.extend(normalizar(raw2, m2, "SECOP Integrado"))

    # ── DS3: SECOP I Contratos (xvdy-vvsk) ──
    print("  [DS3] SECOP I...")
    raw3, m3 = secop_dataset(
        url="https://www.datos.gov.co/resource/xvdy-vvsk.json",
        campo_entidad="nombre_entidad",
        campo_municipio="municipio",
        campo_objeto="descripcion_proceso",
        campo_proveedor="nombre_del_proveedor",
        campo_nit="nit_del_proveedor",
        campo_valor="valor_contrato",
        campo_fecha="fecha_adjudicacion",
        terminos=["HUEVO","FAMI","ICBF","PAE","BATALLON"],
        nombre_ds="SECOP I"
    )
    todos_raw.extend(normalizar(raw3, m3, "SECOP I"))

    # ── DS4: Contratos ICBF SECOP II (cvym-nxdk) — ESPECÍFICO ICBF ──
    print("  [DS4] Contratos ICBF especifico...")
    for t in ["FAMI","HOGAR COMUNITARIO","MATERNO","CDI","HUEVO","ALIMENTO"]:
        datos = api_get(
            "https://www.datos.gov.co/resource/cvym-nxdk.json",
            {
                "$where": f"upper(descripcion_del_proceso) like '%{t}%' "
                          f"AND upper(ciudad) like '%BOYAC%'",
                "$order": "fecha_de_firma DESC",
                "$limit": "15",
                "$select": "nombre_entidad,ciudad,descripcion_del_proceso,"
                           "proveedor_adjudicado,documento_proveedor,"
                           "valor_del_contrato,fecha_de_firma"
            },
            f"ICBF DS '{t}'"
        )
        todos_raw.extend(normalizar(
            datos,
            ("nombre_entidad","ciudad","descripcion_del_proceso",
             "proveedor_adjudicado","documento_proveedor",
             "valor_del_contrato","fecha_de_firma"),
            "ICBF SECOP II"
        ))
        time.sleep(1)

    # ── DS5: Fuerzas Militares — ALFM (agencia logistica) ──
    print("  [DS5] Fuerzas Militares / ALFM...")
    for t in ["HUEVO","RANCHO","ALIMENTO","AVICOLA"]:
        datos = api_get(
            "https://www.datos.gov.co/resource/jbjy-vk9h.json",
            {
                "$where": f"upper(descripcion_del_proceso) like '%{t}%' "
                          f"AND (upper(nombre_entidad) like '%MILITAR%' "
                          f"OR upper(nombre_entidad) like '%EJERCITO%' "
                          f"OR upper(nombre_entidad) like '%EJÉRCITO%' "
                          f"OR upper(nombre_entidad) like '%ALFM%' "
                          f"OR upper(nombre_entidad) like '%BATALLON%' "
                          f"OR upper(nombre_entidad) like '%BRIGADA%')",
                "$order": "fecha_de_firma DESC",
                "$limit": "15",
                "$select": "nombre_entidad,ciudad,descripcion_del_proceso,"
                           "proveedor_adjudicado,documento_proveedor,"
                           "valor_del_contrato,fecha_de_firma"
            },
            f"FFMM '{t}'"
        )
        todos_raw.extend(normalizar(
            datos,
            ("nombre_entidad","ciudad","descripcion_del_proceso",
             "proveedor_adjudicado","documento_proveedor",
             "valor_del_contrato","fecha_de_firma"),
            "FUERZAS MILITARES"
        ))
        time.sleep(1)

    # ── DS6: Buscar específicamente "Dando Pasos de Vida" ──
    print("  [DS6] Buscando Fundacion Dando Pasos de Vida...")
    for ds_url in [
        "https://www.datos.gov.co/resource/jbjy-vk9h.json",
        "https://www.datos.gov.co/resource/xvdy-vvsk.json",
        "https://www.datos.gov.co/resource/rpmr-utcd.json"
    ]:
        for campo_prov in ["proveedor_adjudicado","nombre_del_proveedor"]:
            datos = api_get(ds_url, {
                "$where": f"upper({campo_prov}) like '%DANDO PASOS%'",
                "$order": "fecha_de_firma DESC" if "jbjy" in ds_url else "fecha_adjudicacion DESC",
                "$limit": "20"
            }, f"Dando Pasos ({campo_prov[:15]})")
            if datos:
                # Detectar campos disponibles
                primer = datos[0]
                ent  = "nombre_entidad"
                mun  = "ciudad" if "ciudad" in primer else "municipio"
                obj  = "descripcion_del_proceso" if "descripcion_del_proceso" in primer else "descripcion_proceso"
                prov = campo_prov
                nit  = "documento_proveedor" if "documento_proveedor" in primer else "nit_del_proveedor"
                val  = "valor_del_contrato" if "valor_del_contrato" in primer else "valor_contrato"
                fech = "fecha_de_firma" if "fecha_de_firma" in primer else "fecha_adjudicacion"
                todos_raw.extend(normalizar(datos, (ent,mun,obj,prov,nit,val,fech),
                                            "Dando Pasos de Vida"))
            time.sleep(1)

    # ── Deduplicar ──
    vistos = set()
    unicos = []
    for c in todos_raw:
        clave = f"{c['entidad'][:25]}|{c['proveedor'][:20]}|{c['valor']}"
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(c)

    # ── Ordenar: externos y fundaciones primero ──
    unicos.sort(key=lambda x: (
        0 if "EXTERNO" in x["tipo_prov"] else
        1 if "FUNDACION" in x["tipo_prov"] else
        2 if "COOPERATIVA" in x["tipo_prov"] else
        3 if "LOCAL" in x["tipo_prov"] else 4
    ))

    # ── Estadísticas ──
    externos   = [c for c in unicos if "EXTERNO"   in c["tipo_prov"]]
    fundas     = [c for c in unicos if "FUNDACION" in c["tipo_prov"]]
    locales    = [c for c in unicos if "LOCAL"     in c["tipo_prov"]]
    icbf_l     = [c for c in unicos if "ICBF"      in c["categoria"] or "HOGAR" in c["categoria"]]
    pae_l      = [c for c in unicos if "PAE"       in c["categoria"]]
    militar_l  = [c for c in unicos if "MILITAR"   in c["categoria"]]
    dando      = [c for c in unicos if "DANDO PASOS" in c["proveedor"].upper()]

    print(f"\n  ══ RESUMEN SECOP ══")
    print(f"  Total contratos:               {len(unicos)}")
    print(f"  Externos (atacar):             {len(externos)}")
    print(f"  Fundaciones / cooperativas:    {len(fundas)}")
    print(f"  Locales Boyaca (competencia):  {len(locales)}")
    print(f"  ICBF / FAMI / Materno:         {len(icbf_l)}")
    print(f"  PAE escolar:                   {len(pae_l)}")
    print(f"  Fuerzas Militares:             {len(militar_l)}")
    print(f"  Fundacion Dando Pasos:         {len(dando)}")

    return unicos


# ═══════════════════════════════════════════════════════
# MÓDULO EXCEL — 5 ARCHIVOS
# ═══════════════════════════════════════════════════════

def guardar_excels(contratos, fecha):
    if not contratos:
        print("  Sin datos para exportar")
        return

    campos = ["fuente","entidad","municipio","objeto","categoria",
              "proveedor","nit_prov","tipo_prov","valor","fecha"]

    archivos = {
        f"reportes/1_TODOS_los_contratos_{fecha}.csv":           contratos,
        f"reportes/2_ATACAR_intermediarios_externos_{fecha}.csv":
            [c for c in contratos if "EXTERNO"   in c["tipo_prov"]],
        f"reportes/3_ICBF_FAMI_materno_infantil_{fecha}.csv":
            [c for c in contratos if "ICBF" in c["categoria"] or "HOGAR" in c["categoria"]],
        f"reportes/4_PAE_escolar_{fecha}.csv":
            [c for c in contratos if "PAE" in c["categoria"]],
        f"reportes/5_FUERZAS_MILITARES_{fecha}.csv":
            [c for c in contratos if "MILITAR" in c["categoria"]],
    }

    # Archivo especial: Fundacion Dando Pasos de Vida
    dando = [c for c in contratos if "DANDO PASOS" in c["proveedor"].upper()]
    if dando:
        archivos[f"reportes/6_Fundacion_Dando_Pasos_TODOS_municipios_{fecha}.csv"] = dando

    for ruta, datos in archivos.items():
        if datos:
            with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
                w.writeheader()
                w.writerows(datos)
            print(f"  ✓ {ruta.split('/')[-1]}  ({len(datos)} filas)")
        else:
            print(f"  — Sin datos: {ruta.split('/')[-1]}")


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════

def main():
    fecha = date.today().isoformat()
    inicio = datetime.now()

    print("=" * 60)
    print(f"  AGENTE AVICOLA SIACHOQUE - {fecha}")
    print("=" * 60)

    # 1. SECOP completo
    contratos = secop_completo()

    externos  = [c for c in contratos if "EXTERNO"   in c["tipo_prov"]]
    fundas    = [c for c in contratos if "FUNDACION" in c["tipo_prov"]]
    locales   = [c for c in contratos if "LOCAL"     in c["tipo_prov"]]
    icbf_l    = [c for c in contratos if "ICBF"      in c["categoria"] or "HOGAR" in c["categoria"]]
    pae_l     = [c for c in contratos if "PAE"       in c["categoria"]]
    militar_l = [c for c in contratos if "MILITAR"   in c["categoria"]]
    dando     = [c for c in contratos if "DANDO PASOS" in c["proveedor"].upper()]

    # Guardar Excels inmediatamente
    print("\nGenerando archivos Excel...")
    guardar_excels(contratos, fecha)

    # 2. Convocatorias
    print("\n[2/5] Buscando convocatorias abiertas...")
    time.sleep(12)
    convocatorias = claude_buscar(f"""
Eres agente comercial para avicultor de Siachoque, Boyaca (500-2000 aves ponedoras).
Busca HOY {date.today().strftime('%d/%m/%Y')} convocatorias abiertas en:
1. PAE Boyaca: alimenteengrande.boyaca.gov.co
2. ICBF Regional Boyaca: icbf.gov.co (FAMI, hogares comunitarios, CDI)
3. ADR ruedas de negocios avicolas: adr.gov.co/convocatorias
4. ALFM Fuerzas Militares: agencialogistica.gov.co
5. Gobernacion Boyaca: boyaca.gov.co

Para cada convocatoria: entidad, objeto, fecha cierre, como aplicar.
Clasifica: URGENTE / PROXIMA / FUTURA.
""")

    # 3. Programas ICBF y militares en zona
    print("\n[3/5] Programas ICBF y Fuerzas Militares en zona...")
    time.sleep(18)
    icbf_militar = claude_buscar(f"""
Busca en Siachoque, Soraca, Toca, Chivata y Tunja, Boyaca en 2026:

ICBF:
- Hogares FAMI activos (madres lactantes y gestantes)
- Hogares Comunitarios de Bienestar (HCB) 
- CDI Centros de Desarrollo Infantil
- Operadores que los ejecutan y si incluyen huevos en la racion

FUERZAS MILITARES:
- Batallon de Infanteria No. 1 Tarqui en Tunja
- Brigada No. 5 Tunja
- Agencia Logistica Fuerzas Militares ALFM — suministro alimentos
- Como registrarse como proveedor de huevos para el Ejercito

Contactos: ICBF Tunja (608)7422929 — ALFM 018000126537
""")

    # 4. Precio semanal
    print("\n[4/5] Precio FENAVI...")
    time.sleep(18)
    precio = claude_buscar(f"""
Precio cubeta 30 huevos Colombia semana {date.today().strftime('%d/%m/%Y')}:
1. Precio FENAVI nacional
2. Precio plaza Tunja SIPSA-DANE
Compara con $11.500 productor Siachoque. Maximo 5 lineas.
""")

    # 5. Resumen ejecutivo con toda la inteligencia
    print("\n[5/5] Generando resumen ejecutivo...")
    time.sleep(18)

    # Preparar contexto rico para el resumen
    txt_ext = "\n".join(
        f"  {c['municipio']:15} | {c['entidad'][:38]} | proveedor: {c['proveedor'][:30]} | ${c['valor']}"
        for c in externos[:8]
    ) or "  No identificados aun"

    txt_dando = "\n".join(
        f"  {c['municipio']:15} | {c['entidad'][:38]} | {c['categoria']} | ${c['valor']} | {c['fecha']}"
        for c in dando[:10]
    ) or "  No encontrada en SECOP con ese nombre exacto — verificar manualmente"

    txt_icbf = "\n".join(
        f"  {c['municipio']:15} | {c['entidad'][:38]} | {c['categoria']} | ${c['valor']}"
        for c in icbf_l[:6]
    ) or "  Sin contratos ICBF encontrados"

    txt_militar = "\n".join(
        f"  {c['municipio']:15} | {c['entidad'][:38]} | ${c['valor']}"
        for c in militar_l[:5]
    ) or "  Sin contratos militares encontrados"

    resumen = claude_buscar(f"""
Eres asesor de avicultor campesino de Siachoque, Boyaca, 500-2000 aves ponedoras.
Hoy: {date.today().strftime('%d/%m/%Y')}

INTELIGENCIA SECOP RECOPILADA HOY:

Contratos totales encontrados en Boyaca: {len(contratos)}

FUNDACION DANDO PASOS DE VIDA — en cuantos municipios opera ({len(dando)} contratos):
{txt_dando}

INTERMEDIARIOS EXTERNOS que puedes desplazar con Ley 2046 ({len(externos)}):
{txt_ext}

CONTRATOS ICBF / FAMI / Materno Infantil ({len(icbf_l)}):
{txt_icbf}

CONTRATOS FUERZAS MILITARES ({len(militar_l)}):
{txt_militar}

PROGRAMAS ICBF Y MILITARES EN ZONA:
{icbf_militar[:500]}

PRECIO: {precio[:150]}
CONVOCATORIAS: {convocatorias[:350]}

CONTACTOS ESTABLECIDOS:
- ESE Siachoque: 7319093 (Heidy Johana Correa)
- Alcaldia Siachoque: 7404476 (Jairo Grijalba)
- ESE Soraca: 7404270 (Maricela Guerrero)
- ESE Tunja: 311 2169007
- ICBF Tunja: (608) 7422929
- ALFM Ejercito: 018000126537
- PAE Boyaca: 7420150 Ext. 2367

Con base en los municipios donde opera Fundacion Dando Pasos de Vida
y los intermediarios externos identificados, dame las 3 ACCIONES MAS 
URGENTES esta semana para comenzar a desplazarlos como proveedor local.
Para cada accion: municipio especifico, entidad, telefono, que decir.
Maximo 300 palabras. Solo texto plano.
""")

    duracion = (datetime.now() - inicio).seconds

    # ── Reporte TXT completo ──
    sep = "=" * 60
    lin = "─" * 50

    reporte = f"""REPORTE AVICOLA SIACHOQUE
{fecha}
{sep}

ACCIONES URGENTES ESTA SEMANA:
{resumen}

{sep}
PRECIO HUEVO:
{precio}

{sep}
CONVOCATORIAS ABIERTAS (PAE + ICBF + ADR + EJERCITO):
{convocatorias}

{sep}
PROGRAMAS ICBF Y FUERZAS MILITARES EN TU ZONA:
{icbf_militar}

{sep}
RESUMEN COMPETIDORES SECOP
Total contratos:                    {len(contratos)}
Intermediarios externos (atacar):   {len(externos)}
Fundaciones / cooperativas:         {len(fundas)}
Proveedores locales Boyaca:         {len(locales)}
Contratos ICBF / FAMI:             {len(icbf_l)}
Contratos PAE escolar:             {len(pae_l)}
Contratos Fuerzas Militares:       {len(militar_l)}
Fundacion Dando Pasos de Vida:     {len(dando)} municipios

ARCHIVOS EXCEL GENERADOS:
  1_TODOS_los_contratos_{fecha}.csv
  2_ATACAR_intermediarios_externos_{fecha}.csv
  3_ICBF_FAMI_materno_infantil_{fecha}.csv
  4_PAE_escolar_{fecha}.csv
  5_FUERZAS_MILITARES_{fecha}.csv
  6_Fundacion_Dando_Pasos_TODOS_municipios_{fecha}.csv (si encontro datos)
{sep}

FUNDACION DANDO PASOS DE VIDA — municipios donde opera:
"""
    for c in dando:
        reporte += f"""
  Municipio:  {c['municipio']}
  Entidad:    {c['entidad']}
  Programa:   {c['categoria']}
  Objeto:     {c['objeto'][:90]}
  Valor:      ${c['valor']}
  Fecha:      {c['fecha']}
  {lin}"""

    if not dando:
        reporte += "\n  No encontrada con nombre exacto — verificar en SECOP buscando 'DANDO PASOS'\n"

    reporte += f"\n{sep}\nINTERMEDIARIOS EXTERNOS — ATACAR YA:\n"
    for c in externos[:12]:
        reporte += f"""
  Municipio:  {c['municipio']}
  Entidad:    {c['entidad']}
  Programa:   {c['categoria']}
  Proveedor:  {c['proveedor']}  [{c['tipo_prov']}]
  NIT:        {c['nit_prov']}
  Valor:      ${c['valor']}
  Fecha:      {c['fecha']}
  {lin}"""

    reporte += f"\n{sep}\nCONTRATOS ICBF / FAMI / MATERNO INFANTIL:\n"
    for c in icbf_l[:10]:
        reporte += f"""
  Municipio:  {c['municipio']}
  Entidad:    {c['entidad']}
  Programa:   {c['categoria']}
  Proveedor:  {c['proveedor']}  [{c['tipo_prov']}]
  Valor:      ${c['valor']}
  {lin}"""

    reporte += f"\n{sep}\nCONTRATOS FUERZAS MILITARES:\n"
    for c in militar_l[:8]:
        reporte += f"""
  Entidad:    {c['entidad']}
  Municipio:  {c['municipio']}
  Proveedor:  {c['proveedor']}
  Valor:      ${c['valor']}
  {lin}"""

    reporte += f"\n{sep}\nPROVEEDORES LOCALES BOYACA (competencia):\n"
    for c in locales[:8]:
        reporte += f"""
  Municipio:  {c['municipio']}
  Proveedor:  {c['proveedor']}
  NIT:        {c['nit_prov']}
  Entidad:    {c['entidad']}
  Valor:      ${c['valor']}
  {lin}"""

    reporte += f"\n\nGenerado en {duracion} segundos."

    # Guardar
    with open(f"reportes/reporte_{fecha}.txt", "w", encoding="utf-8") as f:
        f.write(reporte)
    with open(f"reportes/contratos_{fecha}.json", "w", encoding="utf-8") as f:
        json.dump(contratos, f, ensure_ascii=False, indent=2)

    # Consola
    print()
    print(sep)
    print("ACCIONES URGENTES:")
    print(resumen)
    print()
    print(f"  Contratos SECOP:      {len(contratos)}")
    print(f"  Dando Pasos de Vida:  {len(dando)} municipios encontrados")
    print(f"  Externos (atacar):    {len(externos)}")
    print(f"  ICBF / FAMI:         {len(icbf_l)}")
    print(f"  Militares:            {len(militar_l)}")
    print(f"  Duracion:             {duracion}s")
    print(sep)


if __name__ == "__main__":
    main()
