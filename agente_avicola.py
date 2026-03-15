"""
AGENTE AVICOLA SIACHOQUE - Sistema de inteligencia comercial automatizado
========================================================================
Accede a:
  - SECOP II (API publica datos.gov.co)
  - Inventario aves Boyaca (UPRA / datos.gov.co)  
  - FENAVI precios semanales (web scraping)
  - PAE Boyaca (web scraping)
  - ADR convocatorias (web scraping)
  - Gobernacion Boyaca (web scraping)

Ejecuta automaticamente cada lunes a las 8:00am
y guarda el reporte en la carpeta /reportes/
"""

import os
import json
import time
import requests
import pandas as pd
import schedule
from datetime import date, datetime
from pathlib import Path

# ============================================================
# CONFIGURACION - edita solo esta seccion
# ============================================================

# Opcion 1: poner la key directamente aqui
API_KEY = ""

# Opcion 2: leer desde archivo config.txt (mas seguro)
if not API_KEY:
    config_file = Path("config.txt")
    if config_file.exists():
        for line in config_file.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip()

# Opcion 3: variable de entorno del sistema
if not API_KEY:
    API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

if not API_KEY:
    print("ERROR: No se encontro API key de Anthropic.")
    print("Edita config.txt y agrega: ANTHROPIC_API_KEY=sk-ant-...")
    exit(1)

# Carpeta donde se guardan los reportes
REPORTES_DIR = Path("reportes")
REPORTES_DIR.mkdir(exist_ok=True)

# ============================================================
# MODULO 1: SCRAPING DIRECTO - SECOP II (API publica)
# ============================================================

def scraping_secop_huevos_boyaca():
    """
    Consulta directa a la API publica de SECOP II en datos.gov.co
    Sin necesidad de Claude - datos en tiempo real
    """
    print("  [SECOP II] Consultando contratos de huevos en Boyaca...")
    
    resultados = {"contratos": [], "error": None}
    
    # Dataset SECOP II - contratos adjudicados
    urls_secop = [
        # SECOP II contratos
        {
            "url": "https://www.datos.gov.co/resource/jbjy-vk9h.json",
            "params": {
                "$where": "upper(descripcion_del_proceso) like '%HUEVO%' AND upper(nombre_departamento) like '%BOYAC%'",
                "$order": "fecha_de_firma DESC",
                "$limit": 30
            },
            "nombre": "SECOP II - Contratos huevos Boyaca"
        },
        # SECOP I contratos 
        {
            "url": "https://www.datos.gov.co/resource/xvdy-vvsk.json",
            "params": {
                "$where": "upper(descripcion_proceso) like '%HUEVO%' AND upper(departamento_entidad) like '%BOYAC%'",
                "$order": "fecha_adjudicacion DESC", 
                "$limit": 20
            },
            "nombre": "SECOP I - Contratos huevos Boyaca"
        }
    ]
    
    for fuente in urls_secop:
        try:
            resp = requests.get(
                fuente["url"], 
                params=fuente["params"],
                timeout=20,
                headers={"Accept": "application/json"}
            )
            resp.raise_for_status()
            datos = resp.json()
            
            if datos:
                print(f"  [OK] {fuente['nombre']}: {len(datos)} contratos encontrados")
                for c in datos:
                    resultados["contratos"].append({
                        "fuente": fuente["nombre"],
                        "entidad": c.get("nombre_entidad", c.get("nombre_entidad_contratante", "N/A")),
                        "municipio": c.get("municipio_entidad", c.get("municipio", "N/A")),
                        "objeto": c.get("descripcion_del_proceso", c.get("descripcion_proceso", "N/A"))[:120],
                        "proveedor": c.get("proveedor_adjudicado", c.get("nombre_representante_legal", "N/A")),
                        "valor": c.get("valor_total_adjudicacion", c.get("valor_contrato", "N/A")),
                        "fecha": c.get("fecha_de_firma", c.get("fecha_adjudicacion", "N/A"))
                    })
            else:
                print(f"  [--] {fuente['nombre']}: sin resultados")
                
        except requests.exceptions.RequestException as e:
            print(f"  [!] Error en {fuente['nombre']}: {e}")
            resultados["error"] = str(e)
    
    return resultados


def scraping_inventario_aves_boyaca():
    """
    Descarga el inventario de aves ponedoras por municipio en Boyaca
    Fuente: UPRA / datos.gov.co - dataset rpqz-9ebw
    """
    print("  [UPRA] Descargando inventario aves Boyaca...")
    
    try:
        resp = requests.get(
            "https://www.datos.gov.co/resource/rpqz-9ebw.json",
            params={"$limit": 200, "$order": "a_os DESC"},
            timeout=20
        )
        resp.raise_for_status()
        datos = resp.json()
        
        if datos:
            df = pd.DataFrame(datos)
            print(f"  [OK] Inventario aves: {len(df)} registros")
            
            # Identificar columnas clave
            col_muni = next((c for c in df.columns if "municipio" in c.lower()), None)
            col_postura = next((c for c in df.columns 
                               if any(p in c.lower() for p in ["postura","ponedora","huevo"])), None)
            
            if col_muni and col_postura:
                df[col_postura] = pd.to_numeric(df[col_postura], errors="coerce").fillna(0)
                
                # Municipios objetivo (radio 80km de Siachoque)
                municipios_objetivo = [
                    "SORACÁ","TOCA","CHIVATÁ","OICATÁ","MOTAVITA",
                    "VENTAQUEMADA","SAMACÁ","CUCAITA","SORA","CÓMBITA",
                    "JENESANO","NUEVO COLÓN","TIBANÁ","TURMEQUÉ","ÚMBITA",
                    "RAMIRIQUÍ","SIACHOQUE","TUNJA","CHÍQUIZA","RÁQUIRA",
                    "ALMEIDA","BOYACÁ","PAIPA","DUITAMA"
                ]
                
                sin_postura = []
                con_postura = []
                
                for muni in municipios_objetivo:
                    fila = df[df[col_muni].str.upper().str.contains(
                        muni.upper().replace("Á","A").replace("Ó","O")
                        .replace("É","E").replace("Í","I").replace("Ú","U"), 
                        na=False
                    )]
                    
                    if fila.empty or fila[col_postura].sum() == 0:
                        sin_postura.append(muni)
                    else:
                        aves = int(fila[col_postura].sum())
                        con_postura.append({"municipio": muni, "aves_postura": aves})
                
                return {
                    "sin_productor_local": sin_postura,
                    "con_productor_local": con_postura,
                    "columnas_disponibles": list(df.columns)
                }
            else:
                print(f"  [!] Columnas disponibles: {list(df.columns)}")
                return {"datos_crudos": datos[:5], "columnas": list(df.columns)}
                
        else:
            print("  [--] Dataset aves: sin datos")
            return {"sin_productor_local": [], "nota": "Dataset no disponible"}
            
    except Exception as e:
        print(f"  [!] Error inventario aves: {e}")
        return {"error": str(e)}


def scraping_secop_procesos_abiertos():
    """
    Busca procesos ABIERTOS (no adjudicados) de huevos en Boyaca
    """
    print("  [SECOP] Buscando procesos abiertos en Boyaca...")
    
    try:
        resp = requests.get(
            "https://www.datos.gov.co/resource/p6dx-8zbt.json",
            params={
                "$where": "upper(descripcion_del_proceso) like '%HUEVO%' AND upper(nombre_departamento) like '%BOYAC%' AND estado_proceso='Convocado'",
                "$order": "fecha_cierre_proceso ASC",
                "$limit": 20
            },
            timeout=20
        )
        resp.raise_for_status()
        datos = resp.json()
        
        if datos:
            print(f"  [OK] Procesos abiertos: {len(datos)} encontrados")
            return [{
                "entidad": p.get("nombre_entidad", "N/A"),
                "municipio": p.get("municipio_entidad", "N/A"),
                "objeto": p.get("descripcion_del_proceso", "N/A")[:120],
                "presupuesto": p.get("precio_base", "N/A"),
                "fecha_cierre": p.get("fecha_cierre_proceso", "N/A"),
                "url": p.get("urlproceso", {}).get("url", "N/A") if isinstance(p.get("urlproceso"), dict) else "N/A"
            } for p in datos]
        else:
            print("  [--] Sin procesos abiertos de huevos en Boyaca ahora mismo")
            return []
            
    except Exception as e:
        print(f"  [!] Error procesos abiertos: {e}")
        return []


# ============================================================
# MODULO 2: AGENTE CLAUDE CON WEB SEARCH
# ============================================================

def buscar_con_claude(prompt_texto):
    """
    Llama a la API de Claude con web search activado
    para buscar informacion que no esta en APIs publicas
    """
    try:
        resp = requests.post(
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
                "messages": [{"role": "user", "content": prompt_texto}]
            },
            timeout=60
        )
        resp.raise_for_status()
        data = resp.json()
        
        texto = " ".join(
            b["text"] for b in data.get("content", []) 
            if b.get("type") == "text"
        )
        return texto
        
    except Exception as e:
        return f"Error al consultar Claude: {e}"


def buscar_convocatorias_web():
    """Usa Claude + web search para buscar convocatorias actuales"""
    print("  [WEB] Buscando convocatorias con Claude + web search...")
    return buscar_con_claude(f"""
Eres agente de inteligencia para avicultor de Siachoque, Boyacá.
Busca HOY {date.today().strftime('%d/%m/%Y')} convocatorias ABIERTAS para:
- Compra de huevos / PAE en Boyacá
- Ruedas de negocios ADR para productores avícolas
- Convocatorias Gobernación Boyacá pequeños productores

Fuentes: alimenteengrande.boyaca.gov.co, adr.gov.co/convocatorias, boyaca.gov.co

Para cada convocatoria: entidad, municipio, fecha cierre, requisitos.
Clasifica: URGENTE (menos de 15 días) / PRÓXIMA / FUTURA.
Sé conciso y específico.
""")


def buscar_precio_fenavi():
    """Consulta el precio semanal del huevo según FENAVI"""
    print("  [WEB] Consultando precio huevo FENAVI...")
    return buscar_con_claude(f"""
Busca el precio de referencia de la cubeta de 30 huevos en Colombia esta semana 
({date.today().strftime('%d/%m/%Y')}) según FENAVI (fenavi.org) y la plaza de mercado 
de Tunja según SIPSA-DANE.

Reporta:
- Precio cubeta FENAVI nacional esta semana
- Precio en Tunja específicamente  
- Comparación con $11.500 (precio productor directo Siachoque)
- ¿Está el productor local por debajo del mercado? ¿En cuánto %?
Respuesta en máximo 5 líneas.
""")


def buscar_operadores_pae():
    """Identifica operadores del PAE en municipios objetivo"""
    print("  [WEB] Identificando operadores PAE en municipios objetivo...")
    return buscar_con_claude(f"""
Busca en SECOP II y sece.mineducacion.gov.co quiénes son los operadores del PAE 
contratados en 2026 para estos municipios de Boyacá:
Siachoque, Soracá, Toca, Chivatá, Ventaquemada, Tunja.

Para cada municipio: nombre del operador, empresa, teléfono si está disponible.
Estos operadores necesitan proveedores de huevos locales por Ley 2046.
""")


# ============================================================
# MODULO 3: GENERACION DE REPORTE
# ============================================================

def generar_reporte_completo():
    """
    Ejecuta todos los módulos y genera el reporte semanal completo
    """
    inicio = datetime.now()
    fecha_str = date.today().isoformat()
    
    print(f"\n{'='*55}")
    print(f"  REPORTE SEMANAL - {date.today().strftime('%A %d de %B %Y').upper()}")
    print(f"{'='*55}\n")
    
    reporte = {
        "fecha": fecha_str,
        "hora_generacion": inicio.strftime("%H:%M:%S"),
        "modulos": {}
    }
    
    # --- MÓDULO A: Datos directos de APIs públicas ---
    print("[1/5] Consultando SECOP II - contratos adjudicados...")
    reporte["modulos"]["secop_contratos"] = scraping_secop_huevos_boyaca()
    
    print("\n[2/5] Consultando SECOP II - procesos abiertos...")
    reporte["modulos"]["secop_abiertos"] = scraping_secop_procesos_abiertos()
    
    print("\n[3/5] Descargando inventario aves Boyacá (UPRA)...")
    reporte["modulos"]["inventario_aves"] = scraping_inventario_aves_boyaca()
    
    # --- MÓDULO B: Web search con Claude ---
    print("\n[4/5] Buscando convocatorias y precios con web search...")
    reporte["modulos"]["convocatorias_web"] = buscar_convocatorias_web()
    reporte["modulos"]["precio_fenavi"] = buscar_precio_fenavi()
    
    print("\n[5/5] Identificando operadores PAE...")
    reporte["modulos"]["operadores_pae"] = buscar_operadores_pae()
    
    # --- RESUMEN EJECUTIVO ---
    print("\n[+] Generando resumen ejecutivo...")
    
    # Preparar datos para el resumen
    n_contratos = len(reporte["modulos"]["secop_contratos"].get("contratos", []))
    n_abiertos = len(reporte["modulos"]["secop_abiertos"])
    sin_productor = reporte["modulos"]["inventario_aves"].get("sin_productor_local", [])
    
    resumen_prompt = f"""
Eres el agente de inteligencia comercial de un avicultor campesino de Siachoque, Boyacá.

Con base en estos datos recopilados hoy {date.today().strftime('%d/%m/%Y')}:

CONTRATOS SECOP II ENCONTRADOS ({n_contratos}):
{json.dumps(reporte["modulos"]["secop_contratos"].get("contratos", [])[:5], ensure_ascii=False, indent=2)}

PROCESOS ABIERTOS ({n_abiertos}):
{json.dumps(reporte["modulos"]["secop_abiertos"][:3], ensure_ascii=False, indent=2)}

MUNICIPIOS SIN PRODUCTOR LOCAL: {', '.join(sin_productor[:10]) if sin_productor else 'Ver datos UPRA'}

CONVOCATORIAS WEB: {reporte["modulos"]["convocatorias_web"][:400]}

PRECIO FENAVI: {reporte["modulos"]["precio_fenavi"][:200]}

Genera un RESUMEN EJECUTIVO con:
1. LAS 3 ACCIONES MÁS URGENTES esta semana (con nombre, teléfono y fecha si aplica)
2. OPORTUNIDAD MÁS CALIENTE identificada hoy
3. MUNICIPIO PRIORITARIO para visitar esta semana
4. ESTADO DEL MERCADO: ¿buen momento para conseguir contratos? ¿por qué?

Máximo 300 palabras. Directo y accionable.
"""
    reporte["modulos"]["resumen_ejecutivo"] = buscar_con_claude(resumen_prompt)
    
    duracion = (datetime.now() - inicio).seconds
    reporte["duracion_segundos"] = duracion
    
    # --- GUARDAR REPORTE ---
    # JSON completo
    ruta_json = REPORTES_DIR / f"reporte_{fecha_str}.json"
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(reporte, f, ensure_ascii=False, indent=2)
    
    # CSV de contratos SECOP
    contratos = reporte["modulos"]["secop_contratos"].get("contratos", [])
    if contratos:
        ruta_csv = REPORTES_DIR / f"contratos_secop_{fecha_str}.csv"
        pd.DataFrame(contratos).to_csv(ruta_csv, index=False, encoding="utf-8-sig")
        print(f"\n  [OK] CSV contratos: {ruta_csv}")
    
    # CSV municipios sin productor
    if sin_productor:
        ruta_muni = REPORTES_DIR / f"municipios_sin_productor_{fecha_str}.csv"
        pd.DataFrame({"municipio": sin_productor}).to_csv(
            ruta_muni, index=False, encoding="utf-8-sig"
        )
        print(f"  [OK] CSV municipios: {ruta_muni}")
    
    # TXT legible para imprimir
    ruta_txt = REPORTES_DIR / f"reporte_{fecha_str}.txt"
    with open(ruta_txt, "w", encoding="utf-8") as f:
        f.write(f"REPORTE INTELIGENCIA AVÍCOLA - SIACHOQUE, BOYACÁ\n")
        f.write(f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
        f.write("="*55 + "\n\n")
        
        f.write("RESUMEN EJECUTIVO\n")
        f.write("-"*40 + "\n")
        f.write(reporte["modulos"]["resumen_ejecutivo"] + "\n\n")
        
        f.write("PRECIO HUEVO ESTA SEMANA\n")
        f.write("-"*40 + "\n")
        f.write(reporte["modulos"]["precio_fenavi"] + "\n\n")
        
        f.write("CONVOCATORIAS ABIERTAS\n")
        f.write("-"*40 + "\n")
        f.write(reporte["modulos"]["convocatorias_web"] + "\n\n")
        
        f.write("CONTRATOS ADJUDICADOS EN BOYACÁ (últimos)\n")
        f.write("-"*40 + "\n")
        for c in contratos[:10]:
            f.write(f"• {c.get('entidad','N/A')} ({c.get('municipio','N/A')})\n")
            f.write(f"  Proveedor: {c.get('proveedor','N/A')}\n")
            f.write(f"  Objeto: {c.get('objeto','N/A')[:80]}...\n\n")
        
        f.write("MUNICIPIOS SIN PRODUCTOR LOCAL\n")
        f.write("-"*40 + "\n")
        for m in sin_productor:
            f.write(f"  → {m}\n")
        
        f.write(f"\nOperadores PAE:\n{reporte['modulos']['operadores_pae']}\n")
    
    # Imprimir resumen en consola
    print(f"\n{'='*55}")
    print("RESUMEN EJECUTIVO")
    print("="*55)
    print(reporte["modulos"]["resumen_ejecutivo"])
    print(f"\n{'='*55}")
    print(f"  Duración: {duracion}s")
    print(f"  Reportes guardados en: {REPORTES_DIR}/")
    print(f"  - {ruta_txt.name}")
    print(f"  - {ruta_json.name}")
    if contratos:
        print(f"  - contratos_secop_{fecha_str}.csv")
    print("="*55)
    
    return reporte


# ============================================================
# PROGRAMACION AUTOMATICA - cada lunes 8am
# ============================================================

def programar_automatico():
    """Programa el agente para ejecutarse cada lunes a las 8am"""
    print("\nAgente avícola programado:")
    print("  → Ejecución automática: lunes 08:00am")
    print("  → Reportes en carpeta: ./reportes/")
    print("  → Presiona Ctrl+C para detener\n")
    
    schedule.every().monday.at("08:00").do(generar_reporte_completo)
    
    # Mostrar próxima ejecución
    proximo = schedule.next_run()
    print(f"  Próximo reporte: {proximo.strftime('%A %d/%m/%Y a las %H:%M')}")
    print()
    
    while True:
        schedule.run_pending()
        time.sleep(30)


# ============================================================
# PUNTO DE ENTRADA
# ============================================================

if __name__ == "__main__":
    import sys
    
    print("\n" + "="*55)
    print("  AGENTE AVÍCOLA SIACHOQUE v1.0")
    print("  Inteligencia comercial automatizada")
    print("="*55 + "\n")
    
    if len(sys.argv) > 1 and sys.argv[1] == "--automatico":
        # Modo programado: corre cada lunes 8am
        generar_reporte_completo()  # Ejecutar una vez al inicio
        programar_automatico()
    else:
        # Modo manual: ejecutar ahora y salir
        generar_reporte_completo()
        print("\n¿Quieres programarlo para ejecutarse cada lunes automáticamente?")
        resp = input("Escribe 'si' y presiona Enter: ").strip().lower()
        if resp == "si":
            programar_automatico()
