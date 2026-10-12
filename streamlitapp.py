import streamlit as st
import pandas as pd
import plotly.express as px
from auth import AuthManager
from datetime import date,timedelta
from dateutil.relativedelta import relativedelta
from supabase_client import get_supabase
import pandas as pd

supabase = get_supabase()

class MainDashboardPage:
    """Página principal con navegación lateral y vistas personalizadas."""

    def verificar_riesgo_de_corte(self,fecha_compra, dia_corte):
        """
        Devuelve un mensaje de advertencia si la compra podría caer en un periodo
        diferente al calculado, o None si no hay riesgo.
        """
        # Determinar el próximo corte respecto a la fecha de compra
        try:
            corte_este_mes = fecha_compra.replace(day=dia_corte)
        except ValueError:
            # El mes no tiene ese día (ej. 31 en febrero)
            return None
        
        if fecha_compra > corte_este_mes:
            # La compra es después del corte de este mes,
            # el próximo corte es el del mes siguiente
            siguiente_mes = (fecha_compra + timedelta(days=32)).replace(day=1)
            try:
                proximo_corte = siguiente_mes.replace(day=dia_corte)
            except ValueError:
                return None
        else:
            proximo_corte = corte_este_mes
        
        # ¿El corte cae en fin de semana o viernes?
        dia_semana = proximo_corte.weekday()  # 0=lunes, 4=viernes, 5=sábado, 6=domingo
        
        dias_de_riesgo = {
            4: "viernes",
            5: "sábado",
            6: "domingo",
        }
        
        if dia_semana not in dias_de_riesgo:
            return None  # Corte en día hábil, sin riesgo
        
        # ¿La compra está cerca del corte? (mismo día o los 2 días previos)
        diferencia = (proximo_corte - fecha_compra).days
        
        if 0 <= diferencia <= 2:
            nombre_dia = dias_de_riesgo[dia_semana]
            return (
                f"⚠️ **Atención**: tu fecha de corte ({proximo_corte.strftime('%d/%m/%Y')}) "
                f"cae en **{nombre_dia}**, y estás registrando una compra muy cerca de esa fecha.\n\n"
                f"Los bancos suelen tardar en acreditar compras hechas en {nombre_dia}s o fines de semana, "
                f"por lo que **es posible que esta compra caiga en la siguiente factura** en lugar de la actual.\n\n"
                f"💡 **Recomendación**: verifica en la app de tu banco cuándo se acreditó realmente la compra. "
                f"Si aún no aparece, considera esperar para registrarla y que el sistema calcule bien el periodo."
            )
        
        return None

    def calcular_fecha_corte(self,fecha_compra, dia_corte):
        """Devuelve la fecha de corte ajustando días inválidos al último del mes."""
        def ajustar_dia(fecha, dia):
            ultimo_dia_mes = (fecha.replace(day=1) + relativedelta(months=1) - timedelta(days=1)).day
            return fecha.replace(day=min(dia, ultimo_dia_mes))
        
        corte_este_mes = ajustar_dia(fecha_compra, dia_corte)
        if fecha_compra <= corte_este_mes:
            return corte_este_mes
        else:
            siguiente_mes = fecha_compra + relativedelta(months=1)
            return ajustar_dia(siguiente_mes, dia_corte)
    
    def contar_pagos_vencidos(self,fecha_compra,dia_corte,dias_gracia,meses_totales):
        """Devuelve cuantos pagos ya vencieron y se asumen pagagos"""
        primera_corte = self.calcular_fecha_corte(fecha_compra,dia_corte)
        primera_limite = primera_corte + timedelta(days=dias_gracia)

        hoy = date.today()
        contador = 0

        for i in range(meses_totales):
            fecha_corte_i = primera_corte + relativedelta(months=i)
            fecha_limite_i = fecha_corte_i + timedelta(days=días_gracia)

            if fecha_limite_i < hoy:
                contador += 1
            else:
                break # ya llegamos a pagos futuros
        
        return contador

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

    def guardar_compra_db(self,descripcion,monto,meses,tarjeta_id,fecha_compra,usuario_id):
        # obtener datos de tarjeta
        tarjeta = supabase.table("tarjetas").select("*").eq("id",tarjetas_id).execute().data[0]

        #calcular cuantos pagos ya vencieron
        pagos_heredados = self.contar_pagos_vencidos(
            fecha_compra=fecha_compra,
            dia_corte=tarjeta["dia_corte"],
            dias_gracia=tarjeta["dias_gracia"],
            meses_totales=meses,
        )

        #insertar la compra con pagos heredados
        compra = supabase.table("compras").insert({
            "usuario_id": usuario_id,
            "tarjeta_id": tarjeta_id,
            "descripcion": descripcion,
            "monto_total": monto,
            "meses_sin_intereses": meses,
            "fecha_compra": fecha_compra.isoformat(),
            "pagos_heredados": pagos_heredados,
        }).execute()

        compra_id = compra.data[0]["id"]

        # generar los pagos programados
        self.generar_pagos_programados(
            compra_id=compra_id,
            usuario_id=usuario_id,
            monto_total=monto,
            meses_totales=meses,
            fecha_compra=fecha_compra,
            tarjeta=tarjeta,
            pagos_heredados=pagos_heredados,
        )

    def generar_pagos_programados(self,compra_id, usuario_id, monto_total, meses_totales,fecha_compra, tarjeta, pagos_heredados):
        """
        Genera las filas de pagos_programados para una compra.
        
        - Genera TODOS los pagos (incluidos los ya vencidos).
        - Los pagos vencidos se marcan automáticamente como pagado = TRUE.
        - El último pago absorbe la diferencia de redondeo para que la suma sea exacta.
        """
        
        # 1. Calcular la fecha de corte de la primera factura
        primera_corte = self.calcular_fecha_corte(fecha_compra, tarjeta["dia_corte"])
        
        # 2. Calcular montos (con ajuste del último pago)
        monto_por_mes = round(monto_total / meses_totales, 2)
        monto_ultimo = monto_total - (monto_por_mes * (meses_totales - 1))
        
        hoy = date.today()
        pagos = []
        
        # 3. Generar TODOS los pagos
        for i in range(meses_totales):
            fecha_corte = primera_corte + relativedelta(months=i)
            fecha_limite = fecha_corte + timedelta(days=tarjeta["dias_gracia"])
            
            # ¿Este pago ya venció?
            ya_vencio = fecha_limite < hoy
            
            # Monto: los primeros N-1 son iguales, el último absorbe la diferencia
            if i < meses_totales - 1:
                monto = monto_por_mes
            else:
                monto = monto_ultimo
            
            pagos.append({
                "compra_id": compra_id,
                "usuario_id": usuario_id,
                "numero_mes": i + 1,
                "fecha_corte": fecha_corte.isoformat(),
                "fecha_limite_pago": fecha_limite.isoformat(),
                "monto": monto,
                "pagado": ya_vencio,
                "fecha_pago": fecha_limite.isoformat() if ya_vencio else None,
            })
        
        # 4. Insertar todos los pagos en un solo INSERT
        supabase.table("pagos_programados").insert(pagos).execute()

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
                monto_total = st.number_input("Monto ($)", min_value=0.0, step=10.0)

                #tarjeta bajadas de la base de datos
                tarjeta = st.selectbox("Tarjeta", options=list(mapa_tarjetas.keys()))
                tarjeta_id = mapa_tarjetas[tarjeta]
                print(f"tarjeta id {tarjeta_id}")

            with col2:
                meses_sin_intereses = st.number_input("Meses a pagar", min_value=1, step=1,max_value=36)
                fecha_compra = st.date_input("Fecha de compra")

                    #obtener los datos de la tarjeta, dias de corte, dias gracia
            tarjeta_data = supabase.table("tarjetas") \
                .select("dia_corte, dias_gracia") \
                .eq("id",tarjeta_id) \
                .execute().data[0]

            advertencia = self.verificar_riesgo_de_corte(fecha_compra, tarjeta_data["dia_corte"])

            submit = st.form_submit_button("Guardar Compra", use_container_width=True,type="primary")

            #para las compras que se ejercen los días viernes y fines de semana
            #st.warning("⚠️ Antes de continuar, asegurate que la compra se haya acreditado en la banca ya que tu perdiodo de corte termina es fin de semana")
            errores = []

            if submit:
                if not producto.strip():
                    errores.append("hay campos vacios")
                elif monto_total <= 0:
                    errores.append("el monto debe ser mayor a cero")
                elif  fecha_compra > date.today():
                    errores.append("la fecha que intentas guardar aun no llega")
                elif not tarjeta:
                    errores.append("seleccione una tarjeta")
                else:
                    try:
                        print(f"producto: {producto}")
                        print(f"monto: {monto_total}")
                        print(f"fecha: {fecha_compra}")
                        print(f"tarjeta: {tarjeta}:{tarjeta_id}")
                        
                        #Insertar la compra
                        compra_response = supabase.table("compras").insert({
                            "usuario_id": st.session_state["usuario_id"],
                            "tarjeta_id": tarjeta_id,
                            "descripcion": producto.strip(),
                            "monto_total": monto_total,
                            "meses_sin_intereses":meses_sin_intereses,
                            "fecha_compra": fecha_compra.isoformat(),
                        }).execute()

                        #obtener el id de la compra recien creada
                        compra_id = compra_response.data[0]["id"]  # ✅

                        #generar los pagos programados
                        self.generar_pagos_programados(
                            compra_id = compra_id,
                            usuario_id = st.session_state["usuario_id"],
                            monto_total = monto_total,
                            meses_totales = meses_sin_intereses,
                            fecha_compra = fecha_compra,
                            tarjeta = tarjeta_data,
                            pagos_heredados = 0, #por ahora, siempre 0
                        )

                        #notificar y redirigir
                        st.toast(f"✅ Compra '{producto}' registrada.", icon="✅")
                        #st.session_state["compra_guardada_exitosamente"] = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al gaurdar: {e}")
                
                for i in errores:
                    st.error(f"⚠️ {i}")

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

        usuario_id = st.session_state["usuario_id"]

        # ===== 1. Consultar tarjetas del usuario (una sola vez) =====
        tarjetas = supabase.table("tarjetas") \
            .select("id, nombre") \
            .eq("usuario_id", usuario_id) \
            .order("nombre") \
            .execute().data
        
        # Diccionario para búsqueda rápida
        tarjetas_dict = {t["id"]: t["nombre"] for t in tarjetas}

        # Lista de opciones para el selectbox: "Todas" + nombres de tarjetas
        opciones_tarjetas = ["Todas"] + [t["nombre"] for t in tarjetas]

        # Mapa inverso: nombre → id (para filtrar después)
        nombre_a_id = {t["nombre"]: t["id"] for t in tarjetas}

         # ===== 2. Tabs =====
        tabs = st.tabs([
            "Compras",
            "Historial"
        ])

        with tabs[0]:
            #muestra las compras que estan activas con opcones para seleccionar que tarjetas se han utilizado
            st.subheader("Compras activas")

            if not tarjetas:
                st.info("No tienes tarjetas registradas. Agrega una en Configuración.")
            else:
                opcion = st.selectbox("Filtrar por tarjeta", opciones_tarjetas)
                tarjeta_id_filtro = nombre_a_id.get(opcion) if opcion != "Todas" else None

                # 1. Consultar las compras activas
                query = supabase.table("compras") \
                    .select("*") \
                    .eq("usuario_id", usuario_id) \
                    .eq("activa", True)

                if tarjeta_id_filtro:
                    query = query.eq("tarjeta_id", tarjeta_id_filtro)

                compras = query.order("fecha_compra", desc=True).execute().data

                if not compras:
                    st.info(f"No hay compras activas{' para ' + opcion if opcion != 'Todas' else ''}.")
                else:
                    # 2. Consultar TODOS los pagos programados de esas compras
                    ids_compras = [c["id"] for c in compras]
                    pagos = supabase.table("pagos_programados") \
                        .select("compra_id, monto, pagado") \
                        .in_("compra_id", ids_compras) \
                        .execute().data

                    # 3. Agrupar pagos por compra
                    pagos_por_compra = {}
                    for p in pagos:
                        pagos_por_compra.setdefault(p["compra_id"], []).append(p)

                    # 4. Construir filas
                    filas = []
                    for c in compras:
                        pagos_compra = pagos_por_compra.get(c["id"], [])

                        total_pagado = sum(p["monto"] for p in pagos_compra if p["pagado"])
                        total_restante = sum(p["monto"] for p in pagos_compra if not p["pagado"])

                        pagos_hechos = sum(1 for p in pagos_compra if p["pagado"])
                        pagos_faltantes = sum(1 for p in pagos_compra if not p["pagado"])

                        fila = {
                            "Descripción": c["descripcion"],
                            "Fecha": c["fecha_compra"],
                            "Monto total": c["monto_total"],
                            "MSI": c["meses_sin_intereses"],
                        }

                        # Cuando es "Todas": mostrar nombre de tarjeta
                        # Cuando es una tarjeta específica: mostrar pagado/restante
                        if opcion == "Todas":
                            fila["Tarjeta"] = tarjetas_dict.get(c["tarjeta_id"], "Desconocida")
                            fila["Pagado"] = total_pagado
                            fila["Restante"] = total_restante
                        else:
                            fila["Pagado"] = total_pagado
                            fila["Restante"] = total_restante
                            fila["Meses"] = f"{pagos_hechos}/{c['meses_sin_intereses']}"

                        filas.append(fila)
                    df = pd.DataFrame(filas)
                    # 5. Configurar columnas del DataFrame según el filtro
                    if opcion == "Todas":
                        column_config = {
                            "Monto total": st.column_config.NumberColumn(format="$%.2f"),
                            "Pagado": st.column_config.NumberColumn(format="$%.2f"),
                            "Restante": st.column_config.NumberColumn(format="$%.2f"),
                        }
                        orden_columnas = ["Tarjeta", "Descripción", "Fecha", "Monto total", "MSI", "Pagado", "Restante"]
                    else:
                        column_config = {
                            "Monto total": st.column_config.NumberColumn(format="$%.2f"),
                            "Pagado": st.column_config.NumberColumn(format="$%.2f"),
                            "Restante": st.column_config.NumberColumn(format="$%.2f"),
                        }
                        orden_columnas = ["Descripción", "Fecha", "Monto total", "MSI", "Pagado", "Restante", "Meses"]
                    # Reordenar columnas
                    df = df[orden_columnas]
                    st.dataframe(
                        df,
                        use_container_width=True,
                        hide_index=True,
                        column_config=column_config,
                    )

                    # 6. Métricas resumen
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("💳 Total en compras", f"${df['Monto total'].sum():,.2f}")
                    with col2:
                        st.metric("✅ Ya pagado", f"${df['Pagado'].sum():,.2f}")
                    with col3:
                        st.metric("⏳ Por pagar", f"${df['Restante'].sum():,.2f}")
            
            # opcion = st.selectbox("Seleccione una opción",opciones_tarjetas)

            # # Determinar qué tarjeta_id filtrar (o None si es "Todas")
            # tarjeta_id_filtro = nombre_a_id.get(opcion) if opcion != "Todas" else None

            # # Consultar compras activas
            # query = supabase.table("compras") \
            #     .select("*") \
            #     .eq("usuario_id", usuario_id) \
            #     .eq("activa", True)
            
            # if tarjeta_id_filtro:
            #     query = query.eq("tarjeta_id", tarjeta_id_filtro)

            # compras = query.order("fecha_compra", desc=True).execute().data

            # if not compras:
            #     st.info(f"No hay compras activas{' para ' + opcion if opcion != 'Todas' else ''}.")
            # else:
            #     # Construir filas para el DataFrame
            #     filas = []
            #     for c in compras:
            #         nombre_tarjeta = tarjetas_dict.get(c["tarjeta_id"], "Desconocida")
            #         filas.append({
            #             "Tarjeta": nombre_tarjeta,
            #             "Descripción": c["descripcion"],
            #             "Fecha": c["fecha_compra"],
            #             "Monto total": c["monto_total"],
            #             "MSI": c["meses_sin_intereses"],
            #             "Pago mensual": round(c["monto_total"] / c["meses_sin_intereses"], 2),
            #         })
                
            #     df = pd.DataFrame(filas)
            #     st.dataframe(
            #         df,
            #         use_container_width=True,
            #         hide_index=True,
            #         column_config={
            #             "Monto total": st.column_config.NumberColumn(format="$%.2f"),
            #             "Pago mensual": st.column_config.NumberColumn(format="$%.2f"),
            #         }
            #     )
            #     st.metric("Total en compras activas", f"${df['Monto total'].sum():,.2f}")

            # # with st.form("form_compras"):
            
        with tabs[1]:
            #muestras tpdas las compras que ya se terminaron de pagar
            st.subheader("Compras pagadas")

            # Consultar todas las compras activas
            compras_activas = supabase.table("compras") \
                .select("id, descripcion, monto_total, meses_sin_intereses, fecha_compra, tarjeta_id") \
                .eq("usuario_id", usuario_id) \
                .eq("activa", True) \
                .execute().data

            if not compras_activas:
                st.info("Aún no tienes compras registradas.")
            else:
                # Obtener todos los pagos programados del usuario
                pagos = supabase.table("pagos_programados") \
                    .select("compra_id, pagado") \
                    .eq("usuario_id", usuario_id) \
                    .execute().data
                
                # Agrupar pagos por compra
                pagos_por_compra = {}
                for p in pagos:
                    pagos_por_compra.setdefault(p["compra_id"], []).append(p["pagado"])
                
                # Filtrar compras donde TODOS los pagos están pagados
                compras_terminadas = []
                for c in compras_activas:
                    pagos_compra = pagos_por_compra.get(c["id"], [])
                    if pagos_compra and all(pagos_compra):
                        compras_terminadas.append(c)
                
                if not compras_terminadas:
                    st.info("Aún no has terminado de pagar ninguna compra.")
                else:
                    filas = []
                    for c in compras_terminadas:
                        nombre_tarjeta = tarjetas_dict.get(c["tarjeta_id"], "Desconocida")
                        filas.append({
                            "Tarjeta": nombre_tarjeta,
                            "Descripción": c["descripcion"],
                            "Fecha": c["fecha_compra"],
                            "Monto total": c["monto_total"],
                            "MSI": c["meses_sin_intereses"],
                        })
                    
                    df = pd.DataFrame(filas)
                    st.dataframe(
                        df,
                        use_container_width=True,
                        hide_index=True,
                        column_config={"Monto total": st.column_config.NumberColumn(format="$%.2f"),}
                    )

                    st.metric("Total pagado en compras terminadas", f"${df['Monto total'].sum():,.2f}")

        # # Datos de prueba
        
        # df = pd.DataFrame({
        #     "Mes": ["Ene", "Feb", "Mar", "Abr", "May", "Jun"],
        #     "Ventas": [12000, 15000, 11000, 18000, 22000, 25000],
        #     "Gastos": [8000, 9500, 7000, 10000, 12000, 13000]
        # })

        # col1, col2 = st.columns(2)
        # with col1:
        #     st.subheader("Tendencia de Ventas vs Gastos")
        #     fig = px.line(df, x="Mes", y=["Ventas", "Gastos"], markers=True)
        #     st.plotly_chart(fig, use_container_width=True)

        # with col2:
        #     st.subheader("Distribución de Gastos")
        #     fig_pie = px.pie(values=[40, 25, 20, 15], names=["Nómina", "Marketing", "Servicios", "Otros"])
        #     st.plotly_chart(fig_pie, use_container_width=True)