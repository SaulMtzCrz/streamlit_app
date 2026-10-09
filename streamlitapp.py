import streamlit as st
import pandas as pd
import plotly.express as px
from auth import AuthManager
from datetime import date
from supabase_client import get_supabase

supabase = get_supabase()

class MainDashboardPage:
    """Página principal con navegación lateral y vistas personalizadas."""

    def _cambio_opcion(self, opcion):
        """Actualiza la opción seleccionada en el estado de sesión."""
        st.session_state["opcion_seleccionada"] = opcion

    def guardar_tarjeta_db(self,nombre: str, fecha_corte: int, plazo_pago: int, limite_credito: float):
        """
        Guarda una nueva tarjeta en Supabase asociada al usuario logueado.
        
        Args:
            nombre: Nombre de la tarjeta (ej: "Banamex")
            fecha_corte: Día del mes de corte (1-31)
            plazo_pago: Días de gracia después del corte
            limite_credito: Límite de crédito de la tarjeta
        """
        supabase = get_supabase()
        #verificar que el usuario esté logueado
        if "usuario_id" not in st.session_state:
            raise Exception("No hay session activa. Inicia sesión primero.")

        #insertar en la tabla tarjetas
        respuesta = supabase.table("tarjetas").insert({
            "usuario_id": st.session_state["usuario_id"],
             "nombre": nombre,
             "dia_corte": fecha_corte,
             "dias_gracia": plazo_pago,
             "limite_credito": limite_credito,
        }).execute()

        return respuesta.data


    def render(self):
        print("Renderizando MainDashboardPage...")

        # Almacena la opción seleccionada en el estado de sesión si aún no existe   
        if "opcion_seleccionada" not in st.session_state:
            st.session_state["opcion_seleccionada"] = "🏠 Inicio"
        if "tarjeta_guardada_exitosamente" not in st.session_state:
            st.session_state["tarjeta_guardada_exitosamente"] = False

        if st.session_state.get("tarjeta_guardada_exitosamente"):
            self._cambio_opcion("🏠 Inicio")
            #st.session_state["tabs_configuracion"] = "Preferencias"
            st.session_state["tarjeta_guardada_exitosamente"] = False

        # 1. Barra Lateral - Menú de Navegación
        st.sidebar.title("📋 Menú")
        
        opciones = [
            "🏠 Inicio",
            "💳 Registrar compra",
            "👤 Mi perfil",
            "⚙️ Configuración",
            "📊 Estadísticas"
        ]
        
        seccion = st.sidebar.radio(
            "Selecciona una opción:",
            options=opciones,
            key="opcion_seleccionada"
        )

        st.sidebar.divider()

        # 2. Encabezado común y botón de Cerrar Sesión
        col_title, col_logout = st.columns([4, 1])
        with col_logout:
            if st.button("🚪 Cerrar Sesión", use_container_width=True):
                AuthManager.logout()

        # 3. Renderizado condicional según la opción del menú
        if seccion == "🏠 Inicio":
            self._render_inicio()
        elif seccion == "💳 Registrar compra":
            self._render_registrar_compra()
        elif seccion == "👤 Mi perfil":
            self._render_mi_perfil()
        elif seccion == "⚙️ Configuración":
            self._render_configuracion()
        elif seccion == "📊 Estadísticas":
            self._render_estadisticas()

    # --- MÉTODOS DE CADA VISTA ---

    def _render_inicio(self):
        # cuando el usuario llega al dashboard despues del login
        usuario_id = st.session_state["usuario_id"]

        #consulta cuantas tarjetas tiene
        tarjetas = supabase.table("tarjetas") \
        .select("id") \
        .eq("usuario_id", usuario_id) \
        .execute()

        if not tarjetas.data:
            st.title(f"Bienvenido, {st.session_state['usuario_nombre']}!  👋")
            st.info(
                "Para empezar, necesitas registrar al menos una tarjeta de crédito. "
                "Con ella podrás registrar tus compras y llevar el control de tus pagos."
            )
            st.session_state["cards"] = False
            st.button("Registrar mi primera tarjeta", type="primary",on_click=self._cambio_opcion, args=("⚙️ Configuración",))

        else:
            st.session_state["cards"] = True
            usuario = st.session_state.get("username", "admin")
            st.title(f"¡Hola! {usuario}")
            st.divider()

            st.subheader("📌 Resumen del día")
            col1, col2, col3 = st.columns(3)
            col1.metric("Gasto total", "$0", "+0%")
            col2.metric("Gasto Mensual", "$0", "+0%")
            col3.metric("Compras pendientes", "0", "+0%")

            st.info("💡 Consejo: Usa el menú lateral para navegar entre las diferentes secciones.")

    def _render_registrar_compra(self):
        st.title("💳 Registrar nueva compra")
        st.divider()

        #obtener el usuario_id del session_state
        usuario_id = st.session_state.get("usuario_id")

        #consultar las tarjetas del usuario
        tarjetas_response = supabase.table("tarjetas") \
            .select("id, nombre") \
            .eq("usuario_id", usuario_id) \
            .execute()
        
        tarjetas = tarjetas_response.data #lista de dicts: [{"id":1,"nombre": "banamex"}, ...]

        #manejar en el caso en que no haya tarjetas
        if not tarjetas:
            st.warning("No tienes tarjetas registradas. Agrega una primero en configuracion -> agregar tarjeta")
            st.stop()
        
        #construir el diccionario nombre -id
        mapa_tarjetas = {t["nombre"]: t["id"] for t in tarjetas}

        with st.form("form_compra", clear_on_submit=True):
            #producto o servicio
            producto = st.text_input("Producto / Servicio",placeholder="Ej: Espejo Luz Led Touch Pared Tocador")
            col1, col2 = st.columns(2)

            with col1:
                monto = st.number_input("Monto ($)", min_value=0.0, step=10.0)

                #tarjeta bajadas de la base de datos
                tarjeta = st.selectbox("Tarjeta", options=list(mapa_tarjetas.keys()))
                tarjeta_id = mapa_tarjetas[tarjeta]

            with col2:
                meses_compra = st.number_input("Meses a pagar", min_value=1, step=1,max_value=36)
                fecha = st.date_input("Fecha de compra")

            submit = st.form_submit_button("Guardar Compra", use_container_width=True,type="primary")

            if submit:
                if fecha < date.today():
                    st.warning("⚠️Se registró como una compra pasada")
                else:
                    if producto and monto > 0:
                        #para compras que ya tienen tiempo registrar en esta parte
                        st.success(f"✅ Compra de '{producto}' por ${monto:,.2f} registrada con éxito.")
                    else:
                        st.warning("⚠️ Completa el nombre del producto y asegúrate de que el monto sea mayor a 0.")

    def _render_mi_perfil(self):
        usuario = st.session_state.get("username", "admin")
        st.title("👤 Mi perfil")
        st.divider()

        col_img, col_data = st.columns([1, 2])
        with col_img:
            st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=150)
        with col_data:
            st.markdown(f"**Nombre de usuario:** `{usuario}`")
            st.markdown("**Rol:** Administrador del Sistema")
            st.markdown("**Estado:** Activo 🟢")

        st.subheader("Modificar datos")
        with st.form("form_perfil"):
            email = st.text_input("Correo Electrónico", value="admin@empresa.com")
            password_nueva = st.text_input("Nueva Contraseña", type="password")
            if st.form_submit_button("Actualizar Perfil"):
                st.success("Perfil actualizado correctamente.")

    def _render_configuracion(self):
        st.title("⚙️ Configuración")
        st.divider()

        if not st.session_state["cards"]:
            st.subheader("Agregar tarjeta de pago")

            with st.form("form_tarjeta"):
                nombre_tarjeta = st.text_input("Nombre de la tarjeta",placeholder="Ej: Banamex")
                _columns = st.columns(3)

                with _columns[0]:
                    fecha_de_corte = st.text_input("Fecha de corte", placeholder="Ej: 5")
                with _columns[1]:
                    fecha_expiracion = st.text_input("Plazo de pago", placeholder="Ej: 20")
                with _columns[2]:
                    limite = st.text_input("limite de crédito", placeholder="Ej: 10000")

                if st.form_submit_button("Agregar tarjeta",type="primary",width='stretch'):
                    errores = []

                    #validar Nombre
                    if not nombre_tarjeta.strip():
                        errores.append("El nombre de la tarjeta no puede estar vacío.")
                    
                    #validar dia de corte (entero entre 1 y 31)
                    try:
                        val_corte = int(fecha_de_corte)
                        if not (1 <= val_corte <= 31):
                            errores.append("La fecha de corte debe ser un día válido entre 1 y 31.")
                    except ValueError:
                        errores.append("La fecha de corte debe ser un número entero (ej: 5).")
                    
                    #validar plazo de pago (entero positivo)
                    try:
                        val_plazo = int(fecha_expiracion)
                        if val_plazo <= 0:
                            errores.append("El plazo de pago debe ser un número mayor a 0.")
                    except ValueError:
                        errores.append("El plazo de pago debe ser un número entero (ej: 20).")

                    #validar limite de credito (flotante o entero positivo)
                    try:
                        val_limite = float(limite)
                        if val_limite <= 0:
                            errores.append("El límite de crédito debe ser un monto positivo.")
                    except ValueError:
                        errores.append("El límite de crédito debe ser un valor numérico (ej: 10000 o 10000.50).")
                    
                    if errores:
                        for error in errores:
                            st.error(f"⚠️ {error}")
                    else:
                        try:
                            #si pasa las validaciones, llamamos a la funcion
                            self.guardar_tarjeta_db(
                                nombre=nombre_tarjeta.strip(),
                                fecha_corte=val_corte,
                                plazo_pago=val_plazo,
                                limite_credito=val_limite,
                            )
                            st.success(f"✅ Tarjeta '{nombre_tarjeta}' agregada con éxito.")

                            #actualizar el estado de navegacion para vovler al inicio
                            st.session_state["cards"] = True
                            st.session_state["tarjeta_guardada_exitosamente"] = True
                            #recargar la app
                            st.rerun()
                        except Exception as e:
                            st.error(f"Ocurrió un error al guardar en la base de datos: {e}")
        else:
            #pestañas de configuración
            tabs = st.tabs([
                "Preferencias", 
                "Notificaciones",
                "Agregar tarjetas",
                "Eliminar tarjetas"
                ])

            with tabs[0]:
                st.subheader("Preferencias de la aplicación")
                notificaciones = st.checkbox("Activar notificaciones por correo", value=True)
                modo_oscuro = st.checkbox("Modo oscuro activado", value=True, disabled=True)
                moneda = st.selectbox("Moneda principal", ["USD ($)", "MXN ($)", "EUR (€)"])

                if st.button("Guardar preferencias"):
                    st.success("Preferencias guardadas con éxito")
            
            with tabs[1]:
                st.subheader("Notificaciones")

            with tabs[2]:
                st.subheader("Agregar tarjeta de pago")

                with st.form("form_tarjeta"):
                    nombre_tarjeta = st.text_input("Nombre de la tarjeta",placeholder="Ej: Banamex")
                    _columns = st.columns(3)

                    with _columns[0]:
                        fecha_de_corte = st.text_input("Fecha de corte", placeholder="Ej: 5")
                    with _columns[1]:
                        fecha_expiracion = st.text_input("Plazo de pago", placeholder="Ej: 20")
                    with _columns[2]:
                        limite = st.text_input("limite de crédito", placeholder="Ej: 10000")

                    if st.form_submit_button("Agregar tarjeta",type="primary",width='stretch'):
                        errores = []

                        #validar Nombre
                        if not nombre_tarjeta.strip():
                            errores.append("El nombre de la tarjeta no puede estar vacío.")
                        
                        #validar dia de corte (entero entre 1 y 31)
                        try:
                            val_corte = int(fecha_de_corte)
                            if not (1 <= val_corte <= 31):
                                errores.append("La fecha de corte debe ser un día válido entre 1 y 31.")
                        except ValueError:
                            errores.append("La fecha de corte debe ser un número entero (ej: 5).")
                        
                        #validar plazo de pago (entero positivo)
                        try:
                            val_plazo = int(fecha_expiracion)
                            if val_plazo <= 0:
                                errores.append("El plazo de pago debe ser un número mayor a 0.")
                        except ValueError:
                            errores.append("El plazo de pago debe ser un número entero (ej: 20).")

                        #validar limite de credito (flotante o entero positivo)
                        try:
                            val_limite = float(limite)
                            if val_limite <= 0:
                                errores.append("El límite de crédito debe ser un monto positivo.")
                        except ValueError:
                            errores.append("El límite de crédito debe ser un valor numérico (ej: 10000 o 10000.50).")
                        
                        if errores:
                            for error in errores:
                                st.error(f"⚠️ {error}")
                        else:
                            try:
                                #si pasa las validaciones, llamamos a la funcion
                                self.guardar_tarjeta_db(
                                    nombre=nombre_tarjeta.strip(),
                                    fecha_corte=val_corte,
                                    plazo_pago=val_plazo,
                                    limite_credito=val_limite,
                                )
                                st.success(f"✅ Tarjeta '{nombre_tarjeta}' agregada con éxito.")

                                #actualizar el estado de navegacion para vovler al inicio
                                # st.session_state["cards"] = True
                                # st.session_state["tarjeta_guardada_exitosamente"] = True
                                # #recargar la app
                                # st.rerun()
                            except Exception as e:
                                st.error(f"Ocurrió un error al guardar en la base de datos: {e}")
                        
                        # if nombre_tarjeta and numero_tarjeta and fecha_expiracion and cvv:
                        #     st.success(f"✅ Tarjeta '{nombre_tarjeta}' agregada con éxito.")
                        # else:
                        #     st.warning("⚠️ Completa todos los campos para agregar la tarjeta.")

                # st.info("Aquí puedes gestionar tus tarjetas de pago.")
                # Aquí podrías agregar un formulario para agregar o eliminar tarjetas

            with tabs[3]:
                st.subheader("Eliminar tarjeta de pago")
                # Aquí podrías agregar un formulario para eliminar tarjetas
                with st.form("form_eliminar_tarjeta"):
                    tarjeta_a_eliminar = st.selectbox("Selecciona la tarjeta a eliminar", ["Banamex", "Mercado pago", "Nu", "BBVA"])
                    if st.form_submit_button("Eliminar tarjeta",type="primary"):
                        st.warning(f"⚠️ Tarjeta '{tarjeta_a_eliminar}' eliminada con éxito.")
            # st.subheader("Preferencias de la aplicación")
            # notificaciones = st.toggle("Activar notificaciones por correo", value=True)
            # modo_oscuro = st.toggle("Modo oscuro activado", value=True, disabled=True)
            # moneda = st.selectbox("Moneda principal", ["USD ($)", "MXN ($)", "EUR (€)"])

            # if st.button("Guardar preferencias"):
            #     st.toast("Preferencias guardadas con éxito", icon="✅")

    def _render_estadisticas(self):
        st.title("📊 Estadísticas generales")
        st.divider()

        # Datos de prueba
        df = pd.DataFrame({
            "Mes": ["Ene", "Feb", "Mar", "Abr", "May", "Jun"],
            "Ventas": [12000, 15000, 11000, 18000, 22000, 25000],
            "Gastos": [8000, 9500, 7000, 10000, 12000, 13000]
        })

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Tendencia de Ventas vs Gastos")
            fig = px.line(df, x="Mes", y=["Ventas", "Gastos"], markers=True)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Distribución de Gastos")
            fig_pie = px.pie(values=[40, 25, 20, 15], names=["Nómina", "Marketing", "Servicios", "Otros"])
            st.plotly_chart(fig_pie, use_container_width=True)