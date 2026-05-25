import streamlit as st
import pandas as pd
import numpy as np
import datetime

# 1. CONFIGURACIÓN DE LA INTERFAZ
st.set_page_config(page_title="Analizador Profit Plus - ORI OIL", layout="wide")

st.title("📊 Extractor de Ajustes de Inventario - Profit Plus")
st.write("Versión Corregida: Extracción por Patrón 'UND' (Evita falsos 5) y Buscador Operativo")

# Componente de carga de archivos
uploaded_file = st.file_uploader("Carga el archivo original de Profit Plus (CSV o Excel)", type=["csv", "xls", "xlsx"])

if uploaded_file is not None:
    try:
        # Lectura elástica sin forzar tipos estrictos
        if uploaded_file.name.endswith('.csv'):
            df_raw = pd.read_csv(uploaded_file, header=None, dtype=str)
        else:
            df_raw = pd.read_excel(uploaded_file, header=None, dtype=str)

        # Limpieza inicial de líneas vacías
        df_raw = df_raw.dropna(how='all').fillna("")
        
        registros = []
        articulo_actual = "Desconocido"

        # Procesamiento secuencial basado en la estructura real de Profit
        for idx, row in df_raw.iterrows():
            fila_lista = [str(celda).strip() for celda in row.tolist()]
            fila_completa_str = " ".join(fila_lista).upper()
            
            # Detectar si la fila está vacía
            elementos_visibles = [x for x in fila_lista if x != ""]
            if not elementos_visibles:
                continue

            # 1. DETECCIÓN DE ARTÍCULO (Fila de Cabecera del Producto)
            if fila_lista[0] != "" and not ("ENTRAD" in fila_completa_str or "SALID" in fila_completa_str or "SUB-TOTAL" in fila_completa_str or "ARTÍCULO" in fila_completa_str or "NÚMERO" in fila_completa_str):
                codigo = fila_lista[0]
                descripcion = ""
                for celda in fila_lista[1:]:
                    if celda != "":
                        descripcion = celda
                        break
                articulo_actual = f"{codigo} - {descripcion}" if descripcion else codigo
                continue

            # 2. DETECCIÓN DE TRANSACCIÓN
            tipo_movimiento_detectado = None
            idx_tipo = -1
            
            for i, celda in enumerate(fila_lista):
                if "ENTRAD" in celda.upper() or "SALID" in celda.upper():
                    tipo_movimiento_detectado = "ENTRADA" if "ENTRAD" in celda.upper() else "SALIDA"
                    idx_tipo = i
                    break
            
            # Si localizamos la transacción, aplicamos la búsqueda inteligente alrededor de 'UND'
            if tipo_movimiento_detectado and idx_tipo > 0:
                try:
                    # Nro de Ajuste siempre está en el índice 1
                    nro_ajuste = fila_lista[1] if fila_lista[1] else "S/N"
                    
                    # DETECCIÓN DE LA CANTIDAD REAL BASADA EN 'UND'
                    cantidad_real_raw = ""
                    for i, celda in enumerate(fila_lista):
                        if celda.upper() == "UND":
                            # Buscamos hacia atrás el primer valor que no esté vacío antes de UND
                            for desc in range(i-1, 0, -1):
                                if fila_lista[desc] != "":
                                    cantidad_real_raw = fila_lista[desc]
                                    break
                            break
                    
                    # Si no se encontró el patrón UND, usamos la columna 22 del renglón como respaldo
                    if not cantidad_real_raw:
                        cantidad_real_raw = fila_lista[22] if len(fila_lista) > 22 else "0"

                    # Filtrar elementos de texto después del Tipo para extraer Fecha y Centro de Costo
                    elementos_despues = [x for x in fila_lista[idx_tipo+1:] if x != ""]
                    
                    if len(elementos_despues) >= 2:
                        fecha_raw = elementos_despues[0]  # Texto original de fecha y hora
                        cc_raw = elementos_despues[1]     # Centro de Costo Real (VL025, TALLER, etc.)

                        # --- PROCESADOR DE FECHAS ---
                        fecha_original_mostrar = fecha_raw
                        fecha_objeto_filtro = datetime.date.today()
                        try:
                            solo_fecha_str = fecha_raw.split()[0] if " " in fecha_raw else fecha_raw
                            if "/" in solo_fecha_str:
                                d, m, a = solo_fecha_str.split("/")
                                fecha_objeto_filtro = datetime.date(int(a), int(m), int(d))
                            elif "-" in solo_fecha_str:
                                a, m, d = solo_fecha_str.split("-")
                                fecha_objeto_filtro = datetime.date(int(a), int(m), int(d))
                        except:
                            pass 

                        # --- PROCESADOR DE CANTIDADES REALES ---
                        try:
                            cant_limpia = cantidad_real_raw.replace(' ', '')
                            # Evaluamos si el texto original ya conserva el signo negativo de Profit (ej: -1.0)
                            tiene_signo_menos = '-' in cant_limpia
                            
                            # Limpieza para conversión a float puro
                            cant_limpia = cant_limpia.replace('-', '')
                            cantidad_float = float(cant_limpia.replace(',', '.'))
                            
                            # Sincronización matemática: Si es SALIDA o el texto traía un '-', se fuerza negativo
                            if tipo_movimiento_detectado == "SALIDA" or tiene_signo_menos:
                                cantidad_final = -abs(cantidad_float)
                            else:
                                cantidad_final = abs(cantidad_float)
                        except ValueError:
                            cantidad_final = 0.0

                        registros.append({
                            'Artículo': articulo_actual,
                            'Nro Ajuste': nro_ajuste,
                            'Tipo Movimiento': tipo_movimiento_detectado,
                            'Fecha_Filtro': fecha_objeto_filtro,
                            'Fecha Original': fecha_original_mostrar,
                            'Centro de Costo': cc_raw if cc_raw else "NO ESPECIFICADO",
                            'Cantidad': int(cantidad_final)
                        })
                except Exception as row_err:
                    continue

        if not registros:
            st.warning("⚠️ Estructura desalineada o no se encontró el indicador 'UND' en las filas de transacciones.")
            st.stop()

        df_final = pd.DataFrame(registros)

        st.success(f"🎯 ¡Estructura Corregida! Se procesaron {len(df_final)} transacciones con cantidades exactas.")
        st.write("---")

        # --- BARRA LATERAL CONTROLES Y FILTROS ---
        st.sidebar.header("🎯 Parámetros del Reporte")
        
        # 1. BUSCADOR DE TEXTO INTEGRAL
        busqueda_texto = st.sidebar.text_input("🔎 Escribe el Artículo a buscar (Código o Nombre):", "").strip()
        
        # Filtro de rango de fechas
        min_date = df_final['Fecha_Filtro'].min()
        max_date = df_final['Fecha_Filtro'].max()
        rango_fechas = st.sidebar.date_input("2. Rango de Fechas", value=(min_date, max_date))
        
        # Filtro dinámico por Centros de Costo reales
        lista_cc = ["Todos"] + sorted(df_final['Centro de Costo'].unique().tolist())
        cc_sel = st.sidebar.selectbox("3. Filtrar por Centro de Costo (C.Cost)", lista_cc)

        # Filtro de Entradas y Salidas
        tipo_sel = st.sidebar.radio("4. Tipo de Movimiento", ["Todos", "Solo ENTRADAS", "Solo SALIDAS"])

        # Sincronización de la lista desplegable basada en el cuadro de búsqueda escrita
        if busqueda_texto:
            df_lista_filtrada = df_final[df_final['Artículo'].str.contains(busqueda_texto, case=False, na=False)]
        else:
            df_lista_filtrada = df_final.copy()
            
        lista_articulos = ["Todos"] + sorted(df_lista_filtrada['Artículo'].unique().tolist())
        articulo_sel = st.sidebar.selectbox("📦 O selecciónalo de la lista filtrada:", lista_articulos)

        # --- FILTRADO GLOBAL DEL DATAFRAME ---
        df_filtrado = df_final.copy()
        
        # Aplicar el filtro de lo que se haya escrito en el cuadro de búsqueda
        if busqueda_texto:
            df_filtrado = df_filtrado[df_filtrado['Artículo'].str.contains(busqueda_texto, case=False, na=False)]
        
        # Aplicar el filtro de la lista desplegable si no es "Todos"
        if articulo_sel != "Todos":
            df_filtrado = df_filtrado[df_filtrado['Artículo'] == articulo_sel]
            
        # Aplicar rango de fechas
        if isinstance(rango_fechas, tuple) and len(rango_fechas) == 2:
            df_filtrado = df_filtrado[(df_filtrado['Fecha_Filtro'] >= rango_fechas[0]) & (df_filtrado['Fecha_Filtro'] <= rango_fechas[1])]
            
        # Aplicar Centro de Costo
        if cc_sel != "Todos":
            df_filtrado = df_filtrado[df_filtrado['Centro de Costo'] == cc_sel]
            
        # Aplicar Tipo de Movimiento
        if tipo_sel == "Solo ENTRADAS":
            df_filtrado = df_filtrado[df_filtrado['Tipo Movimiento'] == 'ENTRADA']
        elif tipo_sel == "Solo SALIDAS":
            df_filtrado = df_filtrado[df_filtrado['Tipo Movimiento'] == 'SALIDA']

        # --- KPIs ---
        c1, c2, c3 = st.columns(3)
        ent = df_filtrado[df_filtrado['Cantidad'] > 0]['Cantidad'].sum()
        sal = df_filtrado[df_filtrado['Cantidad'] < 0]['Cantidad'].sum()
        
        with c1: st.metric("Total Entradas", f"{int(ent)} unds")
        with c2: st.metric("Total Salidas (Negativas)", f"{int(sal)} unds")
        with c3: st.metric("Balance Neto", f"{int(df_filtrado['Cantidad'].sum())} unds")

        # --- TABLA DE DATOS FINAL ---
        st.subheader("📋 Transacciones Consolidadas")
        df_pantalla = df_filtrado[['Fecha Original', 'Nro Ajuste', 'Artículo', 'Centro de Costo', 'Cantidad']].copy()
        st.dataframe(df_pantalla, use_container_width=True)

        # Descarga de reportes estructurados
        nombre_reporte = f"reporte_auditoria_{cc_sel.lower().replace(' ', '_')}.csv"
        csv_bytes = df_pantalla.to_csv(index=False).encode('utf-8')
        st.download_button(label="📊 Descargar Reporte en CSV", data=csv_bytes, file_name=nombre_reporte, mime="text/csv")

    except Exception as e:
        st.error(f"Error crítico en el motor de datos: {e}")
else:
    st.info("A la espera de que cargues el reporte original de Profit Plus para iniciar la auditoría.")
