import streamlit as st
from auth import AuthManager
import bcrypt
from supabase_client import get_supabase
import re

supabase = get_supabase()

def verify_password(password: str, hashed: str) -> bool:
    """Verifica si la contraseña coincide con el hash."""
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False

def hash_password(password: str) -> str:
    """Genera un hash seguro para la contraseña."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

class LoginRegisterPage:
    """Página de registro de usuario."""

    def render(self):
        col1, col2, col3 = st.columns([1, 2, 1])

        with col2:
            st.title("Registro de Usuario")
            st.write("Ingresa tus datos para crear una cuenta.")

            with st.form("register_form"):
                new_name = st.text_input("👤 Nombre", key="register_user",placeholder="Salomón Flores")
                new_email  = st.text_input("✉️ Email", key="register_user_name",placeholder="flores_2026@example.com")
                new_password = st.text_input("🔓 Nueva Contraseña", type="password", key="register_pass",placeholder="password")
                repeat_password = st.text_input("🔓 Repetir Contraseña", type="password", key="register_pass_repeat",placeholder="password")

                colu1,colu2 = st.columns(2)
                
                with colu2:
                    return_button = st.form_submit_button("Volver", width='stretch',type="primary")
                    if return_button:
                        st.session_state["registering"] = False
                        st.rerun()  # Recarga la página para ir a la página de inicio

                with colu1:
                    submit_button = st.form_submit_button("Registrar", width='stretch',type="primary")

                if submit_button:
                    # Limpieza y normalización del email
                    email_clean = new_email.strip().lower()

                    # Aquí podrías agregar la lógica para registrar al usuario en tu base de datos
                    if not new_name or not email_clean or not new_password:
                        st.error("Todos los campos son obligatorios.")
                        return
                    
                    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_clean):
                        st.error("El email debe tener entre 3 y 10 caracteres (letras, números, _).")
                        return

                    if new_password != repeat_password:
                        st.error("Las contraseñas no coinciden.")
                        return
                    
                    if len(new_password) < 8:
                        st.error("La contraseña debe tener al menos 8 caracteres.")
                        return

                    # verificar si el email ya existe en la base de datos
                    try:
                        existing = supabase.table("usuarios").select("id").eq("email", email_clean).execute()
                        if existing.data:
                            st.error("El email ya está en uso. Por favor, elige otro.")
                            return

                        supabase.table("usuarios").insert({
                            "nombre":new_name.strip(),
                            "email":email_clean,
                            "password_hash":hash_password(new_password),
                        }).execute()

                        st.success(f"Usuario {new_name} registrado exitosamente.")
                        st.session_state["registering"] = False
                        #st.rerun()  # Recarga la página para ir a la página de inicio

                    except Exception as e:
                        error_str = str(e)
                        if "23505" in error_str or "duplicate key" in error_str:
                            st.error(f"El correo '{email_clean}' ya está registrado.")
                        else:
                            st.error(f"Error al registrar: {e}")

                    # else:
                    #     st.session_state["registering"] = False
                    #     st.info(f"Registrando usuario: {new_name} ({new_username})")
                    #st.rerun()  # Recarga la página para ir a la página de inicio

class LoginPage:
    """Página de inicio de sesión."""

    def __init__(self):
        AuthManager.init_session()
    
    def render(self):
        col1, col2, col3 = st.columns([1, 2, 1])

        with col2:
            st.title("Iniciar Sesión")

            with st.form("login_form"):
                email_input = st.text_input("✉️ Email", key="login_user",placeholder="flores_2026@example.com")
                password_input  = st.text_input("🔓 Contraseña", type="password", key="login_pass",placeholder="password")

                colu1,colu2 = st.columns(2)

                with colu1:
                    login = st.form_submit_button("Entrar", width='stretch',type="primary")

                with colu2:
                    submit_button = st.form_submit_button("Nuevo usuario", width='stretch',type="primary")
                    if submit_button:
                        st.session_state["registering"] = True
                        st.rerun()  # Recarga la página para ir a la página de registro

                if login:
                    email_clean = email_input.strip().lower()

                    if not email_clean or not password_input:
                        st.error("Todos los campos son obligatorios.")
                        return
                    
                    try:
                        resultado = supabase.table("usuarios") \
                        .select("id, nombre, email, password_hash") \
                        .eq("email", email_clean) \
                        .execute()

                        if not resultado.data:
                            st.error("Usuario o contraseña incorrectos.")
                            return
                        
                        usuario = resultado.data[0]

                        if verify_password(password_input, usuario["password_hash"]):

                            AuthManager.login(usuario["nombre"], password_input)  # Marca al usuario como autenticado

                            st.session_state["logged_in"] = True
                            st.session_state["usuario_id"] = usuario["id"]
                            st.session_state["usuario_nombre"] = usuario["nombre"]
                            st.session_state["usuario_email"] = usuario["email"]
                            st.session_state["registering"] = False

                            print(usuario["email"])

                            st.success(f"¡Bienvenido, {usuario['nombre']}!")

                            st.rerun()  # Recarga la página para ir al dashboard principal
                        else:
                            st.error("Usuario o contraseña incorrectos.")
                    
                    except Exception as e:
                        st.error(f"Error al iniciar sesión: {e}")