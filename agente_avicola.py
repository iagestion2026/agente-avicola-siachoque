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

# ═══════════════════════════════════════════════════════════
# LOS 123 MUNICIPIOS DE BOYACÁ — nombres exactos como están
# en SECOP (sin tildes, en mayúsculas)
# ═══════════════════════════════════════════════════════════

MUNICIPIOS_BOYACA = [
    "TUNJA","SOGAMOSO","DUITAMA","PAIPA","CHIQUINQUIRA","MONIQUIRA",
    "SOATA","PUERTO BOYACA","SANTA ROSA DE VITERBO","NOBSA","TIBASOSA",
    "SAMACA","VENTAQUEMADA","VILLA DE LEYVA","RAQUIRA","SACHICA",
    "TINJACA","ARCABUCO","GACHANTIVA","SUTAMARCHAN","SANTA SOFIA",
    "TOGUI","BELEN","CERINZA","CORRALES","FLORESTA","BUSBANZA",
    "BETEITIVA","CHITA","JERICO","SUSACON","TIPACOQUE","SOCHA","TASCO",
    "PAZ DE RIO","SOCOTA","TUTAZA","MONGUA","GAMEZA","TOPAGA","MONGUI",
    "IZA","CUITIVA","TOTA","AQUITANIA","LABRANZAGRANDE","PISBA","PAYA",
    "PAJARITO","CUBARA","GUICAN","EL COCUY","PANQUEBA","EL ESPINO",
    "BOAVITA","COVARACHIA","LA UVITA","SAN MATEO","CHITARAQUE","SANTANA",
    "BRICENO","SAN JOSE DE PARE","BERBEO","RAMIRIQUI","RONDON","TIBANA",
    "TURMEQUE","UMBITA","VIRACACHA","JENESANO","NUEVO COLON","BOYACA",
    "CIENEGA","SIACHOQUE","SORACA","TOCA","COMBITA","CHIVATA","OICATA",
    "MOTAVITA","CUCAITA","SORA","TUNUNGUA","OTANCHE","COPER","MARIPI",
    "SAN PABLO BORBUR","MUZO","CALDAS","BUENAVISTA","QUIPAMA","SABOYA",
    "SAN MIGUEL DE SEMA","TUNUNGUA","ALMEIDA","CHIVOR","MACANAL",
    "MIRAFLORES","SANTA MARIA","SAN LUIS DE GACENO","LA CAPILLA",
    "PACHAVITA","GUATEQUE","GUAYATA","SUTATENZA","TENZA","GARAGOA",
    "SOMONDOCO","ZETAQUIRA","PAEZ","CAMPOHERMOSO","CHISCAS","GUICAN",
    "CUBARA","PISBA","SAN EDUARDO","BERBEO","ZETAQUIRA","RAMIRIQUI"
]
# Eliminar duplicados
MUNICIPIOS_BOYACA = list(dict.fromkeys(MUNICIPIOS_BOYACA))

# Departamentos de Boyacá para filtrar correctamente
DPTO_BOYACA = ["BOYACA","BOYACÁ","BOYACá","Boyacá","Boyaca","BOYACA"]

# ═══════════════════════════════════════════════════════════
# UTILIDADES
# ═══════════════════════════════════════════════════════════

def api_get(url, params, nombre=""):
    for intento in range(3):
        try:
            r = requests.get(url, params=params, timeout=35,
                             headers={"Accept": "application/json"})
            r.raise_for_status()
            datos = r.json()
            if isinstance(datos, list) and datos:
                if nombre:
                    print(f"    {nombre}: {len(datos)}")
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


def es_boyaca(municipio, departamento, entidad):
    """
    Verifica si un registro pertenece a Boyacá.
    Revisa municipio, departamento y nombre de entidad.
    """
    muni_up  = str(municipio).upper().strip()
    dpto_up  = str(departamento).upper().strip()
    ent_up   = str(entidad).upper().strip()

    # Si el departamento dice explícitamente Boyacá — incluir
    if any(d in dpto_up for d in ["BOYAC"]):
        return True

    # Si el municipio está en la lista de Boyacá — incluir
    for m in MUNICIPIOS_BOYACA:
        if m in muni_up or muni_up in m:
            return True

    # Si la entidad menciona Boyacá — incluir
    if "BOYAC" in ent_up:
        return True

    return False


def clasificar_proveedor(nombre, nit=""):
    if not nombre or nombre in ("N/A", "", "Sin Descripcion"):
        return "NO IDENTIFICADO"
    p = nombre.upper()

    # Proveedores locales de Boyacá
    boyaca_local = [
        "BOYACA","BOYACÁ","TUNJA","DUITAMA","SOGAMOSO","PAIPA",
        "SIACHOQUE","SORACA","VENTAQUEMADA","SAMACA","TOCA",
        "CHIVATA","JENESANO","COMBITA","RAMIRIQUI","MOTAVITA",
        "CUCAITA","OICATA","NUEVO COLON","TIBANA","TURMEQUE",
        "BELEN","SOATA","CHIQUINQUIRA","MONIQUIRA","NOBSA",
        "TIBASOSA","VILLA DE LEYVA","RAQUIRA","AQUITANIA",
        "NUTRITUNJA","BOYACA","ASOCIACION DE PRODUCTORES AGRICOLAS DE BOYACA"
    ]
    externos = [
        "BOGOTA","BOGOTÁ","MEDELLIN","MEDELLÍN","CALI","BARRANQUILLA",
        "BUCARAMANGA","ANTIOQUIA","CUNDINAMARCA","SANTANDER","VALLE",
        "ATLANTICO","RISARALDA","CALDAS","NARINO","TOLIMA","HUILA",
        "VALLEDUPAR","MANIZALES","PEREIRA","CARTAGENA","CUCUTA"
    ]
    cooperativas = [
        "COOPERATIVA","COOP ","ASOCIACION","ASOC ","FUNDACION",
        "FUNDACIÓN","CORP ","CORPORACION","FEDERACION","BALUARTE"
    ]

    if any(x in p for x in boyaca_local):
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
                              "TROPA","MILITAR","ALFM","RANCHO","LOGISTICA"]):
        return "FUERZAS MILITARES"
    if any(x in o for x in ["ICBF","INFANCIA","BIENESTAR"]):
        return "ICBF GENERAL"
    return "ALIMENTOS GENERAL"


# ═══════════════════════════════════════════════════════════
# BÚSQUEDA SECOP — ESTRATEGIA CORRECTA PARA BOYACÁ
# ═══════════════════════════════════════════════════════════

def buscar_secop2_por_dpto(terminos):
    """
    SECOP II: filtra por departamento = Boyacá directamente.
    Este es el filtro más preciso para SECOP II.
    """
    print("  [SECOP II] Filtrando por departamento Boyacá...")
    resultados = []

    for t in terminos:
        # Intentar con y sin tilde
        for dpto in ["Boyacá", "Boyaca", "BOYACA", "BOYACÁ"]:
            datos = api_get(
                "https://www.datos.gov.co/resource/jbjy-vk9h.json",
                {
                    "$where": f"upper(descripcion_del_proceso) like '%{t}%' "
                              f"AND (departamento='{dpto}' "
                              f"OR upper(departamento) like '%BOYAC%')",
                    "$order": "fecha_de_firma DESC",
                    "$limit": "30",
                    "$select": "nombre_entidad,ciudad,departamento,"
                               "descripcion_del_proceso,proveedor_adjudicado,"
                               "documento_proveedor,valor_del_contrato,"
                               "fecha_de_firma,estado_contrato"
                },
                f"SECOP2 dpto '{t}'"
            )
            resultados.extend(datos)
            time.sleep(0.8)

    print(f"    SECOP II por dpto: {len(resultados)} raw")
    return resultados


def buscar_secop2_por_municipios(terminos):
    """
    SECOP II: busca municipio por municipio para los 123 de Boyacá.
    Garantiza cobertura completa incluyendo municipios pequeños.
    """
    print("  [SECOP II] Buscando por cada municipio de Boyacá...")
    resultados = []

    # Procesar en lotes de 15 municipios para no hacer queries enormes
    lote_size = 15
    lotes = [MUNICIPIOS_BOYACA[i:i+lote_size]
             for i in range(0, len(MUNICIPIOS_BOYACA), lote_size)]

    for i, lote in enumerate(lotes):
        cond_munis = " OR ".join(
            f"upper(ciudad) like '%{m}%'" for m in lote
        )
        for t in ["HUEVO","PAE","FAMI","ICBF","BATALLON"]:
            datos = api_get(
                "https://www.datos.gov.co/resource/jbjy-vk9h.json",
                {
                    "$where": f"upper(descripcion_del_proceso) like '%{t}%' "
                              f"AND ({cond_munis})",
                    "$order": "fecha_de_firma DESC",
                    "$limit": "20",
                    "$select": "nombre_entidad,ciudad,departamento,"
                               "descripcion_del_proceso,proveedor_adjudicado,"
                               "documento_proveedor,valor_del_contrato,"
                               "fecha_de_firma"
                },
                f"Lote{i+1} '{t}'"
            )
            resultados.extend(datos)
            time.sleep(0.8)

    print(f"    SECOP II por municipios: {len(resultados)} raw")
    return resultados


def buscar_secop1_boyaca(terminos):
    """
    SECOP I: usa campo departamento_entidad y municipios_ejecucion.
    """
    print("  [SECOP I] Filtrando por Boyacá...")
    resultados = []

    for t in terminos:
        datos = api_get(
            "https://www.datos.gov.co/resource/9kwp-7nmt.json",
            {
                "$where": f"(upper(objeto_a_contratar) like '%{t}%' "
                          f"OR upper(detalle_del_objeto_a_contratar) like '%{t}%') "
                          f"AND (upper(municipios_ejecucion) like '%BOYAC%' "
                          f"OR upper(dpto_y_muni_entidad_ejecutora) like '%BOYAC%')",
                "$order": "fecha_de_firma_del_contrato DESC",
                "$limit": "25",
                "$select": "nombre_entidad,municipios_ejecucion,"
                           "dpto_y_muni_entidad_ejecutora,objeto_a_contratar,"
                           "nom_razon_social_contratista,"
                           "identificacion_del_contratista,"
                           "cuantia_proceso,fecha_de_firma_del_contrato"
            },
            f"SECOP1 '{t}'"
        )
        resultados.extend(datos)
        time.sleep(0.8)

    print(f"    SECOP I Boyacá: {len(resultados)} raw")
    return resultados


def buscar_militares():
    """Fuerzas Militares — sin filtro de municipio (son nacionales)."""
    print("  [FFMM] Fuerzas Militares...")
    resultados = []
    for t in ["HUEVO","RANCHO","AVICOLA","ALIMENTO TROPA","VIVERES"]:
        datos = api_get(
            "https://www.datos.gov.co/resource/jbjy-vk9h.json",
            {
                "$where": f"upper(descripcion_del_proceso) like '%{t}%' "
                          f"AND (upper(nombre_entidad) like '%MILITAR%' "
                          f"OR upper(nombre_entidad) like '%EJERCITO%' "
                          f"OR upper(nombre_entidad) like '%EJÉRCITO%' "
                          f"OR upper(nombre_entidad) like '%ALFM%' "
                          f"OR upper(nombre_entidad) like '%BATALLON%' "
                          f"OR upper(nombre_entidad) like '%BRIGADA%' "
                          f"OR upper(nombre_entidad) like '%LOGISTICA%')",
                "$order": "fecha_de_firma DESC",
                "$limit": "20",
                "$select": "nombre_entidad,ciudad,descripcion_del_proceso,"
                           "proveedor_adjudicado,documento_proveedor,"
                           "valor_del_contrato,fecha_de_firma"
            },
            f"FFMM '{t}'"
        )
        resultados.extend(datos)
        time.sleep(0.8)
    return resultados


def buscar_dando_pasos():
    """Busca Fundacion Dando Pasos por NIT en todos los datasets."""
    print(f"  [DANDO PASOS] NIT {NIT_DANDO_PASOS}...")
    resultados = []

    configs = [
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
    ]

    for url, cp, cn, cm, co, cv, cf in configs:
        datos = api_get(url, {
            "$where": f"{cn}='{NIT_DANDO_PASOS}' "
                      f"OR upper({cp}) like '%DANDO PASOS%'",
            "$limit": "100",
            "$select": f"nombre_entidad,{cm},{co},{cp},{cn},{cv},{cf}"
        }, "Dando Pasos NIT")
        for c in datos:
            resultados.append({
                "fuente":    "Dando Pasos de Vida",
                "entidad":   str(c.get("nombre_entidad", "N/A")),
                "municipio": str(c.get(cm, "N/A")),
                "objeto":    str(c.get(co, "N/A"))[:130],
                "categoria": clasificar_categoria(str(c.get(co, ""))),
                "proveedor": str(c.get(cp, "N/A")),
                "nit_prov":  str(c.get(cn, "N/A")),
                "tipo_prov": "FUNDACION DANDO PASOS DE VIDA",
                "valor":     str(c.get(cv, "N/A")),
                "fecha":     str(c.get(cf, "N/A"))[:10]
            })
        time.sleep(1)

    print(f"    Dando Pasos: {len(resultados)} contratos")
    return resultados


def normalizar_y_filtrar(raw_list, campo_entidad, campo_municipio,
                          campo_dpto, campo_objeto, campo_proveedor,
                          campo_nit, campo_valor, campo_fecha, fuente):
    """
    Normaliza registros Y filtra para quedarse solo con Boyacá.
    """
    normalizados = []
    descartados = 0

    for c in raw_list:
        entidad   = str(c.get(campo_entidad, "N/A"))
        municipio = str(c.get(campo_municipio, "N/A"))
        dpto      = str(c.get(campo_dpto, ""))
        objeto    = str(c.get(campo_objeto, "N/A"))[:130]
        proveedor = str(c.get(campo_proveedor, "N/A"))
        nit       = str(c.get(campo_nit, "N/A"))
        valor     = str(c.get(campo_valor, "N/A"))
        fecha     = str(c.get(campo_fecha, "N/A"))[:10]

        # FILTRO CRÍTICO: solo Boyacá
        if not es_boyaca(municipio, dpto, entidad):
            descartados += 1
            continue

        normalizados.append({
            "fuente":    fuente,
            "entidad":   entidad,
            "municipio": municipio,
            "objeto":    objeto,
            "categoria": clasificar_categoria(objeto),
            "proveedor": proveedor,
            "nit_prov":  nit,
            "tipo_prov": clasificar_proveedor(proveedor, nit),
            "valor":     valor,
            "fecha":     fecha
        })

    if descartados > 0:
        print(f"    Filtrados fuera de Boyacá: {descartados}")
    return normalizados


def secop_completo():
    print("\n[1/5] Consultando SECOP — cobertura 123 municipios Boyacá...")
    todos = []

    terminos_alimentos = ["HUEVO","AVICOLA","PAE","FAMI","ICBF",
                          "MATERNO","CANASTA","HOGAR COMUNITARIO",
                          "EJERCITO","BATALLON","ALIMENTO"]

    # ── Estrategia 1: SECOP II por departamento ──
    raw1 = buscar_secop2_por_dpto(terminos_alimentos)
    todos.extend(normalizar_y_filtrar(
        raw1, "nombre_entidad","ciudad","departamento",
        "descripcion_del_proceso","proveedor_adjudicado",
        "documento_proveedor","valor_del_contrato","fecha_de_firma",
        "SECOP II (dpto)"
    ))

    # ── Estrategia 2: SECOP II por municipios ──
    raw2 = buscar_secop2_por_municipios(terminos_alimentos)
    todos.extend(normalizar_y_filtrar(
        raw2, "nombre_entidad","ciudad","departamento",
        "descripcion_del_proceso","proveedor_adjudicado",
        "documento_proveedor","valor_del_contrato","fecha_de_firma",
        "SECOP II (municipio)"
    ))

    # ── Estrategia 3: SECOP I por Boyacá ──
    raw3 = buscar_secop1_boyaca(terminos_alimentos)
    todos.extend(normalizar_y_filtrar(
        raw3, "nombre_entidad","municipios_ejecucion",
        "dpto_y_muni_entidad_ejecutora","objeto_a_contratar",
        "nom_razon_social_contratista","identificacion_del_contratista",
        "cuantia_proceso","fecha_de_firma_del_contrato",
        "SECOP I"
    ))

    # ── Estrategia 4: Fuerzas Militares ──
    raw4 = buscar_militares()
    for c in raw4:
        todos.append({
            "fuente":    "Fuerzas Militares",
            "entidad":   str(c.get("nombre_entidad","N/A")),
            "municipio": str(c.get("ciudad","Nacional")),
            "objeto":    str(c.get("descripcion_del_proceso","N/A"))[:130],
            "categoria": "FUERZAS MILITARES",
            "proveedor": str(c.get("proveedor_adjudicado","N/A")),
            "nit_prov":  str(c.get("documento_proveedor","N/A")),
            "tipo_prov": clasificar_proveedor(str(c.get("proveedor_adjudicado",""))),
            "valor":     str(c.get("valor_del_contrato","N/A")),
            "fecha":     str(c.get("fecha_de_firma","N/A"))[:10]
        })

    # ── Estrategia 5: Dando Pasos por NIT ──
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

    # ── Estadísticas ──
    dando_f  = [c for c in unicos if "DANDO PASOS" in c["tipo_prov"]]
    externos = [c for c in unicos if c["tipo_prov"] in
                ("INTERMEDIARIO EXTERNO","EXTERNO (verificar)")]
    locales  = [c for c in unicos if "LOCAL" in c["tipo_prov"]]
    icbf_l   = [c for c in unicos if "ICBF" in c["categoria"] or "HOGAR" in c["categoria"]]
    pae_l    = [c for c in unicos if "PAE" in c["categoria"]]
    mil_l    = [c for c in unicos if "MILITAR" in c["categoria"]]
    ese_l    = [c for c in unicos if "HOSPITAL" in c["categoria"]]
    munis    = set(c["municipio"] for c in unicos
                  if c["municipio"] not in ("N/A","Nacional","Bogotá","BOGOTA"))

    print(f"\n  ══ RESUMEN FINAL (solo Boyacá) ══")
    print(f"  Municipios con datos:              {len(munis)}")
    print(f"  Total contratos:                   {len(unicos)}")
    print(f"  Fundacion Dando Pasos de Vida:     {len(dando_f)}")
    print(f"  Externos (atacar):                 {len(externos)}")
    print(f"  Proveedores locales:               {len(locales)}")
    print(f"  ICBF / FAMI:                       {len(icbf_l)}")
    print(f"  PAE escolar:                       {len(pae_l)}")
    print(f"  Hospitales / ESE:                  {len(ese_l)}")
    print(f"  Fuerzas Militares:                 {len(mil_l)}")
    print(f"\n  Municipios encontrados: {sorted(munis)}")

    return unicos


# ═══════════════════════════════════════════════════════════
# EXCEL — 6 ARCHIVOS
# ═══════════════════════════════════════════════════════════

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

    print("\nGenerando archivos Excel...")
    for nombre, datos in archivos.items():
        ruta = f"reportes/{nombre}"
        with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
            w.writeheader()
            if datos:
                w.writerows(datos)
        estado = f"{len(datos)} filas" if datos else "sin datos"
        print(f"  {'✓' if datos else '—'} {nombre} ({estado})")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    fecha = date.today().isoformat()
    inicio = datetime.now()
    sep = "=" * 60
    lin = "─" * 50

    print(sep)
    print(f"  AGENTE AVICOLA SIACHOQUE - {fecha}")
    print(sep)

    contratos = secop_completo()
    guardar_excels(contratos, fecha)

    dando_f  = [c for c in contratos if "DANDO PASOS" in c["tipo_prov"]]
    externos = [c for c in contratos if c["tipo_prov"] in
                ("INTERMEDIARIO EXTERNO","EXTERNO (verificar)")]
    locales  = [c for c in contratos if "LOCAL" in c["tipo_prov"]]
    icbf_l   = [c for c in contratos if "ICBF" in c["categoria"] or "HOGAR" in c["categoria"]]
    pae_l    = [c for c in contratos if "PAE" in c["categoria"]]
    mil_l    = [c for c in contratos if "MILITAR" in c["categoria"]]
    ese_l    = [c for c in contratos if "HOSPITAL" in c["categoria"]]
    munis    = set(c["municipio"] for c in contratos
                  if c["municipio"] not in ("N/A","Nacional","Bogotá","BOGOTA"))

    # 2. Convocatorias
    print("\n[2/5] Convocatorias...")
    time.sleep(12)
    convocatorias = claude_buscar(
        f"Eres agente para avicultor de Siachoque, Boyaca (500-2000 aves). "
        f"Busca HOY {date.today().strftime('%d/%m/%Y')} convocatorias abiertas en: "
        "alimenteengrande.boyaca.gov.co (PAE Boyaca), "
        "icbf.gov.co Regional Boyaca (FAMI, hogares, CDI), "
        "adr.gov.co/convocatorias (ruedas avicolas), "
        "agencialogistica.gov.co (ALFM), boyaca.gov.co. "
        "Para cada una: entidad, fecha cierre, como aplicar. "
        "Clasifica: URGENTE / PROXIMA / FUTURA."
    )

    # 3. Programas ICBF y militares
    print("\n[3/5] Programas ICBF y Militares...")
    time.sleep(18)
    icbf_militar = claude_buscar(
        "Busca en Siachoque, Soraca, Toca, Chivata, Tunja, Boyaca en 2026: "
        "ICBF: Hogares FAMI, HCB, CDI — operadores y si incluyen huevos. "
        "FFMM: Batallon Tarqui Tunja, ALFM — como ser proveedor via "
        "Bolsa Mercantil Colombia (bolsamercantil.com.co) o ALFM 018000126537. "
        "ICBF Tunja: (608)7422929"
    )

    # 4. Precio
    print("\n[4/5] Precio FENAVI...")
    time.sleep(18)
    precio = claude_buscar(
        f"Precio cubeta 30 huevos Colombia {date.today().strftime('%d/%m/%Y')}: "
        "FENAVI nacional y Tunja SIPSA-DANE. "
        "Compara con $11.500 productor Siachoque. Maximo 5 lineas."
    )

    # 5. Resumen
    print("\n[5/5] Resumen ejecutivo...")
    time.sleep(18)

    txt_dando = "\n".join(
        f"  {c['municipio']:18} | {c['entidad'][:40]} | "
        f"{c['categoria']} | ${c['valor']} | {c['fecha']}"
        for c in dando_f
    ) or f"  NIT {NIT_DANDO_PASOS}: 0 contratos directos en SECOP."

    txt_ext = "\n".join(
        f"  {c['municipio']:18} | {c['entidad'][:35]} | "
        f"{c['proveedor'][:28]} | ${c['valor']}"
        for c in externos[:10]
    ) or "  Sin externos en Boyacá esta semana"

    # Destacar UT NUTRITUNJA (operador PAE Tunja) y ALIMENTOS EDIL (FFMM)
    nutritunja = [c for c in locales if "NUTRITUNJA" in c["proveedor"].upper()]
    edil       = [c for c in contratos if "ALIMENTOS EDIL" in c["proveedor"].upper()]

    resumen = claude_buscar(
        f"Eres asesor de avicultor de Siachoque, Boyaca, 500-2000 aves. "
        f"Hoy: {date.today().strftime('%d/%m/%Y')}. "
        f"Municipios Boyaca con datos: {len(munis)}. "
        f"Contratos totales: {len(contratos)}. "
        f"DANDO PASOS ({len(dando_f)} contratos): {txt_dando[:300]}. "
        f"EXTERNOS BOYACA ({len(externos)}): {txt_ext[:400]}. "
        f"UT NUTRITUNJA (operador PAE Tunja $11.510M): {len(nutritunja)} contratos detectados. "
        f"ALIMENTOS EDIL SAS (proveedor FFMM $8.700M): {len(edil)} contratos. "
        f"ICBF/FAMI: {len(icbf_l)} | PAE: {len(pae_l)} | FFMM: {len(mil_l)}. "
        f"Precio: {precio[:120]}. "
        f"Convocatorias: {convocatorias[:300]}. "
        "CONTACTOS: ESE Siachoque 7319093, Alcaldia 7404476, "
        "ESE Soraca 7404270, ESE Tunja 311-2169007, "
        "ICBF (608)7422929, ALFM 018000126537, PAE 7420150 Ext.2367. "
        "Dame las 3 ACCIONES MAS URGENTES esta semana. "
        "Para cada una: municipio, entidad, telefono, que decir exactamente. "
        "Maximo 300 palabras. Solo texto plano."
    )

    duracion = (datetime.now() - inicio).seconds

    reporte = f"""REPORTE AVICOLA SIACHOQUE
{fecha}
{sep}
COBERTURA: {len(munis)} municipios de Boyaca
Municipios encontrados: {', '.join(sorted(munis)[:30])}

ACCIONES URGENTES:
{resumen}

{sep}
PRECIO HUEVO:
{precio}

{sep}
CONVOCATORIAS:
{convocatorias}

{sep}
ICBF Y MILITARES EN TU ZONA:
{icbf_militar}

{sep}
RESUMEN SECOP — SOLO BOYACA
Municipios con contratos:     {len(munis)}
Total contratos:              {len(contratos)}
Fundacion Dando Pasos:        {len(dando_f)} contratos
Externos (atacar):            {len(externos)}
Proveedores locales:          {len(locales)}
ICBF / FAMI:                 {len(icbf_l)}
PAE escolar:                  {len(pae_l)}
Hospitales / ESE:             {len(ese_l)}
Fuerzas Militares:            {len(mil_l)}

CLAVES IDENTIFICADAS:
UT NUTRITUNJA OG 2026 = operador PAE Tunja ($11.510M) — llama ya
ALIMENTOS EDIL SAS = proveedor FFMM ($8.700M) — estudiar como competir
ASOCIACION PRODUCTORES AGRICOLAS BOYACA = competencia local ($2.166M)

EXCELS ADJUNTOS:
  1_TODOS — {len(contratos)} filas
  2_EXTERNOS — {len(externos)} filas
  3_ICBF_FAMI — {len(icbf_l)} filas
  4_PAE — {len(pae_l)} filas
  5_MILITARES — {len(mil_l)} filas
  6_DANDO_PASOS — {len(dando_f)} filas
{sep}

FUNDACION DANDO PASOS DE VIDA (NIT {NIT_DANDO_PASOS}):
"""
    for c in dando_f:
        reporte += f"\n  {c['municipio']} | {c['entidad']} | {c['categoria']} | ${c['valor']} | {c['fecha']}\n  {lin}"
    if not dando_f:
        reporte += f"\n  0 contratos directos con NIT {NIT_DANDO_PASOS}\n"
        reporte += "  Ver archivo dando_pasos_investigacion.txt adjunto\n"

    reporte += f"\n{sep}\nEXTERNOS EN BOYACA — ATACAR:\n"
    for c in externos[:20]:
        reporte += (f"\n  {c['municipio']:18} | {c['entidad'][:38]}\n"
                    f"  Proveedor: {c['proveedor']} | NIT: {c['nit_prov']}"
                    f" | ${c['valor']}\n  {lin}")

    reporte += f"\n{sep}\nICBF / FAMI / MATERNO:\n"
    for c in icbf_l[:15]:
        reporte += (f"\n  {c['municipio']:18} | {c['entidad'][:38]}\n"
                    f"  {c['categoria']} | {c['proveedor']} | ${c['valor']}\n  {lin}")

    reporte += f"\n{sep}\nFUERZAS MILITARES:\n"
    for c in mil_l[:10]:
        reporte += (f"\n  {c['entidad'][:40]}\n"
                    f"  Proveedor: {c['proveedor']} | ${c['valor']}\n  {lin}")

    reporte += f"\n{sep}\nPROVEEDORES LOCALES BOYACA:\n"
    for c in locales[:12]:
        reporte += (f"\n  {c['municipio']:18} | {c['proveedor']}\n"
                    f"  NIT: {c['nit_prov']} | ${c['valor']}\n  {lin}")

    reporte += f"\n\nGenerado en {duracion}s"

    with open(f"reportes/reporte_{fecha}.txt","w",encoding="utf-8") as f:
        f.write(reporte)
    with open(f"reportes/contratos_{fecha}.json","w",encoding="utf-8") as f:
        json.dump(contratos, f, ensure_ascii=False, indent=2)

    print(f"\n{sep}")
    print("ACCIONES URGENTES:")
    print(resumen)
    print(f"\n  Municipios Boyaca: {len(munis)}")
    print(f"  Contratos:         {len(contratos)}")
    print(f"  Dando Pasos:       {len(dando_f)}")
    print(f"  Externos:          {len(externos)}")
    print(f"  ICBF/FAMI:        {len(icbf_l)}")
    print(f"  PAE:               {len(pae_l)}")
    print(f"  Militares:         {len(mil_l)}")
    print(f"  Duracion:          {duracion}s")
    print(sep)


if __name__ == "__main__":
    main()
