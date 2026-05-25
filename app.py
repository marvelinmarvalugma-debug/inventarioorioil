import streamlit as st
import pandas as pd
import numpy as np
import datetime
import re

# 1. CONFIGURACIÓN DE LA INTERFAZ (Estricta primera instrucción)
st.set_page_config(page_title="Analizador Profit Plus - ORI OIL", layout="wide")

st.title("📊 Extractor de Ajustes de Inventario - Profit Plus")
st.write("Versión Optimizada de Alta Velocidad (Anti-Bloqueo de Localhost)")

# Componente de carga de archivos
uploaded_file = st.file_uploader("Carga el archivo original de Profit Plus (CSV o Excel)", type=["csv", "xls", "xlsx"])

if uploaded_file is not None:
    try:
        # Lectura eficiente limitando el exceso de columnas vacías de Profit
        if uploaded_file.name.endswith('.csv'):
            df_raw = pd.read_csv(uploaded_file, header=None, dtype=str).dropna(how='all')
        else:
            df_raw = pd.read_excel(uploaded_file, header=None, dtype=str).dropna(how='all')

        # Acotar el DataFrame a las columnas que realmente nos interesan para evitar consumo de RAM
        if df_raw.shape[1] >= 26:
            df_raw = df_raw.iloc[:, :35] 
        else:
            st.error("⚠️ El archivo no cuenta con la estructura mínima de columnas requerida.")
            st.stop()

        df_raw = df_raw.fillna("").astype(str).apply(lambda x: x.str.strip())

        # --- MAPEO DE COLUMNAS EXACTO DEL REPORTE REAL ---
        # Columna2=1, Columna8=7, Columna10=9, Columna14=13, Columna22=21, Columna26=25
        idx_numero   = 1
        idx_tipo     = 7
        idx_fecha    = 9
        idx_motivo   = 13
        idx_almacen  = 21
        idx_cantidad = 25 

        # --- PARSEO RÁPIDO DE FECHAS ---
        def limpiar_fecha(val):
            val_str = str(val).strip().lower()
            if not val_str or any(x in val_str for x in ['nan', 'sub-tot', 'total', 'entrad', 'salid']):
                return pd.NaT
            try:
                num = float(val_str.replace(',', '.'))
                if 35000 < num < 60000:
                    return pd.to_datetime(num, unit='D', origin='1899-12-30').round('s')
            except ValueError:
                pass
            
            val_limpio = val_str.replace('a.m.', 'am').replace('p.m.', 'pm').replace('m.', 'm')
            val_limpio = re.sub(r'\s+', ' ', val_limpio)
            for fmt in ['%d/%m/%Y %H:%M:%S', '%d-%m-%Y %H:%M:%S', '%d/%m/%Y', '%Y-%m-%d']:
                try: return pd.to_datetime(val_limpio, format=fmt)
                except: continue
            return pd.NaT

        registros = []
        articulo_actual = "Desconocido"

        # Procesamiento secuencial optimizado (Solo evalúa filas clave)
        for idx, row in df_raw.iterrows():
            if idx == 0: continue # Saltar títulos internos de cabecera de comas
            
            col0 = row[0].strip()
            tipo_raw = str(row[idx_tipo]).strip().upper()
            es_mov = "ENTRAD" in tipo_raw or "SALID" in tipo_raw

            # Detección del Artículo
            if col0 != "" and not es_mov and not any(p in col0.upper() for p in ['ARTÍCULO', 'PROFIT', 'INVENTARIO', 'R.I.F', 'NÚMERO', 'TOTAL', 'SUB-TOTALES']):
                articulo_actual = col0
                # Buscar si hay descripción continua
                for cell in row[1:10]:
                    if cell.strip() != "" and cell.strip() != col0:
                        articulo_actual = f"{col0} - {cell.strip()}"
                        break
                continue

            # Extracción del Movimiento
            if es_mov:
                cantidad_val = row[idx_cantidad].strip()
                if not cantidad_val or cantidad_val == "0.0":
                    continue # Ignora basura de filas vacías
                
                fecha_dt = limpiar_fecha(row[idx_fecha])
                if pd.isna(fecha_dt):
                    fecha_dt = pd.to_datetime(datetime.date.today())

                registros.append({
                    'Artículo': articulo_actual,
                    'Nro Ajuste': row[idx_numero] if row[idx_numero] else "S/N",
                    'Tipo_Raw': tipo_raw,
                    'Fecha_Convertida': fecha_dt,
                    'Centro de Costo': row[idx_motivo] if row[idx_motivo] else "ALMACEN PRINCIPAL",
                    'Almacén': row[idx_almacen] if row[idx_almacen] else "General",
                    'Cantidad_Raw': cantidad_val
                })

        if not registros:
            st.warning("⚠️ No se estructuraron movimientos válidos. Asegúrate de estar subiendo el reporte correcto de Profit Plus.")
            st.stop()

        df_final = pd.DataFrame(registros)

        # --- NORMALIZACIÓN DE CANTIDADES Y FLUJO ---
        df_final['Cantidad'] = pd.to_numeric(df_final['Cantidad_Raw'].str.replace(',', '.'), errors='coerce').fillna(0)
        df_final['Tipo Movimiento'] = np.where(df_final['Tipo_Raw'].str.contains('ENTRAD|ING|E'), 'ENTRADA', 'SALIDA')
        
        # Las salidas restan, las entradas suman
        df_final['Cantidad'] = np.where(df_final['Tipo Movimiento'] == 'SALIDA', -df_final['Cantidad'].abs(), df_final['Cantidad'].abs())
        df_final['Fecha_Sencilla'] = df_final['Fecha_Convertida'].dt.date

        st.success("¡Datos sincronizados con éxito desde las columnas reales de Profit!")
        st.write("---")

        # --- BARRA LATERAL CONTROLES ---
        st.sidebar.header("🎯 Filtros y Búsqueda")
        min_date = df_final['Fecha_Sencilla'].min()
        max_date = df_final['Fecha_Sencilla'].max()
        rango_fechas = st.sidebar.date_input("Rango de Fechas", value=(min_date, max_date))
        
        lista_articulos = ["Todos"] + sorted(df_final['Artículo'].unique().tolist())
        articulo_sel = st.sidebar.selectbox("🔎 Seleccionar Artículo", lista_articulos)
        cc_sel = st.sidebar.selectbox("Filtrar por Centro de Costo", ["Todos"] + sorted(df_final['Centro de Costo'].unique().tolist()))

        # Filtrar
        df_filtrado = df_final.copy()
        if isinstance(rango_fechas, tuple) and len(rango_fechas) == 2:
            df_filtrado = df_filtrado[(df_filtrado['Fecha_Sencilla'] >= rango_fechas[0]) & (df_filtrado['Fecha_Sencilla'] <= rango_fechas[1])]
        if articulo_sel != "Todos":
            df_filtrado = df_filtrado[df_filtrado['Artículo'] == articulo_sel]
        if cc_sel != "Todos":
            df_filtrado = df_filtrado[df_filtrado['Centro de Costo'] == cc_sel]

        df_filtrado['Fecha y Hora'] = df_filtrado['Fecha_Convertida'].dt.strftime('%d/%m/%Y %I:%M:%S %p')

        # --- KPIs ---
        c1, c2, c3 = st.columns(3)
        ent = df_filtrado[df_filtrado['Tipo Movimiento'] == 'ENTRADA']['Cantidad'].sum()
        sal = df_filtrado[df_filtrado['Tipo Movimiento'] == 'SALIDA']['Cantidad'].sum()
        with c1: st.metric("Total Entradas", f"{int(abs(ent))} unds")
        with c2: st.metric("Total Salidas", f"{int(abs(sal))} unds")
        with c3: st.metric("Balance Neto", f"{int(df_filtrado['Cantidad'].sum())} unds")

        # --- TABLA ---
        st.subheader("📋 Transacciones Consolidadas")
        df_pantalla = df_filtrado[['Fecha y Hora', 'Nro Ajuste', 'Artículo', 'Centro de Costo', 'Almacén', 'Cantidad']].copy()
        df_pantalla['Cantidad'] = df_pantalla['Cantidad'].astype(int)
        st.dataframe(df_pantalla, use_container_width=True)

        # Descargas
        csv_bytes = df_pantalla.to_csv(index=False).encode('utf-8')
        st.download_button(label="📊 Descargar Informe en Excel (CSV)", data=csv_bytes, file_name="ajustes_inventario.csv", mime="text/csv")

    except Exception as e:
        st.error(f"Error crítico en el motor de datos: {e}")
else:
    st.info("A la espera de que cargues el reporte original de Profit Plus para iniciar la auditoría.")