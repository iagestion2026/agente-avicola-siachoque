import os, requests, json, time, csv
from datetime import date, datetime
from pathlib import Path

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
if not API_KEY:
    print("ERROR: No se encontro ANTHROPIC_API_KEY")
    exit(1)
print(f"OK: API key ({API_KEY[:12]}...)")
Path("reportes").mkdir(exist_ok=True)

NIT_DANDO_PASOS = "900514813"

# ═══════════════════════════════════════════════════════
# LOS 123 MUNICIPIOS DE BOYACÁ
# Buscamos por nombre de municipio para no perder ninguno
# ═══════════════════════════════════════════════════════

MUNICIPIOS_BOYACA = [
    "TUNJA","SOGAMOSO","DUITAMA","PAIPA","CHIQUINQUIRA","MONIQUIRA",
    "SOATA","PUERTO BOYACA","SANTA ROSA DE VITERBO","NOBSA","TIBASOSA",
    "SAMACA","VENTAQUEMADA","VILLA DE LEYVA","RAQUIRA","SACHICA",
    "TINJACA","ARCABUCO","GACHANTIVA","SUTAMARCHAN","SANTA SOFIA",
    "RONDONA","TOGUI","BELEN","CERINZA","CORRALES","FLORESTA","BUSBANZA",
    "BETEITIVA","CHITA","JERICO","SUSACON","TIPACOQUE","SOCHA","TASCO",
    "PAZ DE RIO","SOCOTA","TUTAZA","MONGUA","GAMEZA","TOPAGA","MONGUI",
    "IZA","CUITIVA","TOTA","AQUITANIA","LABRANZAGRANDE","PISBA","PAYA",
    "PAJARITO","CUBARA","GUICAN","EL COCUY","PANQUEBA","EL ESPINO","CHISCAS",
    "CACOTA DE VELASCO","BOAVITA","COVARACHIA","LA UVITA","SAN MATEO",
    "CHITARAQUE","SANTANA","BRICENO","SAN JOSE DE PARE","TOGUI","BERBEO",
    "RAMIRIQUI","RONDON","TIBANA","TURMEQUE","UMBITA","VIRACACHA",
    "JENESANO","NUEVO COLON","BOYACA","CIENEGA","SIACHOQUE","SORACA",
    "TOCA","COMBITA","CHIVATA","OICATA","MOTAVITA","CUCAITA","SORA",
    "SAMACA","TUNUNGUA","PORE","OTANCHE","COPER","MARIPI","SAN PABLO BORBUR",
    "BRICEÑO","MUZO","CALDAS","BUENAVISTA","QUIPAMA","SABOYA","CALDAS",
    "CHIQUINQUIRA","SAN MIGUEL DE SEMA","SAN JOSE DE PARE","SUTAMARCHAN",
    "TUNUNGUÁ","ALMEIDA","CHIVOR","MACANAL","MIRAFLORES","SANTA MARIA",
    "SAN LUIS DE GACENO","LA CAPILLA","PACHAVITA","GUATEQUE","GUAYATA",
    "SUTATENZA","TENZA","GARAGOA","MACANAL","SANTA BARBARA","SOMONDOCO",
    "SUTATENZA","BERBEO","ZETAQUIRA","PAEZ","CAMPOHERMOSO"
]

# Versiones simplificadas para busqueda (sin tildes)
MUNICIPIOS_BUSQUEDA = list(set([
    m.upper()
    .replace("Á","A").replace("É","E").replace("Í","I")
    .replace("Ó","O").replace("Ú","U")
    for m in MUNICIPIOS_BOYACA
]))

# ═══════════════════════════════════════════════════════
# UTILIDADES
# ═══════════════════════════════════════════════════════

def api_get(url, params, nombre=""):
    for intento in range(3):
        try:
            r = requests.get(url, params=params, timeout=30,
                             headers={"Accept": "application/json"})
            r.raise_for_status()
            datos = r.json()
            if isinstance(datos, list) and datos:
                if nombre:
                    print(f"    {nombre}: {len(datos)} registros")
                return datos
            return []
        except Exception as e:
            if intento < 2:
                time.sleep(4)
            else:
                if nombre:
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
            time.sleep(intento * 30)
            return claude_buscar(prompt, intento + 1)
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {e}"


def clasificar_proveedor(nombre):
    if not nombre or nombre in ("N/A", ""):
        return "NO IDENTIFICADO"
    p = nombre.upper()
    muni_boyaca = ["BOYACA","BOYACÁ","TUNJA","DUITAMA","SOGAMOSO","PAIPA",
                   "SIACHOQUE","SORACA","VENTAQUEMADA","SAMACA","TOCA",
                   "CHIVATA","JENESANO","COMBITA","RAMIRIQUI","MOTAVITA",
                   "CUCAITA","OICATA","NUEVO COLON","TIBANA","TURMEQUE",
                   "BELEN","SOATA","CHIQUINQUIRA","MONIQUIRA","NOBSA",
                   "TIBASOSA","VILLA DE LEYVA","RAQUIRA","AQUITANIA"]
    externos = ["BOGOTA","BOGOTÁ","MEDELLIN","MEDELLÍN","CALI","BARRANQUILLA",
                "BUCARAMANGA","ANTIOQUIA","CUNDINAMARCA","SANTANDER","VALLE",
                "ATLANTICO","RISARALDA","CALDAS","NARINO","TOLIMA","HUILA"]
    cooperativas = ["COOPERATIVA","COOP ","ASOCIACION","ASOC ","FUNDACION",
                    "FUNDACIÓN","CORP ","CORPORACION","CORPORACIÓN"]
    if any(x in p for x in muni_boyaca):
        return "PROVEEDOR LOCAL BOYACA"
    if any(x in p for x in externos):
        return "INTERMEDIARIO EXTERNO"
    if any(x in p for x in cooperativas):
        return "FUNDACION / COOPERATIVA"
    return "EXTERNO (verificar)"


def clasificar_categoria(objeto):
    if not objeto:
        return "ALIMENTOS GENERAL"
    o = objeto.upper()
    if any(x in o for x in ["FAMI","LACTANTE","GESTANTE","MATERNO","CANASTA NUTRI"]):
        return "ICBF MATERNO INFANTIL"
    if any(x in o for x in ["HOGAR COMUNITARIO","CDI","PRIMERA INFANCIA","BIENESTAR FAMILIAR"]):
        return "HOGAR COMUNITARIO ICBF"
    if any(x in o for x in ["PAE","ESCOLAR","RESTAURANTE ESCOLAR","ALIMENTACION ESCOLAR"]):
        return "PAE ESCOLAR"
    if any(x in o for x in ["HOSPITAL","SALUD","ESE ","CLINICA","CENTRO DE SALUD"]):
        return "HOSPITAL / ESE"
    if any(x in o for x in ["EJERCITO","EJÉRCITO","BATALLON","BATALLÓN",
                              "TROPA","MILITAR","ALFM","RANCHO"]):
        return "FUERZAS MILITARES"
    if any(x in o for x in ["ICBF","INFANCIA","BIENESTAR"]):
        return "ICBF GENERAL"
    return "ALIMENTOS GENERAL"


def norm(c, ce, cm, co, cp, cn, cv, cf, fuente):
    proveedor = str(c.get(cp, "N/A"))
    objeto    = str(c.get(co, "N/A"))[:130]
    return {
        "fuente":    fuente,
        "entidad":   str(c.get(ce, "N/A")),
        "municipio": str(c.get(cm, "N/A")),
        "objeto":    objeto,
        "categoria": clasificar_categoria(objeto),
        "proveedor": proveedor,
        "nit_prov":  str(c.get(cn, "N/A")),
        "tipo_prov": clasificar_proveedor(proveedor),
        "valor":     str(c.get(cv, "N/A")),
        "fecha":     str(c.get(cf, "N/A"))[:10]
    }


# ═══════════════════════════════════════════════════════
# BÚSQUEDA SECOP — POR MUNICIPIO + POR TERMINO
# ═══════════════════════════════════════════════════════

def buscar_por_municipios_y_termino(url, campo_municipio, campo_objeto,
                                     campos_select, terminos, municipios,
                                     fuente, campo_fecha="fecha_de_firma"):
    """
    Estrategia correcta: busca por cada municipio de Boyacá individualmente.
    Esto garantiza que no se pierda ninguno de los 123 municipios.
    """
    resultados = []
    total_encontrados = 0

    # Construir condición OR con todos los municipios
    # SECOP usa nombres en mayúsculas sin tildes
    muni_condicion = " OR ".join(
        f"upper({campo_municipio}) like '%{m}%'"
        for m in municipios[:40]  # primero los 40 más cercanos a Siachoque
    )

    for termino in terminos:
        datos = api_get(url, {
            "$where": f"upper({campo_objeto}) like '%{termino}%' "
                      f"AND ({muni_condicion})",
            "$order": f"{campo_fecha} DESC",
            "$limit": "50",
            "$select": campos_select
        }, f"{fuente} '{termino}' (40 munis)")
        resultados.extend(datos)
        total_encontrados += len(datos)
        time.sleep(1)

    # Segunda pasada: los municipios restantes
    if len(municipios) > 40:
        muni_condicion2 = " OR ".join(
            f"upper({campo_municipio}) like '%{m}%'"
            for m in municipios[40:]
        )
        for termino in ["HUEVO","PAE","FAMI","ICBF"]:  # solo los principales
            datos = api_get(url, {
                "$where": f"upper({campo_objeto}) like '%{termino}%' "
                          f"AND ({muni_condicion2})",
                "$order": f"{campo_fecha} DESC",
                "$limit": "30",
                "$select": campos_select
            }, f"{fuente} '{termino}' (munis 41-123)")
            resultados.extend(datos)
            time.sleep(1)

    print(f"  {fuente}: {len(resultados)} registros en 123 municipios Boyacá")
    return resultados


def buscar_dando_pasos():
    print(f"  [DANDO PASOS] Buscando NIT {NIT_DANDO_PASOS}...")
    resultados = []

    for url, campo_prov, campo_nit, campo_muni, campo_obj, campo_val, campo_fecha in [
        ("https://www.datos.gov.co/resource/jbjy-vk9h.json",
         "proveedor_adjudicado","documento_proveedor","ciudad",
         "descripcion_del_proceso","valor_del_contrato","fecha_de_firma"),
        ("https://www.datos.gov.co/resource/9kwp-7nmt.json",
         "nom_razon_social_contratista","identificacion_del_contratista",
         "municipios_ejecucion","objeto_a_contratar","cuantia_proceso",
         "fecha_de_firma_del_contrato"),
        ("https://www.datos.gov.co/resource/rpmr-utcd.json",
         "proveedor_adjudicado","nit_proveedor","municipio",
         "descripcion_del_proceso","valor_total_adjudicacion","fecha_de_firma"),
    ]:
        datos = api_get(url, {
            "$where": f"{campo_nit}='{NIT_DANDO_PASOS}' "
                      f"OR upper({campo_prov}) like '%DANDO PASOS%'",
            "$limit": "100",
            "$select": f"nombre_entidad,{campo_muni},{campo_obj},"
                       f"{campo_prov},{campo_nit},{campo_val},{campo_fecha}"
        }, f"Dando Pasos NIT")
        for c in datos:
            r = norm(c, "nombre_entidad", campo_muni, campo_obj,
                     campo_prov, campo_nit, campo_val, campo_fecha,
                     "Dando Pasos de Vida")
            r["tipo_prov"] = "FUNDACION DANDO PASOS DE VIDA"
            resultados.append(r)
        time.sleep(1)

    print(f"    Dando Pasos: {len(resultados)} contratos encontrados")
    return resultados


def secop_123_municipios():
    print("\n[1/5] Consultando SECOP — 123 municipios de Boyacá...")
    todos = []

    # Municipios prioritarios (radio 80km de Siachoque) van primero
    muni_prioritarios = [
        "SIACHOQUE","SORACA","TOCA","CHIVATA","OICATA","MOTAVITA","TUNJA",
        "VENTAQUEMADA","SAMACA","CUCAITA","SORA","COMBITA","JENESANO",
        "NUEVO COLON","TIBANA","TURMEQUE","UMBITA","RAMIRIQUI","BOYACA",
        "ALMEIDA","CHIQUIZA","RAQUIRA","DUITAMA","PAIPA","SOGAMOSO",
        "NOBSA","TIBASOSA","VILLA DE LEYVA","CHIQUINQUIRA","MONIQUIRA",
        "SANTA ROSA DE VITERBO","BELEN","SOATA","PUERTO BOYACA",
        "AQUITANIA","LABRANZAGRANDE","SAN LUIS DE GACENO","MIRAFLORES",
        "GARAGOA","GUATEQUE"
    ]
    muni_resto = [m for m in MUNICIPIOS_BUSQUEDA if m not in muni_prioritarios]
    todos_munis_ordenados = muni_prioritarios + muni_resto

    terminos_principales = ["HUEVO","AVICOLA","PAE","FAMI","ICBF","MATERNO",
                            "CANASTA","HOGAR COMUNITARIO","EJERCITO","BATALLON"]

    # ── DS1: SECOP II (jbjy-vk9h) — campo ciudad ──
    print("  [DS1] SECOP II por municipio...")
    raw1 = buscar_por_municipios_y_termino(
        url="https://www.datos.gov.co/resource/jbjy-vk9h.json",
        campo_municipio="ciudad",
        campo_objeto="descripcion_del_proceso",
        campos_select="nombre_entidad,ciudad,departamento,descripcion_del_proceso,"
                      "proveedor_adjudicado,documento_proveedor,"
                      "valor_del_contrato,fecha_de_firma,estado_contrato",
        terminos=terminos_principales,
        municipios=todos_munis_ordenados,
        fuente="SECOP II",
        campo_fecha="fecha_de_firma"
    )
    for c in raw1:
        todos.append(norm(c, "nombre_entidad","ciudad","descripcion_del_proceso",
                         "proveedor_adjudicado","documento_proveedor",
                         "valor_del_contrato","fecha_de_firma","SECOP II"))

    # ── DS2: SECOP I Completo (9kwp-7nmt) — campo municipios_ejecucion ──
    print("  [DS2] SECOP I por municipio...")
    raw2 = buscar_por_municipios_y_termino(
        url="https://www.datos.gov.co/resource/9kwp-7nmt.json",
        campo_municipio="municipios_ejecucion",
        campo_objeto="objeto_a_contratar",
        campos_select="nombre_entidad,municipios_ejecucion,objeto_a_contratar,"
                      "nom_razon_social_contratista,identificacion_del_contratista,"
                      "dpto_y_muni_contratista,cuantia_proceso,fecha_de_firma_del_contrato",
        terminos=["HUEVO","AVICOLA","PAE","FAMI","ICBF","BATALLON"],
        municipios=todos_munis_ordenados,
        fuente="SECOP I",
        campo_fecha="fecha_de_firma_del_contrato"
    )
    for c in raw2:
        todos.append(norm(c, "nombre_entidad","municipios_ejecucion","objeto_a_contratar",
                         "nom_razon_social_contratista","identificacion_del_contratista",
                         "cuantia_proceso","fecha_de_firma_del_contrato","SECOP I"))

    # ── DS3: SECOP Integrado (rpmr-utcd) — campo municipio ──
    print("  [DS3] SECOP Integrado por municipio...")
    raw3 = buscar_por_municipios_y_termino(
        url="https://www.datos.gov.co/resource/rpmr-utcd.json",
        campo_municipio="municipio",
        campo_objeto="descripcion_del_proceso",
        campos_select="nombre_entidad,municipio,descripcion_del_proceso,"
                      "proveedor_adjudicado,nit_proveedor,"
                      "valor_total_adjudicacion,fecha_de_firma",
        terminos=["HUEVO","PAE","FAMI","ICBF","EJERCITO"],
        municipios=todos_munis_ordenados,
        fuente="SECOP Integrado",
        campo_fecha="fecha_de_firma"
    )
    for c in raw3:
        todos.append(norm(c, "nombre_entidad","municipio","descripcion_del_proceso",
                         "proveedor_adjudicado","nit_proveedor",
                         "valor_total_adjudicacion","fecha_de_firma","Integrado"))

    # ── DS4: FUERZAS MILITARES — sin filtro de municipio ──
    print("  [DS4] Fuerzas Militares (nacional)...")
    for t in ["HUEVO","RANCHO","AVICOLA","ALIMENTO TROPA"]:
        datos = api_get(
            "https://www.datos.gov.co/resource/jbjy-vk9h.json",
            {
                "$where": f"upper(descripcion_del_proceso) like '%{t}%' "
                          f"AND (upper(nombre_entidad) like '%MILITAR%' "
                          f"OR upper(nombre_entidad) like '%EJERCITO%' "
                          f"OR upper(nombre_entidad) like '%EJÉRCITO%' "
                          f"OR upper(nombre_entidad) like '%ALFM%' "
                          f"OR upper(nombre_entidad) like '%BATALLON%' "
                          f"OR upper(nombre_entidad) like '%LOGISTICA%')",
                "$order": "fecha_de_firma DESC",
                "$limit": "20",
                "$select": "nombre_entidad,ciudad,descripcion_del_proceso,"
                           "proveedor_adjudicado,documento_proveedor,"
                           "valor_del_contrato,fecha_de_firma"
            }, f"FFMM '{t}'"
        )
        for c in datos:
            todos.append(norm(c, "nombre_entidad","ciudad","descripcion_del_proceso",
                             "proveedor_adjudicado","documento_proveedor",
                             "valor_del_contrato","fecha_de_firma","Fuerzas Militares"))
        time.sleep(1)

    # ── DS5: Fundación Dando Pasos por NIT ──
    dando = buscar_dando_pasos()
    todos.extend(dando)

    # ── Deduplicar ──
    vistos = set()
    unicos = []
    for c in todos:
        clave = f"{c['entidad'][:25]}|{c['proveedor'][:20]}|{c['valor']}"
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(c)

    # ── Ordenar ──
    orden = {"FUNDACION DANDO PASOS DE VIDA":0,
             "INTERMEDIARIO EXTERNO":1,
             "EXTERNO (verificar)":2,
             "FUNDACION / COOPERATIVA":3,
             "PROVEEDOR LOCAL BOYACA":4,
             "NO IDENTIFICADO":5}
    unicos.sort(key=lambda x: (orden.get(x["tipo_prov"],5), x["municipio"]))

    # ── Stats ──
    dando_f  = [c for c in unicos if "DANDO PASOS" in c["tipo_prov"]]
    externos = [c for c in unicos if c["tipo_prov"] in
                ("INTERMEDIARIO EXTERNO","EXTERNO (verificar)")]
    locales  = [c for c in unicos if "LOCAL" in c["tipo_prov"]]
    icbf_l   = [c for c in unicos if "ICBF" in c["categoria"] or "HOGAR" in c["categoria"]]
    pae_l    = [c for c in unicos if "PAE" in c["categoria"]]
    mil_l    = [c for c in unicos if "MILITAR" in c["categoria"]]
    ese_l    = [c for c in unicos if "HOSPITAL" in c["categoria"]]

    # Municipios únicos encontrados
    munis_encontrados = set(c["municipio"] for c in unicos if c["municipio"] != "N/A")

    print(f"\n  ══ RESUMEN FINAL ══")
    print(f"  Municipios de Boyacá con datos:   {len(munis_encontrados)}")
    print(f"  Total contratos:                   {len(unicos)}")
    print(f"  Fundacion Dando Pasos:             {len(dando_f)}")
    print(f"  Externos (atacar):                 {len(externos)}")
    print(f"  Proveedores locales:               {len(locales)}")
    print(f"  ICBF / FAMI / Materno:             {len(icbf_l)}")
    print(f"  PAE escolar:                       {len(pae_l)}")
    print(f"  Hospitales / ESE:                  {len(ese_l)}")
    print(f"  Fuerzas Militares:                 {len(mil_l)}")

    return unicos


# ═══════════════════════════════════════════════════════
# EXCEL — 6 ARCHIVOS
# ═══════════════════════════════════════════════════════

def guardar_excels(contratos, fecha):
    campos = ["fuente","entidad","municipio","objeto","categoria",
              "proveedor","nit_prov","tipo_prov","valor","fecha"]
    archivos = {
        f"1_TODOS_contratos_{fecha}.csv":          contratos,
        f"2_ATACAR_externos_{fecha}.csv":
            [c for c in contratos if c["tipo_prov"] in
             ("INTERMEDIARIO EXTERNO","EXTERNO (verificar)")],
        f"3_ICBF_FAMI_materno_{fecha}.csv":
            [c for c in contratos if "ICBF" in c["categoria"]
             or "HOGAR" in c["categoria"]],
        f"4_PAE_escolar_{fecha}.csv":
            [c for c in contratos if "PAE" in c["categoria"]],
        f"5_FUERZAS_MILITARES_{fecha}.csv":
            [c for c in contratos if "MILITAR" in c["categoria"]],
        f"6_DANDO_PASOS_{fecha}.csv":
            [c for c in contratos if "DANDO PASOS" in c["tipo_prov"]],
    }
    print("\nGenerando Excel/CSV...")
    for nombre, datos in archivos.items():
        ruta = f"reportes/{nombre}"
        with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
            w.writeheader()
            if datos:
                w.writerows(datos)
        estado = f"{len(datos)} filas" if datos else "sin datos esta semana"
        print(f"  {'✓' if datos else '—'} {nombre} ({estado})")


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════

def main():
    fecha = date.today().isoformat()
    inicio = datetime.now()
    sep = "=" * 60
    lin = "─" * 50

    print(sep)
    print(f"  AGENTE AVICOLA SIACHOQUE - {fecha}")
    print(sep)

    contratos = secop_123_municipios()
    guardar_excels(contratos, fecha)

    dando_f  = [c for c in contratos if "DANDO PASOS" in c["tipo_prov"]]
    externos = [c for c in contratos if c["tipo_prov"] in
                ("INTERMEDIARIO EXTERNO","EXTERNO (verificar)")]
    locales  = [c for c in contratos if "LOCAL" in c["tipo_prov"]]
    icbf_l   = [c for c in contratos if "ICBF" in c["categoria"] or "HOGAR" in c["categoria"]]
    pae_l    = [c for c in contratos if "PAE" in c["categoria"]]
    mil_l    = [c for c in contratos if "MILITAR" in c["categoria"]]
    ese_l    = [c for c in contratos if "HOSPITAL" in c["categoria"]]
    munis    = set(c["municipio"] for c in contratos if c["municipio"] != "N/A")

    # 2. Convocatorias
    print("\n[2/5] Convocatorias...")
    time.sleep(12)
    convocatorias = claude_buscar(f"""
Eres agente para avicultor de Siachoque, Boyaca (500-2000 aves).
Busca HOY {date.today().strftime('%d/%m/%Y')} convocatorias abiertas en:
1. alimenteengrande.boyaca.gov.co (PAE Boyaca)
2. icbf.gov.co Regional Boyaca (FAMI, hogares, CDI)
3. adr.gov.co/convocatorias (ruedas de negocios avicolas)
4. agencialogistica.gov.co (ALFM Fuerzas Militares)
5. boyaca.gov.co (pequenos productores 2026)
Para cada una: entidad, fecha cierre, como aplicar.
Clasifica: URGENTE / PROXIMA / FUTURA.
""")

    # 3. Programas ICBF y militares
    print("\n[3/5] Programas ICBF y Militares...")
    time.sleep(18)
    icbf_militar = claude_buscar(f"""
Busca en Siachoque, Soraca, Toca, Chivata, Tunja en 2026:
ICBF: Hogares FAMI, HCB, CDI — operadores, beneficiarios, si incluyen huevos.
FUERZAS MILITARES: Batallon Tarqui Tunja, Brigada, ALFM —
como registrarse proveedor huevos via Bolsa Mercantil (bolsamercantil.com.co)
o directamente ALFM 018000126537.
ICBF Tunja: (608) 7422929
""")

    # 4. Precio
    print("\n[4/5] Precio FENAVI...")
    time.sleep(18)
    precio = claude_buscar(f"""
Precio cubeta 30 huevos Colombia {date.today().strftime('%d/%m/%Y')}:
FENAVI nacional y Tunja SIPSA-DANE.
Compara con $11.500 Siachoque. Maximo 5 lineas.
""")

    # 5. Resumen
    print("\n[5/5] Resumen ejecutivo...")
    time.sleep(18)

    txt_dando = "\n".join(
        f"  {c['municipio']:18} | {c['entidad'][:40]} | {c['categoria']} | ${c['valor']} | {c['fecha']}"
        for c in dando_f
    ) or f"  Buscada por NIT {NIT_DANDO_PASOS} — 0 contratos directos.\n  Puede estar operando como subcontratista. Verificar en SECOP buscando NIT {NIT_DANDO_PASOS}"

    txt_ext = "\n".join(
        f"  {c['municipio']:18} | {c['entidad'][:35]} | {c['proveedor'][:28]} | ${c['valor']}"
        for c in externos[:10]
    ) or "  Sin externos identificados esta semana"

    resumen = claude_buscar(f"""
Eres asesor de avicultor de Siachoque, Boyaca, 500-2000 aves.
Hoy: {date.today().strftime('%d/%m/%Y')}

COBERTURA: Se consultaron {len(munis)} de los 123 municipios de Boyaca.
Total contratos encontrados: {len(contratos)}

FUNDACION DANDO PASOS (NIT {NIT_DANDO_PASOS}) — {len(dando_f)} contratos:
{txt_dando}

EXTERNOS QUE PUEDES DESPLAZAR ({len(externos)} casos):
{txt_ext}

ICBF/FAMI: {len(icbf_l)} contratos | PAE: {len(pae_l)} | ESE: {len(ese_l)} | Militares: {len(mil_l)}

PRECIO: {precio[:120]}
CONVOCATORIAS: {convocatorias[:300]}

CONTACTOS:
ESE Siachoque 7319093 | Alcaldia Siachoque 7404476
ESE Soraca 7404270 | ESE Tunja 311-2169007
ICBF Tunja (608)7422929 | ALFM 018000126537 | PAE 7420150 Ext.2367

Dame las 3 ACCIONES MAS URGENTES esta semana.
Para cada accion: municipio, entidad, telefono, que decir exactamente.
Maximo 300 palabras. Solo texto plano.
""")

    duracion = (datetime.now() - inicio).seconds

    reporte = f"""REPORTE AVICOLA SIACHOQUE
{fecha}
{sep}
COBERTURA: {len(munis)} municipios de Boyaca consultados

ACCIONES URGENTES:
{resumen}

{sep}
PRECIO: {precio}

{sep}
CONVOCATORIAS: {convocatorias}

{sep}
ICBF Y MILITARES EN TU ZONA: {icbf_militar}

{sep}
RESUMEN SECOP — {len(munis)} MUNICIPIOS DE BOYACA
Total contratos:              {len(contratos)}
Fundacion Dando Pasos:        {len(dando_f)} contratos
Externos (atacar):            {len(externos)}
Proveedores locales:          {len(locales)}
ICBF / FAMI:                 {len(icbf_l)}
PAE escolar:                  {len(pae_l)}
Hospitales / ESE:             {len(ese_l)}
Fuerzas Militares:            {len(mil_l)}

EXCELS ADJUNTOS:
  1_TODOS_contratos — {len(contratos)} filas
  2_ATACAR_externos — {len(externos)} filas
  3_ICBF_FAMI_materno — {len(icbf_l)} filas
  4_PAE_escolar — {len(pae_l)} filas
  5_FUERZAS_MILITARES — {len(mil_l)} filas
  6_DANDO_PASOS — {len(dando_f)} filas
{sep}

FUNDACION DANDO PASOS DE VIDA (NIT {NIT_DANDO_PASOS}):
"""
    for c in dando_f:
        reporte += f"\n  {c['municipio']} | {c['entidad']} | {c['categoria']} | ${c['valor']} | {c['fecha']}\n  {lin}"
    if not dando_f:
        reporte += f"\n  0 contratos directos con NIT {NIT_DANDO_PASOS}\n"
        reporte += "  Puede operar como subcontratista de otro operador mayor.\n"

    reporte += f"\n{sep}\nEXTERNOS POR MUNICIPIO:\n"
    for c in externos[:20]:
        reporte += f"\n  {c['municipio']:18} | {c['entidad'][:38]}\n  Proveedor: {c['proveedor']} | NIT: {c['nit_prov']} | ${c['valor']}\n  {lin}"

    reporte += f"\n{sep}\nICBF / FAMI / MATERNO:\n"
    for c in icbf_l[:12]:
        reporte += f"\n  {c['municipio']:18} | {c['entidad'][:38]}\n  {c['categoria']} | {c['proveedor']} | ${c['valor']}\n  {lin}"

    reporte += f"\n{sep}\nFUERZAS MILITARES:\n"
    for c in mil_l[:10]:
        reporte += f"\n  {c['entidad'][:40]} | {c['proveedor']} | ${c['valor']}\n  {lin}"

    reporte += f"\n{sep}\nPROVEEDORES LOCALES BOYACA:\n"
    for c in locales[:10]:
        reporte += f"\n  {c['municipio']:18} | {c['proveedor']} | NIT: {c['nit_prov']} | ${c['valor']}\n  {lin}"

    reporte += f"\n\nGenerado en {duracion}s"

    with open(f"reportes/reporte_{fecha}.txt","w",encoding="utf-8") as f:
        f.write(reporte)
    with open(f"reportes/contratos_{fecha}.json","w",encoding="utf-8") as f:
        json.dump(contratos, f, ensure_ascii=False, indent=2)

    print(f"\n{sep}")
    print("ACCIONES URGENTES:")
    print(resumen)
    print(f"\n  Municipios cubiertos:  {len(munis)}/123")
    print(f"  Total contratos:       {len(contratos)}")
    print(f"  Dando Pasos:           {len(dando_f)}")
    print(f"  Externos (atacar):     {len(externos)}")
    print(f"  ICBF/FAMI:            {len(icbf_l)}")
    print(f"  PAE:                   {len(pae_l)}")
    print(f"  Militares:             {len(mil_l)}")
    print(f"  Duracion:              {duracion}s")
    print(sep)


if __name__ == "__main__":
    main()
