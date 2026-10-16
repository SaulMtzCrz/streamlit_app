import streamlit as st

class AuthManager:
    """Maneja la autenticación y el estado de sesión."""

    # Base de datos simulada de usuarios (en producción usa una DB o Hash de contraseñas)
    USERS_DB = {
        "admin": "1234",
        "usuario": "secret"
    }

    @staticmethod
    def init_session():
        """Inicializa las variables de estado de la sesión si no existen."""
        if "authenticated" not in st.session_state:
            st.session_state["authenticated"] = False
        if "username" not in st.session_state:
            st.session_state["username"] = None
        if "registering" not in st.session_state:
            st.session_state["registering"] = False
        if "cards" not in st.session_state:
            st.session_state["cards"] = True
        if "db_cards" not in st.session_state:
            st.session_state["db_cards"] = None
        if "db_buys" not in st.session_state:
            st.session_state["db_buys"] = None
        if "db_payments" not in st.session_state:
            st.session_state["db_payments"] = None
        if "deuda_pendiente" not in st.session_state:
            st.session_state["deuda_pendiente"] = 0
        if "pagos_proximos" not in st.session_state:
            st.session_state["pagos_proximos"] = False

    @classmethod
    def login(cls, username, password) -> bool:
        """Valida las credenciales e inicia sesión."""
        st.session_state["authenticated"] = True
        st.session_state["username"] = username
        return True

    @staticmethod
    def logout():
        """Cierra la sesión del usuario."""
        st.session_state["authenticated"] = False
        st.session_state["username"] = None
        st.rerun()

    # @classmethod
    # def register(cls, username, password) -> bool:
    #     """Registra un nuevo usuario en la base de datos simulada."""
    #     if username in cls.USERS_DB:
    #         return False  # Usuario ya existe
    #     cls.USERS_DB[username] = password
    #     return True