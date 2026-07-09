import streamlit as st
import pandas as pd
from datetime import datetime
from fpdf import FPDF
import io
from sqlalchemy import create_engine, text

# Versión del sistema
VERSION = "v3.0 Nube"

# Configuración inicial
st.set_page_config(page_title=f"Gestión Eventos Pro {VERSION}", layout="wide")

# --- CONEXIÓN A BASE DE DATOS EN LA NUBE (SUPABASE) ---
def get_db_engine():
    # Obtiene la URI de conexión desde los Secrets de Streamlit
    try:
        db_uri = st.secrets["connections"]["postgresql"]["url"]
        return create_engine(db_uri)
    except Exception:
        st.error("❌ Error de configuración: No se encontró la credencial de conexión a Supabase en los Secrets.")
        st.stop()

# --- 1. INICIALIZACIÓN BD ---
def inicializar_bd():
    engine = get_db_engine()
    with engine.begin() as conn:
        # Tabla Clientes
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS clientes (
                id_cliente SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL,
                telefono TEXT,
                direccion TEXT,
                cedula TEXT DEFAULT ''
            );
        """))

        # Tabla Productos
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS productos (
                id_producto SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL,
                stock INTEGER DEFAULT 0,
                stock_total INTEGER DEFAULT 0,
                stock_disponible INTEGER DEFAULT 0,
                valor_unitario NUMERIC DEFAULT 0
            );
        """))

        # Tabla Agendamientos
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agendamientos (
                id_cita SERIAL PRIMARY KEY,
                id_cliente INTEGER REFERENCES clientes(id_cliente),
                valor_total NUMERIC,
                abono NUMERIC,
                saldo_restante NUMERIC,
                observaciones TEXT,
                fecha_solicitud TEXT,
                fecha_entrega TEXT,
                fecha_hora TEXT,
                concepto TEXT,
                domiciliario TEXT DEFAULT '',
                estado TEXT DEFAULT 'Alquilado'
            );
        """))

        # Tabla Detalles Pedido
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS detalles_pedido (
                id_detalle SERIAL PRIMARY KEY,
                id_cita INTEGER REFERENCES agendamientos(id_cita),
                id_producto INTEGER REFERENCES productos(id_producto),
                cantidad INTEGER DEFAULT 1
            );
        """))

try:
    inicializar_bd()
except Exception as e:
    st.error(f"Error inicializando base de datos en la nube: {e}")

# Inicialización de estados globales
if 'id_cliente_activo' not in st.session_state:
    st.session_state.id_cliente_activo = None
if 'pedido_completado' not in st.session_state:
    st.session_state.pedido_completado = False
if 'pdf_descarga' not in st.session_state:
    st.session_state.pdf_descarga = None
if 'excel_descarga' not in st.session_state:
    st.session_state.excel_descarga = None
if 'nombre_cliente_descarga' not in st.session_state:
    st.session_state.nombre_cliente_descarga = ""
if 'fecha_entrega_descarga' not in st.session_state:
    st.session_state.fecha_entrega_descarga = ""
if 'form_reset_counter' not in st.session_state:
    st.session_state.form_reset_counter = 0

# --- 2. MENÚ LATERAL ---
st.sidebar.markdown(f"**Versión:** {VERSION}")
menu = ["Nuevo Pedido", "Inventario", "Clientes", "Auditoría"]
opcion = st.sidebar.selectbox("Selección de módulo:", menu)

if opcion == "Nuevo Pedido":
    st.title("📝 Nuevo Pedido")

    if st.session_state.pedido_completado:
        st.success("✅ ¡Pedido guardado de forma limpia! El stock disponible en bodega se ha actualizado.")
        st.write("### ⬇️ Descargar comprobantes del pedido actual:")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            st.download_button(label="📄 Descargar Recibo PDF", data=st.session_state.pdf_descarga,
                               file_name=f"pedido_{st.session_state.nombre_cliente_descarga}_{st.session_state.fecha_entrega_descarga}.pdf",
                               mime="application/pdf")
        with col_btn2:
            st.download_button(label="📊 Descargar Reporte Excel", data=st.session_state.excel_descarga,
                               file_name=f"pedido_{st.session_state.nombre_cliente_descarga}_{st.session_state.fecha_entrega_descarga}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        if st.button("🔄 Crear otro Pedido nuevo", type="primary"):
            st.session_state.id_cliente_activo = None
            st.session_state.pedido_completado = False
            st.session_state.pdf_descarga = None
            st.session_state.excel_descarga = None
            st.session_state.nombre_cliente_descarga = ""
            st.session_state.fecha_entrega_descarga = ""
            st.session_state.form_reset_counter += 1
            st.rerun()
        st.divider()

    with st.expander("👤 Gestión de Cliente", expanded=not st.session_state.pedido_completado):
        tipo = st.radio("Acción:", ["Seleccionar existente", "Agregar nuevo"], horizontal=True,
                        key=f"tipo_cliente_{st.session_state.form_reset_counter}")

        engine = get_db_engine()
        if tipo == "Seleccionar existente":
            termino_busqueda = st.text_input("🔍 Escribe el nombre o número de cédula para buscar:",
                                             key=f"busqueda_cli_{st.session_state.form_reset_counter}",
                                             placeholder="Ej: Carolina Vega o 1017...")

            with engine.connect() as conn:
                if termino_busqueda.strip() != "":
                    query = "SELECT id_cliente, nombre, cedula FROM clientes WHERE nombre ILIKE %%(term)s OR cedula LIKE %%(term)s"
                    df = pd.read_sql_query(query, conn, params={"term": f"%{termino_busqueda}%"})
                else:
                    df = pd.read_sql_query("SELECT id_cliente, nombre, cedula FROM clientes ORDER BY id_cliente DESC LIMIT 15", conn)

            if not df.empty:
                df['display_name'] = df.apply(
                    lambda row: f"{row['nombre']} (Cédula: {row['cedula']})" if row['cedula'] else row['nombre'],
                    axis=1)

                sel = st.selectbox("Selecciona el cliente de la lista filtrada:", df['display_name'],
                                   key=f"sel_cliente_{st.session_state.form_reset_counter}")
                st.session_state.id_cliente_activo = int(df.loc[df['display_name'] == sel, 'id_cliente'].values[0])
            else:
                st.warning("⚠️ No se encontraron clientes con esos datos. Intenta otra búsqueda o marca 'Agregar nuevo'.")
                st.session_state.id_cliente_activo = None
        else:
            c_nombre = st.text_input("Nombre:", key=f"c_nom_{st.session_state.form_reset_counter}")
            c_cedula = st.text_input("Cédula / NIT (Opcional):", key=f"c_ced_{st.session_state.form_reset_counter}")
            c_tel = st.text_input("Teléfono:", key=f"c_tel_{st.session_state.form_reset_counter}")
            c_dir = st.text_input("Dirección:", key=f"c_dir_{st.session_state.form_reset_counter}")

            if st.button("Guardar y continuar"):
                if c_nombre.strip() == "":
                    st.error("El campo 'Nombre' es requerido.")
                else:
                    with engine.begin() as conn:
                        result = conn.execute(
                            text("INSERT INTO clientes (nombre, telefono, direccion, cedula) VALUES (:nom, :tel, :dir, :ced) RETURNING id_cliente"),
                            {"nom": c_nombre, "tel": c_tel, "dir": c_dir, "ced": c_cedula}
                        )
                        st.session_state.id_cliente_activo = result.scalar()
                    st.rerun()

    if st.session_state.id_cliente_activo and not st.session_state.pedido_completado:
        engine = get_db_engine()
        with engine.connect() as conn:
            df_prod = pd.read_sql_query("SELECT * FROM productos ORDER BY nombre ASC", conn)

        prods_sel = st.multiselect("Productos a alquilar:", df_prod['nombre'],
                                   key=f"multiselect_prods_{st.session_state.form_reset_counter}")

        col1, col2 = st.columns(2)
        with col1:
            f_solicitud = st.date_input("Fecha de solicitud:", key=f"f_solicitud_{st.session_state.form_reset_counter}")
        with col2:
            f_entrega = st.date_input("Fecha de entrega:", key=f"f_entrega_{st.session_state.form_reset_counter}")
            h_entrega = st.time_input("Hora de entrega:", key=f"h_entrega_{st.session_state.form_reset_counter}")

        st.write("### Detalle del pedido:")

        subtotal_productos = 0.0
        lista_detalles_pdf = []
        error_stock = False

        for p in prods_sel:
            match = df_prod[df_prod['nombre'] == p]
            if not match.empty:
                precio_unitario = float(match['valor_unitario'].iloc[0])
                stock_en_bodega = int(match['stock_disponible'].iloc[0])
                id_prod = int(match['id_producto'].iloc[0])

                if stock_en_bodega <= 0:
                    error_stock = True
                    st.error(f"❌ ¡No hay stock en Bodega de **{p}**! (Disponibles: 0)")
                else:
                    col_cant, col_desc = st.columns([1, 5])
                    with col_cant:
                        cant_elegida = st.number_input(
                            f"Cant. (Max: {stock_en_bodega})",
                            min_value=1,
                            max_value=stock_en_bodega,
                            value=1,
                            key=f"cant_{id_prod}_{st.session_state.form_reset_counter}",
                            label_visibility="collapsed"
                        )

                    precio_total_items = precio_unitario * cant_elegida

                    with col_desc:
                        st.markdown(f"<div style='padding-top: 5px;'>• <b>{p}</b> (x{cant_elegida}): <b>${precio_total_items:,.0f}</b> <span style='color:gray;'>(${precio_unitario:,.0f} c/u)</span></div>", unsafe_allow_html=True)

                    subtotal_productos += precio_total_items
                    lista_detalles_pdf.append({
                        "Producto": f"{p} (x{cant_elegida})",
                        "Precio": precio_total_items,
                        "id_producto": id_prod,
                        "cantidad": cant_elegida
                    })

        val_domicilio = st.number_input("Valor Domicilio:", value=0, format="%d", key=f"domicilio_{st.session_state.form_reset_counter}")
        val_abono = st.number_input("Abono:", value=0, format="%d", key=f"abono_{st.session_state.form_reset_counter}")
        nom_domiciliario = st.text_input("Nombre del Domiciliario (Opcional):", value="", placeholder="Ej: Juan Pérez", key=f"domiciliario_{st.session_state.form_reset_counter}")

        total_final = float(subtotal_productos) + float(val_domicilio)
        saldo_final = max(0.0, total_final - float(val_abono))
        obs = st.text_area("Observaciones:", key=f"observaciones_{st.session_state.form_reset_counter}")

        st.divider()
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.metric("Total General", f"${total_final:,.0f}")
        with col_m2:
            st.metric("Saldo Restante", f"${saldo_final:,.0f}")

        # Funciones generadoras de PDF y Excel
        def generar_pdf_pedido(nombre_c, tel_c, dir_c, prods, total, abono, saldo, domicilio, observaciones, f_sol, f_ent, domi_name):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", "B", 18)
            pdf.cell(0, 10, "Mobi eventos y dream events", ln=True, align="C")
            pdf.set_font("Arial", "", 10)
            pdf.cell(0, 5, "Direccion: Diagonal 57# 35-53", ln=True, align="C")
            pdf.cell(0, 5, "Contacto: 3245625531 - 3005424773", ln=True, align="C")
            pdf.ln(10)
            pdf.line(10, 35, 200, 35)
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 8, "COMPROBANTE DE PEDIDO / GUIA DE ENTREGA", ln=True)
            pdf.set_font("Arial", "", 11)
            pdf.cell(0, 6, f"Cliente: {nombre_c}", ln=True)
            pdf.cell(0, 6, f"Direccion Entrega: {dir_c if dir_c else 'No registrada'}", ln=True)
            pdf.cell(0, 6, f"Telefono Cliente: {tel_c if tel_c else 'No registrado'}", ln=True)
            pdf.cell(0, 6, f"Domiciliario Asignado: {domi_name if domi_name.strip() else 'Por asignar'}", ln=True)
            pdf.cell(0, 6, f"Fecha Solicitud: {f_sol}", ln=True)
            pdf.cell(0, 6, f"Fecha Entrega: {f_ent}", ln=True)
            pdf.ln(5)
            pdf.cell(130, 8, "Producto / Concepto (Cant.)", border=1)
            pdf.cell(50, 8, "Valor Subtotal", border=1, ln=True, align="R")
            pdf.set_font("Arial", "", 11)
            for item in prods:
                pdf.cell(130, 8, str(item['Producto']), border=1)
                pdf.cell(50, 8, f"${item['Precio']:,.0f}", border=1, ln=True, align="R")
            if domicilio > 0:
                pdf.cell(130, 8, "Valor Domicilio", border=1)
                pdf.cell(50, 8, f"${domicilio:,.0f}", border=1, ln=True, align="R")
            pdf.ln(5)
            pdf.set_font("Arial", "B", 11)
            pdf.cell(130, 6, "TOTAL GENERAL:", align="R")
            pdf.cell(50, 6, f"${total:,.0f}", ln=True, align="R")
            pdf.cell(130, 6, "ABONO:", align="R")
            pdf.cell(50, 6, f"${abono:,.0f}", ln=True, align="R")
            pdf.set_text_color(200, 0, 0)
            pdf.cell(130, 8, "VALOR A COBRAR EN ENTREGA:", align="R")
            pdf.cell(50, 8, f"${saldo:,.0f}", ln=True, align="R", border=1)
            pdf.set_text_color(0, 0, 0)
            if observaciones:
                pdf.ln(5)
                pdf.cell(0, 6, "Observaciones:", ln=True)
                pdf.set_font("Arial", "", 10)
                pdf.multi_cell(0, 5, observaciones)
            return pdf.output(dest="S").encode("latin1")

        def generar_excel_pedido(nombre_c, tel_c, dir_c, prods, total, abono, saldo, domicilio, observaciones, f_sol, f_ent, domi_name):
            output = io.BytesIO()
            datos = []
            for item in prods:
                datos.append({"Concepto": item['Producto'], "Valor": item['Precio']})
            if domicilio > 0:
                datos.append({"Concepto": "Valor Domicilio", "Valor": domicilio})
            datos.append({"Concepto": "TOTAL GENERAL", "Valor": total})
            datos.append({"Concepto": "ABONO", "Valor": abono})
            datos.append({"Concepto": "SALDO RESTANTE (POR COBRAR)", "Valor": saldo})
            df_excel = pd.DataFrame(datos)
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                encabezado = pd.DataFrame([
                    ["Mobi eventos y dream events", ""],
                    ["Direccion: Diagonal 57# 35-53", ""],
                    ["Contacto: 3245625531 - 3005424773", ""],
                    ["", ""],
                    ["Cliente:", nombre_c],
                    ["Direccion Cliente:", str(dir_c)],
                    ["Telefono Cliente:", str(tel_c)],
                    ["Domiciliario:", domi_name if domi_name.strip() else "Por asignar"],
                    ["Fecha Solicitud:", str(f_sol)],
                    ["Fecha Entrega:", str(f_ent)],
                    ["Observaciones:", observaciones]
                ], columns=["Detalle del Pedido", ""])
                encabezado.to_excel(writer, sheet_name="Pedido", index=False)
                df_excel.to_excel(writer, sheet_name="Pedido", startrow=13, index=False)
            return output.getvalue()

        if error_stock or len(prods_sel) == 0:
            st.button("💾 Finalizar Pedido", disabled=True)
        else:
            if st.button("💾 Finalizar Pedido", type="primary"):
                try:
                    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    with engine.begin() as conn:
                        cliente_info = conn.execute(text("SELECT nombre, telefono, direccion FROM clientes WHERE id_cliente = :id"), {"id": int(st.session_state.id_cliente_activo)}).fetchone()
                        nombre_cliente_pdf = cliente_info[0] if cliente_info else "Cliente"
                        tel_cliente_pdf = cliente_info[1] if cliente_info else ""
                        dir_cliente_pdf = cliente_info[2] if cliente_info else ""

                        res_cita = conn.execute(text("""
                            INSERT INTO agendamientos (id_cliente, valor_total, abono, saldo_restante, observaciones, fecha_solicitud, fecha_entrega, fecha_hora, concepto, domiciliario, estado)
                            VALUES (:id_cli, :tot, :ab, :sal, :obs, :f_sol, :f_ent, :f_hr, 'Pedido nuevo', :dom, 'Alquilado') RETURNING id_cita
                        """), {"id_cli": st.session_state.id_cliente_activo, "tot": total_final, "ab": float(val_abono), "sal": saldo_final, "obs": obs, "f_sol": str(f_solicitud), "f_ent": f"{f_entrega} {h_entrega}", "f_hr": fecha_actual, "dom": nom_domiciliario})
                        id_nuevo_pedido = res_cita.scalar()

                        for item in lista_detalles_pdf:
                            conn.execute(text("INSERT INTO detalles_pedido (id_cita, id_producto, cantidad) VALUES (:id_c, :id_p, :cant)"), {"id_c": id_nuevo_pedido, "id_p": item['id_producto'], "cant": item['cantidad']})
                            conn.execute(text("UPDATE productos SET stock_disponible = GREATEST(0, stock_disponible - :cant) WHERE id_producto = :id_p"), {"cant": item['cantidad'], "id_p": item['id_producto']})

                    st.session_state.pdf_descarga = generar_pdf_pedido(nombre_cliente_pdf, tel_cliente_pdf, dir_cliente_pdf, lista_detalles_pdf, total_final, float(val_abono), saldo_final, float(val_domicilio), obs, f_solicitud, f"{f_entrega} {h_entrega}", nom_domiciliario)
                    st.session_state.excel_descarga = generar_excel_pedido(nombre_cliente_pdf, tel_cliente_pdf, dir_cliente_pdf, lista_detalles_pdf, total_final, float(val_abono), saldo_final, float(val_domicilio), obs, f_solicitud, f"{f_entrega} {h_entrega}", nom_domiciliario)
                    st.session_state.nombre_cliente_descarga = nombre_cliente_pdf
                    st.session_state.fecha_entrega_descarga = str(f_entrega)
                    st.session_state.pedido_completado = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar: {e}")

elif opcion == "Inventario":
    st.title("🛠️ Inventario y Control de Bodega")
    tab1, tab2 = st.tabs(["📦 Stock de Productos", "🔄 Devoluciones"])

    engine = get_db_engine()
    with tab1:
        with st.expander("➕ Agregar Nuevo Producto"):
            with st.form("nuevo_prod_form", clear_on_submit=True):
                n_nombre = st.text_input("Nombre:")
                n_stock = st.number_input("Stock Total Empresa:", min_value=0, value=0)
                n_valor = st.number_input("Valor de Alquiler:", min_value=0, value=0)

                if st.form_submit_button("Guardar"):
                    if n_nombre.strip() == "":
                        st.error("❌ El nombre no puede estar vacío.")
                    else:
                        with engine.begin() as conn:
                            conn.execute(text("INSERT INTO productos (nombre, stock, stock_total, stock_disponible, valor_unitario) VALUES (:nom, :st, :st, :st, :val)"), {"nom": n_nombre, "st": n_stock, "val": n_valor})
                        st.success(f"✅ ¡{n_nombre} agregado!")
                        st.rerun()

        with engine.connect() as conn:
            df_inv = pd.read_sql_query("SELECT id_producto, nombre, stock_total, stock_disponible, valor_unitario FROM productos ORDER BY id_producto ASC", conn)

        edited_df = st.data_editor(df_inv, use_container_width=True, hide_index=True)

        if st.button("💾 Guardar cambios en Inventario"):
            with engine.begin() as conn:
                for _, row in edited_df.iterrows():
                    conn.execute(text("UPDATE productos SET nombre=:nom, stock_total=:st, stock_disponible=:sd, valor_unitario=:val, stock=:st WHERE id_producto=:id"), {"nom": row['nombre'], "st": int(row['stock_total']), "sd": int(row['stock_disponible']), "val": float(row['valor_unitario']), "id": int(row['id_producto'])})
            st.success("✅ ¡Inventario actualizado!")
            st.rerun()

    with tab2:
        st.write("### Pedidos Activos")
        with engine.connect() as conn:
            df_pendientes = pd.read_sql_query("SELECT a.id_cita, c.nombre as cliente, a.fecha_entrega, a.valor_total, a.domiciliario, a.estado FROM agendamientos a JOIN clientes c ON a.id_cliente = c.id_cliente WHERE a.estado IN ('Alquilado', 'Pendiente')", conn)

        if df_pendientes.empty:
            st.info("🎉 ¡Todo está en bodega!")
        else:
            for index, row in df_pendientes.iterrows():
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([1, 2, 2, 1])
                    c1.markdown(f"**Pedido #{row['id_cita']}**")
                    c2.write(f"👤 {row['cliente']}")
                    c3.write(f"💰 Total: ${row['valor_total']:,.0f}")
                    if c4.button("📥 Recibir", key=f"retorno_{row['id_cita']}"):
                        with engine.begin() as conn:
                            items = conn.execute(text("SELECT id_producto, cantidad FROM detalles_pedido WHERE id_cita = :id"), {"id": row['id_cita']}).fetchall()
                            for item in items:
                                conn.execute(text("UPDATE productos SET stock_disponible = stock_disponible + :cant WHERE id_producto = :id_p"), {"cant": item[1], "id_p": item[0]})
                            conn.execute(text("UPDATE agendamientos SET estado = 'Devuelto' WHERE id_cita = :id"), {"id": row['id_cita']})
                        st.success("✅ ¡Productos recibidos en bodega!")
                        st.rerun()

elif opcion == "Clientes":
    st.title("👤 Clientes")
    engine = get_db_engine()
    with engine.connect() as conn:
        st.dataframe(pd.read_sql_query("SELECT id_cliente AS ID, nombre AS Nombre, cedula AS Cedula, telefono AS Telefono, direccion AS Direccion FROM clientes ORDER BY id_cliente DESC", conn), use_container_width=True, hide_index=True)

elif opcion == "Auditoría":
    st.title("👻 Auditoría Global")
    engine = get_db_engine()
    with engine.connect() as conn:
        query_segura = """
            SELECT a.id_cita AS "ID Cita", c.nombre AS "Nombre Cliente", a.fecha_hora AS "Fecha Registro",
            a.valor_total AS "Valor Total", a.estado AS "Estado", a.abono AS "Abono", a.saldo_restante AS "Saldo Restante",
            a.fecha_entrega AS "Fecha Entrega", a.domiciliario AS "Domiciliario", a.observaciones AS "Observaciones"
            FROM agendamientos a LEFT JOIN clientes c ON a.id_cliente = c.id_cliente ORDER BY a.id_cita DESC
        """
        st.dataframe(pd.read_sql_query(query_segura, conn), use_container_width=True, hide_index=True)
